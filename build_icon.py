"""Render original SVG artwork into native Windows icon sizes and review sheet."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, PngImagePlugin
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtSvg import QSvgRenderer

root=Path(__file__).parent; assets=root/'lcxl/assets'
app=QGuiApplication([])
renderer=QSvgRenderer(str(assets/'xl-view.svg')); assert renderer.isValid()
sizes=(16,20,24,32,40,48,64,128,256); frames=[]
for size in sizes:
    img=QImage(size*4,size*4,QImage.Format.Format_ARGB32);img.fill(Qt.GlobalColor.transparent)
    p=QPainter(img);renderer.render(p);p.end()
    buf=QBuffer();buf.open(QIODevice.OpenModeFlag.WriteOnly);img.save(buf,'PNG')
    frames.append(Image.open(BytesIO(bytes(buf.data()))).convert('RGBA').resize((size,size),Image.Resampling.LANCZOS))
meta=PngImagePlugin.PngInfo();meta.add_text('Source','Original XL View vector artwork, rendered from xl-view.svg; no external assets.')
frames[-1].save(assets/'xl-view.png',pnginfo=meta)
frames[-1].save(assets/'xl-view.ico',format='ICO',sizes=[(s,s) for s in sizes],append_images=frames[:-1])
sheet=Image.new('RGB',(720,340),'#15191d');draw=ImageDraw.Draw(sheet)
sheet.paste(frames[-1],(22,30),frames[-1]);draw.text((28,300),'XL View / original controller icon',fill='#eceff2')
for i,bg in enumerate(('#eceff2','#202327')):
    x=304;y=45+i*140
    draw.rounded_rectangle((294,y-14,704,y+100),radius=8,fill=bg)
    for size in (16,24,32,48,64):
        frame=frames[sizes.index(size)];sheet.paste(frame,(x,y),frame)
        draw.text((x,y+74),str(size),fill='#202327' if i==0 else '#eceff2');x+=78
sheet.save(root/'review/app-icon-sizes.png',pnginfo=meta)
print('ICO sizes:',sorted(Image.open(assets/'xl-view.ico').ico.sizes()))
