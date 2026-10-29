"""Application-only label appearance; never part of a mode or MIDI payload."""
from dataclasses import dataclass,asdict
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QColor,QFont,QFontMetrics,QPainter,QTextLayout,QTextOption
from PySide6.QtWidgets import QLabel


@dataclass(frozen=True)
class LabelStyle:
    family: str='Segoe UI'
    scale: int=100
    bold: bool=False
    text_color: str=''
    background: bool=False
    background_color: str='#30363d'

    @classmethod
    def load(cls,settings):
        if settings is None:return cls()
        values={k:settings.value('control_labels/'+k,v) for k,v in asdict(cls()).items()}
        return cls.normalize(values)

    @classmethod
    def normalize(cls,values):
        defaults=cls();values=dict(values)
        def boolean(value):return value is True or str(value).lower() in ('true','1')
        try:scale=max(75,min(200,int(values.get('scale',100))))
        except (TypeError,ValueError):scale=100
        family=str(values.get('family') or defaults.family).replace('\n',' ').replace('\r',' ')[:128]
        text=str(values.get('text_color') or '')
        if text and not QColor(text).isValid():text=''
        bg=str(values.get('background_color') or defaults.background_color)
        if not QColor(bg).isValid():bg=defaults.background_color
        return cls(family,scale,boolean(values.get('bold',False)),QColor(text).name() if text else '',boolean(values.get('background',False)),QColor(bg).name())

    def save(self,settings):
        if settings is not None:
            for key,value in asdict(self).items():settings.setValue('control_labels/'+key,value)

    def font(self):
        font=QFont(self.family);font.setPixelSize(round(13*self.scale/100));font.setBold(self.bold);return font


class ControlNameLabel(QLabel):
    """Two centered lines with honest ellipsis, independent of global app CSS."""
    def __init__(self,text='—'):
        super().__init__(text);self.appearance=LabelStyle();self.disabled_assignment=False
        self.setTextFormat(Qt.TextFormat.PlainText);self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True);self.apply_appearance(self.appearance)

    def apply_appearance(self,style):
        self.appearance=style;metrics=QFontMetrics(style.font())
        self.setFixedHeight(max(32,metrics.lineSpacing()*2+2));self.updateGeometry();self.update()

    def set_disabled_assignment(self,disabled):
        self.disabled_assignment=disabled;self.update()

    def display_lines(self):
        font=self.appearance.font();metrics=QFontMetrics(font);width=self.text_width()
        text=self.text().replace('\n',' ')
        if metrics.horizontalAdvance(text)<=width:return [text]
        layout=QTextLayout(text,font);option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option);layout.beginLayout();line=layout.createLine();line.setLineWidth(width)
        split=line.textLength();layout.endLayout()
        return [text[:split].rstrip(),metrics.elidedText(text[split:].lstrip(),Qt.TextElideMode.ElideRight,width)]

    def text_width(self):return max(1,self.width()-(8 if self.appearance.background else 0))

    def paintEvent(self,event):
        style=self.appearance;p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if style.background:
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(style.background_color));p.drawRoundedRect(QRectF(self.rect()),3,3)
        p.setFont(style.font());p.setPen(QColor(style.text_color or ('#8e9ba7' if self.disabled_assignment else '#eceff2')))
        metrics=QFontMetrics(style.font());lines=self.display_lines();height=len(lines)*metrics.lineSpacing()
        y=(self.height()-height)/2+metrics.ascent()
        for line in lines:
            p.drawText(int((self.width()-metrics.horizontalAdvance(line))/2),int(y),line);y+=metrics.lineSpacing()

    def setText(self,text):
        super().setText(text);self.setToolTip(text)
