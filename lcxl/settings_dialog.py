"""Live, persisted controller-label preferences alongside existing MIDI options."""
from dataclasses import asdict
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QWidget,QLabel,
    QCheckBox,QPushButton,QTabWidget,QFontComboBox,QColorDialog,QFrame,QGraphicsOpacityEffect)
from .widgets import ValueSlider,ColorSwatches
from .label_style import LabelStyle,ControlNameLabel
from .version import VERSION

TEXT_COLORS=['#eceff2','#95d4ff','#6cd5d0','#77d59e','#ead664','#ffb4a9','#c19bec','#15191d']
BACKGROUNDS=['#30363d','#15191d','#243746','#213a36','#40352a','#3d2c38','#312d46','#eceff2']


class SettingsDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.loading=True
        self.setWindowTitle('Settings');self.resize(540,620);self.setMinimumSize(500,580)
        outer=QVBoxLayout(self);outer.setContentsMargins(18,18,18,18);outer.setSpacing(12)
        self.tabs=QTabWidget();self.tabs.setStyleSheet('QTabWidget::pane {border:0;} QTabBar::tab {background:#30363d;color:#b3bec8;padding:9px 16px;border:1px solid #505b67;} QTabBar::tab:selected {background:#292f35;color:#eceff2;border-bottom:2px solid #95d4ff;} QTabBar::tab:focus {border-color:#95d4ff;}')
        outer.addWidget(self.tabs,1)
        general=QWidget();layout=QVBoxLayout(general);layout.setContentsMargins(0,18,0,0);layout.setSpacing(12)
        for title,enabled,callback,hint in (
            ('Follow controller',window.follow_enabled,window.follow_changed,'Show the active hardware slot automatically. Unsent edits pause following until you send them or choose Resume following.'),
            ('Reconnect automatically',window.reconnect_enabled,window.reconnect_changed,'Reconnect after a cable or port interruption. Clicking Disconnect pauses retries. Interrupted writes are never repeated automatically.'),
            ('Preview changes before sending',window.preview_changes,window.preview_changes_changed,'Review changes before sending a control or an entire mode. When off, Send starts immediately. You can still review manually with Changes in the editor.')):
            check=QCheckBox(title);check.setChecked(enabled);check.toggled.connect(callback);layout.addWidget(check)
            label=QLabel(hint);label.setWordWrap(True);label.setObjectName('muted');layout.addWidget(label);layout.addSpacing(4)
        diagnostics=QPushButton('MIDI diagnostics');diagnostics.clicked.connect(lambda:(self.accept(),window.open_diagnostics()));layout.addWidget(diagnostics);layout.addStretch();self.tabs.addTab(general,'General')
        labels=QWidget();layout=QVBoxLayout(labels);layout.setContentsMargins(0,16,0,0);layout.setSpacing(10)
        intro=QLabel('Style the names under knobs, faders and buttons. Changes apply immediately to every mode.');intro.setWordWrap(True);intro.setObjectName('muted');layout.addWidget(intro)
        row=QHBoxLayout();font_label=QLabel('Font');self.family=QFontComboBox();self.family.setFontFilters(QFontComboBox.FontFilter.ScalableFonts);self.family.setAccessibleName('Control label font');font_label.setBuddy(self.family)
        row.addWidget(font_label);row.addWidget(self.family,1);layout.addLayout(row)
        row=QHBoxLayout();label=QLabel('Scale');self.scale=ValueSlider();self.scale.setRange(75,200);self.scale.spin.setSuffix('%');self.scale.setAccessibleName('Control label scale');row.addWidget(label);row.addWidget(self.scale,1);layout.addLayout(row)
        self.bold=QCheckBox('Bold labels');layout.addWidget(self.bold)
        self.foreground,self.text_custom=self.color_row(layout,'Text color',TEXT_COLORS,'text_color')
        self.background=QCheckBox('Label background');layout.addWidget(self.background)
        self.background_swatches,self.background_custom=self.color_row(layout,None,BACKGROUNDS,'background_color')
        self.background_opacity=QGraphicsOpacityEffect(self.background_swatches);self.background_swatches.setGraphicsEffect(self.background_opacity)
        preview_title=QLabel('Preview');preview_title.setObjectName('muted');layout.addWidget(preview_title)
        preview=QFrame();preview.setObjectName('display');row=QHBoxLayout(preview);row.setContentsMargins(10,8,10,8);row.setSpacing(12)
        self.preview_name=ControlNameLabel('U1 Filter Cutoff');self.preview_name.setFixedWidth(150)
        self.preview_disabled=ControlNameLabel('Unassigned');self.preview_disabled.setFixedWidth(150);self.preview_disabled.set_disabled_assignment(True)
        row.addStretch();row.addWidget(self.preview_name);row.addWidget(self.preview_disabled);row.addStretch();layout.addWidget(preview)
        note=QLabel('Long names use up to two lines. Hover over a label to read its full name. Larger labels may increase the minimum window height.');note.setWordWrap(True);note.setObjectName('muted');layout.addWidget(note);layout.addStretch();self.tabs.addTab(labels,'Control labels')
        bottom=QHBoxLayout();self.reset=QPushButton('Reset label style');self.reset.clicked.connect(self.reset_labels);bottom.addWidget(self.reset);bottom.addStretch()
        version=QLabel(f'XL View {VERSION}');version.setObjectName('muted');bottom.addWidget(version);close=QPushButton('Close');close.clicked.connect(self.accept);bottom.addWidget(close);outer.addLayout(bottom)
        self.family.currentFontChanged.connect(lambda font:self.change(family=font.family()))
        self.scale.valueChanged.connect(lambda value:self.change(scale=value));self.bold.toggled.connect(lambda value:self.change(bold=value));self.background.toggled.connect(lambda value:self.change(background=value))
        self.tabs.currentChanged.connect(lambda index:self.reset.setVisible(index==1))
        self.populate();self.loading=False;self.reset.hide()

    def color_row(self,layout,title,colors,key):
        if title:layout.addWidget(QLabel(title))
        row=QHBoxLayout();swatches=ColorSwatches();swatches.setAccessibleName(title or 'Label background color')
        swatches.setOptions([(i,color,color.upper()) for i,color in enumerate(colors)])
        swatches.valueActivated.connect(lambda index:self.change(**{key:colors[index]}))
        custom=QPushButton('Custom…');custom.setAccessibleName('Choose '+(title.lower() if title else 'background color'));custom.clicked.connect(lambda:self.choose_color(key))
        row.addWidget(swatches);row.addStretch();row.addWidget(custom);layout.addLayout(row);return swatches,custom

    def populate(self):
        style=self.window.label_style;previous=self.loading;self.loading=True
        self.family.setCurrentFont(QFont(style.family));self.scale.setValue(style.scale);self.bold.setChecked(style.bold);self.background.setChecked(style.background)
        text=style.text_color or '#eceff2';self.foreground.setValue(TEXT_COLORS.index(text) if text in TEXT_COLORS else -1)
        self.background_swatches.setValue(BACKGROUNDS.index(style.background_color) if style.background_color in BACKGROUNDS else -1)
        for button,color in ((self.text_custom,text),(self.background_custom,style.background_color)):
            button.setToolTip('Current color: '+color.upper())
            button.setStyleSheet('border-bottom:3px solid '+color+';')
        self.background_swatches.setEnabled(style.background);self.background_custom.setEnabled(style.background)
        self.background_opacity.setOpacity(1 if style.background else .35)
        self.preview_name.apply_appearance(style);self.preview_disabled.apply_appearance(style);self.loading=previous

    def change(self,**values):
        if self.loading:return
        self.window.set_label_style(LabelStyle.normalize({**asdict(self.window.label_style),**values}));self.populate()

    def choose_color(self,key):
        style=self.window.label_style;initial=getattr(style,key) or '#eceff2'
        color=QColorDialog.getColor(QColor(initial),self,'Label text color' if key=='text_color' else 'Label background color')
        if color.isValid():self.change(**{key:color.name()})

    def reset_labels(self):
        self.window.set_label_style(LabelStyle());self.populate()
