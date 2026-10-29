from copy import deepcopy
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt
from test_editor_ui import window


@pytest.mark.parametrize('group',[False,True])
def test_full_send_preserves_inspector_selection_geometry_and_feedback(tmp_path,group):
    app,w=window();w.show();w.connected=True;w.active_slot=5;w.library_root=tmp_path
    w.mode_received(deepcopy(w.current),w.token)
    w.tile_clicked(22)
    if group:w.tile_clicked(26,Qt.KeyboardModifier.ShiftModifier)
    w.rename_mode('Send draft');app.processEvents()
    w.editor.scroll.verticalScrollBar().setValue(40)
    selection=set(w.selection);anchor=w.selection_anchor;focus=w.selected_id
    geometry=w.geometry();grid=w.controller_panel.size();scroll=w.editor.scroll.verticalScrollBar().value()
    writer=Mock();w.worker=writer
    w.send_mode(False)
    assert w.busy and not w.editor.isEnabled() and w.selection==selection
    args=writer.write.call_args.args;actual=deepcopy(args[2]);actual.slot=args[0]
    w.write_received(actual,args[1],'fixture backup',None);app.processEvents()
    assert w.editor.isVisible() and w.editor.isEnabled() and w.editor.group_mode==group
    assert w.selection==selection and w.selection_anchor==anchor and w.selected_id==focus
    assert w.geometry()==geometry and w.controller_panel.size()==grid
    assert w.editor.scroll.verticalScrollBar().value()==scroll
    assert not w.dirty and not w.has_pending() and not w.history
    assert all(w.tiles[i].property('selected')==(i in selection) for i in w.tiles)
    w.midi_received(bytes([0xb0,20,81]));assert w.tiles[16].visual.value==81 and w.selection==selection
    # Subsequent edits remain possible in the same inspector.
    if group:w.edit_group({'color':5})
    else:
        c=deepcopy(w.current.controls[focus]);c.label='Continue';w.edit_control(c)
    assert w.dirty and w.selection==selection
    w.worker=None;w.dirty=False;w.close()


def test_send_buttons_are_in_editor_and_scope_is_explicit():
    app,w=window();w.show();w.connected=True;w.active_slot=5;w.tile_clicked(16);app.processEvents()
    w.review_and_send=Mock()
    assert w.send_all.parent() is w.editor and w.editor.send.parent() is w.editor
    assert w.send_all.geometry().top()>w.editor.send.geometry().bottom()
    w.editor.send.click();w.send_all.click()
    assert [c.args for c in w.review_and_send.call_args_list]==[(True,),(False,)]
    w.tile_clicked(17,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert w.editor.send.isHidden() and w.send_all.isVisible() and w.send_all.isEnabled()
    w.close()


def test_full_send_does_not_follow_away_from_open_editor():
    app,w=window();w.show();w.connected=True;w.active_slot=5;w.worker=Mock()
    w.tile_clicked(16);w.tile_clicked(18,Qt.KeyboardModifier.ShiftModifier)
    selection=set(w.selection);w.busy=True;w.surface_changed('Custom',6)
    w.write_received(deepcopy(w.current),w.token,'fixture backup',None)
    assert w.selected_slot==5 and w.active_slot==6 and w.selection==selection and w.editor.isVisible()
    assert not w.live and not w.resume.isHidden();w.worker.request.assert_not_called()
    # An explicit user decision to resume following can still navigate.
    w.resume_following();w.worker.request.assert_called_once_with(6,w.token)
    w.worker=None;w.close()


def test_stale_or_failed_write_does_not_change_selection():
    app,w=window();w.show();w.tile_clicked(16);w.tile_clicked(20,Qt.KeyboardModifier.ShiftModifier)
    selected=set(w.selection);w.write_received(deepcopy(w.current),w.token-1,'fixture',None)
    w.busy=True;w.read_failed('Simulated failure',w.token)
    assert w.selection==selected and w.editor.isVisible() and w.editor.group_mode
    w.close()
