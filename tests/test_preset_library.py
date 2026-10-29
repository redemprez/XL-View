from copy import deepcopy
from unittest.mock import Mock
import os
import pytest
from PySide6.QtCore import QObject,Signal
from PySide6.QtWidgets import QDialog
from test_editor_ui import window
from lcxl.library import store_preset,save_preset,backup_mode,grouped_presets,trim_versions
from lcxl.protocol import new_mode,parse_mode,same_mode,encode_mode
from lcxl.preset_library import PresetLibraryDialog
from lcxl.workspace_tools import ChangesDialog


class Worker(QObject):
    import_result=Signal(object,int,int,str)
    def __init__(self):
        super().__init__();self.requests=[];self.write=Mock();self.request=Mock()
    def request_import(self,slot,job):self.requests.append((slot,job))


def setup(tmp_path):
    app,w=window();w.library_root=tmp_path;w.connected=True;w.active_slot=6;w.worker=Worker()
    return app,w,PresetLibraryDialog(w)


def finish(w,d):
    d.reject();w.worker=None;w.busy=False;w.dirty=False;w.close()


def test_grouped_versions_retention_dedup_and_backups(tmp_path):
    m=new_mode('Synth');paths=[]
    for i in range(8):
        m.controls[16].label=f'Control {i}';path,created=store_preset(m,tmp_path);assert created;paths.append(path)
        os.utime(path,ns=(1_000_000_000_000_000_000+i*1000,1_000_000_000_000_000_000+i*1000))
    groups=grouped_presets(tmp_path);assert len(groups)==1 and len(groups[0]['versions'])==5
    assert len(list((tmp_path/'archive/library').glob('*.syx')))==3
    path,created=store_preset(m,tmp_path);assert not created and path==paths[-1]
    for _ in range(7):backup_mode(m,tmp_path)
    assert len(grouped_presets(tmp_path,'backups')[0]['versions'])==7
    save_preset(new_mode('synth'),tmp_path);assert len(grouped_presets(tmp_path))==2


def test_legacy_migration_preserves_bad_files(tmp_path):
    root=tmp_path/'library';root.mkdir()
    for i in range(7):
        p=root/f'{i}.syx';p.write_bytes(encode_mode(new_mode('Legacy')));os.utime(p,(100+i,100+i))
    bad=root/'broken.syx';bad.write_bytes(b'bad');trim_versions(tmp_path)
    assert bad.read_bytes()==b'bad' and len(grouped_presets(tmp_path))==2
    assert [p.name for p in grouped_presets(tmp_path)[1]['versions']]==['6.syx','5.syx','4.syx','3.syx','2.syx']
    assert len(list((tmp_path/'archive/library').glob('*')))==2


def test_unknown_settings_are_distinct_versions(tmp_path):
    m=new_mode('Settings');save_preset(m,tmp_path);m.extras={0:b'\x01\x02'}
    _,created=store_preset(m,tmp_path)
    assert created and len(grouped_presets(tmp_path)[0]['versions'])==2


def test_archive_failure_keeps_new_and_previous_files(monkeypatch,tmp_path):
    from pathlib import Path
    m=new_mode('Archive')
    for i in range(5):m.controls[16].label=str(i);save_preset(m,tmp_path)
    monkeypatch.setattr(Path,'replace',Mock(side_effect=PermissionError('Archive is read-only')))
    m.controls[16].label='Newest'
    with pytest.raises(PermissionError):store_preset(m,tmp_path)
    files=list((tmp_path/'library').glob('*.syx'))
    assert len(files)==6 and any(parse_mode(p.read_bytes()).controls[16].label=='Newest' for p in files)


def test_import_reads_all_slots_and_preserves_editor_feedback(tmp_path):
    app,w,d=setup(tmp_path);w.show_control(16);before=deepcopy(w.current);feedback=deepcopy(w.current);w.feedback_mode=feedback;w.live=True
    d.toggle_import();worker=w.worker;job=d.job
    for slot in range(1,16):
        assert worker.requests[-1]==(slot,job)
        worker.import_result.emit(new_mode('Repeated'),slot,job,'')
    assert d.job is None and len(worker.requests)==15 and len(grouped_presets(tmp_path))==1
    assert d.created==1 and d.unchanged==14 and not worker.write.called
    assert same_mode(w.current,before) and w.feedback_mode is feedback and w.live and w.selection=={16}
    finish(w,d)


def test_import_partial_cancel_stale_and_disconnect(tmp_path):
    app,w,d=setup(tmp_path);d.toggle_import();job=d.job;worker=w.worker
    worker.import_result.emit(None,1,job,'Timeout')
    worker.import_result.emit(new_mode('Good'),2,job,'');assert len(d.failures)==1
    d.toggle_import();worker.import_result.emit(new_mode('Late'),3,job,'')
    assert [g['name'] for g in grouped_presets(tmp_path)]==['Good']
    d.toggle_import();newjob=d.job;worker.import_result.emit(new_mode('Stale'),1,job,'');assert d.next_slot==1
    w.connected=False;worker.import_result.emit(new_mode('Gone'),1,newjob,'')
    assert d.job is None and len(grouped_presets(tmp_path))==1
    finish(w,d)


def test_select_old_version_and_load(tmp_path):
    m=new_mode('Saved');m.controls[16].label='Old';save_preset(m,tmp_path);m.controls[16].label='New';save_preset(m,tmp_path)
    app,w,d=setup(tmp_path);w.guard_unsaved=Mock(return_value=True)
    assert d.table.rowCount()==1 and d.table.item(0,0).text()=='1' and d.versions.count()==2
    d.versions.setCurrentIndex(1);d.load_selected();assert w.current.controls[16].label=='Old' and not w.worker.write.called
    finish(w,d)


def test_send_targets_active_not_editing_slot(tmp_path):
    save_preset(new_mode('Saved'),tmp_path);app,w,d=setup(tmp_path);assert w.selected_slot==5
    w.guard_unsaved=Mock(return_value=True);d.send_selected()
    assert w.busy and w.worker.write.call_args.args[0]==6 and w.current.name=='Saved'
    finish(w,d)


@pytest.mark.parametrize('slot',[None,16])
def test_unknown_or_factory_target_cannot_send(tmp_path,slot):
    save_preset(new_mode('Saved'),tmp_path);app,w,d=setup(tmp_path);w.active_slot=slot;d.update_actions()
    assert not d.send.isEnabled();d.send_selected();assert not w.worker.write.called;finish(w,d)


def test_target_changed_during_guard_does_not_load_or_send(tmp_path):
    save_preset(new_mode('Saved'),tmp_path);app,w,d=setup(tmp_path);before=w.current
    def guard(**kwargs):w.active_slot=7;return True
    w.guard_unsaved=guard;d.send_selected();assert w.current is before and not w.worker.write.called;finish(w,d)


def test_target_changed_during_preview_does_not_send(monkeypatch,tmp_path):
    save_preset(new_mode('Saved'),tmp_path);app,w,d=setup(tmp_path);w.guard_unsaved=Mock(return_value=True);w.preview_changes=True
    def review(dialog):w.surface_changed('Other',7);return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ChangesDialog,'exec',review);d.send_selected();assert not w.worker.write.called and not w.busy;finish(w,d)


def test_missing_version_preserves_current(tmp_path):
    save_preset(new_mode('Saved'),tmp_path);app,w,d=setup(tmp_path);before=w.current;d.versions.currentData().unlink()
    d.send_selected();assert w.current is before and not w.worker.write.called and 'Could not' in d.notice.text();finish(w,d)


def test_library_pauses_follow_without_stopping_feedback(tmp_path):
    app,w,d=setup(tmp_path);before=w.current;w.surface_changed('Other',7)
    assert w.current is before and w.active_slot==7 and not w.worker.request.called
    finish(w,d);assert not w.library_open
