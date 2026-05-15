from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
import tempfile
import os

def conv(in_svg, out_png, fill_color):
    with open(in_svg, 'r', encoding='utf-8') as f:
        c = f.read()
    c = c.replace('fill="#000000"', f'fill="{fill_color}"')
    with tempfile.NamedTemporaryFile('w', suffix='.svg', delete=False, encoding='utf-8') as tf:
        tf.write(c)
        temp_svg = tf.name
    renderer = QSvgRenderer(temp_svg)
    img = QImage(32, 32, QImage.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    img.save(out_png)
    os.unlink(temp_svg)

for p in ['hourglass-low', 'hourglass-medium', 'hourglass-high', 'hourglass-simple-low', 'hourglass-simple-medium', 'hourglass-simple-high']:
    conv(f'assets/icons/hourglass/{p}.svg', f'assets/icons/hourglass/{p}_light.png', '#202020')
    conv(f'assets/icons/hourglass/{p}.svg', f'assets/icons/hourglass/{p}_dark.png', '#E0E0E0')
