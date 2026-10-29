"""Explicit offline package check. Never opens MIDI or changes user settings."""
import json
import sys
import tempfile
from pathlib import Path


def run(report_path):
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    from .device import Device
    from .library import data_root, save_preset
    from .protocol import new_mode, parse_mode, same_mode, Control
    from copy import deepcopy
    from .ui import Window, STYLE
    from .version import VERSION
    from .workspace_tools import ChangesDialog
    report={'ok':False,'version':VERSION,'midi_opened':False,'executable':sys.executable,'qt':qVersion()}
    app=QApplication.instance() or QApplication([])
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    original=Device.discover
    window=None
    try:
        Device.discover=staticmethod(lambda:[])
        root=data_root();root.mkdir(parents=True,exist_ok=True)
        report['data_root']=str(root)
        with tempfile.TemporaryDirectory(prefix='install-check-',dir=root) as folder:
            mode=new_mode('Install check');path=save_preset(mode,Path(folder))
            assert same_mode(mode,parse_mode(path.read_bytes()))
        window=Window(auto=False,settings=False);window.display_mode(mode)
        window.show();app.processEvents()
        assert len(window.tiles)==48 and len(window.bank.buttons)==16
        from .label_style import LabelStyle
        from .settings_dialog import SettingsDialog
        appearance=SettingsDialog(window);appearance.tabs.setCurrentIndex(1)
        appearance.change(scale=140,bold=True,text_color='#95d4ff',background=True)
        appearance.show();app.processEvents()
        assert all(t.name.appearance.scale==140 and t.name.appearance.bold for t in window.tiles.values())
        assert not appearance.grab().isNull()
        appearance.reset_labels();appearance.accept();assert window.label_style==LabelStyle()
        report['label_appearance_checked']=True
        window.show_control(16)
        changes=ChangesDialog(window);changes.show();app.processEvents()
        assert not changes.grab().isNull();changes.close()
        from PySide6.QtCore import Qt
        window.tile_clicked(17,Qt.KeyboardModifier.ControlModifier);app.processEvents()
        assert window.editor.group_mode and not window.editor.grab().isNull()
        window.close_editor()
        # Exercise the actual packaged event path with synthetic MIDI, no ports.
        mode.controls[16]=Control(16,'Source','CC',20)
        mode.controls[17]=Control(17,'Target','CC',21);mode.slot=5
        window.connected=True;window.active_slot=5
        window.mode_received(deepcopy(mode),window.token)
        window.tile_clicked(16);window.copy_controls();window.tile_clicked(17);window.paste_copied()
        window.midi_received(bytes([0xb0,20,71]));window.midi_received(bytes([0xb0,21,72]))
        assert window.live and window.tiles[16].visual.value==71 and window.tiles[17].visual.value is None
        assert window.last_meta.text()=='CC 20 · Global\nAbsolute · 7-bit'
        report['message_details_checked']=True
        window.undo_edit();window.midi_received(bytes([0xb0,21,73]))
        assert window.tiles[17].visual.value==73
        window.rename_mode('Live renamed');window.midi_received(bytes([0xb0,20,74]))
        assert window.tiles[16].visual.value==74
        window.tile_clicked(16,Qt.KeyboardModifier.ControlModifier)
        selected=set(window.selection);size=window.size()
        window.busy=True;window.write_received(deepcopy(window.current),window.token,'offline fixture',None)
        assert window.editor.isVisible() and window.editor.group_mode and window.selection==selected and window.size()==size
        assert window.send_all.parent() is window.editor and window.send_all.isVisible()
        report['send_preserves_inspector_checked']=True
        assert not window.preview_changes
        original_send=window.send_mode;requested=[]
        window.send_mode=lambda one=False:requested.append(one)
        window.review_and_send(False);window.review_and_send(True)
        assert requested==[False,True]
        window.send_mode=original_send;report['optional_preview_checked']=True
        window.connected=False;window.dirty=False;window.close_editor()
        from .preset_library import PresetLibraryDialog
        with tempfile.TemporaryDirectory(prefix='library-check-',dir=root) as folder:
            window.library_root=Path(folder)
            for i in range(7):
                sample=new_mode('Version check');sample.controls[16].label=f'Control {i}';save_preset(sample,Path(folder))
            library=PresetLibraryDialog(window);library.show();app.processEvents()
            assert library.table.rowCount()==1 and library.versions.count()==5
            assert not library.send.isEnabled() and not library.grab().isNull()
            assert len(list((Path(folder)/'archive/library').glob('*.syx')))==2
            library.reject()
        report['preset_library_checked']=True
        report['live_feedback_checked']=True
        report['new_dialogs_rendered']=True
        report['rendered_size']=[window.width(),window.height()]
        report['ok']=not window.grab().isNull()
    except Exception as ex:
        report['error']=f'{type(ex).__name__}: {ex}'
    finally:
        if window:window.close()
        Device.discover=staticmethod(original)
        Path(report_path).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1
