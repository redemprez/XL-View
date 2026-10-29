import sys
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from lcxl.ui import Window, STYLE

if __name__=='__main__':
    if '--check-install' in sys.argv:
        import os
        os.environ['QT_QPA_PLATFORM']='offscreen'
        from lcxl.installation_check import run
        sys.exit(run(sys.argv[sys.argv.index('--check-install')+1]))
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GearStation.XLView')
    app=QApplication(sys.argv); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(Path(__file__).parent/'lcxl/assets/xl-view.ico')))
    window=Window(auto='--offline' not in sys.argv)
    if '--file' in sys.argv: window.load_file(sys.argv[sys.argv.index('--file')+1])
    window.show(); sys.exit(app.exec())
