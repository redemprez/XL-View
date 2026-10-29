from unittest.mock import Mock
from copy import deepcopy
import pytest
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication,QDialog,QCheckBox
from test_editor_ui import window
from lcxl.workspace_tools import ChangesDialog


@pytest.mark.parametrize('one',[False,True])
def test_default_send_skips_preview_but_uses_existing_write_path(monkeypatch,tmp_path,one):
    app,w=window();w.connected=True;w.active_slot=5;w.worker=Mock();w.library_root=tmp_path;w.show_control(16)
    preview=Mock(side_effect=AssertionError('Preview must be off by default'))
    monkeypatch.setattr(ChangesDialog,'exec',preview)
    assert not w.preview_changes
    w.review_and_send(one)
    assert w.busy and len(list((tmp_path/'library').glob('*.syx')))==1
    slot,token,draft,cid,baseline=w.worker.write.call_args.args
    assert slot==5 and cid==(16 if one else None) and baseline.slot==5
    w.write_received(deepcopy(draft),token,'fixture backup',cid)
    assert w.editor_expansion and w.selection=={16}
    preview.assert_not_called();w.worker=None;w.close()


@pytest.mark.parametrize('one',[False,True])
@pytest.mark.parametrize('accepted',[False,True])
def test_enabled_preview_can_confirm_or_cancel(monkeypatch,one,accepted):
    app,w=window();w.connected=True;w.show_control(16);w.preview_changes_changed(True);w.send_mode=Mock()
    preview=Mock(return_value=QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected)
    monkeypatch.setattr(ChangesDialog,'exec',preview);w.review_and_send(one)
    preview.assert_called_once()
    if accepted:w.send_mode.assert_called_once_with(one)
    else:w.send_mode.assert_not_called()
    assert not w.reviewing;w.close()


def test_manual_changes_is_available_when_preview_is_off(monkeypatch):
    app,w=window();w.send_mode=Mock();preview=Mock(return_value=QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ChangesDialog,'exec',preview);w.open_changes()
    preview.assert_called_once();w.send_mode.assert_not_called();w.close()


def test_setting_checkbox_persists_across_windows(monkeypatch,tmp_path):
    import lcxl.ui as ui
    import lcxl.workspace_tools as workflows
    app=QApplication.instance() or QApplication([])
    store=QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(ui,'QSettings',lambda *args:store)
    monkeypatch.setattr(workflows,'data_root',lambda:tmp_path)
    w=ui.Window(auto=False);assert not w.preview_changes
    def toggle():
        d=app.activeModalWidget();check=next(c for c in d.findChildren(QCheckBox) if c.text()=='Preview changes before sending')
        assert not check.isChecked();check.click();d.accept()
    QTimer.singleShot(0,toggle);w.open_settings();store.sync();w.close()
    w=ui.Window(auto=False);assert w.preview_changes
    w.preview_changes_changed(False);store.sync();w.close()
    w=ui.Window(auto=False);assert not w.preview_changes;w.close()
