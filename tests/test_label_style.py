from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor,QFontMetrics
from PySide6.QtWidgets import QApplication
from test_editor_ui import window
from lcxl.label_style import LabelStyle,ControlNameLabel
from lcxl.settings_dialog import SettingsDialog
from lcxl.protocol import same_mode,encode_mode


def test_preferences_persist_and_invalid_settings_are_bounded(tmp_path):
    settings=QSettings(str(tmp_path/'labels.ini'),QSettings.Format.IniFormat)
    style=LabelStyle('Arial',175,True,'#95d4ff',True,'#15191d');style.save(settings);settings.sync()
    assert LabelStyle.load(QSettings(str(tmp_path/'labels.ini'),QSettings.Format.IniFormat))==style
    settings.setValue('control_labels/scale','garbage');settings.setValue('control_labels/text_color','invalid')
    settings.setValue('control_labels/background_color','invalid');settings.setValue('control_labels/bold','false')
    loaded=LabelStyle.load(settings);assert loaded.scale==100 and loaded.text_color=='' and not loaded.bold and loaded.background_color=='#30363d'
    assert LabelStyle.normalize({'scale':900}).scale==200
    assert LabelStyle.normalize({'scale':1}).scale==75


@pytest.mark.parametrize('scale',[75,100,150,200])
def test_two_line_labels_fit_and_preserve_full_name(scale):
    app=QApplication.instance() or QApplication([])
    label=ControlNameLabel();label.resize(74,32);text='SuperLongUnbrokenControllerLabel';label.setText(text)
    label.apply_appearance(LabelStyle('Segoe UI',scale,True));lines=label.display_lines();metrics=QFontMetrics(label.appearance.font())
    assert len(lines)<=2 and all(metrics.horizontalAdvance(line)<=label.text_width() for line in lines)
    assert lines[-1].endswith('…') and label.toolTip()==text and label.text()==text
    assert label.height()>=metrics.lineSpacing()*len(lines)
    label.close()


def test_style_does_not_edit_draft_midi_feedback_or_inspector():
    app,w=window();w.show_control(16);w.connected=True;w.active_slot=5;w.feedback_mode=deepcopy(w.current);w.live=True
    w.midi_received(bytes([0xb0,20,81]));before=encode_mode(w.current);history=list(w.history);selection=set(w.selection);feedback=w.feedback_mode
    style=LabelStyle('Arial',140,True,'#ead664',True,'#243746');w.set_label_style(style)
    assert encode_mode(w.current)==before and w.history==history and w.selection==selection and not w.dirty
    assert w.feedback_mode is feedback and w.live and w.tiles[16].visual.value==81
    assert all(t.name.appearance==style for t in w.tiles.values())
    w.rename_mode('Other');w.undo_edit();assert all(t.name.appearance==style for t in w.tiles.values())
    w.display_mode(deepcopy(w.current));assert all(t.name.appearance==style for t in w.tiles.values())
    w.dirty=False;w.close()


def test_live_dialog_controls_reset_and_cancel_color(monkeypatch):
    app,w=window();d=SettingsDialog(w);d.tabs.setCurrentIndex(1);d.show();app.processEvents()
    assert not d.background_swatches.isEnabled()
    d.scale.setValue(150);d.bold.click();d.foreground.choose(1);d.background.click();d.background_swatches.choose(2)
    assert w.label_style==LabelStyle('Segoe UI',150,True,'#95d4ff',True,'#243746')
    assert d.preview_name.appearance==w.label_style and d.background_swatches.isEnabled()
    before=w.label_style;monkeypatch.setattr('lcxl.settings_dialog.QColorDialog.getColor',lambda *args:QColor())
    d.choose_color('text_color');assert w.label_style==before
    d.reset.click();assert w.label_style==LabelStyle() and not d.background.isChecked() and not d.bold.isChecked()
    d.accept();w.close()


def test_restored_window_preferences_and_reset_survive_restart(tmp_path,monkeypatch):
    import lcxl.ui as ui
    import lcxl.workspace_tools as workflows
    app=QApplication.instance() or QApplication([]);settings=QSettings(str(tmp_path/'window.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(ui,'QSettings',lambda *args:settings);monkeypatch.setattr(workflows,'data_root',lambda:tmp_path)
    w=ui.Window(auto=False);style=LabelStyle('Arial',125,True,'#77d59e',True,'#15191d');w.set_label_style(style);w.close();settings.sync()
    w=ui.Window(auto=False);assert w.label_style==style and all(t.name.appearance==style for t in w.tiles.values())
    w.set_label_style(LabelStyle());w.close();settings.sync();w=ui.Window(auto=False);assert w.label_style==LabelStyle();w.close()


def test_maximum_scale_keeps_all_rows_visible_with_inspector():
    app,w=window();w.show();w.resize(940,900);w.set_label_style(LabelStyle('Arial',200,True,background=True));app.processEvents()
    def check():
        assert all(w.controller_panel.rect().contains(t.geometry()) for t in w.tiles.values())
        assert all(t.visual.height()>=t.visual.minimumHeight() for t in w.tiles.values())
        assert all(t.rect().contains(t.name.geometry()) for t in w.tiles.values())
    check();size=w.controller_panel.size();w.show_control(16);app.processEvents();check();assert w.controller_panel.size()==size
    w.close_editor();app.processEvents();check();w.set_label_style(LabelStyle());app.processEvents();assert w.minimumHeight()==900;w.close()
