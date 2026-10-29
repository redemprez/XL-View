from pathlib import Path
import pytest
from lcxl.protocol import parse_mode, read_request, decode_surface, Values
FIX=Path(__file__).parent/'fixtures'

def test_physical_readback_matches_export():
    export=parse_mode((FIX/'d50-export.syx').read_bytes())
    device=parse_mode((FIX/'d50-device.syx').read_bytes(),5)
    assert export.name==device.name=='D50 Perform'
    assert len(device.controls)==48
    for cid,c in export.controls.items():
        d=device.controls[cid]
        assert (c.label,c.kind,c.number,c.low,c.high,c.color)==(d.label,d.kind,d.number,d.low,d.high,d.color)
    assert device.controls[16].number==20
    assert device.controls[32].label=='U1 Filt Env'
    assert device.controls[40].label=='U1 Level'
    assert device.controls[63].kind=='disabled'

def test_missing_page_and_truncation_rejected():
    data=(FIX/'d50-export.syx').read_bytes()
    for bad in [b'',data[:-1],data[:data.index(247)+1],data+b'junk',b'\xf0\x80\xf7']:
        with pytest.raises(ValueError): parse_mode(bad)

def test_repeated_page_rejected():
    data=(FIX/'d50-export.syx').read_bytes(); first=data[:data.index(247)+1]
    with pytest.raises(ValueError): parse_mode(first+first)

def test_mode_numbers_and_read_only_request():
    assert decode_surface(18)==('Custom',5)
    assert decode_surface(29)==('Custom',16)
    assert decode_surface(1)==('DAW Mixer',None)
    assert read_request(5,3)==bytes.fromhex('f0 00 20 29 02 15 05 00 40 03 04 f7')
    with pytest.raises(ValueError): read_request(16,0)

def test_unknown_values_channel_filter_and_reset():
    mode=parse_mode((FIX/'d50-device.syx').read_bytes()); values=Values()
    assert values.values=={}
    assert values.feed(mode,bytes([0xb0,20,91]))==[16]
    assert values.values[16]==91
    mode.controls[16].channel=2
    assert values.feed(mode,bytes([0xb0,20,7]))==[]
    assert values.feed(mode,bytes([0xb1,20,7]))==[16]
    assert values.feed(mode,bytes([0x90,20,127]))==[]
    values.reset(); assert values.values=={}

def test_shared_cc_updates_all_matching_controls():
    mode=parse_mode((FIX/'d50-device.syx').read_bytes()); values=Values()
    mode.controls[17].number=20
    assert values.feed(mode,bytes([0xb0,20,91]))==[16,17]
