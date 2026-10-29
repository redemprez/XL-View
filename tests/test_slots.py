from copy import deepcopy
from PySide6.QtCore import Qt, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from test_editor_ui import window
from lcxl.device import Device


def test_factory_mode_cannot_become_write_target_or_replace_pending_draft():
    app,w=window();w.connected=True;w.active_slot=5
    w.rename_mode('Keep draft');draft=deepcopy(w.current)
    w.surface_changed('Custom',16)
    assert w.current==draft and w.selected_slot==5 and w.bank.buttons[16].live
    w.bank.buttons[16].click();w.manual_slot(16)
    assert w.current==draft and w.selected_slot==5
    assert not w.bank.buttons[16].isEnabled() and not w.bank.buttons[16].isChecked()
    # Once no unsent changes remain, following acknowledges the fixed mode
    # without reading it as an editable slot or enabling either send action.
    w.dirty=False;w.baseline=deepcopy(w.current);w.surface_changed('Custom',16)
    assert w.current is None and w.selected_slot is None
    assert not w.send_all.isEnabled() and not w.editor.send.isEnabled()
    assert w.mode_name.text()=='Default' and w.resume.isHidden()
    assert 16 not in Device('test').inventory
    w.close()


def test_follow_keeps_unsent_draft_even_after_library_save(tmp_path):
    app,w=window();w.connected=True;w.active_slot=5;w.library_root=tmp_path
    w.show_control(16);w.editor.color.choose(5);draft=deepcopy(w.current)
    assert w.save_current() and not w.dirty and w.has_pending()
    w.surface_changed('Custom',2)
    assert w.current==draft and w.selected_slot==5 and w.active_slot==2 and w.follow_enabled
    assert w.bank.buttons[2].live and w.bank.buttons[5].isChecked()
    assert not w.bank.buttons[5].live and not w.resume.isHidden()
    w.close()


def test_cancel_slot_navigation_preserves_single_target(monkeypatch):
    app,w=window();w.rename_mode('Draft')
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Cancel)
    w.manual_slot(2)
    assert w.selected_slot==5 and w.current.name=='Draft' and w.bank.buttons[5].isChecked()
    w.dirty=False;w.close()


def test_follow_reads_new_hardware_slot_and_ignores_stale_read():
    app,w=window();w.connected=True
    class Reader:
        def request(self,slot,token):self.requested=(slot,token)
    reader=Reader();w.worker=reader;old=deepcopy(w.current)
    w.surface_changed('Custom',2);old_token=w.token
    assert reader.requested==(2,w.token) and w.selected_slot==2
    w.surface_changed('Custom',3)
    w.mode_received(old,old_token)
    assert w.current is None and w.selected_slot==3 and reader.requested==(3,w.token)
    w.worker=None;w.close()


def test_inline_name_cancel_commit_and_partial_write_keep_device_name():
    app,w=window();w.show();app.processEvents();actual=deepcopy(w.current)
    w.mode_name.begin();w.mode_name.field.setText('Cancelled');QTest.keyClick(w.mode_name.field,Qt.Key.Key_Escape)
    assert w.current.name==actual.name
    w.mode_name.begin();w.mode_name.field.setText('Draft name');QTest.keyClick(w.mode_name.field,Qt.Key.Key_Return)
    assert w.current.name=='Draft name' and w.slot_names[5]==actual.name
    w.write_received(actual,w.token,'backup',16)
    assert w.current.name=='Draft name' and w.slot_names[5]==actual.name and w.has_pending()
    sent=deepcopy(w.current);sent.slot=5
    w.write_received(sent,w.token,'backup',None)
    assert w.slot_names[5]=='Draft name' and not w.has_pending()
    w.dirty=False;w.close()


def test_offline_names_and_pending_first_destination():
    app,w=window();w.slot_name_received(2,'Other');w.connected=True;w.active_slot=5;w.update_actions()
    w.connection_status('Disconnected',False)
    assert w.bank.buttons[2].name=='Other' and not any(b.live for b in w.bank.buttons.values())
    w.clear_mode();w.selected_slot=None;w.create_mode();draft=deepcopy(w.current)
    w.manual_slot(7)
    assert w.selected_slot==7 and w.current==draft and w.has_pending()
    w.dirty=False;w.close()


def test_settings_persists_follow_without_losing_draft(tmp_path):
    app,w=window();settings=QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat);w.settings=settings
    assert w.follow_enabled
    w.rename_mode('Keep');w.follow_changed(False);w.follow_changed(True)
    assert settings.value('follow_controller',False,type=bool) and w.current.name=='Keep'
    w.dirty=False;w.close()


def test_background_inventory_yields_to_reads_and_writes():
    d=Device('test');d.request(5,12)
    assert d._next_request()==('read',5,12) and 5 not in d.inventory
    assert d._next_request()==('inventory',1,0)
    d.commands.put(('write',7,13,None,None,None))
    assert d._next_request()[0:3]==('write',7,13)
    assert d._next_request()==('inventory',2,0)


def test_follow_protects_inline_name_until_commit_or_cancel():
    app,w=window();w.connected=True;w.active_slot=5;w.show();app.processEvents()
    class Reader:
        def request(self,*args):raise AssertionError('Must not navigate during rename')
    w.worker=Reader();original=w.current.name
    w.mode_name.begin();w.mode_name.field.setText('Typing')
    w.surface_changed('Custom',2)
    assert w.selected_slot==5 and w.mode_name.field.text()=='Typing' and w.has_pending()
    QTest.keyClick(w.mode_name.field,Qt.Key.Key_Escape)
    assert w.current.name==original and not w.has_pending() and w.selected_slot==5
    w.mode_name.begin();w.mode_name.field.setText('Confirmed');w.surface_changed('Custom',3)
    QTest.keyClick(w.mode_name.field,Qt.Key.Key_Return)
    assert w.current.name=='Confirmed' and w.selected_slot==5 and w.has_pending()
    w.worker=None;w.dirty=False;w.close()


def test_verified_send_follows_latest_hardware_but_partial_draft_stays():
    app,w=window();w.connected=True;w.active_slot=5
    class Reader:
        requested=None
        def request(self,*args):self.requested=args
    reader=Reader();w.worker=reader;w.rename_mode('Sent name');sent=deepcopy(w.current);sent.slot=5
    w.busy=True;w.surface_changed('Custom',2);assert w.selected_slot==5
    w.write_received(sent,w.token,'backup',None)
    assert w.selected_slot==2 and reader.requested==(2,w.token)
    # A hardware change while the draft was pending also reconciles after sending.
    w.display_mode(sent);w.rename_mode('Later');sent=deepcopy(w.current)
    w.surface_changed('Custom',3);assert w.selected_slot==5
    w.write_received(sent,w.token,'backup',None);assert w.selected_slot==3
    # A single-control send must keep other unsent work on its original destination.
    w.display_mode(sent);actual=deepcopy(w.current);w.rename_mode('Keep unsent')
    reader.requested=None;w.busy=True;w.surface_changed('Custom',4)
    w.write_received(actual,w.token,'backup',16)
    assert w.selected_slot==5 and w.current.name=='Keep unsent' and reader.requested is None
    w.worker=None;w.dirty=False;w.close()
