"""Worker owns MIDI handles; writes require an explicit queued UI action."""
import queue, time, re
from copy import deepcopy
from PySide6.QtCore import QThread, Signal
from .transport import WinMidi
from .protocol import PREFIX, read_request, parse_mode, decode_surface, encode_mode, split_frames, same_mode, merge_control
from .library import backup_mode

class Device(QThread):
    status=Signal(str,bool)
    surface=Signal(str,object)
    mode=Signal(object,int)
    midi=Signal(bytes)
    failed=Signal(str,int)
    written=Signal(object,int,str,object)
    slot_name=Signal(int,str,str)
    import_result=Signal(object,int,int,str)

    def __init__(self, device_name):
        super().__init__(); self.device_name=device_name
        self.commands=queue.Queue(); self.stopping=False; self.inventory=list(range(1,16))
        self.main=None; self.daw=None; self.pending=bytearray()

    @staticmethod
    def discover():
        io=WinMidi(); ins,outs=io.devices()
        return [name for _,name in ins if re.fullmatch(r'LCXL3 \d+ MIDI',name) and any(n==name for _,n in outs)]

    def request(self, slot, token): self.commands.put(('read',slot,token))
    def request_import(self,slot,job):self.commands.put(('import',slot,job))
    def write(self, slot, token, draft, cid=None, baseline=None):
        self.commands.put(('write',slot,token,deepcopy(draft),cid,deepcopy(baseline)))
    def stop(self): self.stopping=True

    def _frames(self, chunk):
        if not chunk: return []
        # WinMM delivers short channel messages separately from SysEx buffers.
        # A fragmented or damaged SysEx must never swallow ordinary knob messages.
        if 0x80<=chunk[0]<0xF0:
            self.midi.emit(chunk); return []
        result=[]
        for x in chunk:
            if x>=0xF8:continue
            if x==0xF0:self.pending.clear()  # Resynchronise after an incomplete reply.
            elif not self.pending:continue
            elif x>=0x80 and x!=0xF7:
                self.pending.clear();continue
            self.pending.append(x)
            if len(self.pending)>131072:
                self.pending.clear();raise ValueError('Controller response is too long.')
            if x==0xF7:
                result.append(bytes(self.pending));self.pending.clear()
        return result

    def _read_slot(self,slot):
        result=[]
        for page in (0,3):
            if self.stopping: return None
            self.main.send(read_request(slot,page))
            deadline=time.monotonic()+1.5
            found=None
            while time.monotonic()<deadline and not self.stopping:
                for frame in self._frames(self.main.read(.015)):
                    if frame.startswith(PREFIX+bytes([0x10,page])): found=frame
                if found: break
            if not found: raise TimeoutError(f'No response while reading slot {slot}. Try Read again.')
            result.append(found)
        return parse_mode(b''.join(result),slot)

    def _write_slot(self,slot,draft,cid=None,baseline=None,backup_root=None):
        before=self._read_slot(slot)
        if before is None: raise RuntimeError('Write cancelled before sending.')
        target=merge_control(before,draft,cid,baseline) if cid is not None else deepcopy(draft)
        target.slot=slot
        encoded=encode_mode(target,slot)  # Validate the complete result before any write.
        backup=backup_mode(before,backup_root)
        try:
            for frame in split_frames(encoded):
                if self.stopping: raise RuntimeError('Write cancelled.')
                self.main.send(frame)
                deadline=time.monotonic()+2; ack=False
                while time.monotonic()<deadline and not self.stopping:
                    for response in self._frames(self.main.read(.015)):
                        if response.startswith(PREFIX+bytes([0x15,frame[9]])): ack=True
                    if ack: break
                if not ack: raise TimeoutError('No page-write acknowledgement.')
            time.sleep(.12)
            after=self._read_slot(slot)
            if after is None or not same_mode(target,after):
                raise ValueError('Readback differs from the sent settings.')
            return after,str(backup)
        except Exception as ex:
            raise RuntimeError(f'Write not confirmed. {ex} The slot may be partially changed. Backup: {backup}') from ex

    def _next_request(self):
        # Foreground transactions take priority between complete background reads.
        try:
            request=self.commands.get_nowait()
            if request[1] in self.inventory:self.inventory.remove(request[1])
            return request
        except queue.Empty:
            return ('inventory',self.inventory.pop(0),0) if self.inventory else None

    def run(self):
        try:
            self.main=WinMidi(); ins,outs=self.main.devices()
            def port(items,name):
                matches=[i for i,n in items if n==name]
                if len(matches)!=1: raise RuntimeError(f'Port {name} was not found.')
                return matches[0]
            self.main.open(port(ins,self.device_name),port(outs,self.device_name))
            try:
                self.daw=WinMidi()
                self.daw.open(port(ins,f'MIDIIN2 ({self.device_name})'),port(outs,f'MIDIOUT2 ({self.device_name})'))
            except Exception:
                if self.daw: self.daw.close()
                self.daw=None
            self.status.emit('Connected' if self.daw else 'Connected Â· select mode manually (DAW port busy)',True)
            last_query=0; started=time.monotonic(); got_surface=False; feature_enabled=False
            last_surface=None; last_inventory=time.monotonic(); last_reply=None
            while not self.stopping:
                for _ in range(100):
                    chunk=self.main.read(0)
                    if not chunk: break
                    self._frames(chunk)
                if self.daw:
                    for _ in range(100):
                        msg=self.daw.read(0)
                        if not msg: break
                        if len(msg)==3 and msg[:2]==bytes([0xB6,30]):
                            got_surface=True
                            last_reply=time.monotonic()
                            current=decode_surface(msg[2])
                            if current!=last_surface: self.surface.emit(*current); last_surface=current
                    now=time.monotonic()
                    if not got_surface and not feature_enabled and now-started>1:
                        # Enable transient feature reporting; never enter DAW mode.
                        self.daw.short(0x9F,11,127); feature_enabled=True
                    if now-last_query>.7:
                        self.daw.short(0xB7,30,0); last_query=now
                    if last_reply and now-last_reply>4:
                        raise RuntimeError('Controller stopped responding. Check USB and reconnect.')
                if time.monotonic()-last_inventory>4:
                    if self.device_name not in self.discover(): raise RuntimeError('Controller disconnected. Connect USB and reconnect.')
                    last_inventory=time.monotonic()
                request=self._next_request()
                if request:
                    action,slot,token,*args=request
                    try:
                        if action=='inventory':
                            m=self._read_slot(slot)
                        elif action=='import':
                            m=self._read_slot(slot)
                            self.import_result.emit(m,slot,token,'' if m else 'Read cancelled.')
                        elif action=='write':
                            m,backup=self._write_slot(slot,*args)
                            self.written.emit(m,token,backup,args[1])
                        else:
                            m=self._read_slot(slot)
                            if m: self.mode.emit(m,token)
                        if m:self.slot_name.emit(slot,m.name,'')
                    except Exception as ex:
                        if action=='inventory':self.slot_name.emit(slot,'',str(ex))
                        elif action=='import':self.import_result.emit(None,slot,token,str(ex))
                        else:self.failed.emit(str(ex),token)
                    # A transaction temporarily pauses DAW polling.
                    if last_reply: last_reply=time.monotonic()
                time.sleep(.012)
        except Exception as ex: self.status.emit(f'Not connected: {ex}',False)
        finally:
            if self.main: self.main.close()
            if self.daw: self.daw.close()
