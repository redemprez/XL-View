"""Right-hand inspector; edits drafts only, never talks to MIDI directly."""
from copy import deepcopy
import json
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QColor,QIcon,QPixmap,QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QLineEdit,QSpinBox,QComboBox,QCheckBox,QPushButton,QScrollArea)
from .protocol import control_record,ascii_text
from .widgets import IconButton,ValueSlider,ColorSwatches

PALETTE=json.loads(Path(__file__).with_name('palette.json').read_text(encoding='utf8'))
COLOR_MAP={c['index']:QColor(*c['rgb']).name() for c in PALETTE}
def color_name(name):
    return name.replace('fushcia','fuchsia').replace('_',' ').capitalize()

class Editor(QWidget):
    changed=Signal(object)
    group_changed=Signal(dict)
    send_one=Signal()
    closed=Signal()
    def __init__(self):
        super().__init__(); self.control=None; self.loading=False; self.group_mode=False; self.group_typed=set(); self.setFixedWidth(340)
        outer=QVBoxLayout(self); outer.setContentsMargins(12,0,0,0)
        head=QHBoxLayout(); self.title=QLabel('Control'); self.title.setStyleSheet('font-size:18px;font-weight:600;')
        close=IconButton('close','Close editor'); close.clicked.connect(self.closed); head.addWidget(self.title,1); head.addWidget(close); outer.addLayout(head)
        self.hint=QLabel('Select a knob, fader or button.'); self.hint.setWordWrap(True); self.hint.setObjectName('muted'); outer.addWidget(self.hint)
        actions=QHBoxLayout();self.copy=QPushButton('Copy');self.paste=QPushButton('Paste')
        actions.addWidget(self.copy);actions.addWidget(self.paste);outer.addLayout(actions)
        scroll=QScrollArea(); self.scroll=scroll; scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        contents=QWidget(); self.form=QFormLayout(contents); self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.form.setContentsMargins(0,6,8,0); self.form.setVerticalSpacing(7); scroll.setWidget(contents); outer.addWidget(scroll,1)
        self.fields={}; self.labels={}
        self.name=QLineEdit(); self.name.setMaxLength(31); self.name.setPlaceholderText('Name on the XL display')
        self.name.setValidator(QRegularExpressionValidator(QRegularExpression('[ -}]*')))
        self.add('Name',self.name,'label')
        self.kind=QComboBox(); self.add('Message type',self.kind,'kind')
        self.number=ValueSlider(); self.number.setRange(0,127); self.add('CC number',self.number,'number')
        self.channel=QComboBox(); self.channel.addItem('Global',None)
        for i in range(1,17): self.channel.addItem(str(i),i)
        self.add('MIDI channel',self.channel,'channel')
        self.behaviour=QComboBox(); self.add('Behaviour',self.behaviour,'behaviour')
        self.relative=QCheckBox('Relative CC'); self.add('',self.relative,'relative')
        self.low=ValueSlider(); self.high=ValueSlider()
        self.add('Minimum / OFF value',self.low,'low'); self.add('Maximum / ON value',self.high,'high')
        self.velocity=ValueSlider(); self.velocity.setRange(1,127); self.add('Note velocity',self.velocity,'velocity')
        self.key=QComboBox()
        keys=[('None',0)]+[(chr(65+i),4+i) for i in range(26)]+[(str((i+1)%10),30+i) for i in range(10)]
        keys += [('Enter',40),('Escape',41),('Backspace',42),('Tab',43),('Space',44)]+[(f'F{i+1}',58+i) for i in range(12)]
        keys += [('Insert',73),('Home',74),('Page Up',75),('Delete',76),('End',77),('Page Down',78),('Right arrow',79),('Left arrow',80),('Down arrow',81),('Up arrow',82)]
        for label,val in keys: self.key.addItem(label,val)
        self.add('Key',self.key,'keycode')
        mods=QWidget(); row=QHBoxLayout(mods); row.setContentsMargins(0,0,0,0); self.mods=[]
        for title,bit in [('Ctrl',1),('Shift',2),('Alt',4),('Win',8)]:
            cb=QCheckBox(title); row.addWidget(cb); self.mods.append((cb,bit)); cb.toggled.connect(self.edit)
        self.add('Modifiers',mods,'modifiers')
        self.bipolar=QCheckBox('Bipolar range'); self.add('',self.bipolar,'bipolar')
        self.led=QCheckBox('Enable LED feedback'); self.add('',self.led,'led_feedback')
        self.color=ColorSwatches(); self.on_color=ColorSwatches()
        self.add('LED color',self.color,'color'); self.add('LED color when ON',self.on_color,'on_color')
        self.error=QLabel(); self.error.setWordWrap(True); self.error.setStyleSheet('color:#ffb4a9;'); outer.addWidget(self.error)
        self.send=QPushButton('Send this control'); self.send.clicked.connect(self.send_one); outer.addWidget(self.send)
        self.send_all=QPushButton('Send entire mode');outer.addWidget(self.send_all)
        send_hint=QLabel('Sending the entire mode replaces this slot. A backup is created automatically.')
        send_hint.setWordWrap(True);send_hint.setObjectName('muted');outer.addWidget(send_hint)
        self.field_titles={key:label.text() for key,label in self.labels.items()}
        for key,w in self.fields.items():
            callback=lambda *args,k=key:self.field_edited(k)
            if isinstance(w,QLineEdit): w.textEdited.connect(callback)
            elif isinstance(w,QComboBox): w.activated.connect(callback)
            elif isinstance(w,ColorSwatches): w.valueActivated.connect(callback)
            elif isinstance(w,ValueSlider):
                w.valueChanged.connect(callback)
                w.spin.lineEdit().textEdited.connect(lambda text,k=key:self.group_typed.add(k))
                w.spin.editingFinished.connect(lambda k=key:self.field_edited(k) if self.group_mode and k in self.group_typed else None)
                w.slider.sliderReleased.connect(lambda k=key:self.field_edited(k) if self.group_mode else None)
            elif isinstance(w,QCheckBox): w.toggled.connect(callback)
        self.kind.currentIndexChanged.connect(self.type_changed)
        self.relative.toggled.connect(self.type_changed)

    def add(self,title,widget,key):
        label=QLabel(title); self.form.addRow(label,widget); self.labels[key]=label; self.fields[key]=widget
        widget.setAccessibleName(title or widget.text())
    def visible(self,key,value):
        self.fields[key].setVisible(value); self.labels[key].setVisible(value)
    def fill_colors(self,combo,c):
        palette=PALETTE if c.id>=48 else [p for p in PALETTE if p['name'].startswith('vibrant') or p['index'] in (0,3)]
        options=[(p['index'],COLOR_MAP[p['index']],f"{color_name(p['name'])} · {p['index']}") for p in palette]
        values={p['index'] for p in palette}
        for v in (c.color,c.on_color):
            if v not in values:options.append((v,COLOR_MAP.get(v,'#66717c'),f'Imported color · {v}')); values.add(v)
        combo.setOptions(options)
    def load(self,c,position):
        self.loading=True; self.group_mode=False; self.group_typed.clear(); self.control=deepcopy(c); self.error.clear(); self.title.setText(position)
        self.send.show()
        for key,text in self.field_titles.items():self.labels[key].setText(text)
        self.visible('label',True);self.visible('kind',True)
        self.title.setWordWrap(True); self.hint.setText('Edits stay in the draft until sent. Names support up to 31 ASCII characters.')
        self.kind.clear()
        options=[('Disabled','disabled'),('Control Change · 7 bit','CC'),('Control Change · 14 bit','CC14'),('NRPN · 7 bit','NRPN'),('NRPN · 14 bit','NRPN14')]
        if c.id>=48: options += [('Note','Note'),('Program Change','PC'),('Keyboard shortcut','Key')]
        if c.kind not in [v for _,v in options]: options.append(('Keep imported type',c.kind))
        for text,value in options:self.kind.addItem(text,value)
        self.kind.setCurrentIndex(self.kind.findData(c.kind)); self.name.setText(c.label)
        self.fill_colors(self.color,c); self.fill_colors(self.on_color,c)
        self.relative.setChecked(c.relative)
        self.configure(c.kind,c.behaviour)
        for key,w in self.fields.items():
            value=getattr(c,key)
            if isinstance(w,(ValueSlider,ColorSwatches)): w.setValue(value or 0)
            elif isinstance(w,QCheckBox): w.setChecked(bool(value))
            elif isinstance(w,QComboBox):
                idx=w.findData(value)
                if idx<0: w.addItem(f'Imported: {value}',value); idx=w.count()-1
                w.setCurrentIndex(idx)
            if isinstance(w,ValueSlider):
                w.spin.lineEdit().setPlaceholderText('');w.spin.lineEdit().setText(str(w.value()));w.slider.setToolTip('')
        for cb,bit in self.mods: cb.setChecked(bool(c.modifiers&bit))
        self.loading=False
    def load_group(self,controls):
        self.load(controls[0],'Multiple controls selected')
        self.loading=True;self.group_mode=True;self.send.hide()
        valid=all(c.kind not in ('disabled','unknown','Key') for c in controls)
        allowed={'channel'} if valid else set()
        if valid and all(not 40<=c.id<48 for c in controls):allowed.add('color')
        if valid and all(c.id>=48 for c in controls):allowed.add('on_color')
        if valid and all(c.kind!='Note' and not c.relative for c in controls):allowed.update(('low','high'))
        self.hint.setText(f'{len(controls)} selected · Changes affect every selected control in the draft. Mixed settings stay unchanged until you edit them. Send the entire mode when ready.' if valid else f'{len(controls)} selected · Select assigned MIDI controls to edit shared settings. Disabled controls and keyboard shortcuts have no shared MIDI settings.')
        maximum=min(16383 if c.kind in ('CC14','NRPN14') else 127 for c in controls)
        for key,w in self.fields.items():
            self.visible(key,key in allowed)
            if key not in allowed:continue
            values={getattr(c,key) for c in controls};mixed=len(values)>1
            self.labels[key].setText(self.field_titles[key]+(' · Mixed' if mixed else ''))
            if isinstance(w,ColorSwatches):
                palette=PALETTE if all(c.id>=48 for c in controls) else [p for p in PALETTE if p['name'].startswith('vibrant') or p['index'] in (0,3)]
                options=[(p['index'],COLOR_MAP[p['index']],color_name(p['name'])) for p in palette]
                offered={p['index'] for p in palette}
                options += [(v,COLOR_MAP.get(v,'#66717c'),f'Imported color · {v}') for v in sorted(values-offered)]
                w.setOptions(options);w.setValue(-1 if mixed else next(iter(values)))
            elif isinstance(w,QComboBox):
                w.setPlaceholderText('Mixed');w.setCurrentIndex(-1 if mixed else w.findData(next(iter(values))))
            elif isinstance(w,ValueSlider):
                w.setRange(0,maximum);w.setValue(min(getattr(controls[0],key),maximum))
                w.spin.lineEdit().setPlaceholderText('Mixed')
                if mixed:w.spin.lineEdit().clear()
                w.slider.setToolTip('Mixed values: move to set a value for all selected controls.' if mixed else '')
        self.loading=False
    def field_edited(self,key):
        if self.loading:return
        if not self.group_mode:self.edit();return
        w=self.fields[key]
        value=w.currentData() if isinstance(w,QComboBox) else w.value()
        self.group_changed.emit({key:value})
    def configure(self,kind,behaviour=None):
        c=self.control; button=c.id>=48; fader=40<=c.id<48
        active=kind not in ('disabled','unknown'); numeric=kind in ('CC','CC14','NRPN','NRPN14','PC')
        self.number.setMaximum(16383 if kind.startswith('NRPN') else 31 if kind=='CC14' else 127)
        self.labels['number'].setText('Note number' if kind=='Note' else 'NRPN number (MSB × 128 + LSB)' if kind.startswith('NRPN') else 'CC number')
        for w in (self.low,self.high): w.setRange(0,16383 if kind in ('CC14','NRPN14') else 127)
        self.behaviour.clear()
        opts=[('Momentary',0),('Toggle',2)] if button else [('Device setting',0),('Pickup',1),('Jump',2)]
        if kind=='PC': opts=[('Select program',2),('Next / previous',7)]
        for text,value in opts:self.behaviour.addItem(text,value)
        if behaviour is not None:
            idx=self.behaviour.findData(behaviour)
            if idx<0: self.behaviour.addItem(f'Imported: {behaviour}',behaviour); idx=self.behaviour.count()-1
            self.behaviour.setCurrentIndex(idx)
        for key,yes in {'number':active and kind not in ('Key','PC'), 'channel':active and kind!='Key',
            'behaviour':active and (button or fader) and kind!='Key','relative':kind=='CC' and c.id<40,
            'low':numeric and not self.relative.isChecked(),'high':numeric and not self.relative.isChecked(),
            'velocity':kind=='Note','keycode':kind=='Key','modifiers':kind=='Key',
            'bipolar':numeric and not button,'led_feedback':numeric and not fader,
            'color':active and not fader,'on_color':active and button}.items(): self.visible(key,yes)
        if kind=='unknown': self.hint.setText('The imported definition is preserved. Rename it or select a supported message type.')
    def type_changed(self,*args):
        if self.loading or not self.control: return
        self.loading=True
        kind=self.kind.currentData()
        if kind!='CC' or self.control.id>=40:self.relative.setChecked(False)
        self.configure(kind)
        if kind!=self.control.kind:
            self.low.setValue(0); self.high.setValue(16383 if kind in ('CC14','NRPN14') else 127)
        self.loading=False; self.edit()
    def edit(self,*args):
        if self.loading or not self.control or self.group_mode:return
        c=deepcopy(self.control)
        for key,w in self.fields.items():
            if isinstance(w,QLineEdit):value=w.text()
            elif isinstance(w,(ValueSlider,ColorSwatches)):value=w.value()
            elif isinstance(w,QComboBox):value=w.currentData()
            elif isinstance(w,QCheckBox):value=w.isChecked()
            else:continue
            setattr(c,key,value)
        c.modifiers=sum(bit for cb,bit in self.mods if cb.isChecked())
        if c.kind=='PC':c.number=0
        try: ascii_text(c.label,31); control_record(c)
        except ValueError as ex:self.error.setText(str(ex)); return
        self.error.clear(); self.control=c; self.changed.emit(deepcopy(c))
