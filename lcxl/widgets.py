"""Small native editor controls with keyboard and accessible-name support."""
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget, QHBoxLayout, QGridLayout, QSpinBox, QSlider, QToolButton, QLabel


class DisplayControlName(QLabel):
    """Use only the lines needed, including device labels without spaces."""
    def text_layout(self):
        layout=QTextLayout(self.text(),self.font())
        option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option);layout.beginLayout();height=0
        while True:
            line=layout.createLine()
            if not line.isValid():break
            line.setLineWidth(max(1,self.width()));line.setPosition(QPointF(0,height));height+=line.height()
        layout.endLayout();return layout,height
    def fit_text(self):
        _,height=self.text_layout();self.setFixedHeight(max(self.fontMetrics().height(),int(height+.99)))
    def setText(self,text):
        super().setText(text);self.fit_text()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if event.size().width()!=event.oldSize().width():self.fit_text()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.FontChange:self.fit_text()
    def paintEvent(self,event):
        p=QPainter(self);p.setPen(QColor('#eceff2'))
        layout,_=self.text_layout();layout.draw(p,QPointF(0,0))


class StatusText(QLabel):
    """Single-line status that never changes the controller grid's geometry."""
    def setText(self,text):
        super().setText(text);self.setToolTip(text);self.setAccessibleName(text)
    def sizeHint(self):return QSize(240,20)
    def minimumSizeHint(self):return QSize(0,20)
    def paintEvent(self,event):
        p=QPainter(self);p.setPen(QColor('#b3bec8'))
        text=self.fontMetrics().elidedText(self.text().replace('\n',' '),Qt.TextElideMode.ElideRight,self.width())
        p.drawText(self.rect(),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,text)


class MidiStatusButton(QToolButton):
    def __init__(self):
        super().__init__();self.setFixedSize(220,34);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_state(False,False,'')
    def set_state(self,connected,connecting,device):
        self.state='Connected' if connected else 'Connecting…' if connecting else 'Disconnected'
        self.led='#77d59e' if connected else '#edb55c' if connecting else '#fb7774'
        self.setAccessibleName(f'MIDI {self.state}. Connection settings')
        self.setToolTip(f'MIDI: {self.state}\n{device or "No controller selected"}\nClick to select a device, connect, disconnect or scan.')
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor('#30363d' if self.underMouse() else '#202327'))
        p.setPen(QPen(QColor('#95d4ff' if self.hasFocus() else '#505b67'),1))
        p.drawRoundedRect(QRectF(1,1,218,32),4,4)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#b3bec8'),1.5))
        p.drawEllipse(QRectF(10,7,20,20));p.drawLine(17,7,17,10);p.drawLine(23,7,23,10)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#b3bec8'))
        for x,y in ((14,16),(16,21),(20,23),(24,21),(26,16)):p.drawEllipse(QPointF(x,y),1.3,1.3)
        p.setBrush(QColor(self.led));p.drawEllipse(QPointF(44,17),4,4)
        p.setPen(QColor('#eceff2'));p.drawText(QRectF(57,0,143,34),Qt.AlignmentFlag.AlignVCenter,'MIDI · '+self.state)
        p.setPen(QPen(QColor('#b3bec8'),1.5));p.drawLine(202,19,206,15);p.drawLine(206,15,210,19)


class IconButton(QToolButton):
    def __init__(self, icon, label, checkable=False):
        super().__init__()
        self.icon_kind=icon
        self.setFixedSize(34,34)
        self.setCheckable(checkable)
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        active=self.isChecked()
        p.setBrush(QColor('#3a454f' if self.underMouse() or active else '#30363d'))
        p.setPen(QPen(QColor('#95d4ff' if self.hasFocus() or active else '#505b67'),1))
        p.drawRoundedRect(QRectF(1,1,32,32),4,4)
        p.translate(17,17)
        p.setPen(QPen(QColor('#95d4ff' if active else '#eceff2'),1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.icon_kind=='close':
            p.drawLine(-5,-5,5,5); p.drawLine(-5,5,5,-5)
        elif self.icon_kind=='settings':
            p.drawEllipse(QRectF(-5,-5,10,10)); p.drawEllipse(QRectF(-2,-2,4,4))
            for _ in range(8):p.drawLine(0,-6,0,-8);p.rotate(45)
        else:
            if not active:p.rotate(35)
            path=QPainterPath(QPointF(-4,-7)); path.lineTo(4,-7); path.lineTo(3,-1)
            path.lineTo(6,3); path.lineTo(-6,3); path.lineTo(-3,-1); path.closeSubpath()
            p.drawPath(path); p.drawLine(0,3,0,9)


class ValueSlider(QWidget):
    valueChanged=Signal(int)
    def __init__(self):
        super().__init__()
        row=QHBoxLayout(self); row.setContentsMargins(0,0,0,0); row.setSpacing(12)
        self.spin=QSpinBox(); self.spin.setFixedWidth(80); self.spin.setKeyboardTracking(False)
        self.slider=QSlider(Qt.Orientation.Horizontal)
        row.addWidget(self.spin); row.addWidget(self.slider,1)
        self.spin.valueChanged.connect(self._spin_changed)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.setFocusProxy(self.spin)
    def _spin_changed(self,value):
        self.slider.blockSignals(True); self.slider.setValue(value); self.slider.blockSignals(False)
        self.valueChanged.emit(value)
    def setAccessibleName(self,name):
        super().setAccessibleName(name); self.spin.setAccessibleName(name); self.slider.setAccessibleName(name+' slider')
    def setRange(self,low,high):
        self.slider.setRange(low,high); self.spin.setRange(low,high)
    def setMaximum(self,value):self.setRange(self.spin.minimum(),value)
    def setValue(self,value):self.spin.setValue(value)
    def value(self):return self.spin.value()


class Swatch(QToolButton):
    def __init__(self,color,label):
        super().__init__(); self.color=QColor(color)
        self.setCheckable(True); self.setFixedSize(32,28)
        self.setAccessibleName(label); self.setToolTip(label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#ffffff' if self.isChecked() else '#95d4ff' if self.hasFocus() or self.underMouse() else '#505b67'),2 if self.isChecked() or self.hasFocus() else 1))
        p.setBrush(self.color); p.drawRoundedRect(QRectF(2,2,28,24),3,3)
        if self.isChecked():
            # Dark backing makes the selection distinguishable on every LED color.
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#15191d')); p.drawEllipse(QRectF(9,7,14,14))
            p.setPen(QPen(QColor('#ffffff'),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            p.drawLine(12,14,15,17); p.drawLine(15,17,20,11)


class ColorSwatches(QWidget):
    valueChanged=Signal(int)
    valueActivated=Signal(int)
    def __init__(self):
        super().__init__(); self.buttons={}; self._value=0
        self.grid=QGridLayout(self); self.grid.setContentsMargins(0,0,0,0)
        self.grid.setSpacing(5); self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
    def setOptions(self,options):
        rows=(len(options)+7)//8
        self.setMinimumHeight(rows*28+max(0,rows-1)*5)
        while self.grid.count():
            w=self.grid.takeAt(0).widget(); w.hide(); w.deleteLater()
        self.buttons={}
        for i,(value,color,label) in enumerate(options):
            b=Swatch(color,label); self.buttons[value]=b
            self.grid.addWidget(b,i//8,i%8)
            b.clicked.connect(lambda checked=False,v=value:self.choose(v))
        self.setValue(self._value)
    def setValue(self,value):
        self._value=value
        for v,b in self.buttons.items():b.setChecked(v==value)
    def choose(self,value):
        changed=value!=self._value; self.setValue(value)
        if changed:self.valueChanged.emit(value)
        self.valueActivated.emit(value)
    def value(self):return self._value
