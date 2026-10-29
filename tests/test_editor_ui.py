import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from copy import deepcopy
from PySide6.QtWidgets import QApplication
from lcxl.ui import Window,STYLE
from lcxl.protocol import parse_mode,control_record,control_signature

def window():
    app=QApplication.instance() or QApplication([]); app.setStyleSheet(STYLE)
    w=Window(auto=False,settings=False)
    w.display_mode(parse_mode((Path(__file__).parent/'fixtures/d50-device.syx').read_bytes(),5))
    return app,w

def test_inspector_name_edit_preserves_midi_fields():
    app,w=window(); before=deepcopy(w.current)
    w.show_control(16); w.editor.name.setText('Filter'); w.editor.edit()
    assert w.current.controls[16].label=='Filter'
    assert control_record(w.current.controls[16])==before.controls[16].raw
    assert all(w.current.controls[i]==before.controls[i] for i in range(17,64))
    assert w.dirty and w.follow_enabled and w.selected_id==16
    w.undo_edit(); assert w.current.controls[16].label==before.controls[16].label
    w.dirty=False;w.close()

def test_midi_does_not_steal_inspector_selection_or_change_draft():
    app,w=window(); w.show_control(17); w.live=True
    w.midi_received(bytes([0xb0,20,76]))
    assert w.selected_id==17 and w.editor.control.id==17
    assert w.tiles[16].visual.value==76
    w.close()

def test_edit_disabled_button_and_save_version(tmp_path):
    app,w=window(); w.library_root=tmp_path; w.show_control(63)
    w.editor.kind.setCurrentIndex(w.editor.kind.findData('Note'))
    w.editor.number.setValue(60);w.editor.name.setText('Play');w.editor.edit()
    c=w.current.controls[63]
    assert c.kind=='Note' and c.number==60 and c.label=='Play'
    assert w.save_current() and not w.dirty
    paths=list((tmp_path/'library').glob('*.syx')); assert len(paths)==1
    assert parse_mode(paths[0].read_bytes()).controls[63].number==60
    w.close()

def test_single_send_readback_keeps_other_draft_edits():
    app,w=window(); w.current.controls[17].label='Keep unsent'; before=deepcopy(w.baseline)
    before.controls[16].label='Sent'; w.token=12; w.busy=True
    w.write_received(before,12,'backup.syx',16)
    assert not w.busy and w.current.controls[17].label=='Keep unsent'
    assert w.baseline.controls[17].label!='Keep unsent'
    assert w.current.controls[16].label=='Sent'
    assert 'Unsent' in w.source.text()
    w.close()

def test_read_failure_preserves_visible_inspector_selection():
    app,w=window();w.show_control(16);w.read_failed('Test rozłączenia')
    assert w.selected_id==16 and w.editor.control.id==16
    w.editor.name.setText('Still editable');w.editor.edit()
    assert w.selected_id==16 and w.current.controls[16].label=='Still editable'
    w.connected=True;w.update_actions();assert w.editor.send.isEnabled()
    w.dirty=False;w.close()

def test_inspector_expands_window_without_resizing_controller():
    app,w=window(); w.resize(1100,850); w.show(); app.processEvents()
    before=w.controller_panel.size(); tiles=[t.size() for t in w.tiles.values()]
    w.show_control(16); app.processEvents()
    assert w.width()==1456 and w.controller_panel.size()==before
    assert [t.size() for t in w.tiles.values()]==tiles
    w.show_control(48); app.processEvents(); assert w.width()==1456
    w.close_editor(); app.processEvents()
    assert w.width()==1100 and w.controller_panel.size()==before
    w.show_control(40);app.processEvents();w.resize(1556,850);app.processEvents()
    w.close_editor();app.processEvents();assert w.width()==1200
    w.close()

def test_sliders_sync_and_follow_message_ranges():
    app,w=window();w.show_control(16)
    field=w.editor.number
    field.slider.setValue(77);assert field.value()==77 and w.current.controls[16].number==77
    field.spin.setValue(12);assert field.slider.value()==12 and w.current.controls[16].number==12
    w.editor.kind.setCurrentIndex(w.editor.kind.findData('NRPN14'))
    field.slider.setValue(10000)
    assert field.value()==10000 and w.current.controls[16].number==10000
    assert w.editor.high.slider.maximum()==16383
    w.editor.kind.setCurrentIndex(w.editor.kind.findData('CC14'))
    assert field.slider.maximum()==31 and field.value()<=31
    w.dirty=False;w.close()

def test_swatches_keep_one_selection_and_edit_only_color():
    app,w=window();w.show_control(48);before=deepcopy(w.current)
    palette=w.editor.color;palette.buttons[5].click()
    assert palette.value()==5 and w.current.controls[48].color==5
    assert sum(b.isChecked() for b in palette.buttons.values())==1
    expected=deepcopy(before.controls[48]);expected.color=5
    assert control_signature(w.current.controls[48])==control_signature(expected)
    assert len(palette.buttons)==56
    palette.buttons[5].click();assert palette.buttons[5].isChecked()
    w.dirty=False;w.close()

def test_send_control_resumes_midi_after_each_verified_write(tmp_path):
    from lcxl.protocol import merge_control
    app,w=window();w.connected=True;w.active_slot=5;w.live=True;w.library_root=tmp_path
    hardware=deepcopy(w.current)
    w.feedback_mode=deepcopy(hardware)
    class Writer:
        def write(self,slot,token,draft,cid,baseline):
            self.result=merge_control(hardware,draft,cid,baseline);self.result.slot=slot
            self.token=token;self.cid=cid
    writer=Writer();w.worker=writer
    for number in (70,71):
        w.show_control(16);w.editor.number.setValue(number)
        assert w.live and w.tiles[16].visual.value is None
        w.send_mode(True);assert w.busy and not w.live
        hardware=deepcopy(writer.result)
        w.write_received(hardware,writer.token,'backup.syx',writer.cid)
        assert w.live and w.follow_enabled and w.selected_id==16
        w.midi_received(bytes([0xb0,number,91]))
        assert w.tiles[16].visual.value==91
        w.midi_received(bytes([0xb0,21,54]))
        assert w.tiles[17].visual.value==54
    w.worker=None;w.dirty=False;w.close()

def test_send_control_does_not_display_values_for_unsent_assignments():
    app,w=window();w.connected=True;w.active_slot=5
    w.show_control(17);w.editor.number.setValue(70)
    actual=deepcopy(w.baseline);actual.controls[16].color=5
    w.write_received(actual,w.token,'backup.syx',16)
    w.midi_received(bytes([0xb0,21,54]));w.midi_received(bytes([0xb0,70,55]))
    assert w.current.controls[17].number==70 and w.tiles[17].visual.value is None
    assert 17 not in w.values.values
    w.midi_received(bytes([0xb0,20,90]));assert w.tiles[16].visual.value==90
    w.dirty=False;w.close()

def test_send_to_inactive_slot_waits_until_that_slot_is_active():
    app,w=window();w.follow_changed(False);w.connected=True;w.active_slot=4;w.detach()
    w.write_received(deepcopy(w.current),w.token,'backup.syx',16)
    w.midi_received(bytes([0xb0,20,80]));assert w.tiles[16].visual.value is None
    w.surface_changed('Custom',5);w.midi_received(bytes([0xb0,20,81]))
    assert w.tiles[16].visual.value==81
    w.surface_changed('Custom',4);w.midi_received(bytes([0xb0,20,82]))
    assert w.tiles[16].visual.value is None
    w.read_failed('Read failed');w.surface_changed('Custom',5)
    assert not w.live
    w.close()

def test_send_entire_mode_resumes_values_but_stale_reply_does_not():
    app,w=window();w.connected=True;w.active_slot=5;w.detach()
    mode=deepcopy(w.current)
    w.write_received(mode,w.token-1,'backup.syx',None);assert not w.live
    w.write_received(mode,w.token,'backup.syx',None)
    w.midi_received(bytes([0xb0,20,83]));assert w.tiles[16].visual.value==83
    w.connection_status('Disconnected',False)
    w.surface_changed('Custom',5);assert not w.live
    w.close()

def test_manual_slot_then_hardware_switch_enables_values_and_sends_to_new_slot(tmp_path):
    app,w=window();w.connected=True;w.active_slot=5;w.library_root=tmp_path
    class Worker:
        def request(self,slot,token):self.requested=(slot,token)
        def write(self,slot,token,draft,cid,baseline):self.sent=(slot,cid,deepcopy(draft),baseline)
    worker=Worker();w.worker=worker
    w.manual_slot(1)
    slot,token=worker.requested;assert slot==1
    mode=parse_mode((Path(__file__).parent/'fixtures/d50-device.syx').read_bytes(),1)
    mode.name='Fury800';mode.controls[16].number=13
    w.mode_received(mode,token)
    assert not w.live and w.selected_slot==1
    w.surface_changed('Custom',1);w.midi_received(bytes([0xb0,13,64]))
    assert w.tiles[16].visual.value==64 and w.follow_enabled
    w.show_control(16);w.editor.color.choose(5);w.send_mode(True)
    assert worker.sent[0:2]==(1,16) and worker.sent[2].controls[16].color==5
    assert worker.sent[3].slot==1
    w.worker=None;w.busy=False;w.dirty=False;w.close()

def test_hardware_switch_before_manual_read_uses_single_destination():
    app,w=window();w.connected=True;w.follow_changed(False);w.active_slot=1
    mode=deepcopy(w.current);mode.slot=1
    w.mode_received(mode,w.token)
    assert w.live and w.selected_slot==1
    w.show_control(16);w.editor.color.choose(5)
    assert w.selected_slot==1 and '01' in w.editor.send.text()
    w.dirty=False;w.close()
