import sys
from pathlib import Path
from lcxl.library import data_root,save_preset
from lcxl.protocol import new_mode


def test_installed_library_survives_application_folder_change(tmp_path,monkeypatch):
    user=tmp_path/'user';app=tmp_path/'installed';app.mkdir()
    (app/'installed-mode.txt').write_text('installed')
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(app/'XL View.exe'))
    monkeypatch.setenv('LOCALAPPDATA',str(user))
    expected=user/'XL View'/'presets'
    assert data_root()==expected
    preset=save_preset(new_mode('Keep me'))
    upgraded=tmp_path/'upgraded';upgraded.mkdir();(upgraded/'installed-mode.txt').write_text('installed')
    monkeypatch.setattr(sys,'executable',str(upgraded/'XL View.exe'))
    assert data_root()==expected and preset.exists()


def test_portable_and_source_keep_existing_library(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(tmp_path/'dist'/'XL View'/'XL View.exe'))
    assert data_root()==tmp_path/'presets'
    monkeypatch.setattr(sys,'executable',str(tmp_path/'portable'/'XL View.exe'))
    assert data_root()==tmp_path/'portable'/'presets'
    monkeypatch.setattr(sys,'frozen',False)
    assert data_root()==Path(__file__).resolve().parents[1]/'presets'
