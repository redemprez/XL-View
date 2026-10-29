import math, time
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QRectF, Signal, QSettings, QPoint, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QComboBox,QCheckBox,QFileDialog,QFrame,QSizePolicy,
    QLineEdit,QMessageBox,QDialog,QListWidget,QListWidgetItem,QScrollArea)
from .protocol import Control, Values, parse_mode, encode_mode, new_mode, same_mode, control_signature, feedback_signature
from .device import Device
from .editor import Editor,COLOR_MAP
from .widgets import IconButton, MidiStatusButton, StatusText, DisplayControlName
from .slots import SlotBank, EditableName
from .library import save_preset,list_presets,atomic_write,data_root
from .workspace_tools import WorkspaceTools
from .version import VERSION
from .label_style import LabelStyle,ControlNameLabel

# Controller palette subset; unknown stored colors use a neutral readable marker.
COLORS={0:'#66717c',1:'#8995a2',3:'#e8edf0',5:'#fb7774',9:'#edb55c',13:'#ead664',
        25:'#77d59e',37:'#6cd5d0',45:'#73b8f6',53:'#c19bec'}
COLORS.update(COLOR_MAP)
STYLE='''
QWidget { background:#202327; color:#ECEFF2; font-family:"Segoe UI"; font-size:13px; }
QMainWindow { background:#202327; }
QPushButton,QComboBox { background:#30363d; border:1px solid #505B67; border-radius:4px; padding:6px 10px; min-height:20px; }
QPushButton:hover,QComboBox:hover { background:#3a454f; }
QPushButton:focus,QComboBox:focus { border:1px solid #95D4FF; }
QPushButton:disabled { color:#7c8793; border-color:#3a424b; }
QLineEdit,QSpinBox,QListWidget { background:#15191d; border:1px solid #505b67; border-radius:4px; padding:5px; }
QLineEdit:focus,QSpinBox:focus { border-color:#95d4ff; }
QListWidget::item { padding:10px; }
QListWidget::item:selected { background:#3a454f; color:#ffffff; }
QScrollArea { border:0; }
QScrollBar:vertical { background:#202327; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#505b67; min-height:30px; border-radius:4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:#202327; }
QFrame#control[selected="true"] { border-color:#95d4ff; background:#292f35; }
QCheckBox { spacing:7px; }
QCheckBox::indicator { width:15px; height:15px; }
QLabel#muted { color:#b3bec8; }
QLabel#status { color:#b3bec8; }
QLabel#modeName { font-size:24px; font-weight:600; background:#15191d; }
QFrame#display { background:#15191d; border:1px solid #505b67; border-radius:5px; }
QFrame#display QLabel { background:transparent; }
QFrame#left { background:#202327; }
QFrame#control { border:1px solid transparent; border-radius:4px; }
QFrame#control:focus { border:1px solid #95d4ff; }
QSlider::groove:horizontal { height:4px; background:#505b67; border-radius:2px; }
QSlider::sub-page:horizontal { background:#95d4ff; border-radius:2px; }
QSlider::handle:horizontal { background:#eceff2; border:2px solid #202327; width:14px; margin:-6px 0; border-radius:8px; }
QSlider::handle:horizontal:hover,QSlider::handle:horizontal:focus { background:#95d4ff; }
QToolTip { background:#343b43; color:#eceff2; border:1px solid #607080; padding:6px; }
'''

class Visual(QWidget):
    selected=Signal()
    def __init__(self,kind):
        super().__init__(); self.kind=kind; self.value=None; self.maximum=127; self.color='#b3bec8'; self.active=False
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setMinimumSize(30,24)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height(); c=QColor(self.color)
        p.setPen(QPen(QColor('#505b67'),1))
        if self.kind=='knob':
            r=max(2,min(w*.28,(h-14)/2,34)); x=w/2; y=h/2
            p.setBrush(QColor('#111519')); p.drawEllipse(QRectF(x-r,y-r,r*2,r*2))
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(c,4 if self.active else 2))
            p.drawArc(QRectF(x-r-4,y-r-4,2*r+8,2*r+8),-45*16,270*16)
            if self.value is not None:
                a=math.radians(135+270*self.value/self.maximum)
                p.setPen(QPen(c,3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
                p.drawLine(int(x+math.cos(a)*r*.42),int(y+math.sin(a)*r*.42),int(x+math.cos(a)*r*.82),int(y+math.sin(a)*r*.82))
            else:
                p.setPen(QColor('#b3bec8')); p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'—')
        elif self.kind=='fader':
            x=w/2; top=12; bottom=h-12
            p.setPen(QPen(QColor('#111519'),6,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap)); p.drawLine(int(x),top,int(x),bottom)
            p.setPen(QPen(QColor('#505b67'),1))
            for i in range(9):
                y=top+(bottom-top)*i/8; p.drawLine(int(x-15),int(y),int(x-10),int(y))
            if self.value is not None:
                y=bottom-(bottom-top)*self.value/self.maximum
                p.setPen(QPen(c,1)); p.setBrush(QColor('#454f59')); p.drawRoundedRect(QRectF(x-18,y-8,36,16),2,2)
                p.setPen(QPen(c,2)); p.drawLine(int(x-12),int(y),int(x+12),int(y))
            else:
                p.setPen(QColor('#b3bec8')); p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'—')
        else:
            bh=min(26,h-6); box=QRectF(8,(h-bh)/2,w-16,bh)
            p.setPen(QPen(c if self.active else QColor('#505b67'),1))
            p.setBrush(c.darker(240) if self.value else QColor('#30363d')); p.drawRoundedRect(box,3,3)
            p.setPen(QPen(c,3)); p.drawLine(QPointF(w/2-13,box.center().y()),QPointF(w/2+13,box.center().y()))
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.selected.emit()

class ControlTile(QFrame):
    selected=Signal(int)
    def __init__(self,cid):
        super().__init__(); self.cid=cid; self.control=Control(cid); self.expires=0
        self.setObjectName('control')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.kind='knob' if cid<40 else 'fader' if cid<48 else 'button'
        layout=QVBoxLayout(self); layout.setContentsMargins(3,1,3,1); layout.setSpacing(0)
        self.name=ControlNameLabel('—')
        self.visual=Visual(self.kind)
        self.visual.setMinimumHeight(36 if self.kind=='knob' else 42 if self.kind=='fader' else 18)
        self.value=QLabel('—'); self.value.setAlignment(Qt.AlignmentFlag.AlignCenter); self.value.setStyleSheet('font-size:13px; color:#b3bec8;')
        self.value.setFixedHeight(16)
        layout.addWidget(self.visual,1); layout.addWidget(self.name); layout.addWidget(self.value)
        self.visual.selected.connect(self.select)
        self.setMinimumWidth(60)
        self.apply_label_style(LabelStyle())
    def apply_label_style(self,style):
        self.name.apply_appearance(style)
        self.setMinimumHeight(self.visual.minimumHeight()+self.name.height()+self.value.height()+2)
        self.layout().invalidate()
    def set_control(self,c):
        self.visual.maximum=16383 if c.kind in ('CC14','NRPN14') else 127
        self.control=c; self.name.setText(c.label or ('Unassigned' if c.kind=='disabled' else f'{c.kind} {c.number or ""}'))
        self.visual.color=COLORS.get(c.color,'#b3bec8'); self.visual.value=None
        self.value.setText('off' if c.kind=='disabled' else '—')
        self.name.set_disabled_assignment(c.kind=='disabled')
        self.setToolTip(f'{self.position()}\n{c.label or "Unnamed"}\n{c.assignment}\nValue: last received from MIDI.\nCtrl-click: toggle selection · Shift-click: range · Ctrl+Shift: add range.')
        self.setAccessibleName(f'{self.position()}, {c.label}, {c.assignment}')
        self.visual.update()
    def position(self):
        i=self.cid-16
        return f'Knob {i%8+1}, row {i//8+1}' if i<24 else f'Fader {i-23}' if i<32 else f'Button {(i-32)%8+1}, row {(i-32)//8+1}'
    def set_value(self,value):
        self.visual.value=None if self.control.relative else value; self.visual.active=True; self.expires=time.monotonic()+.45
        self.value.setText(f'rel {value}' if self.control.relative else str(value)); self.visual.update()
    def cool(self):
        if self.visual.active and time.monotonic()>self.expires:
            self.visual.active=False; self.visual.update()
    def select(self): self.setFocus(); self.selected.emit(self.cid)
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:self.select()
    def keyPressEvent(self,e):
        if e.key() in (Qt.Key.Key_Return,Qt.Key.Key_Space): self.selected.emit(self.cid)
        else: super().keyPressEvent(e)

class Window(WorkspaceTools,QMainWindow):
    def __init__(self, auto=True, settings=True):
        super().__init__(); self.setWindowTitle('XL View — Launch Control XL 3')
        self.resize(1260,980); self.setMinimumSize(940,900)
        self.worker=None; self.current=None; self.active_slot=None; self.active_name='Unknown'
        self.token=0; self.values=Values(); self.live=False; self.connected=False
        self.selected_id=None; self.baseline=None; self.dirty=False; self.busy=False; self.history=[]
        self.loaded=False; self.library_root=None; self.editor_expansion=0; self.feedback_mode=None
        self.feedback_read_token=None
        self.settings=QSettings('GearStation','XL View') if settings else None
        self.label_style=LabelStyle.load(self.settings)
        self.selected_slot=None; self.slot_names={}; self.slot_errors={}; self.hardware_modes={}
        self.follow_enabled=self.settings.value('follow_controller',True,type=bool) if self.settings else True
        self.reading=False
        root=QWidget(); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(16,12,16,10); outer.setSpacing(10)
        top=QHBoxLayout(); title=QLabel('XL View'); title.setStyleSheet('font-size:21px;font-weight:600;')
        top.addWidget(title); top.addSpacing(14)
        self.devices=QComboBox(); self.devices.setMinimumWidth(160); self.devices.setAccessibleName('MIDI controller')
        self.connect_button=QPushButton('Connect'); self.scan=QPushButton('Scan')
        top.addStretch()
        self.settings_button=IconButton('settings','Settings'); top.addWidget(self.settings_button); self.settings_button.clicked.connect(self.open_settings)
        self.on_top=IconButton('pin','Always on top',checkable=True); top.addWidget(self.on_top); outer.addLayout(top)
        self.status=StatusText(); self.status.setText('Select a connected controller.'); self.status.setObjectName('status')
        self.init_tools(outer,auto)
        self.undo_button=QPushButton('Undo edit');self.undo_button.clicked.connect(self.undo_edit)
        self.undo_button.setToolTip('Undo the last local edit. This does not undo a write already sent to the controller.')
        self.changes_button.setToolTip('Review draft changes compared with the last controller readback.')
        top.insertWidget(top.count()-2,self.undo_button);top.insertWidget(top.count()-2,self.changes_button)
        body=QHBoxLayout(); self.body=body; body.setSpacing(16); outer.addLayout(body,1)
        sidebar=QFrame(); sidebar.setObjectName('left'); sidebar.setFixedWidth(174); left=QVBoxLayout(sidebar); left.setContentsMargins(0,8,0,0); left.setSpacing(12)
        display=QFrame();self.mode_display=display;display.setObjectName('display')
        display.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
        dl=QVBoxLayout(display);dl.setContentsMargins(12,10,12,10);dl.setSpacing(3)
        self.slot_label=QLabel('NO DATA'); self.slot_label.setObjectName('muted')
        self.mode_name=EditableName(); self.mode_name.committed.connect(self.rename_mode); self.mode_name.editing_changed.connect(self.update_actions)
        dl.addWidget(self.slot_label); dl.addWidget(self.mode_name)
        dl.addSpacing(6)
        self.last_title=DisplayControlName('Move a control'); self.last_title.setStyleSheet('font-weight:600;')
        self.last_title.setTextFormat(Qt.TextFormat.PlainText); self.last_title.setWordWrap(True)
        self.last_title.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        self.last_meta=QLabel();self.last_meta.setObjectName('muted');self.last_meta.setStyleSheet('font-size:12px;')
        self.last_meta.setTextFormat(Qt.TextFormat.PlainText);self.last_meta.hide()
        self.last_detail=QLabel('—'); self.last_detail.setStyleSheet('font-size:28px; font-weight:600;')
        self.last_detail.setFixedHeight(34)
        dl.addWidget(self.last_title);dl.addWidget(self.last_meta);dl.addWidget(self.last_detail);left.addWidget(display)
        self.resume=QPushButton('Resume following'); self.resume.clicked.connect(self.resume_following); left.addWidget(self.resume)
        self.reload=QPushButton('Read again'); left.addWidget(self.reload)
        self.source=QLabel('Names and assignments\nfrom controller memory.'); self.source.setWordWrap(True); self.source.setObjectName('muted'); left.addWidget(self.source)
        self.save_button=QPushButton('Save preset')
        self.library_button=QPushButton('Preset library')
        for w in (self.save_button,self.library_button):left.addWidget(w)
        self.save_button.clicked.connect(self.save_current)
        self.library_button.clicked.connect(self.open_library)
        left.addStretch()
        sidebar_scroll=QScrollArea(); sidebar_scroll.setWidgetResizable(True); sidebar_scroll.setFixedWidth(194)
        sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame); sidebar_scroll.setWidget(sidebar); body.addWidget(sidebar_scroll)
        panel=QWidget(); self.controller_panel=panel; grid=QGridLayout(panel); grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(7); grid.setVerticalSpacing(5)
        self.tiles={}
        for cid in range(16,64):
            tile=ControlTile(cid); self.tiles[cid]=tile; tile.selected.connect(self.tile_clicked)
            tile.apply_label_style(self.label_style)
            i=cid-16; row=i//8; grid.addWidget(tile,row,i%8); tile.set_control(Control(cid))
        for col in range(8): grid.setColumnStretch(col,1)
        for row,stretch in enumerate((12,12,12,20,9,9)): grid.setRowStretch(row,stretch)
        body.addWidget(panel,1)
        self.editor=Editor(); body.addWidget(self.editor); self.editor.hide()
        self.send_all=self.editor.send_all;self.send_all.clicked.connect(lambda:self.review_and_send(False))
        self.editor.changed.connect(self.edit_control); self.editor.closed.connect(self.close_editor)
        self.editor.group_changed.connect(self.edit_group)
        self.editor.copy.clicked.connect(lambda:self.copy_controls())
        self.editor.paste.clicked.connect(self.paste_copied)
        self.editor.send_one.connect(lambda:self.review_and_send(True))
        self.bank=SlotBank(); self.bank.chosen.connect(self.manual_slot)
        self.bank_status=QLabel(); self.bank_status.setObjectName('muted'); outer.addWidget(self.bank_status)
        outer.addWidget(self.bank)
        line=QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setStyleSheet('color:#505b67;'); outer.addWidget(line)
        footer_bar=QWidget();footer_bar.setFixedHeight(44);bottom=QHBoxLayout(footer_bar);bottom.setContentsMargins(0,0,0,0);bottom.setSpacing(16)
        messages=QVBoxLayout();messages.setContentsMargins(0,0,0,0);messages.setSpacing(2);messages.addWidget(self.status)
        footer=QLabel('MIDI values: 7-bit 0–127 · 14-bit 0–16383 · notes: velocity / 0 off · — unknown');footer.setObjectName('muted')
        footer.setToolTip('7-bit: 0–127. 14-bit: 0–16383. Notes: velocity; 0 = off. Relative CC: raw message, not absolute position.')
        messages.addWidget(footer);bottom.addLayout(messages,1)
        self.midi_status=MidiStatusButton();bottom.addWidget(self.midi_status);outer.addWidget(footer_bar)
        self.connection_popup=QFrame(self,Qt.WindowType.Popup);self.connection_popup.setObjectName('display');self.connection_popup.setFixedWidth(430)
        popup=QVBoxLayout(self.connection_popup);popup.setContentsMargins(16,16,16,16);popup.setSpacing(12)
        heading=QHBoxLayout();label=QLabel('MIDI connection');label.setStyleSheet('font-size:16px;font-weight:600;');heading.addWidget(label);heading.addStretch()
        close=IconButton('close','Close MIDI connection');close.clicked.connect(self.connection_popup.hide);heading.addWidget(close);popup.addLayout(heading)
        popup.addWidget(self.devices);actions=QHBoxLayout()
        for w in (self.connect_button,self.scan):actions.addWidget(w)
        diagnostics=QPushButton('Diagnostics');diagnostics.clicked.connect(lambda:(self.connection_popup.hide(),self.open_diagnostics()));actions.addWidget(diagnostics);popup.addLayout(actions)
        self.midi_status.clicked.connect(self.open_connection_popup)
        self.devices.currentTextChanged.connect(lambda:self.midi_status.set_state(self.connected,bool(self.worker) and not self.connected,self.devices.currentText()))
        self.connect_button.clicked.connect(self.toggle_connection); self.scan.clicked.connect(self.scan_devices)
        self.reload.clicked.connect(self.refresh_mode)
        self.on_top.toggled.connect(self.set_on_top)
        self.timer=QTimer(self); self.timer.timeout.connect(lambda:[t.cool() for t in self.tiles.values()]); self.timer.start(100)
        self.scan_devices(); self.update_actions()
        if self.settings:
            geometry=self.settings.value('geometry')
            if geometry: self.restoreGeometry(geometry)
            self.on_top.setChecked(self.settings.value('on_top',False,type=bool))
        self.fit_label_layout()
        if auto and self.devices.count(): QTimer.singleShot(150,self.toggle_connection)

    def scan_devices(self):
        if self.worker: return
        self.devices.clear()
        try:
            self.devices.addItems(Device.discover())
            if not self.devices.count(): self.status.setText('No XL3 found. Connect USB and click Scan.')
        except Exception as ex: self.status.setText(str(ex))
        self.update_actions()
    def open_connection_popup(self):
        if self.connection_popup.isVisible():self.connection_popup.hide();return
        self.connection_popup.adjustSize()
        point=self.midi_status.mapToGlobal(QPoint(self.midi_status.width()-self.connection_popup.width(),-self.connection_popup.height()-8))
        screen=self.screen().availableGeometry()
        point.setX(max(screen.left(),min(point.x(),screen.right()-self.connection_popup.width()+1)))
        point.setY(max(screen.top(),min(point.y(),screen.bottom()-self.connection_popup.height()+1)))
        self.connection_popup.move(point);self.connection_popup.show();self.devices.setFocus()
    def update_actions(self):
        self.midi_status.set_state(self.connected,bool(self.worker) and not self.connected,self.devices.currentText())
        self.connect_button.setText('Disconnect' if self.worker else 'Connect')
        self.connect_button.setEnabled(bool(self.worker or self.devices.count()))
        self.scan.setEnabled(not bool(self.worker)); self.devices.setEnabled(not bool(self.worker))
        self.reload.setEnabled(self.connected and self.selected_slot is not None and not self.busy)
        self.connect_button.setEnabled(not self.busy and bool(self.worker or self.devices.count()))
        self.library_button.setEnabled(not self.busy)
        self.settings_button.setEnabled(not self.busy)
        for w in (self.save_button,self.mode_name):w.setEnabled(self.current is not None and not self.busy)
        self.send_all.setEnabled(self.current is not None and self.selected_slot is not None and self.connected and not self.busy and not self.reading)
        self.undo_button.setEnabled(bool(self.history) and not self.busy)
        self.editor.setEnabled(not self.busy)
        self.editor.send.setEnabled(self.current is not None and self.selected_id is not None and self.selected_slot is not None and self.connected and not self.busy and not self.reading)
        target=f'slot {self.selected_slot:02d}' if self.selected_slot else 'selected slot'
        self.editor.send.setText(f'Send control to {target}')
        self.send_all.setText(f'Send mode to {target}' if self.selected_slot else 'Send entire mode')
        paused=self.follow_enabled and self.has_pending()
        self.resume.setVisible(bool(self.follow_enabled and (paused or self.selected_slot!=self.active_slot) and self.active_slot and self.active_slot<=15 and self.connected))
        self.resume.setEnabled(not self.busy)
        self.bank.refresh(self.selected_slot,self.active_slot,self.slot_names,self.slot_errors,self.connected,self.busy)
        self.bank_status.setText(('Controller slots' if self.connected else 'Controller slots · offline · last read names')+'  |  Outline: editing destination · LIVE: active on controller'+('  |  Follow paused: unsent changes' if paused else ''))
        self.setWindowTitle(('• ' if self.dirty else '')+'XL View — Launch Control XL 3')
        if self.recovery:
            for w in (self.mode_name,self.editor,self.library_button,self.save_button,self.send_all,self.undo_button,self.reload):w.setEnabled(False)
            self.bank.setEnabled(False)
        else:self.bank.setEnabled(True)
        self.update_tools()
    def toggle_connection(self):
        if self.busy:return
        if self.worker:
            self.want_connection=False; self.log_event('Disconnected by user. Automatic reconnect paused.')
            self.worker.stop();stopped=self.worker.wait(5000)
            if stopped:self.worker=None
            self.connected=False
            self.token+=1; self.feedback_read_token=None; self.reading=False
            self.feedback_mode=None
            self.live=False; self.clear_values(); self.status.setText('Disconnected. Showing the last assignment readback.'); self.source.setText('Last readback · offline')
            if not stopped:self.status.setText('Disconnecting… waiting for MIDI ports to close.')
            self.update_actions(); return
        if not self.devices.count(): return
        self.want_connection=True; self.reconnect_name=self.devices.currentText()
        keep=self.current is not None and (self.has_pending() or not self.follow_enabled)
        self.active_slot=None; self.token+=1
        if not keep:self.clear_mode()
        if not keep:
            self.mode_name.setText('Connecting…'); self.source.setText('Waiting for the active mode.'); self.slot_label.setText('CONTROLLER')
        self.worker=Device(self.devices.currentText())
        worker=self.worker
        # Ignore queued events from a previous port session after reconnecting.
        def bind(signal,handler):
            signal.connect(lambda *args:handler(*args) if self.worker is worker else None)
        for signal,handler in ((worker.status,self.connection_status),(worker.surface,self.surface_changed),
            (worker.mode,self.mode_received),(worker.midi,self.midi_received),(worker.failed,self.read_failed),
            (worker.written,self.write_received),(worker.slot_name,self.slot_name_received),(worker.finished,self.worker_finished)):
            bind(signal,handler)
        self.worker.start(); self.status.setText('Connecting to controller…'); self.update_actions()
    def worker_finished(self):
        if self.worker and not self.worker.isRunning():
            self.token+=1; self.busy=False; self.reading=False
            self.retry_at=time.monotonic()+self.retry_delay
            self.feedback_mode=None
            self.feedback_read_token=None
            self.worker=None; self.connected=False; self.live=False; self.clear_values(); self.update_actions()
    def connection_status(self,text,connected):
        self.log_event(text)
        if connected:self.retry_delay=2
        if not connected:
            self.token+=1; self.feedback_read_token=None
            self.busy=False; self.reading=False; self.feedback_mode=None; self.live=False; self.clear_values()
        self.connected=connected; self.status.setText(text); self.update_actions()
        if connected and 'manually' in text:
            self.source.setText('Active slot unavailable. Choose a slot below to read it.')
    def read_failed(self,text,token=None):
        if token is not None and token!=self.token: return
        was_writing=self.busy
        self.feedback_read_token=None
        self.log_event('Operation failed: '+text)
        self.feedback_mode=None
        self.busy=False; self.reading=False; self.live=False; self.status.setText(text); self.source.setText('Operation failed · draft preserved'); self.clear_values(); self.update_actions()
        # A failed/partial write makes the old map untrustworthy. Recover values
        # with a fresh read only; never repeat a write or replace the user's draft.
        if was_writing:self.request_feedback()
    def clear_values(self):
        self.values.reset()
        self.last_meta.clear();self.last_meta.hide()
        self.last_title.setText('Move a control')
        self.last_detail.setText('—')
        self.last_title.setToolTip('Move or select a control to see its name and last received MIDI value.')
        self.last_detail.setToolTip('No value received.')
        self.last_detail.setAccessibleName('No value received')
        for tile in self.tiles.values():
            tile.visual.value=None; tile.visual.active=False
            tile.value.setText('off' if tile.control.kind=='disabled' else '—'); tile.visual.update()
        if self.current is not None and self.selected_id is not None:self.show_details(self.selected_id)
    def clear_mode(self):
        self.feedback_read_token=None
        self.feedback_mode=None
        self.current=None; self.live=False; self.clear_values()
        self.baseline=None; self.history=[]; self.dirty=False; self.close_editor()
        for cid,tile in self.tiles.items(): tile.set_control(Control(cid))
    def has_pending(self):
        return self.current is not None and (not self.mode_name.field.isHidden() or self.baseline is None or not same_mode(self.current,self.baseline))
    def slot_name_received(self,slot,name,error=''):
        if error:self.slot_errors[slot]=error
        else:self.slot_names[slot]=name; self.slot_errors.pop(slot,None)
        self.update_actions()
    def surface_changed(self,name,slot):
        changed=(self.active_name,self.active_slot)!=(name,slot)
        if changed and self.feedback_read_token is not None:
            self.token+=1;self.feedback_read_token=None
        self.active_name=name; self.active_slot=slot
        self.live=bool(self.connected and not self.busy and self.feedback_mode and self.feedback_mode.slot==slot)
        if changed:self.clear_values()
        if self.follow_enabled and not self.has_pending() and not self.busy and not self.reviewing and not getattr(self,'library_open',False):
            if slot and 1<=slot<=15:
                if self.selected_slot!=slot or (not self.reading and (self.current is None or self.feedback_mode is None)):
                    self.selected_slot=slot; self.refresh_mode(guard=False)
            else:
                self.reading=False; self.token+=1; self.clear_mode(); self.selected_slot=None
                self.mode_name.setText('Default' if slot==16 else name)
                self.slot_label.setText('MODE 16 · FIXED' if slot==16 else 'ACTIVE MODE')
                self.source.setText('Read-only factory mode. Assignments are not displayed. Choose Custom Mode 1–15 to edit.' if slot==16 else 'Choose Custom Mode 1–15 to edit its assignments.')
                if slot==16:
                    self.last_title.setText('Read-only mode')
                    for cid,tile in self.tiles.items():
                        tile.set_control(Control(cid,kind='unknown'))
                        tile.name.setText('—');tile.setToolTip('Factory assignments are not displayed.')
        self.request_feedback()
        self.update_actions()
    def manual_slot(self,slot):
        if self.busy or not 1<=slot<=15:return
        if self.current is not None and self.selected_slot is None:
            self.selected_slot=slot; self.baseline=deepcopy(self.hardware_modes.get(slot))
            self.slot_label.setText(f'SLOT {slot:02d}');self.update_actions();return
        if slot==self.selected_slot and self.current is not None:self.update_actions();return
        if not self.guard_unsaved(pending=True):self.update_actions();return
        self.selected_slot=slot
        if self.connected:self.refresh_mode(guard=False)
        else:
            self.token+=1; self.clear_mode(); self.slot_label.setText(f'SLOT {slot:02d}')
            self.mode_name.setText(self.slot_names.get(slot,'Not read'))
            self.source.setText('Offline. Load a preset from the library for this slot.')
        self.update_actions()
    def follow_changed(self,checked):
        self.follow_enabled=checked
        if self.settings:self.settings.setValue('follow_controller',checked)
        if checked:self.surface_changed(self.active_name,self.active_slot)
        self.update_actions()
    def resume_following(self):
        if not self.active_slot or not 1<=self.active_slot<=15 or self.busy:return
        if not self.guard_unsaved(pending=True):return
        self.selected_slot=self.active_slot; self.refresh_mode(guard=False)
    def open_settings(self):
        from .settings_dialog import SettingsDialog
        SettingsDialog(self).exec()
    def set_label_style(self,style):
        self.label_style=style
        style.save(self.settings)
        for tile in self.tiles.values():tile.apply_label_style(style)
        self.fit_label_layout()
    def fit_label_layout(self):
        if getattr(self,'_fitting_labels',False):return
        self._fitting_labels=True
        try:
            grid=self.controller_panel.layout();grid.invalidate()
            self.controller_panel.setMinimumHeight(grid.minimumSize().height())
            self.body.invalidate();layout=self.centralWidget().layout();layout.invalidate()
            self.setMinimumHeight(max(900,layout.minimumSize().height()));layout.activate()
        finally:self._fitting_labels=False
    def refresh_mode(self,checked=False,guard=True):
        if not self.worker or not self.connected or self.busy:return
        if guard and not self.guard_unsaved(pending=True):return
        slot=self.selected_slot
        if not slot or not 1<=slot<=15:
            self.status.setText('Select a controller slot below.');return
        self.token+=1; self.reading=True; self.clear_mode()
        self.slot_label.setText(f'SLOT {slot:02d}'); self.mode_name.setText('Reading…')
        self.source.setText('Reading assignments…');self.update_actions();self.worker.request(slot,self.token)
    def mode_received(self,mode,token):
        if token!=self.token: return
        if token==self.feedback_read_token:
            self.feedback_read_token=None
            if not self.current or mode.slot!=self.selected_slot:return
            self.feedback_mode=deepcopy(mode);self.hardware_modes[mode.slot]=deepcopy(mode)
            self.live=bool(self.connected and not self.busy and mode.slot==self.active_slot)
            self.clear_values();self.update_actions()
            self.log_event(f'Live feedback map refreshed for slot {mode.slot}; draft preserved.')
            return
        self.reading=False; self.display_mode(mode)
        self.feedback_mode=deepcopy(mode)
        self.live=bool(self.connected and self.active_slot and mode.slot==self.active_slot)
        self.source.setText('Following the active mode' if self.live and self.follow_enabled else 'Live values · selected slot is active' if self.live else 'Slot preview · hardware unchanged')
        self.status.setText(f'Read {mode.name}. MIDI connection active.'); self.update_actions()
    def request_feedback(self):
        """Refresh a verified hardware map without loading it over a pending draft."""
        if (not self.worker or not self.connected or not self.current or self.busy or self.reading
            or self.feedback_mode is not None or self.feedback_read_token is not None
            or self.selected_slot!=self.active_slot or self.selected_slot not in range(1,16)):
            return
        self.token+=1;self.feedback_read_token=self.token
        self.log_event(f'Reading feedback map for slot {self.selected_slot}; no write requested.')
        self.worker.request(self.selected_slot,self.token)
    def feedback_matches(self,cid):
        if self.current is None:return False
        if self.feedback_mode is None:return True
        signature=feedback_signature(self.current.controls[cid])
        return signature is not None and signature==feedback_signature(self.feedback_mode.controls[cid])
    def refresh_feedback_values(self):
        """Keep unchanged values through draft edits; hide only incompatible bindings."""
        if not self.live:
            self.clear_values();return
        for cid,tile in self.tiles.items():
            if not self.feedback_matches(cid):self.values.values.pop(cid,None)
            value=self.values.values.get(cid)
            if value is None:
                tile.visual.value=None;tile.visual.active=False
                tile.value.setText('off' if tile.control.kind=='disabled' else '—');tile.visual.update()
            else:
                # Reapply after set_control without suggesting a new MIDI event.
                active,expires=tile.visual.active,tile.expires
                tile.set_value(value);tile.visual.active=active;tile.expires=expires
        if self.selected_id is not None:self.show_details(self.selected_id)
    def display_mode(self,mode,preserve_editor=False):
        self.draft_discarded=False
        self.reading=False
        self.feedback_mode=None
        self.feedback_read_token=None;self.live=False
        keep_editor=bool(preserve_editor and self.editor_expansion and self.selected_id is not None)
        scroll_position=self.editor.scroll.verticalScrollBar().value() if keep_editor else 0
        if not keep_editor:self.close_editor()
        self.current=mode; self.clear_values(); self.mode_name.setText(mode.name)
        self.baseline=deepcopy(mode); self.dirty=False; self.history=[]; self.loaded=True
        self.slot_label.setText(f'SLOT {mode.slot or self.selected_slot:02d}' if mode.slot or self.selected_slot else 'PRESET · SELECT A SLOT')
        # A newly read hardware slot is the editing destination. Do not leave the
        # previous mode's target selected (which could silently overwrite it).
        if mode.slot is not None and 1<=mode.slot<=15:
            self.selected_slot=mode.slot
            self.hardware_modes[mode.slot]=deepcopy(mode); self.slot_names[mode.slot]=mode.name; self.slot_errors.pop(mode.slot,None)
        for cid,tile in self.tiles.items(): tile.set_control(mode.controls.get(cid,Control(cid)))
        if keep_editor:
            self.refresh_selection_editor()
            self.editor.scroll.verticalScrollBar().setValue(scroll_position)
        self.update_actions()
        self.schedule_draft()
    def midi_received(self,msg):
        self.observe_midi(msg)
        if not self.live or self.current is None: return
        # After a write, decode the verified hardware map, not unsent draft assignments.
        ids=self.values.feed(self.feedback_mode or self.current,msg)
        if self.feedback_mode:
            ids=[cid for cid in ids if self.feedback_matches(cid)]
            for cid in list(self.values.values):
                if not self.feedback_matches(cid):
                    del self.values.values[cid]
        for cid in ids: self.tiles[cid].set_value(self.values.values[cid])
        if ids:
            self.show_details(ids[0])
            if len(ids)>1: self.last_detail.setToolTip(self.last_detail.toolTip()+f'\nShared message: {len(ids)} controls.')
    def show_control(self,cid):
        if not self.current or self.busy or self.recovery:return
        self.selection={cid}
        self.selection_anchor=cid
        self.selected_id=cid
        for key,tile in self.tiles.items():
            tile.setProperty('selected',key==cid); tile.style().unpolish(tile); tile.style().polish(tile)
        self.editor.load(self.current.controls[cid],self.tiles[cid].position())
        if not self.editor_expansion:
            width,height=self.width(),self.height()
            if self.isMaximized():
                # Leave maximized mode so the inspector can add width without squeezing controls.
                self.showNormal(); self.resize(width,height)
            self.editor_expansion=self.editor.width()+self.body.spacing()
            self.setMinimumWidth(940+self.editor_expansion)
            self.editor.show(); self.resize(width+self.editor_expansion,height)
            self.centralWidget().layout().activate()
        self.show_details(cid); self.update_actions(); self.fit_label_layout()
    def show_details(self,cid):
        c=self.current.controls[cid]; value=self.values.values.get(cid)
        name=c.label or ('Unassigned' if c.kind=='disabled' else c.assignment)
        self.last_title.setText(name)
        self.last_title.setToolTip(name+'\n'+c.assignment)
        channel=f'Ch {c.channel}' if c.channel else 'Global'
        if c.kind in ('CC','CC14','NRPN','NRPN14'):
            kind='NRPN' if c.kind.startswith('NRPN') else 'CC'
            number=f'{c.number}/{c.number+32}' if c.kind=='CC14' and c.number is not None else str(c.number)
            bits='14-bit' if c.kind in ('CC14','NRPN14') else '7-bit'
            meta=f'{kind} {number} · {channel}\n'+('Relative · raw' if c.relative else f'Absolute · {bits}')
        elif c.kind=='Note':meta=f'Note {c.number} · {channel}\nVelocity / Off'
        elif c.kind=='PC':meta=f'PC {c.low}–{c.high} · {channel}\nProgram number'
        elif c.kind=='Key':meta=f'Keyboard shortcut\nKey code {c.keycode}'
        elif c.kind=='disabled':meta='Unassigned'
        else:meta='Unknown message\nImported definition'
        self.last_meta.setText(meta);self.last_meta.setToolTip(c.assignment);self.last_meta.show()
        shown='—' if value is None else f'rel {value}' if c.relative else str(value)
        self.last_detail.setText(shown)
        explanation='No value received.' if value is None else f'Last received MIDI value: {value}.'
        if c.relative:explanation+=' Relative CC: raw message, not an absolute position.'
        self.last_detail.setToolTip(explanation)
        self.last_detail.setAccessibleName(name+'. '+explanation)
    def open_file(self,parent=None,on_error=None):
        if on_error:on_error('')
        if not self.guard_unsaved(pending=True):return False
        path,_=QFileDialog.getOpenFileName(parent or self,'Import mode from file','','Launch Control XL 3 mode (*.syx)')
        if not path:return False
        loaded=self.load_file(path)
        if not loaded and on_error:on_error(self.status.text())
        return loaded
    def load_file(self,path):
        try:
            data=Path(path).read_bytes()
            mode=parse_mode(data)
            self.detach(); mode.slot=None; self.display_mode(mode)
            self.baseline=deepcopy(self.hardware_modes.get(self.selected_slot)); self.update_actions()
            self.source.setText('File preview · hardware unchanged'); self.status.setText(f'Opened {Path(path).name}. Nothing sent to the controller.')
            self.request_feedback()
            return True
        except Exception as ex:self.status.setText(f'Could not open file: {ex}');return False
    def set_on_top(self,value):
        geometry=self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,value); self.show(); self.setGeometry(geometry)
        self.on_top.setToolTip('Always on top: on' if value else 'Always on top: off')
    def closeEvent(self,event):
        if self.busy:
            self.status.setText('Writing to XL. Please wait for confirmation.'); event.ignore(); return
        if not self.guard_unsaved():event.ignore(); return
        self.flush_draft(); self.want_connection=False
        if self.worker:
            self.worker.stop()
            if not self.worker.wait(5000):
                self.status.setText('Waiting for MIDI ports to close…'); event.ignore(); return
        self.close_editor()
        if self.settings:
            self.settings.setValue('geometry',self.saveGeometry()); self.settings.setValue('on_top',self.on_top.isChecked())
        event.accept()

    def close_editor(self):
        if not hasattr(self,'editor'):return
        self.selection=set()
        self.selection_anchor=None
        extra=self.editor_expansion
        self.editor_expansion=0; self.editor.hide(); self.selected_id=None; self.setMinimumSize(940,900)
        if extra:self.resize(max(940,self.width()-extra),self.height())
        self.fit_label_layout()
        for tile in self.tiles.values():
            tile.setProperty('selected',False); tile.style().unpolish(tile); tile.style().polish(tile)
        self.update_tools()
    def detach(self):
        self.token+=1; self.reading=False
        self.feedback_read_token=None
        self.live=False; self.feedback_mode=None
        # Keep the chosen inspector intact while clearing values from the hardware map.
        selected=self.selected_id; self.clear_values(); self.selected_id=selected
    def remember(self):
        self.history.append(deepcopy(self.current)); self.history=self.history[-100:]
    def edited(self):
        self.draft_discarded=False
        self.dirty=True
        # Editing pauses automatic navigation, not receiving MIDI. The verified
        # hardware map stays independent from the draft, including after Paste/Undo.
        self.live=bool(self.connected and not self.busy and self.feedback_mode and self.feedback_mode.slot==self.active_slot)
        self.refresh_feedback_values();self.source.setText('Draft edited · not yet sent')
        self.mode_name.setText(self.current.name); self.update_actions()
        self.schedule_draft()
    def edit_control(self,c):
        if not self.current or self.busy:return
        if control_signature(c)==control_signature(self.current.controls[c.id]):return
        self.remember(); self.current.controls[c.id]=c; self.tiles[c.id].set_control(c); self.edited(); self.show_details(c.id)
    def rename_mode(self,name):
        if not self.current or name==self.current.name:return
        self.remember(); self.current.name=name; self.edited()
    def undo_edit(self):
        if not self.history:return
        cid=self.selected_id;selection=set(self.selection);anchor=self.selection_anchor; self.current=self.history.pop()
        for i,t in self.tiles.items():t.set_control(self.current.controls[i])
        self.edited()
        if cid is not None:
            self.show_control(cid);self.selection=selection;self.selection_anchor=anchor
            self.refresh_selection_editor();self.update_tools()
    def guard_unsaved(self,pending=False):
        if not self.dirty and not (pending and self.has_pending()):return True
        answer=QMessageBox.question(self,'Keep your draft?','This draft has unsaved or unsent changes. Save a library copy before leaving it? Saving does not send to the controller.',
            QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        if answer==QMessageBox.StandardButton.Save:return self.save_current()
        if answer==QMessageBox.StandardButton.Discard:
            self.dirty=False; self.draft_discarded=True; self.autosave.stop()
            if self.draft_store and not self.recovery:
                try:self.draft_store.clear()
                except OSError as ex:self.status.setText(f'Could not clear draft recovery: {ex}')
            return True
        return False
    def create_mode(self):
        if not self.guard_unsaved(pending=True):return False
        self.detach(); self.display_mode(new_mode()); self.baseline=deepcopy(self.hardware_modes.get(self.selected_slot)); self.dirty=True
        self.source.setText('New mode · all controls disabled'); self.status.setText('Select a control and assign a message.'); self.update_actions(); self.schedule_draft(); return True
    def save_current(self):
        if not self.current:return False
        try:
            path=save_preset(self.current,self.library_root); self.dirty=False; self.update_actions()
            self.status.setText(f'Preset saved: {path.name}'); return True
        except Exception as ex:self.status.setText(f'Could not save preset: {ex}'); return False
    def export_file(self,mode=None,parent=None,on_status=None):
        self.status.setToolTip('')
        if on_status:on_status('')
        mode=deepcopy(mode if mode is not None else self.current)
        if mode is None:return False
        path,_=QFileDialog.getSaveFileName(parent or self,'Export current mode',mode.name+'.syx','Launch Control XL 3 mode (*.syx)')
        if not path:return False
        try:
            atomic_write(Path(path),encode_mode(mode));message=f'Exported {Path(path).name}. Nothing sent to the controller.'
            self.status.setText(message)
            if on_status:on_status(message)
            return True
        except Exception as ex:
            message='Could not export the file. Choose another folder or filename and try again.'
            self.status.setText(message);self.status.setToolTip(str(ex))
            if on_status:on_status(message)
            return False
    def open_library(self):
        from .preset_library import PresetLibraryDialog
        PresetLibraryDialog(self).exec()
    def send_mode(self,one=False):
        if not self.current or not self.worker or not self.connected or self.busy:return
        cid=self.selected_id if one else None
        if one and cid is None:return
        try:encode_mode(self.current)
        except ValueError as ex:self.status.setText(str(ex)); return
        slot=self.selected_slot
        if slot is None:return
        # Preserve draft first; automatic version is available even after a cable failure.
        if not self.save_current():return
        baseline=self.baseline if self.baseline and self.baseline.slot==slot else None
        self.detach(); self.busy=True; self.update_actions()
        self.status.setText(f'Writing slot {slot}: reading, backing up, sending and verifying…')
        self.log_event(f'Write requested: slot {slot}, '+(f'control {cid}' if cid is not None else 'entire mode'))
        self.worker.write(slot,self.token,self.current,cid,baseline)
    def write_received(self,mode,token,backup,cid):
        if token!=self.token:return
        self.busy=False
        self.hardware_modes[mode.slot]=deepcopy(mode); self.slot_names[mode.slot]=mode.name
        if cid is None:
            self.display_mode(mode,preserve_editor=True)
        else:
            # Only the selected control was sent. Preserve other edits in the draft.
            self.baseline=deepcopy(mode)
            self.current.controls[cid]=deepcopy(mode.controls[cid]); self.tiles[cid].set_control(mode.controls[cid])
            self.show_control(cid)
        remaining=sum(control_signature(self.current.controls[i])!=control_signature(mode.controls[i]) for i in range(16,64))
        name_pending=self.current.name!=mode.name
        pending=f' Unsent draft changes remain: {remaining} controls'+(' and the mode name.' if name_pending else '.') if remaining or name_pending else ''
        # Following mode changes and receiving knob values are independent. Keep the
        # draft/inspector in place, but resume values for the verified active slot.
        self.feedback_mode=deepcopy(mode)
        self.live=bool(self.connected and self.active_slot and mode.slot==self.active_slot)
        self.clear_values()
        self.source.setText(f'Saved {"control" if cid is not None else "mode"} in slot {mode.slot:02d}.'+pending)
        self.status.setText(f'XL confirmed writing {"control" if cid is not None else "entire mode"} in slot {mode.slot}.'+pending+' A backup of the previous slot is in the library.')
        self.log_event(f'Write verified: slot {mode.slot}'); self.schedule_draft()
        self.update_actions()
        # Completing Send is not a navigation action. Keep an open inspector on
        # its destination even if the controller changed slots during the write.
        if self.follow_enabled and not self.has_pending() and self.worker and self.connected and not self.editor_expansion:
            self.surface_changed(self.active_name,self.active_slot)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'bank'):
            self.bank.arrange(self.width()-self.editor_expansion)
            self.fit_label_layout()
