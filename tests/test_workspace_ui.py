from copy import deepcopy
from unittest.mock import Mock
from test_editor_ui import window
from lcxl.workflows import DraftStore,batch_controls
from lcxl.workspace_tools import ChangesDialog
from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest


def test_multiselection_batch_one_undo_and_copy_paste():
    app,w=window();original=deepcopy(w.current)
    w.tile_clicked(16);w.tile_clicked(17,Qt.KeyboardModifier.ControlModifier)
    assert w.selection=={16,17}
    w.apply_candidate(batch_controls(w.current,w.selection,{'channel':4}))
    assert len(w.history)==1 and w.current.controls[16].channel==4
    w.undo_edit();assert w.current.controls[16].channel==original.controls[16].channel
    w.show_control(16);w.copy_controls();w.show_control(24);w.paste_copied()
    assert w.current.controls[24].id==24 and w.current.controls[24].label==original.controls[16].label
    w.dirty=False;w.close()


def test_recovery_is_offline_and_keeps_pending_baseline(tmp_path):
    app,w=window();w.draft_store=DraftStore(tmp_path);w.recovery_checked=True
    w.rename_mode('Recovery');w.flush_draft();w.recovery=w.draft_store.load()
    w.guard_unsaved=lambda **kw:True
    w.worker=Mock();w.restore_draft()
    assert w.current.name=='Recovery' and w.selected_slot==5 and w.has_pending()
    assert not w.live and not w.worker.write.called
    w.worker=None;w.dirty=False;w.close()


def test_discarded_draft_does_not_get_resaved(tmp_path):
    app,w=window();w.draft_store=DraftStore(tmp_path);w.recovery_checked=True
    w.rename_mode('Discard');w.flush_draft();w.draft_store.clear();w.draft_discarded=True
    w.flush_draft();assert w.draft_store.load() is None
    w.dirty=False;w.close()


def test_reconnect_targets_same_device_and_never_replays_write():
    app,w=window();w.want_connection=True;w.reconnect_name='LCXL3 1 MIDI'
    def scan():w.devices.clear();w.devices.addItems(['LCXL3 2 MIDI','LCXL3 1 MIDI'])
    w.scan_devices=scan;w.toggle_connection=Mock();w.health_tick()
    assert w.devices.currentText()=='LCXL3 1 MIDI' and w.toggle_connection.call_count==1
    w.want_connection=False;w.retry_at=0;w.health_tick();assert w.toggle_connection.call_count==1
    w.close()


def test_reconnection_rereads_even_same_active_slot():
    app,w=window();w.connected=True;w.feedback_mode=None;w.worker=Mock();w.surface_changed('Custom',5)
    w.worker.request.assert_called_once_with(5,w.token)
    w.worker=None;w.close()


def test_compare_and_batch_do_not_write():
    app,w=window();w.worker=Mock();w.show_control(16);w.selection={16,17}
    w.rename_mode('Review');d=ChangesDialog(w);assert d.table.rowCount()==1;d.close()
    w.refresh_selection_editor();w.editor.channel.setCurrentIndex(4);w.editor.channel.activated.emit(4)
    assert w.current.controls[16].channel==4 and not w.worker.write.called
    w.worker=None;w.dirty=False;w.close()


def test_review_holds_target_when_controller_changes_slot(monkeypatch):
    app,w=window();w.worker=Mock();w.connected=True;w.active_slot=5;w.send_mode=Mock()
    w.preview_changes=True
    def accept(d):
        w.surface_changed('Custom',6)
        assert w.selected_slot==5 and w.current is not None
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ChangesDialog,'exec',accept);w.review_and_send(False)
    w.send_mode.assert_called_once_with(False);assert w.selected_slot==5
    w.worker=None;w.close()


def test_review_rejects_connection_or_draft_change(monkeypatch):
    app,w=window();w.worker=Mock();w.connected=True;w.send_mode=Mock()
    w.preview_changes=True
    def accept(d):
        w.token+=1
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ChangesDialog,'exec',accept);w.review_and_send(False)
    assert not w.send_mode.called and 'Nothing was sent' in w.status.text()
    w.worker=None;w.close()


def test_batch_range_matches_mixed_selection():
    app,w=window();w.selection={16,17};w.current.controls[16].kind='CC14'
    w.refresh_selection_editor();assert w.editor.high.spin.maximum()==127
    w.close()


def test_ctrl_shift_range_and_group_panel_preserve_grid():
    app,w=window();w.show();app.processEvents();size=w.controller_panel.size()
    QTest.mouseClick(w.tiles[22].visual,Qt.MouseButton.LeftButton)
    QTest.mouseClick(w.tiles[26].visual,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier)
    assert w.selection==set(range(22,27)) and w.editor.group_mode
    assert w.controller_panel.size()==size
    QTest.mouseClick(w.tiles[24],Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier)
    assert w.selection=={22,23,25,26}
    QTest.mouseClick(w.tiles[29],Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
    assert w.selection==set(range(22,30))
    w.live=True;w.midi_received(bytes([0xb0,20,50]))
    assert w.selection==set(range(22,30)) and w.editor.group_mode
    w.close()


def test_group_mouse_edits_apply_only_touched_fields_and_undo():
    app,w=window();w.show();w.tile_clicked(16);w.tile_clicked(17,Qt.KeyboardModifier.ControlModifier)
    w.current.controls[17].low=20;w.current.controls[17].channel=3;w.current.controls[17].color=5;w.refresh_selection_editor();app.processEvents()
    before=deepcopy(w.current)
    # No checkbox or Apply gate: an actual swatch click changes both controls.
    QTest.mouseClick(w.editor.color.buttons[37],Qt.MouseButton.LeftButton)
    assert all(w.current.controls[i].color==37 for i in (16,17))
    assert w.current.controls[17].low==20 and w.current.controls[17].channel==3
    assert len(w.history)==1 and w.editor.group_mode
    # Enter a mixed group's first value: even an unchanged underlying spin value applies it.
    w.editor.low.spin.setFocus();QTest.keyClicks(w.editor.low.spin,'0');QTest.keyClick(w.editor.low.spin,Qt.Key.Key_Return)
    assert w.current.controls[16].low==w.current.controls[17].low==0
    w.undo_edit();assert w.current.controls[17].low==20 and w.selection=={16,17} and w.editor.group_mode
    w.undo_edit();assert w.current==before
    QTest.mouseClick(w.editor.high.slider,Qt.MouseButton.LeftButton,pos=QPoint(10,w.editor.high.slider.height()//2))
    assert w.current.controls[16].high==w.current.controls[17].high<127
    assert w.selection=={16,17} and w.editor.group_mode
    w.dirty=False;w.close()


def test_group_copy_paste_order_and_incompatible_paste_is_atomic():
    app,w=window();w.tile_clicked(16);w.tile_clicked(17,Qt.KeyboardModifier.ControlModifier);w.copy_controls()
    w.tile_clicked(24);w.tile_clicked(25,Qt.KeyboardModifier.ControlModifier);w.paste_copied()
    assert [w.current.controls[i].label for i in (24,25)]==[c.label for c in w.copied]
    w.tile_clicked(40);w.tile_clicked(41,Qt.KeyboardModifier.ControlModifier);before=deepcopy(w.current)
    w.paste_copied();assert w.current==before and w.editor.error.text()
    assert w.editor.color.isHidden() and w.editor.on_color.isHidden()
    w.dirty=False;w.close()


def test_compact_all_six_rows_and_labels_fit():
    app,w=window();w.resize(940,900);w.show();app.processEvents()
    for tile in w.tiles.values():
        assert tile.geometry().bottom()<w.controller_panel.height()
        assert tile.visual.height()>=tile.visual.minimumHeight()
        assert tile.name.height()>=30 and tile.value.height()>=16
    before=w.controller_panel.size();w.show_control(16);app.processEvents()
    assert w.controller_panel.size()==before
    w.close()
