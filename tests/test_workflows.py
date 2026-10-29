from copy import deepcopy
import pytest
from lcxl.protocol import new_mode,Control,Values,same_mode
from lcxl.workflows import paste_controls,batch_controls,row_ids,DraftStore,differences


def test_copy_row_retains_target_ids_and_undo_source():
    m=new_mode();m.controls[16]=Control(16,label='Cutoff',kind='CC',number=21,color=37)
    result=paste_controls(m,[m.controls[i] for i in row_ids(16)],row_ids(24))
    assert result.controls[24].id==24 and result.controls[24].label=='Cutoff'
    assert m.controls[24].kind=='disabled'
    with pytest.raises(ValueError):paste_controls(m,[m.controls[16]],[48])


def test_batch_validates_all_before_applying():
    m=new_mode();m.controls[16]=Control(16,kind='NRPN14',number=300,high=16383)
    m.controls[17]=Control(17,kind='CC',number=20)
    with pytest.raises(ValueError):batch_controls(m,[16,17],{'high':8192,'channel':4})
    assert m.controls[16].channel is None and m.controls[17].high==127
    r=batch_controls(m,[16,17],{'color':37,'channel':4})
    assert all(r.controls[i].channel==4 and r.controls[i].color==37 for i in (16,17))
    assert len(differences(r,m))==4


def test_draft_roundtrip_keeps_baseline_and_slot(tmp_path):
    m=new_mode('Test');b=deepcopy(m);b.slot=6;m.controls[16].label='Unsent'
    store=DraftStore(tmp_path);store.save(m,b,6,'LCXL3 1 MIDI');r=store.load()
    assert same_mode(r['mode'],m) and same_mode(r['baseline'],b) and r['baseline'].slot==6
    assert r['device']=='LCXL3 1 MIDI'
    store.clear();assert store.load() is None


def test_cc14_both_orders_and_channels():
    m=new_mode();m.controls[16]=Control(16,kind='CC14',number=2,channel=1,high=16383)
    v=Values();assert v.feed(m,bytes([0xb0,34,7]))==[]
    assert v.feed(m,bytes([0xb0,2,64]))==[16] and v.values[16]==8199
    assert v.feed(m,bytes([0xb1,2,2]))==[] and v.values[16]==8199
    v.reset();v.feed(m,bytes([0xb0,2,1]));v.feed(m,bytes([0xb0,34,127]));assert v.values[16]==255


def test_nrpn_selection_null_rpn_and_14bit():
    m=new_mode();m.controls[16]=Control(16,kind='NRPN14',number=259,high=16383)
    m.controls[17]=Control(17,kind='NRPN',number=259)
    v=Values()
    def cc(n,val,ch=0):return v.feed(m,bytes([0xb0+ch,n,val]))
    cc(99,2);cc(98,3);assert cc(38,5)==[]
    assert cc(6,64)==[16,17] and v.values=={16:8197,17:64}
    cc(99,2);cc(98,4);assert cc(6,50)==[]
    cc(99,127);cc(98,127);assert cc(6,99)==[]
    cc(99,2);cc(98,3);cc(101,0);assert cc(6,99)==[]
    assert cc(6,55,1)==[]
    v.reset();assert cc(6,55)==[]


def test_note_velocity_noteoff_and_program_change():
    m=new_mode();m.controls[48]=Control(48,kind='Note',number=60,channel=2)
    m.controls[49]=Control(49,kind='PC',low=0,high=127,channel=2)
    v=Values();assert v.feed(m,bytes([0x90,60,100]))==[]
    v.feed(m,bytes([0x91,60,100]));assert v.values[48]==100
    v.feed(m,bytes([0x81,60,64]));assert v.values[48]==0
    v.feed(m,bytes([0x91,60,0]));assert v.values[48]==0
    assert v.feed(m,bytes([0xc1,12]))==[49] and v.values[49]==12
    assert v.feed(m,b'\xb0')==[]
