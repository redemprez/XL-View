"""Native Windows MIDI via WinMM. No Java or third-party MIDI runtime."""
import ctypes as C
from ctypes import wintypes as W
import queue
import threading
import time

class MidiError(RuntimeError): pass
class PortBusy(MidiError):
    """MMSYSERR_ALLOCATED: another program (REAPER, a second XL View) holds the port."""
class DriverFault(MidiError):
    """The driver failed or the device vanished; the ports must be closed and reopened."""
MMSYSERR_ALLOCATED=4
DEVICE_GONE=(2,5,6)  # BADDEVICEID, INVALHANDLE, NODRIVER

class MIDIHDR(C.Structure):
    _pack_ = 1  # Windows SDK mmsyscom.h / pshpack1.h
    _fields_=[('lpData',C.c_void_p),('dwBufferLength',W.DWORD),('dwBytesRecorded',W.DWORD),
     ('dwUser',C.c_size_t),('dwFlags',W.DWORD),('lpNext',C.c_void_p),('reserved',C.c_size_t),
     ('dwOffset',W.DWORD),('dwReserved',C.c_size_t*8)]
class IN_CAPS(C.Structure):
    _fields_=[('wMid',W.WORD),('wPid',W.WORD),('vDriverVersion',W.DWORD),('szPname',W.WCHAR*32),('dwSupport',W.DWORD)]
class OUT_CAPS(C.Structure):
    _fields_=[('wMid',W.WORD),('wPid',W.WORD),('vDriverVersion',W.DWORD),('szPname',W.WCHAR*32),
     ('wTechnology',W.WORD),('wVoices',W.WORD),('wNotes',W.WORD),('wChannelMask',W.WORD),('dwSupport',W.DWORD)]

class WinMidi:
    packed_read = True
    packed_write = True
    buffer_size = 4096
    def __init__(self):
        self.dll=C.WinDLL('winmm')
        self.in_handle=W.HANDLE(); self.out_handle=W.HANDLE()
        self.rx=queue.Queue(); self.returned=queue.Queue()
        self.buffers=[]; self.header_map={}; self.closing=False; self.pump_thread=None
        self._pending_out=[]; self._leaked=[]
        self.input_count=0; self.input_last=None; self.input_played=0.0
        self.callback_type=C.WINFUNCTYPE(None,W.HANDLE,W.UINT,C.c_size_t,C.c_size_t,C.c_size_t)
        self.callback=self.callback_type(self._callback)
        self._configure()
    def _configure(self):
        d=self.dll
        signatures={
         'midiInOpen':([C.POINTER(W.HANDLE),W.UINT,self.callback_type,C.c_size_t,W.DWORD],W.UINT),
         'midiOutOpen':([C.POINTER(W.HANDLE),W.UINT,C.c_size_t,C.c_size_t,W.DWORD],W.UINT),
         'midiInGetDevCapsW':([C.c_size_t,C.POINTER(IN_CAPS),W.UINT],W.UINT),
         'midiOutGetDevCapsW':([C.c_size_t,C.POINTER(OUT_CAPS),W.UINT],W.UINT),
         'midiInGetNumDevs':([],W.UINT),'midiOutGetNumDevs':([],W.UINT),
         'midiOutShortMsg':([W.HANDLE,W.DWORD],W.UINT)}
        for direction in ('In','Out'):
            for op in ('PrepareHeader','UnprepareHeader'):
                signatures['midi'+direction+op]=([W.HANDLE,C.POINTER(MIDIHDR),W.UINT],W.UINT)
            for op in ('Reset','Close'):
                signatures['midi'+direction+op]=([W.HANDLE],W.UINT)
            signatures['midi'+direction+'GetErrorTextW']=([W.UINT,W.LPWSTR,W.UINT],W.UINT)
        signatures.update({'midiInAddBuffer':([W.HANDLE,C.POINTER(MIDIHDR),W.UINT],W.UINT),
         'midiOutLongMsg':([W.HANDLE,C.POINTER(MIDIHDR),W.UINT],W.UINT),
         'midiInStart':([W.HANDLE],W.UINT),'midiInStop':([W.HANDLE],W.UINT)})
        for name,(args,ret) in signatures.items():
            f=getattr(d,name); f.argtypes=args; f.restype=ret
    def check(self,result,direction='Out'):
        if result:
            text=C.create_unicode_buffer(256)
            getattr(self.dll,'midi'+direction+'GetErrorTextW')(result,text,256)
            port='input' if direction=='In' else 'output'
            if result==MMSYSERR_ALLOCATED:
                raise PortBusy(f'MIDI {port} port is busy in another app (such as REAPER or another XL View). Release it there and reconnect.')
            if result in DEVICE_GONE:
                raise DriverFault(f'MIDI device ({port}) is unavailable: {text.value} (code {result}). Check USB, scan ports and reconnect.')
            raise DriverFault(f'MIDI driver ({port}) reported an error: {text.value} (code {result}). Ports were closed. Reconnect; '
                'if the error persists, check the controller USB connection.')
    def devices(self):
        found=[]
        for direction,cls in (('In',IN_CAPS),('Out',OUT_CAPS)):
            items=[]
            for i in range(getattr(self.dll,'midi'+direction+'GetNumDevs')()):
                caps=cls()
                self.check(getattr(self.dll,'midi'+direction+'GetDevCapsW')(i,C.byref(caps),C.sizeof(caps)),direction)
                items.append((i,caps.szPname))
            found.append(items)
        return tuple(found)
    @property
    def connected(self): return bool(self.in_handle.value and self.out_handle.value)
    def open(self,input_id,output_id):
        self.close(); self.closing=False
        self.rx=queue.Queue(); self.returned=queue.Queue(); self.input_count=0; self.input_last=None
        try:
            self.check(self.dll.midiOutOpen(C.byref(self.out_handle),output_id,0,0,0))
            self.check(self.dll.midiInOpen(C.byref(self.in_handle),input_id,self.callback,0,0x30000),'In')
            # Receive whole SysEx messages in generously sized buffers.
            # WinMM calls are made by the pump, never inside the driver callback.
            for i in range(32):
                buf=C.create_string_buffer(self.buffer_size); hdr=MIDIHDR()
                hdr.lpData=C.addressof(buf); hdr.dwBufferLength=self.buffer_size; hdr.dwUser=i
                self.check(self.dll.midiInPrepareHeader(self.in_handle,C.byref(hdr),C.sizeof(hdr)),'In')
                self.buffers.append((buf,hdr))
                self.header_map[C.addressof(hdr)]=(buf,hdr)
                self.check(self.dll.midiInAddBuffer(self.in_handle,C.byref(hdr),C.sizeof(hdr)),'In')
            self.pump_thread=threading.Thread(target=self._pump,daemon=True); self.pump_thread.start()
            self.check(self.dll.midiInStart(self.in_handle),'In')
        except Exception:
            self.close(); raise
    def _callback(self,handle,msg,instance,param1,param2):
        if msg==0x3c3:
            packed = int(param1)
            status = packed & 255
            if status < 0xF0:
                size = 2 if status & 0xF0 in (0xC0, 0xD0) else 3
                self.rx.put(bytes((packed >> (8*i)) & 255 for i in range(size)))
            return
        if msg not in (0x3c4,0x3c6): return  # MIM_LONGDATA / MIM_LONGERROR
        self.input_count+=1; self.input_last=None
        try:
            entry=self.header_map.get(int(param1))
            if entry is None: raise MidiError('Unknown MIDI buffer header.')
            buf,hdr=entry
            if hdr.dwBytesRecorded>C.sizeof(buf): raise MidiError('Driver reported an oversized MIDI response.')
            if hdr.lpData!=C.addressof(buf): raise MidiError('Driver changed the MIDI buffer address.')
            data=buf.raw[:hdr.dwBytesRecorded]
            self.returned.put((int(hdr.dwUser),data,msg==0x3c6))
        except Exception as ex: self.rx.put(MidiError(str(ex)))
    def _pump(self):
        while not self.closing:
            try: index,data,error=self.returned.get(timeout=.05)
            except queue.Empty: continue
            if error: self.rx.put(MidiError('Driver reported a damaged SysEx packet.'))
            elif data: self.rx.put(data)
            if not self.closing and self.in_handle.value:
                hdr=self.buffers[index][1]; hdr.dwBytesRecorded=0
                result=self.dll.midiInAddBuffer(self.in_handle,C.byref(hdr),C.sizeof(hdr))
                if result: self.rx.put(MidiError(f'Could not prepare MIDI buffer again ({result}).'))
    def drain(self):
        while True:
            try: self.rx.get_nowait()
            except queue.Empty: return
    def read(self,timeout):
        try:
            item=self.rx.get(timeout=timeout)
            if isinstance(item,Exception): raise item
            return item
        except queue.Empty: return b''
    # Paced SysEx: 32-byte buffers with 15 ms gaps (about 2 kB/s, below the 3.1 kB/s of
    # a DIN cable). Sent in one burst, about a quarter of the 296-byte tones reached the
    # CZ-1 damaged ("MIDI DATA ERROR"), and a repeat of the same tone usually worked.
    pace_bytes=0
    pace_delay=.015
    def send(self,data):
        if not self.out_handle.value: raise MidiError('Connect MIDI ports first.')
        data=bytes(data)
        if not self.pace_bytes or len(data)<=self.pace_bytes: return self._send_buffer(data)
        for start in range(0,len(data),self.pace_bytes):
            self._send_buffer(data[start:start+self.pace_bytes])
            if start+self.pace_bytes<len(data): time.sleep(self.pace_delay)
    def _send_buffer(self,data):
        buf=C.create_string_buffer(bytes(data)); hdr=MIDIHDR()
        hdr.lpData=C.addressof(buf); hdr.dwBufferLength=len(data)
        self.check(self.dll.midiOutPrepareHeader(self.out_handle,C.byref(hdr),C.sizeof(hdr)))
        try:
            self.check(self.dll.midiOutLongMsg(self.out_handle,C.byref(hdr),C.sizeof(hdr)))
            deadline=time.monotonic()+3
            while not hdr.dwFlags&1:
                if time.monotonic()>deadline:
                    self.dll.midiOutReset(self.out_handle)
                    raise MidiError('Driver did not finish sending MIDI.')
                time.sleep(.002)
        finally:
            result=self.dll.midiOutUnprepareHeader(self.out_handle,C.byref(hdr),C.sizeof(hdr))
            if result:
                # Never free a buffer still owned by a driver.
                self._pending_out.append((buf,hdr))
    def short(self,status,a=0,b=0):
        if not self.out_handle.value: raise MidiError('No MIDI connection.')
        self.check(self.dll.midiOutShortMsg(self.out_handle,status|(a<<8)|(b<<16)))
    def close(self):
        """Always releases both ports and never raises: a half-closed port would stay
        occupied until the process ends. Returns a list of driver problems (may be empty)."""
        self.closing=True; problems=[]
        if self.pump_thread:
            self.pump_thread.join(timeout=1); self.pump_thread=None
        if self.in_handle.value:
            try:
                self.dll.midiInStop(self.in_handle); self.dll.midiInReset(self.in_handle)
                for buf,hdr in self.buffers:
                    if self.dll.midiInUnprepareHeader(self.in_handle,C.byref(hdr),C.sizeof(hdr)): problems.append('input buffer')
                result=self.dll.midiInClose(self.in_handle)
                if result: problems.append(f'closing input (code {result})')
            except Exception as ex: problems.append(str(ex))
            # Buffers the driver may still own are kept alive, never freed.
            if problems: self._leaked.extend(self.buffers)
            self.in_handle=W.HANDLE(); self.buffers=[]; self.header_map.clear()
        if self.out_handle.value:
            try:
                self.dll.midiOutReset(self.out_handle)
                for buf,hdr in self._pending_out:
                    self.dll.midiOutUnprepareHeader(self.out_handle,C.byref(hdr),C.sizeof(hdr))
                result=self.dll.midiOutClose(self.out_handle)
                if result: problems.append(f'closing output (code {result})')
            except Exception as ex: problems.append(str(ex))
            self._leaked.extend(self._pending_out); self.out_handle=W.HANDLE(); self._pending_out=[]
        return problems

