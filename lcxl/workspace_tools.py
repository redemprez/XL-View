"""Window workflows: group editing, recovery, review and connection diagnostics."""
from collections import deque
from copy import deepcopy
from datetime import datetime
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication,QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,
    QAbstractItemView,QPlainTextEdit,QFileDialog)
from .protocol import same_mode,feedback_signature
from .workflows import paste_controls,batch_controls,differences,DraftStore
from .library import data_root


class ChangesDialog(QDialog):
    def __init__(self,window,one=False,sending=False):
        super().__init__(window);self.setWindowTitle('Review changes');self.resize(820,540)
        self.setMinimumSize(620,380);layout=QVBoxLayout(self);layout.setContentsMargins(20,20,20,20);layout.setSpacing(14)
        title=QLabel(('Send one control' if one else 'Send entire mode')+f' · slot {window.selected_slot:02d}' if sending else 'Pending changes')
        title.setStyleSheet('font-size:20px;font-weight:600;');layout.addWidget(title)
        text='Compared with the last readback. The slot is read again and backed up before writing.'
        if not window.baseline:text='No readback is available for comparison. The destination will be read and backed up before writing.'
        text+=' Other draft edits stay unsent.' if one else ' Sending an entire mode replaces every assignment and the mode name in this slot.'
        hint=QLabel(text);hint.setWordWrap(True);layout.addWidget(hint)
        rows=differences(window.current,window.baseline,[window.selected_id] if one else None)
        summary=QLabel(f'{len(rows)} changed fields' if rows else 'No changes compared with the last readback.');layout.addWidget(summary)
        table=QTableWidget(len(rows),4);self.table=table;table.setHorizontalHeaderLabels(['Control','Setting','Last read','Draft'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().hide();table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for r,row in enumerate(rows):
            for col,value in enumerate(row):
                item=QTableWidgetItem(value);item.setToolTip(value);table.setItem(r,col,item)
        table.resizeRowsToContents();layout.addWidget(table,1)
        buttons=QHBoxLayout();buttons.addStretch();close=QPushButton('Cancel' if sending else 'Close');close.clicked.connect(self.reject);buttons.addWidget(close)
        if sending:
            send=QPushButton('Send control' if one else 'Send entire mode');send.clicked.connect(self.accept);buttons.addWidget(send)
        layout.addLayout(buttons)


class WorkspaceTools:
    def init_tools(self,outer,auto):
        self.preview_changes=self.settings.value('preview_changes',False,type=bool) if self.settings else False
        self.selection=set();self.copied=[];self.events=deque(maxlen=400);self.received_count=0;self.last_received=None;self.reviewing=False
        self.diagnostic_dialog=None;self.reconnect_enabled=self.settings.value('auto_reconnect',True,type=bool) if self.settings else True
        self.want_connection=auto;self.reconnect_name='';self.retry_at=0;self.retry_delay=2
        self.recovery=None;self.recovery_checked=False;self.draft_error='';self.draft_discarded=False
        self.draft_store=DraftStore(data_root()) if self.settings else None
        self.autosave=QTimer(self);self.autosave.setSingleShot(True);self.autosave.setInterval(450);self.autosave.timeout.connect(self.flush_draft)
        self.selection_anchor=None
        self.changes_button=QPushButton('Changes');self.changes_button.clicked.connect(self.open_changes)
        self.recovery_bar=QWidget();bar=QHBoxLayout(self.recovery_bar);bar.setContentsMargins(0,0,0,0)
        self.recovery_label=QLabel();self.recovery_label.setWordWrap(True);bar.addWidget(self.recovery_label,1)
        restore=QPushButton('Recover draft');restore.clicked.connect(self.restore_draft);bar.addWidget(restore)
        discard=QPushButton('Discard recovery');discard.clicked.connect(self.discard_recovery);bar.addWidget(discard)
        outer.addWidget(self.recovery_bar);self.recovery_bar.hide()
        self.health_timer=QTimer(self);self.health_timer.timeout.connect(self.health_tick);self.health_timer.start(1000)
        if self.draft_store:QTimer.singleShot(0,self.check_recovery)

    def update_tools(self):
        if not hasattr(self,'editor'):return
        self.undo_button.setVisible(bool(self.editor_expansion))
        self.changes_button.setVisible(bool(self.editor_expansion))
        ready=self.current is not None and not self.busy and not self.reading and not self.recovery
        selected=bool(ready and self.selection)
        self.changes_button.setEnabled(ready)
        self.editor.copy.setEnabled(selected)
        compatible=bool(selected and self.copied and len(self.copied) in (1,len(self.selection)))
        self.editor.paste.setEnabled(compatible)
        self.editor.copy.setText('Copy selected' if len(self.selection)>1 else 'Copy control')
        self.editor.paste.setText('Paste to selected' if len(self.selection)>1 else 'Paste control')
        self.editor.paste.setToolTip('One copied control can fill a selection. Multiple controls require an equal-size selection, in left-to-right row order. Control types must match.')
        for cid,tile in self.tiles.items():
            tile.setProperty('selected',cid in self.selection);tile.style().unpolish(tile);tile.style().polish(tile)

    def tile_clicked(self,cid,modifiers=None):
        if not self.current or self.busy or self.reading or self.recovery:return
        modifiers=QApplication.keyboardModifiers() if modifiers is None else modifiers
        ctrl=bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift=bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        anchor=self.selection_anchor if self.selection_anchor is not None else cid
        if shift:
            span=set(range(min(anchor,cid),max(anchor,cid)+1))
            selected=self.selection|span if ctrl else span
        else:
            selected=self.selection^{cid} if ctrl else {cid}
            anchor=cid
        if not selected:self.close_editor();return
        focus=cid if cid in selected else min(selected)
        self.show_control(focus)
        self.selection=selected;self.selection_anchor=anchor
        self.refresh_selection_editor();self.update_tools()

    def refresh_selection_editor(self):
        if not self.current or not self.selection:return
        if len(self.selection)>1:
            self.editor.load_group([self.current.controls[i] for i in sorted(self.selection)])
        elif self.selected_id is not None:
            self.editor.load(self.current.controls[self.selected_id],self.tiles[self.selected_id].position())

    def copy_controls(self):
        if self.current is None or not self.selection or self.busy or self.recovery:return
        self.copied=[deepcopy(self.current.controls[i]) for i in sorted(self.selection)]
        self.status.setText(f'Copied {len(self.copied)} control(s). Select a compatible destination and use Paste in the right panel.')
        self.update_tools()

    def paste_copied(self):
        if self.current is None or not self.selection or not self.copied or self.busy or self.recovery:return
        ids=sorted(self.selection)
        copied=self.copied*len(ids) if len(self.copied)==1 else self.copied
        try:self.apply_candidate(paste_controls(self.current,copied,ids))
        except ValueError as ex:self.editor.error.setText(str(ex));self.status.setText(str(ex))

    def apply_candidate(self,candidate):
        if same_mode(candidate,self.current):return
        self.remember();self.current=candidate
        for cid,tile in self.tiles.items():tile.set_control(candidate.controls[cid])
        self.edited();self.refresh_selection_editor()
        if self.selected_id is not None:self.show_details(self.selected_id)

    def edit_group(self,changes):
        if not self.current or len(self.selection)<2 or self.busy or self.reading or self.recovery:return
        try:candidate=batch_controls(self.current,sorted(self.selection),changes)
        except ValueError as ex:self.editor.error.setText(str(ex));return
        self.apply_candidate(candidate)

    def open_changes(self):
        if self.current:ChangesDialog(self).exec()
    def preview_changes_changed(self,enabled):
        self.preview_changes=enabled
        if self.settings:self.settings.setValue('preview_changes',enabled)
    def review_and_send(self,one=False,expected_active_slot=None):
        if not self.current or self.selected_slot is None or not self.connected or self.busy or self.reading or self.recovery:return
        if one and self.selected_id is None:return
        if expected_active_slot is not None and self.active_slot!=expected_active_slot:
            self.status.setText('Active slot changed. Nothing was sent. Select the destination again.');return
        if not self.preview_changes:
            self.send_mode(one);return
        snapshot=(deepcopy(self.current),self.selected_slot,self.selected_id,self.token,self.worker)
        self.reviewing=True
        try:accepted=ChangesDialog(self,one,True).exec()==QDialog.DialogCode.Accepted
        finally:self.reviewing=False
        if accepted:
            mode,slot,cid,token,worker=snapshot
            if not self.connected or self.worker is not worker or self.token!=token or self.selected_slot!=slot or self.selected_id!=cid or not self.current or not same_mode(self.current,mode) or (expected_active_slot is not None and self.active_slot!=expected_active_slot):
                self.status.setText('Connection or draft changed during review. Nothing was sent. Open the review again.');return
            self.send_mode(one)
        elif self.follow_enabled and self.connected and self.worker and not self.has_pending():
            self.surface_changed(self.active_name,self.active_slot)

    def schedule_draft(self):
        if self.draft_store and not self.recovery and not self.draft_discarded:self.autosave.start()
    def flush_draft(self):
        if not self.draft_store or self.recovery or not self.recovery_checked or self.draft_discarded:return
        try:
            if self.current and self.has_pending():
                self.draft_store.save(self.current,self.baseline,self.selected_slot,self.reconnect_name or self.devices.currentText())
            else:self.draft_store.clear()
            self.draft_error=''
        except (OSError,ValueError) as ex:
            self.draft_error=f'Draft recovery could not be saved: {ex}'
            self.status.setText(self.draft_error);self.log_event(self.draft_error)
    def check_recovery(self):
        self.recovery_checked=True
        try:self.recovery=self.draft_store.load()
        except (OSError,ValueError,KeyError,TypeError) as ex:
            self.status.setText(f'Could not read recovery file: {ex}');self.log_event(self.status.text());return
        if self.recovery:
            saved=self.recovery
            self.recovery_label.setText(f'Recover “{saved["mode"].name}” · slot {saved["slot"] or "not selected"} · {saved.get("device", "Unknown controller")}\nNothing will be sent to the controller.')
            self.recovery_bar.show();self.status.hide();self.update_actions()
    def restore_draft(self):
        if not self.recovery or self.busy or not self.guard_unsaved(pending=True):return
        saved=self.recovery;self.recovery=None;self.recovery_bar.hide();self.status.show();self.detach()
        self.selected_slot=saved['slot'];self.display_mode(saved['mode']);self.baseline=saved['baseline']
        self.edited();self.status.setText('Draft recovered. Review the destination slot before sending. Nothing was sent.');self.schedule_draft()
        self.request_feedback()
    def discard_recovery(self):
        try:self.draft_store.clear()
        except OSError as ex:self.status.setText(f'Could not remove recovery file: {ex}');return
        self.recovery=None;self.recovery_bar.hide();self.status.show();self.update_actions();self.schedule_draft()

    def log_event(self,text):
        self.events.append(f'{datetime.now():%H:%M:%S}  {text}')
    def observe_midi(self,msg):
        self.received_count+=1;self.last_received=time.monotonic()
        self.log_event('IN  '+bytes(msg).hex(' ').upper())
    def reconnect_changed(self,value):
        self.reconnect_enabled=value
        if self.settings:self.settings.setValue('auto_reconnect',value)
    def health_tick(self):
        if self.diagnostic_dialog and self.diagnostic_dialog.isVisible():self.refresh_diagnostics()
        if not self.want_connection or not self.reconnect_enabled or self.worker or self.busy or time.monotonic()<self.retry_at:return
        self.retry_at=time.monotonic()+self.retry_delay;self.retry_delay=min(30,self.retry_delay*2)
        self.scan_devices()
        index=self.devices.findText(self.reconnect_name) if self.reconnect_name else (0 if self.devices.count() else -1)
        if index>=0:
            self.devices.setCurrentIndex(index);self.log_event('Reconnect attempt. No writes are retried.');self.toggle_connection()
    def open_diagnostics(self):
        if self.diagnostic_dialog:
            self.diagnostic_dialog.show();self.diagnostic_dialog.raise_();return
        dialog=QDialog(self);dialog.setWindowTitle('MIDI diagnostics');dialog.resize(690,480);self.diagnostic_dialog=dialog
        layout=QVBoxLayout(dialog);layout.setContentsMargins(20,20,20,20);layout.setSpacing(12)
        self.diagnostic_summary=QLabel();self.diagnostic_summary.setWordWrap(True);layout.addWidget(self.diagnostic_summary)
        self.diagnostic_text=QPlainTextEdit();self.diagnostic_text.setReadOnly(True);self.diagnostic_text.setMaximumBlockCount(400);self.diagnostic_text.setAccessibleName('Recent MIDI and connection events');layout.addWidget(self.diagnostic_text)
        row=QHBoxLayout();clear=QPushButton('Clear log');clear.clicked.connect(self.clear_diagnostics);row.addWidget(clear)
        export=QPushButton('Export log');export.clicked.connect(self.export_diagnostics);row.addWidget(export);row.addStretch()
        close=QPushButton('Close');close.clicked.connect(dialog.hide);row.addWidget(close);layout.addLayout(row)
        self.refresh_diagnostics();dialog.show()
    def diagnostic_report(self):
        age='none' if self.last_received is None else f'{int(time.monotonic()-self.last_received)} s ago'
        state='Connected' if self.connected else 'Disconnected'
        if not self.connected:feedback='disconnected'
        elif self.busy:feedback='paused during write and verification'
        elif self.current is None:feedback='waiting for a mode'
        elif self.selected_slot!=self.active_slot:feedback='editing slot is not the active hardware slot'
        elif self.feedback_mode is None:feedback='waiting for a verified hardware map'
        else:
            mapped=sum(self.feedback_matches(i) for i in self.current.controls)
            changed=sum(feedback_signature(c)!=feedback_signature(self.feedback_mode.controls[i]) for i,c in self.current.controls.items())
            feedback=f'live · {mapped} matching controls · {changed} changed MIDI assignments awaiting send'
        return f'{state} · {self.reconnect_name or "No controller selected"}\nReceived messages: {self.received_count} · Last message: {age}\nActive slot: {self.active_slot or "unknown"} · Editing slot: {self.selected_slot or "none"}\nFeedback: {feedback}\nAutomatic reconnect: {"on" if self.reconnect_enabled else "off"} · Writes are never retried automatically.'
    def refresh_diagnostics(self):
        self.diagnostic_summary.setText(self.diagnostic_report())
        text='\n'.join(self.events)
        if self.diagnostic_text.toPlainText()!=text:
            self.diagnostic_text.setPlainText(text);bar=self.diagnostic_text.verticalScrollBar();bar.setValue(bar.maximum())
    def clear_diagnostics(self):self.events.clear();self.refresh_diagnostics()
    def export_diagnostics(self):
        path,_=QFileDialog.getSaveFileName(self,'Export MIDI log','XL-View-MIDI.txt','Text (*.txt)')
        if path:
            try:
                from pathlib import Path
                Path(path).write_text(self.diagnostic_report()+'\n\n'+'\n'.join(self.events),encoding='utf8')
            except OSError as ex:self.status.setText(f'Could not export log: {ex}')
