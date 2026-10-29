"""Native slot bank and inline mode-name editor."""
from PySide6.QtCore import Qt, Signal, QRectF, QEvent, QRegularExpression
from PySide6.QtGui import QPainter, QColor, QPen, QRegularExpressionValidator
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QPushButton, QLineEdit


class SlotButton(QPushButton):
    def __init__(self, number):
        super().__init__(); self.number=number; self.name='Not read'; self.live=False
        self.setCheckable(number!=16); self.setFixedHeight(58); self.setMinimumWidth(80)
    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#292f35' if self.live else '#30363d' if self.underMouse() else '#15191d'))
        p.setPen(QPen(QColor('#95d4ff' if self.isChecked() or self.hasFocus() else '#505b67'),2 if self.isChecked() else 1))
        p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),4,4)
        p.setPen(QColor('#95d4ff' if self.live else '#b3bec8'))
        compact=self.height()<58
        p.drawText(10,15 if compact else 21,f'{self.number:02d}'+('  LIVE' if self.live else '  FIXED' if self.number==16 else ''))
        p.setPen(QColor('#eceff2' if self.isEnabled() else '#7c8793'))
        p.drawText(10,33 if compact else 44,p.fontMetrics().elidedText(self.name,Qt.TextElideMode.ElideRight,self.width()-20))


class SlotBank(QWidget):
    chosen=Signal(int)
    def __init__(self):
        super().__init__(); self.columns=0; self.buttons={}
        self.grid=QGridLayout(self); self.grid.setContentsMargins(0,0,0,0); self.grid.setSpacing(6)
        for slot in range(1,17):
            b=SlotButton(slot); self.buttons[slot]=b
            b.clicked.connect(lambda checked=False,s=slot:self.chosen.emit(s))
        self.arrange(1260)
    def arrange(self, base_width):
        columns=8
        height=58 if base_width>=1150 else 42
        if columns==self.columns and self.buttons[1].height()==height:return
        while self.grid.count():self.grid.takeAt(0)
        for col in range(8):self.grid.setColumnStretch(col,1 if col<columns else 0)
        for i,b in enumerate(self.buttons.values()):
            b.setFixedHeight(height);self.grid.addWidget(b,i//columns,i%columns)
        self.columns=columns
        self.setFixedHeight(((len(self.buttons)+columns-1)//columns)*(height+6)-6)
    def refresh(self, selected, active, names, errors, connected, busy):
        for slot,b in self.buttons.items():
            if slot==16:
                b.name='Default';b.live=bool(connected and active==16)
                b.setChecked(False);b.setEnabled(False)
                description='Mode 16: Default · read-only factory mode'+(' · active on controller' if b.live else '')
                b.setAccessibleName(description)
                b.setToolTip(description+'\nFixed assignments. This mode cannot be edited or used as a write destination.')
                b.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips,True);b.update();continue
            b.name=names.get(slot,'Read failed' if slot in errors else 'Reading…' if connected else 'Not read')
            b.live=bool(connected and slot==active); b.setChecked(slot==selected); b.setEnabled(not busy)
            description=f'Slot {slot:02d}: {b.name}'+(' · active on controller' if b.live else '')+(' · editing destination' if slot==selected else '')
            b.setAccessibleName(description); b.setToolTip(description+'\n'+errors.get(slot,'Select to read and edit. This does not switch the controller.')); b.update()


class EditableName(QWidget):
    committed=Signal(str)
    editing_changed=Signal()
    def __init__(self):
        super().__init__(); self._text='Launch Control XL 3'
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.label=QPushButton(); self.label.setStyleSheet('text-align:left; font-size:24px; font-weight:600; background:transparent; border:0; padding:0;')
        self.label.setToolTip('Click to rename. Send entire mode to update the controller name.')
        self.label.setAccessibleName('Rename selected mode'); self.label.clicked.connect(self.begin)
        self.field=QLineEdit();self.field.setMaxLength(16);self.field.setAccessibleName('Mode name')
        self.field.setValidator(QRegularExpressionValidator(QRegularExpression('[ -}]*')))
        self.field.installEventFilter(self);self.field.returnPressed.connect(self.commit)
        layout.addWidget(self.label);layout.addWidget(self.field);self.field.hide();self.setText(self._text)
    def text(self):return self._text
    def setText(self,text):
        self._text=text
        # A narrow instrument display wraps names without truncating the stored text.
        lines=[];line='';metrics=self.label.fontMetrics()
        for word in text.split():
            candidate=(line+' '+word).strip()
            if line and metrics.horizontalAdvance(candidate)>144:
                lines.append(line);line=''
            for char in ((' ' if line else '')+word):
                if line and metrics.horizontalAdvance(line+char)>144:
                    lines.append(line);line=''
                line+=char
        lines.append(line.strip());self.label.setText('\n'.join(lines))
    def begin(self):
        self.field.setText(self._text);self.label.hide();self.field.show();self.field.setFocus();self.field.selectAll();self.editing_changed.emit()
    def finish(self):self.field.hide();self.label.show();self.editing_changed.emit()
    def commit(self):
        if not self.field.isVisible():return
        name=self.field.text().strip()
        if not name:return
        self.finish();self.committed.emit(name)
    def eventFilter(self,obj,event):
        if obj==self.field:
            if event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Escape:self.finish();return True
            if event.type()==QEvent.Type.FocusOut:self.commit()
        return super().eventFilter(obj,event)
