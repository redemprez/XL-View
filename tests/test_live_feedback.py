"""Offline regressions: verified hardware map stays separate from local edits."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt
from test_editor_ui import window
from lcxl.device import Device
from lcxl.protocol import PREFIX, feedback_signature
from lcxl.workflows import batch_controls


@pytest.fixture
def live_window(monkeypatch):
    monkeypatch.setattr(Device,'discover',staticmethod(lambda:[]))
    app,w=window();w.connected=True;w.active_slot=5;w.active_name='Custom'
    w.mode_received(deepcopy(w.current),w.token)
    yield w
    w.worker=None;w.busy=False;w.dirty=False;w.close()


def move(w,cid,value):
    c=w.feedback_mode.controls[cid]
    w.midi_received(bytes([0xb0+((c.channel or 1)-1),c.number,value]))


def test_copy_paste_keeps_other_controls_live_and_undo_restores_target(live_window):
    w=live_window;move(w,16,45);move(w,24,60)
    w.tile_clicked(16);w.copy_controls()
    assert w.live and w.tiles[16].visual.value==45
    w.tile_clicked(24);w.paste_copied()
    assert w.live and w.has_pending() and w.selected_id==24
    assert w.tiles[16].visual.value==45 and w.tiles[24].visual.value is None
    move(w,16,70);move(w,17,50);move(w,24,63)
    assert w.tiles[16].visual.value==70 and w.tiles[17].visual.value==50
    assert w.tiles[24].visual.value is None  # New CC is still unsent.
    w.undo_edit();move(w,24,64)
    assert w.live and w.tiles[24].visual.value==64 and w.selected_id==24


@pytest.mark.parametrize('field,value',[
    ('label','Renamed'),('color',5),('on_color',9),('low',10),('high',90),
    ('bipolar',True),('led_feedback',False)])
def test_cosmetic_and_output_edits_preserve_values(live_window,field,value):
    w=live_window;move(w,16,30);w.show_control(16)
    c=deepcopy(w.current.controls[16]);setattr(c,field,value);w.edit_control(c)
    assert w.live and w.tiles[16].visual.value==30
    move(w,16,75);assert w.tiles[16].visual.value==75
    assert w.selected_id==16 and w.current.controls[16]==c


def test_rename_group_save_and_close_inspector_keep_live(live_window,tmp_path):
    w=live_window;w.library_root=tmp_path;move(w,16,40)
    w.rename_mode('Live draft');assert w.live and w.tiles[16].visual.value==40
    w.tile_clicked(16);w.tile_clicked(17,Qt.KeyboardModifier.ControlModifier)
    w.apply_candidate(batch_controls(w.current,w.selection,{'color':5}))
    assert w.tiles[16].visual.value==40
    move(w,17,60);assert w.selection=={16,17} and w.editor.group_mode
    assert w.tiles[17].visual.value==60
    w.save_current();assert w.has_pending() and w.live
    w.close_editor();move(w,16,65);assert w.tiles[16].visual.value==65


@pytest.mark.parametrize('field,value',[('number',70),('channel',4),('relative',True),('kind','CC14')])
def test_only_changed_midi_binding_waits_for_send(live_window,field,value):
    w=live_window;move(w,16,40)
    c=deepcopy(w.current.controls[16]);setattr(c,field,value);w.edit_control(c)
    assert w.live and w.tiles[16].visual.value is None and 16 not in w.values.values
    move(w,16,60);move(w,17,61)
    assert w.tiles[16].visual.value is None and w.tiles[17].visual.value==61


def test_follow_pause_and_return_to_slot_keep_draft_feedback(live_window):
    w=live_window;w.rename_mode('Keep');draft=deepcopy(w.current)
    w.surface_changed('Custom',6);move(w,16,45)
    assert not w.live and w.current==draft and w.tiles[16].visual.value is None
    w.surface_changed('Custom',5);move(w,16,46)
    assert w.live and w.current==draft and w.tiles[16].visual.value==46
    w.follow_changed(False);w.follow_changed(True)
    assert w.tiles[16].visual.value==46  # Same-slot notification does not erase values.


def test_reconnect_with_pending_draft_reads_map_without_overwriting_edits(live_window):
    w=live_window;w.rename_mode('Keep edits');draft=deepcopy(w.current);baseline=deepcopy(w.baseline)
    w.connection_status('Disconnected',False);w.worker=Mock();w.connection_status('Connected',True)
    w.surface_changed('Custom',5)
    token=w.feedback_read_token
    w.worker.request.assert_called_once_with(5,token)
    assert not w.live and w.current==draft
    actual=deepcopy(baseline);actual.controls[17].number=90
    w.mode_received(actual,token)
    assert w.live and w.current==draft and w.baseline==baseline and w.has_pending()
    move(w,16,66);move(w,17,67)
    assert w.tiles[16].visual.value==66 and w.tiles[17].visual.value is None
    w.worker.write.assert_not_called()


def test_import_read_is_stale_after_new_draft_or_slot_change(live_window,tmp_path):
    from lcxl.protocol import encode_mode
    w=live_window;w.worker=Mock();path=tmp_path/'mode.syx';path.write_bytes(encode_mode(w.current))
    actual=deepcopy(w.current);assert w.load_file(path)
    token=w.feedback_read_token;assert token is not None and not w.live
    w.rename_mode('Edit during read');w.mode_received(actual,token)
    assert w.current.name=='Edit during read' and w.live
    move(w,16,35);assert w.tiles[16].visual.value==35
    assert w.load_file(path);old=w.feedback_read_token
    w.rename_mode('Preserve');w.surface_changed('Custom',6)
    w.mode_received(actual,old)
    assert not w.live and w.current.name=='Preserve' and w.feedback_mode is None
    w.surface_changed('Custom',5);new=w.feedback_read_token;assert new!=old
    w.mode_received(actual,new);assert w.live and w.current.name=='Preserve'
    w.worker.write.assert_not_called()


def test_failed_write_recovers_with_read_only_and_no_retry_loop(live_window):
    w=live_window;w.worker=Mock();w.rename_mode('Unsent');draft=deepcopy(w.current)
    actual=deepcopy(w.baseline);w.detach();w.busy=True
    w.read_failed('Write not confirmed.',w.token)
    token=w.feedback_read_token;assert token is not None
    w.worker.request.assert_called_once_with(5,token);w.worker.write.assert_not_called()
    w.mode_received(actual,token);move(w,16,77)
    assert w.current==draft and w.tiles[16].visual.value==77
    assert w.status.text()=='Write not confirmed.'
    w.detach();w.request_feedback();token=w.feedback_read_token
    count=w.worker.request.call_count;w.read_failed('No response.',token)
    assert not w.live and w.worker.request.call_count==count and w.current==draft


def test_partial_send_keeps_cosmetic_unsent_feedback(live_window):
    w=live_window;actual=deepcopy(w.feedback_mode)
    w.current.controls[17].label='Pending name';w.current.controls[17].color=5;w.edited()
    w.write_received(actual,w.token,'fixture backup',16)
    move(w,17,78)
    assert w.tiles[17].visual.value==78 and w.current.controls[17].label=='Pending name'


def test_displaying_different_mode_never_inherits_live_flag(live_window):
    w=live_window;w.display_mode(deepcopy(w.current))
    w.midi_received(bytes([0xb0,20,89]))
    assert not w.live and w.tiles[16].visual.value is None


def test_slow_disconnect_retains_worker_until_ports_close(live_window):
    w=live_window;worker=Mock();worker.wait.return_value=False;w.worker=worker
    w.toggle_connection()
    assert w.worker is worker and not w.connected and not w.live and not w.want_connection
    assert 'Disconnecting' in w.status.text()


def test_diagnostics_distinguish_connection_from_assignment_mismatch(live_window):
    w=live_window;c=deepcopy(w.current.controls[16]);c.number=70;w.edit_control(c)
    assert '1 changed MIDI assignments awaiting send' in w.diagnostic_report()
    w.surface_changed('Custom',6)
    assert 'editing slot is not the active hardware slot' in w.diagnostic_report()


def test_channel_messages_survive_fragmented_and_abandoned_sysex():
    d=Device('offline');received=[];d.midi.connect(received.append)
    first=PREFIX+b'\x10\x00';rest=b'\x01\x02\xf7'
    assert d._frames(first)==[]
    assert d._frames(bytes([0xb0,20,75]))==[]
    assert received==[bytes([0xb0,20,75])]
    assert d._frames(rest)==[first+rest]
    d._frames(first)
    fresh=PREFIX+b'\x15\x03\x00\xf7'
    assert d._frames(fresh)==[fresh] and not d.pending
    assert d._frames(b'\xf8\x01\x02')==[] and not d.pending


def test_feedback_signature_uses_pc_range_and_ignores_labels(live_window):
    c=deepcopy(live_window.current.controls[16]);other=deepcopy(c);other.label='Other'
    assert feedback_signature(c)==feedback_signature(other)
    c.kind=other.kind='PC';other.high=80
    assert feedback_signature(c)!=feedback_signature(other)


def test_values_continue_during_read_backup_write_and_verification(tmp_path):
    from test_editing import MemoryMidi,sample
    from lcxl.protocol import same_mode
    class InterleavedMidi(MemoryMidi):
        def send(self,data):
            super().send(data)
            response=self.responses.pop()
            self.responses.extend([response[:8],bytes([0xb0,20,85]),response[8:]])
    actual=sample();d=Device('offline');d.main=InterleavedMidi(actual)
    received=[];d.midi.connect(received.append)
    result,backup=d._write_slot(5,actual,16,actual,backup_root=tmp_path)
    assert same_mode(result,actual) and len(received)==6
    assert all(msg==bytes([0xb0,20,85]) for msg in received)
