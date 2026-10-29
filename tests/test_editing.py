from copy import deepcopy
from pathlib import Path
import pytest
from lcxl.protocol import (Control,parse_mode,encode_mode,control_record,control_signature,
    same_mode,merge_control,new_mode,split_frames,PREFIX)
from lcxl.library import save_preset,list_presets
from lcxl.device import Device

FIX=Path(__file__).parent/'fixtures'
def sample():return parse_mode((FIX/'d50-device.syx').read_bytes(),5)

def test_rename_one_preserves_every_other_record_and_settings():
    before=sample(); draft=deepcopy(before); draft.controls[16].label='Filter A'
    after=parse_mode(encode_mode(draft,5),5)
    assert after.controls[16].label=='Filter A'
    assert after.controls[16].raw==before.controls[16].raw
    assert after.extras==before.extras
    for cid in range(17,64):assert after.controls[cid]==before.controls[cid]

def test_channel_and_button_color_flags_from_components_spec():
    c=Control(48,'Button','CC',23,3,0,127,5,25,behaviour=2)
    assert control_record(c)==bytes.fromhex('49 30 02 05 19 22 10 00 17 7f 00')

@pytest.mark.parametrize('kind,number,lo,hi',[
    ('CC',74,7,100),('CC14',5,128,12345),('NRPN',300,2,121),('NRPN14',1123,250,14000)])
def test_types_roundtrip_with_asymmetric_values(kind,number,lo,hi):
    m=new_mode(); m.controls[16]=Control(16,'Test',kind,number,12,lo,hi,37)
    c=parse_mode(encode_mode(m)).controls[16]
    assert (c.kind,c.number,c.channel,c.low,c.high)==(kind,number,12,lo,hi)
    # Components uses little-endian 7-bit pairs; do not copy midi.guide's reversed order.
    if kind=='CC14':assert control_record(c)[10:14]==bytes([57,96,0,1])

@pytest.mark.parametrize('c',[
    Control(48,'Note','Note',60,1,velocity=98,behaviour=2),
    Control(49,'Program','PC',0,2,12,12,behaviour=2),
    Control(50,'Next','PC',0,1,0,127,behaviour=7),
    Control(51,'Space','Key',keycode=44,modifiers=3),
    Control(16,'Rel','CC',70,None,relative=True)])
def test_buttons_and_relative_roundtrip(c):
    m=new_mode(); m.controls[c.id]=c
    assert same_mode(m,parse_mode(encode_mode(m)))

def test_unsupported_raw_record_and_long_label_survive():
    m=sample(); c=m.controls[17]; c.raw=bytes.fromhex('43 11 0b 01 02'); c.kind='unknown'; c.label='A'*31
    after=parse_mode(encode_mode(m))
    assert after.controls[17].raw==c.raw and after.controls[17].label=='A'*31

def test_single_merge_keeps_newer_unrelated_device_edits():
    base=sample(); draft=deepcopy(base); draft.controls[16].color=5; draft.controls[17].label='Not sent'
    current=deepcopy(base); current.controls[17].number=40
    result=merge_control(current,draft,16,base)
    assert result.controls[16].color==5 and result.controls[17].number==40
    assert result.controls[17].label==current.controls[17].label
    current.controls[16].number=99
    with pytest.raises(ValueError,match='changed'):merge_control(current,draft,16,base)

def test_library_versions_are_independent(tmp_path):
    m=sample(); one=save_preset(m,tmp_path); m.controls[16].label='Changed'; two=save_preset(m,tmp_path)
    assert one!=two and len(list_presets(tmp_path))==2
    assert parse_mode(one.read_bytes()).controls[16].label=='U1 Cutoff'
    assert parse_mode(two.read_bytes()).controls[16].label=='Changed'

def test_validation_happens_before_transmission():
    m=sample(); m.controls[16].channel=17
    with pytest.raises(ValueError):encode_mode(m,5)
    m=sample(); m.name='Zażółć'
    with pytest.raises(ValueError):encode_mode(m,5)
    with pytest.raises(ValueError):encode_mode(sample(),16)

class MemoryMidi:
    def __init__(self,mode,corrupt=False):
        self.frames={f[9]:f for f in split_frames(encode_mode(mode,5))}; self.responses=[]; self.sent=[]; self.corrupt=corrupt
    def send(self,b):
        self.sent.append(b)
        if b[8]==0x40:
            data=bytearray(self.frames[b[9]]); data[8]=0x10; self.responses.append(bytes(data))
        elif b[8]==0x45:
            self.frames[b[9]]=b
            if self.corrupt and b[9]==0:
                data=bytearray(b); data[13]=ord('X'); self.frames[0]=bytes(data)
            self.responses.append(PREFIX+bytes([0x15,b[9],0,247]))
    def read(self,timeout=0):return self.responses.pop(0) if self.responses else b''

def test_write_transaction_backup_readback_and_partial_preservation(tmp_path):
    m=sample(); draft=deepcopy(m); draft.controls[16].label='Changed'; draft.controls[17].label='Unsaved other'
    d=Device('test'); d.main=MemoryMidi(m)
    result,backup=d._write_slot(5,draft,16,m,backup_root=tmp_path)
    assert result.controls[16].label=='Changed'
    assert result.controls[17].label==m.controls[17].label
    assert same_mode(parse_mode(Path(backup).read_bytes()),m)
    assert [b[8] for b in d.main.sent]==[64,64,69,69,64,64]

def test_failed_verification_is_not_reported_as_success(tmp_path):
    m=sample(); d=Device('test'); d.main=MemoryMidi(m,True)
    with pytest.raises(RuntimeError,match='Write not confirmed'):d._write_slot(5,m,backup_root=tmp_path)
    assert len(list_presets(tmp_path,'backups'))==1

def test_conflict_does_not_send_write(tmp_path):
    m=sample(); changed=deepcopy(m); changed.controls[16].label='External'
    d=Device('test'); d.main=MemoryMidi(changed)
    with pytest.raises(ValueError):d._write_slot(5,m,16,m,backup_root=tmp_path)
    assert all(b[8]==64 for b in d.main.sent)
