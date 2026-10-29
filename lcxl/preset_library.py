"""Versioned preset browser. Controller imports are read-only, session-scoped jobs."""
from copy import deepcopy
from datetime import datetime
from itertools import count
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from .library import grouped_presets,store_preset,trim_versions
from .protocol import parse_mode

_jobs=count(1)

def saved_at(path,seconds=False):
    try:return datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S' if seconds else '%Y-%m-%d %H:%M')
    except OSError:return 'File unavailable'

class PresetLibraryDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;window.library_open=True;self.import_worker=None;self.job=None;self.next_slot=None
        self.created=0;self.unchanged=0;self.failures=[];self.groups=[]
        self.setWindowTitle('Preset library');self.resize(780,660);self.setMinimumSize(700,600)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,18,18,18);layout.setSpacing(10)
        self.hint=QLabel('One preset per name · five latest versions. Older versions are archived.');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        row=QHBoxLayout();self.import_xl=QPushButton('Import from XL');self.import_file=QPushButton('Import mode from file…');self.export=QPushButton('Export current mode…')
        for b in (self.import_xl,self.import_file,self.export):row.addWidget(b)
        layout.addLayout(row)
        self.export_snapshot=deepcopy(window.current);self.export.setEnabled(self.export_snapshot is not None)
        hint=QLabel('XL import reads all 15 Custom Modes into this library; nothing is written to the controller. File import opens a mode for editing.');hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint)
        hint=QLabel(f'Export: {self.export_snapshot.name} — open mode including local edits.' if self.export_snapshot else 'Open a mode to export its assignments.');hint.setTextFormat(Qt.TextFormat.PlainText);hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint)
        row=QHBoxLayout();self.category=QComboBox();self.category.addItem('My presets','library');self.category.addItem('Slot backups before writing','backups');self.search=QLineEdit();self.search.setPlaceholderText('Search presets…');self.search.setAccessibleName('Search presets');row.addWidget(self.category);row.addWidget(self.search,1);layout.addLayout(row)
        self.table=QTableWidget(0,4);self.table.setAccessibleName('Preset library');self.table.setHorizontalHeaderLabels(['#','Preset','Versions','Last saved']);self.table.verticalHeader().hide();self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet('QTableWidget {background:#15191d;border:1px solid #505b67;selection-background-color:#3a454f;selection-color:#ffffff;} QTableWidget::item {padding:6px;border-bottom:1px solid #3a424b;} QHeaderView::section {background:#292f35;color:#b3bec8;padding:7px;border:0;border-bottom:1px solid #505b67;} QTableWidget:focus {border-color:#95d4ff;}')
        header=self.table.horizontalHeader();header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for col,width in ((0,42),(2,80),(3,152)):header.setSectionResizeMode(col,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(col,width)
        self.table.verticalHeader().setDefaultSectionSize(43);layout.addWidget(self.table,1)
        self.empty=QLabel();self.empty.setWordWrap(True);self.empty.setObjectName('muted');layout.addWidget(self.empty)
        row=QHBoxLayout();label=QLabel('Version');self.versions=QComboBox();self.versions.setAccessibleName('Preset version');label.setBuddy(self.versions);row.addWidget(label);row.addWidget(self.versions,1);layout.addLayout(row)
        self.notice=QLabel();self.notice.setTextFormat(Qt.TextFormat.PlainText);self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.target=QLabel();self.target.setTextFormat(Qt.TextFormat.PlainText);self.target.setWordWrap(True);layout.addWidget(self.target)
        hint=QLabel('Send loads this version into the editor and replaces the active slot. A backup is made before writing.');hint.setWordWrap(True);hint.setObjectName('muted');layout.addWidget(hint)
        row=QHBoxLayout();self.new=QPushButton('New mode');self.load=QPushButton('Load for editing');self.send=QPushButton('Send to active slot');close=QPushButton('Close')
        for b in (self.new,self.load,self.send,close):row.addWidget(b)
        layout.addLayout(row)
        self.category.currentIndexChanged.connect(self.refresh);self.search.textChanged.connect(self.refresh);self.table.itemSelectionChanged.connect(self.selection_changed);self.versions.currentIndexChanged.connect(self.update_actions)
        self.load.clicked.connect(self.load_selected);self.table.itemDoubleClicked.connect(self.load_selected);self.send.clicked.connect(self.send_selected);self.import_xl.clicked.connect(self.toggle_import)
        self.import_file.clicked.connect(self.open_file);self.export.clicked.connect(lambda:window.export_file(self.export_snapshot,self,self.feedback));self.new.clicked.connect(self.new_mode);close.clicked.connect(self.reject)
        try:trim_versions(window.library_root)
        except OSError as ex:self.feedback(f'Could not archive older versions: {ex}',True)
        self.refresh();self.timer=QTimer(self);self.timer.timeout.connect(self.update_actions);self.timer.start(200)
        self.finished.connect(self.cleanup)

    def feedback(self,text,error=False):
        self.notice.setText(text);self.notice.setStyleSheet('color:#ffb4a9;' if error or text.startswith('Could') else 'color:#b3bec8;')

    def refresh(self,*args):
        old=self.table.currentRow();name=self.groups[old]['name'] if 0<=old<len(self.groups) else None
        try:self.groups=[g for g in grouped_presets(self.window.library_root,self.category.currentData()) if self.search.text().casefold() in g['name'].casefold()]
        except OSError as ex:self.groups=[];self.feedback(f'Could not read library: {ex}',True)
        self.table.blockSignals(True);self.table.setRowCount(len(self.groups));selected=-1
        for row,g in enumerate(self.groups):
            date=saved_at(g['versions'][0])
            for col,text in enumerate((str(row+1),g['name'],str(len(g['versions'])),date)):
                item=QTableWidgetItem(text);item.setToolTip(g['error'] or str(g['versions'][0]))
                if g['error']:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(row,col,item)
            if not g['error'] and (selected<0 or g['name']==name):selected=row
        if selected>=0:self.table.selectRow(selected)
        self.table.blockSignals(False)
        self.empty.setText('No matching presets. Try another search.' if not self.groups and self.search.text() else 'No presets yet. Import from XL, or create a mode and save it.' if not self.groups else '')
        self.empty.setVisible(not self.groups);self.hint.setText('Slot backups are kept separately; their history is not limited.' if self.category.currentData()=='backups' else 'One preset per name · five latest versions. Older versions are archived.')
        self.selection_changed()

    def selection_changed(self):
        self.versions.clear();row=self.table.currentRow()
        if 0<=row<len(self.groups) and not self.groups[row]['error']:
            for i,path in enumerate(self.groups[row]['versions']):
                self.versions.addItem(('Latest' if i==0 else f'Version {i+1}')+' — '+saved_at(path,True),path)
                self.versions.setItemData(i,str(path),Qt.ItemDataRole.ToolTipRole)
        self.update_actions()

    def update_actions(self,*args):
        w=self.window
        if self.job is not None and (w.worker is not self.import_worker or not w.connected):self.cancel_import('Connection changed. Import stopped; completed presets were kept.')
        importing=self.job is not None;blocked=bool(w.busy or w.reading or w.recovery)
        valid=bool(w.connected and w.worker and w.active_slot in range(1,16));slot=w.active_slot
        if valid:self.target.setText(f'Active slot {slot:02d} · {w.slot_names.get(slot) or "Name not read"} — will be replaced.')
        elif slot==16 and w.connected:self.target.setText('Active mode 16 is fixed and cannot be overwritten. Select a Custom Mode on XL.')
        else:self.target.setText('Connect XL and select a Custom Mode to enable sending to its active slot.')
        self.send.setText(f'Send to active slot {slot:02d}' if valid else 'Send to active slot')
        self.send.setEnabled(valid and not importing and not blocked and self.versions.currentData() is not None)
        self.load.setEnabled(not importing and not blocked and self.versions.currentData() is not None)
        self.new.setEnabled(not importing and not blocked);self.import_file.setEnabled(not importing and not blocked)
        self.import_xl.setText('Cancel import' if importing else 'Import from XL');self.import_xl.setEnabled(importing or bool(w.connected and w.worker and not blocked))

    def open_file(self):
        if self.window.open_file(self,self.feedback):self.accept()

    def new_mode(self):
        if self.window.create_mode():self.accept()

    def load_selected(self,*args):
        path=self.versions.currentData()
        if not self.load.isEnabled() or path is None:return
        if self.window.guard_unsaved(pending=True):
            if self.window.load_file(path):self.accept()
            else:self.feedback(self.window.status.text(),True)

    def send_selected(self):
        self.update_actions()
        if not self.send.isEnabled():return
        w=self.window;slot=w.active_slot;worker=w.worker;path=self.versions.currentData()
        try:mode=parse_mode(path.read_bytes())
        except (ValueError,OSError) as ex:self.feedback(f'Could not load preset: {ex}',True);return
        if not w.guard_unsaved(pending=True):return
        if not w.connected or w.worker is not worker or w.active_slot!=slot:
            self.feedback('Active slot or connection changed. Nothing was sent. Select the destination again.',True);return
        w.detach();w.selected_slot=slot;mode.slot=None;w.display_mode(mode)
        w.baseline=deepcopy(w.hardware_modes.get(slot));w.source.setText('Library preset · not yet sent');w.update_actions()
        w.review_and_send(False,expected_active_slot=slot)
        if w.busy:self.accept()
        else:
            w.request_feedback();self.feedback('Preset loaded into the editor. Nothing was sent. '+w.status.text())

    def toggle_import(self):
        if self.job is not None:self.cancel_import('Import cancelled; completed presets were kept.');return
        self.update_actions()
        if not self.import_xl.isEnabled():return
        self.import_worker=self.window.worker;self.job=next(_jobs);self.next_slot=1;self.created=0;self.unchanged=0;self.failures=[]
        self.import_worker.import_result.connect(self.import_received);self.queue_import();self.update_actions()

    def queue_import(self):
        self.feedback(f'Reading slot {self.next_slot:02d}/15 · {self.created} new versions · {self.unchanged} unchanged')
        self.import_worker.request_import(self.next_slot,self.job)

    def import_received(self,mode,slot,job,error):
        if job!=self.job or slot!=self.next_slot:return
        if not self.window.connected or self.window.worker is not self.import_worker:
            self.cancel_import('Connection changed. Import stopped; completed presets were kept.');return
        try:
            if error or mode is None:raise ValueError(error or 'No mode received.')
            _,created=store_preset(mode,self.window.library_root)
            self.created+=int(created);self.unchanged+=int(not created)
        except (ValueError,OSError) as ex:self.failures.append((slot,str(ex)))
        self.refresh()
        if slot<15:self.next_slot+=1;self.queue_import()
        else:
            message=f'Import finished · {self.created} new versions · {self.unchanged} unchanged.'
            if self.failures:message+=' Failed slots: '+', '.join(str(s) for s,_ in self.failures)+'. Check the connection and retry.'
            failed=bool(self.failures);details='\n'.join(f'Slot {s}: {e}' for s,e in self.failures)
            self.cancel_import(message);self.notice.setToolTip(details)
            if failed:self.feedback(message,True)

    def cancel_import(self,message=''):
        if self.import_worker is not None:
            try:self.import_worker.import_result.disconnect(self.import_received)
            except (RuntimeError,TypeError):pass
        self.job=None;self.next_slot=None;self.import_worker=None
        if message:self.feedback(message)
        self.update_actions()

    def cleanup(self,*args):
        self.timer.stop();self.cancel_import();self.window.library_open=False
        w=self.window
        if self.result()==QDialog.DialogCode.Rejected and w.follow_enabled and w.connected and w.worker and not w.busy and not w.has_pending():
            w.surface_changed(w.active_name,w.active_slot)
