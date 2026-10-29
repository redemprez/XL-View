from copy import deepcopy
import pytest
from PySide6.QtTest import QTest
from test_editor_ui import window


@pytest.mark.parametrize('kind,number,channel,relative,expected',[
    ('CC',13,None,False,'CC 13 · Global\nAbsolute · 7-bit'),
    ('CC',74,16,True,'CC 74 · Ch 16\nRelative · raw'),
    ('CC14',31,16,False,'CC 31/63 · Ch 16\nAbsolute · 14-bit'),
    ('NRPN14',16383,16,False,'NRPN 16383 · Ch 16\nAbsolute · 14-bit'),
    ('NRPN',16383,None,False,'NRPN 16383 · Global\nAbsolute · 7-bit'),
    ('Note',60,1,False,'Note 60 · Ch 1\nVelocity / Off'),
    ('PC',0,16,False,'PC 0–127 · Ch 16\nProgram number'),
    ('Key',None,None,False,'Keyboard shortcut\nKey code 0'),
    ('disabled',None,None,False,'Unassigned'),
    ('unknown',None,None,False,'Unknown message\nImported definition')])
def test_metadata_matches_message_type(kind,number,channel,relative,expected):
    app,w=window();c=w.current.controls[16];c.kind=kind;c.number=number;c.channel=channel;c.relative=relative
    w.show_details(16);assert w.last_meta.text()==expected and not w.last_meta.isHidden()
    w.clear_mode();assert w.last_meta.isHidden() and not w.last_meta.text()
    w.close()


def test_compact_display_grows_only_for_long_names_without_squeezing_grid():
    app,w=window();w.current.name='BA-1 Perform';w.mode_name.setText(w.current.name)
    w.current.controls[16].label='Tone Dark';w.show();w.resize(940,900);w.show_details(16);app.processEvents()
    size=w.controller_panel.size();short_height=w.mode_display.height()
    assert short_height<210 and w.last_title.height()<25
    w.current.controls[16].label='W'*31;w.show_details(16);QTest.qWait(10)
    assert w.mode_display.height()>short_height and w.last_title.text()=='W'*31
    _,height=w.last_title.text_layout();assert height<=w.last_title.height()
    assert w.controller_panel.size()==size
    w.current.controls[16].label='Tone Dark';w.show_details(16);QTest.qWait(10)
    assert w.mode_display.height()==short_height
    w.close()


def test_midi_metadata_follows_moved_control_without_changing_inspector():
    app,w=window();w.connected=True;w.active_slot=5;w.mode_received(deepcopy(w.current),w.token)
    w.show_control(17);w.midi_received(bytes([0xb0,20,13]))
    assert w.selected_id==17 and w.last_meta.text()=='CC 20 · Global\nAbsolute · 7-bit'
    assert w.last_detail.text()=='13'
    w.close_editor();w.clear_values();assert w.last_meta.isHidden()
    w.close()
