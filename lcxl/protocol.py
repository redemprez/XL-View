"""Bounded parser for XL3 Components files and observed hardware responses.

Evidence: supplied D-50.syx, slot-5 physical readback, Novation programmer guide,
and midi.guide's launch-control-sysex generator. Unknown definitions are retained
as opaque records; never guessed or used to transmit changes.
"""
from dataclasses import dataclass, field, replace
from copy import deepcopy

PREFIX = bytes.fromhex('f0 00 20 29 02 15 05 00')

@dataclass
class Control:
    id: int
    label: str = ''
    kind: str = 'disabled'
    number: int | None = None
    channel: int | None = None  # None means global, not channel 1.
    low: int = 0
    high: int = 127
    color: int = 0
    on_color: int = 0
    raw: bytes = b''
    behaviour: int = 0
    relative: bool = False
    bipolar: bool = False
    led_feedback: bool = True
    velocity: int = 127
    keycode: int = 0
    modifiers: int = 0

    @property
    def assignment(self):
        if self.kind == 'disabled': return 'Unassigned'
        if self.kind == 'unknown': return 'Other message type'
        ch = f'channel {self.channel}' if self.channel else 'global channel'
        return f'{self.kind} {self.number} · {ch}'

@dataclass
class Mode:
    name: str
    controls: dict[int, Control] = field(default_factory=dict)
    slot: int | None = None
    raw: bytes = b''
    extras: dict = field(default_factory=dict)

def split_frames(data: bytes):
    if not data or len(data) > 131072: raise ValueError('File is empty or too large.')
    frames=[]; pos=0
    while pos < len(data):
        if data[pos] != 0xF0: raise ValueError('Invalid SysEx start.')
        try: end=data.index(0xF7,pos)+1
        except ValueError: raise ValueError('Incomplete SysEx message.')
        frame=data[pos:end]
        if any(x>=128 for x in frame[1:-1]): raise ValueError('Invalid SysEx data.')
        frames.append(frame); pos=end
    return frames

def parse_mode(data: bytes, slot=None) -> Mode:
    pages={}; names=[]; controls={}; extras={}
    for b in split_frames(data):
        if len(b)<14 or not b.startswith(PREFIX) or b[8] not in (0x10,0x45):
            raise ValueError('This is not a Launch Control XL 3 Custom Mode file.')
        page=b[9]
        if page not in (0,3) or page in pages: raise ValueError('Duplicate or unknown mode page.')
        pages[page]=True
        if b[11]!=0x20 or b[12]>31 or 13+b[12]>=len(b): raise ValueError('Invalid mode name.')
        name=b[13:13+b[12]].decode('ascii'); names.append(name)
        pos=13+b[12]
        if b[pos:pos+2]==b'\x21\x00': pos+=2
        seen=set(); labeled=set()
        while pos<len(b)-1:
            tag=b[pos]
            if tag < 0x40:
                # Retain device settings and metadata verbatim when editing a slot.
                size=(2+b[pos+1]) if tag in (0x20,0x21) and pos+1<len(b)-1 else 2
                if pos+size>len(b)-1: raise ValueError('Incomplete mode settings.')
                extras[page]=extras.get(page,b'')+b[pos:pos+size]; pos+=size; continue
            if pos+2>len(b)-1: raise ValueError('Incomplete control definition.')
            cid=b[pos+1]
            allowed=range(16,40) if page==0 else range(40,64)
            if cid not in allowed: raise ValueError('Control outside the page range.')
            is_label=0x60<=tag<=0x7F
            length=tag-(0x60 if is_label else 0x40)
            if (not is_label and not 0x40<=tag<=0x5F) or pos+2+length>len(b)-1:
                raise ValueError('Incomplete mode record.')
            raw=b[pos:pos+2+length]; payload=raw[2:]; pos+=len(raw)
            c=controls.setdefault(cid,Control(cid))
            if is_label:
                if cid in labeled: raise ValueError('Duplicate label.')
                labeled.add(cid); c.label=payload.decode('ascii'); continue
            if cid in seen: raise ValueError('Duplicate control.')
            seen.add(cid); c.raw=raw
            decode_control(c,payload)
        for cid in allowed: controls.setdefault(cid,Control(cid))
    if set(pages)!={0,3}: raise ValueError('One of the two Custom Mode pages is missing.')
    names=[n for n in names if n]
    if len(set(names))>1: raise ValueError('Pages contain different mode names.')
    return Mode(names[0] if names else 'Unnamed',controls,slot,data,extras)

TYPES={1:'Note',2:'CC',3:'PC',5:'NRPN14',6:'CC14',10:'NRPN',12:'Key'}
LENGTHS={1:8,2:9,3:9,5:12,6:12,10:11,12:7}

def decode_control(c,payload):
    if not payload: c.kind='disabled'; return
    c.kind=TYPES.get(payload[0],'unknown')
    # Device readback removes trailing zero bytes.
    p=list(payload)+[0]*12
    c.color,c.on_color=p[1:3]
    c.channel=None if p[4]&64 else (p[3]&15)+1
    c.behaviour=p[3]>>4
    c.relative=bool(p[4]&2) if c.kind=='CC' else False
    c.bipolar=bool(p[4]&1); c.led_feedback=not bool(p[4]&32)
    if c.kind in ('CC','PC'): c.number=p[6]; c.high=p[7]; c.low=p[8]
    elif c.kind in ('CC14','NRPN','NRPN14'):
        c.number=p[6]+(p[7]<<7 if c.kind.startswith('NRPN') else 0)
        c.high=p[8]+(p[9]<<7); c.low=p[10]+(p[11]<<7)
    elif c.kind=='Note':
        c.number=p[7]; c.velocity=p[6]; c.behaviour&=2
    elif c.kind=='Key': c.modifiers=(p[3]&15)|((p[4]&15)<<4); c.keycode=(p[5]<<7)|p[6]

def ascii_text(text,maximum):
    if not isinstance(text,str) or len(text)>maximum or any(not 32<=ord(ch)<=125 for ch in text):
        raise ValueError(f'Name: up to {maximum} ASCII characters (XL limitation).')
    return text.encode('ascii')

def control_signature(c):
    # Ignore unencoded UI defaults, but include all MIDI fields and unknown bytes.
    r=control_record(c)
    p=list(r[2:]); p+= [0]*(12-len(p))
    if p and len(r)>2:
        if p[0]!=12 and p[4]&64: p[3]&=0x70  # Global-channel nibble is ignored by hardware.
        if c.id<48 and p[0]!=1: p[4]&=~8  # Firmware marks continuous controls on readback.
    return (c.label,tuple(p) if len(r)>2 else ())

def feedback_signature(c):
    """Only fields needed to identify and interpret an incoming MIDI value.

    Names, LEDs, button behaviour and output ranges do not change CC/Note/NRPN
    decoding. PC is identified by its emitted program range instead of a CC ID.
    This is deliberately separate from the full signature used for write safety.
    """
    if c.kind not in ('CC','CC14','NRPN','NRPN14','Note','PC'):return None
    address=tuple(sorted((c.low,c.high))) if c.kind=='PC' else c.number
    return (c.kind,c.channel,address,c.relative if c.kind=='CC' else False)

def control_record(c):
    if not 16<=c.id<=63: raise ValueError('Invalid control number.')
    if c.kind=='disabled': return bytes([64,c.id])
    if c.kind=='unknown':
        if not c.raw: raise ValueError('Original definition for the unknown control is missing.')
        return c.raw
    typ=next((t for t,k in TYPES.items() if k==c.kind),None)
    if typ is None: raise ValueError('Unsupported control type.')
    limit=16383 if c.kind in ('CC14','NRPN14') else 127
    numlimit=16383 if c.kind.startswith('NRPN') else 31 if c.kind=='CC14' else 127
    for value,maxval in [(c.color,127),(c.on_color,127),(c.low,limit),(c.high,limit),
                         (c.number or 0,numlimit),(c.behaviour,7),(c.velocity,127),(c.keycode,255),(c.modifiers,15)]:
        if not isinstance(value,int) or not 0<=value<=maxval: raise ValueError('Value outside the range for this message type.')
    if c.channel is not None and not 1<=c.channel<=16: raise ValueError('MIDI channel must be between 1 and 16.')
    if c.relative and (c.kind!='CC' or c.id>=40): raise ValueError('Relative mode is available for 7-bit CC knobs.')
    if c.id<48 and c.kind in ('Note','Key'): raise ValueError('This message type is available for buttons.')
    if c.raw:
        original=Control(c.id); decode_control(original,c.raw[2:])
        fields=('kind','number','channel','low','high','color','on_color','behaviour','relative','bipolar','led_feedback','velocity','keycode','modifiers')
        if all(getattr(c,f)==getattr(original,f) for f in fields): return c.raw
    p=[0]*LENGTHS[typ]; p[0:3]=[typ,c.color,c.on_color]
    p[3]=(c.channel-1 if c.channel else 1)|(c.behaviour<<4)
    old=list(c.raw[2:])+[0]*12
    p[4]=(old[4]&8) | (64 if c.channel is None else 0) | (16 if c.id>=48 else 0)
    if c.kind!='Note': p[4]|=(32 if not c.led_feedback else 0)|(2 if c.relative else 0)|(1 if c.bipolar else 0)
    if c.kind in ('CC','PC'):
        p[5]=old[5]; p[6]=c.number or 0; p[7]=c.high; p[8]=c.low
    elif c.kind in ('CC14','NRPN','NRPN14'):
        p[5]=old[5]; p[6]=(c.number or 0)&127; p[7]=((c.number or 0)>>7) if c.kind.startswith('NRPN') else 0
        p[8]=c.high&127; p[9]=c.high>>7; p[10]=c.low&127
        if len(p)>11: p[11]=c.low>>7
    elif c.kind=='Note':
        p[3]=(c.channel-1 if c.channel else 1)|((c.behaviour|1)<<4)
        p[4]|=4; p[6]=c.velocity; p[7]=c.number or 0
    elif c.kind=='Key': p[3:7]=[c.modifiers&15,c.modifiers>>4,c.keycode>>7,c.keycode&127]
    return bytes([64+len(p),c.id]+p)

def encode_mode(mode,slot=None):
    if slot is not None and not 1<=slot<=15: raise ValueError('Select slot 1–15.')
    name=ascii_text(mode.name,16); frames=[]
    for page,ids in ((0,range(16,40)),(3,range(40,64))):
        data=PREFIX+bytes([0x45,page,slot-1 if slot else 127,32,len(name)])+name
        for cid in ids: data+=control_record(mode.controls.get(cid,Control(cid)))
        for cid in ids:
            label=ascii_text(mode.controls.get(cid,Control(cid)).label,31)
            data+=bytes([96+len(label),cid])+label
        data+=mode.extras.get(page,b'')
        frames.append(data+b'\xf7')
    return b''.join(frames)

def same_mode(a,b):
    return a.name==b.name and all(control_signature(a.controls[i])==control_signature(b.controls[i]) for i in range(16,64))

def merge_control(device,draft,cid,baseline=None):
    if baseline and control_signature(device.controls[cid])!=control_signature(baseline.controls[cid]):
        raise ValueError('This control changed on XL since the last read. Read the slot again before sending.')
    merged=deepcopy(device); merged.controls[cid]=deepcopy(draft.controls[cid]); return merged

def new_mode(name='New Custom Mode'):
    return Mode(name,{i:Control(i) for i in range(16,64)})

def read_request(slot: int, page: int):
    if not 1<=slot<=15 or page not in (0,3): raise ValueError('Invalid slot or page.')
    return PREFIX+bytes([0x40,page,slot-1,247])

def decode_surface(value):
    if value==1: return ('DAW Mixer',None)
    if value==2: return ('DAW Control',None)
    if 6<=value<=9: return ('Custom',value-5)
    if 18<=value<=29: return ('Custom',value-13)
    return ('Unknown mode',None)

class Values:
    def __init__(self): self.reset()
    def reset(self): self.values={}; self.last=None; self.cc={}; self.nrpn={}
    def feed(self, mode, msg):
        if not mode or not msg or not 0x80<=msg[0]<0xf0: return []
        typ=msg[0]&0xf0; channel=(msg[0]&15)+1
        needed=2 if typ in (0xc0,0xd0) else 3
        if len(msg)<needed or any(b>127 for b in msg[1:needed]): return []
        number=msg[1]; value=msg[2] if needed==3 else number
        parameter=None; data7=None; data14=None
        if typ==0xb0:
            self.cc[channel,number]=value
            state=self.nrpn.setdefault(channel,{})
            if number in (101,100): state.clear()  # RPN cancels the NRPN selection.
            elif number in (99,98):
                if number==99:
                    state.clear(); state[99]=value
                else:
                    state.pop('msb',None); state.pop('lsb',None); state[98]=value
            elif number in (6,38) and 99 in state and 98 in state:
                parameter=state[99]*128+state[98]
                if parameter!=16383:
                    state['msb' if number==6 else 'lsb']=value
                    if 'msb' in state:
                        data7=state['msb']; data14=data7*128+state.get('lsb',0)
        matched=[]
        for c in mode.controls.values():
            if c.channel not in (None,channel): continue
            received=None
            if typ==0xb0:
                if c.kind=='CC' and c.number==number: received=value
                elif c.kind=='CC14' and c.number is not None and number in (c.number,c.number+32):
                    msb=self.cc.get((channel,c.number))
                    if msb is not None: received=msb*128+self.cc.get((channel,c.number+32),0)
                elif c.kind in ('NRPN','NRPN14') and c.number==parameter:
                    received=data14 if c.kind=='NRPN14' else data7 if number==6 else None
            elif typ in (0x80,0x90) and c.kind=='Note' and c.number==number:
                received=0 if typ==0x80 else value
            elif typ==0xc0 and c.kind=='PC' and (c.low<=number<=c.high or c.high<=number<=c.low):
                received=number
            if received is not None:
                self.values[c.id]=received; matched.append(c.id)
        if matched: self.last=(matched,channel,number,value)
        return matched
