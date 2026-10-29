import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from lcxl.ui import Window,STYLE
from lcxl.protocol import parse_mode

def test_offline_values_remain_unknown_and_stale_result_ignored():
    app=QApplication.instance() or QApplication([]); app.setStyleSheet(STYLE)
    w=Window(auto=False,settings=False)
    mode=parse_mode((Path(__file__).parent/'fixtures/d50-device.syx').read_bytes(),5)
    w.display_mode(mode); w.live=False
    w.midi_received(bytes([0xb0,20,55]))
    assert w.tiles[16].visual.value is None
    w.live=True; w.midi_received(bytes([0xb0,20,55]))
    assert w.tiles[16].visual.value==55
    assert '55' in w.last_detail.text()
    w.token=10; w.mode_received(mode,9)
    assert w.tiles[16].visual.value==55
    w.clear_mode(); assert w.tiles[16].visual.value is None
    assert '55' not in w.last_detail.text()
    w.close()
