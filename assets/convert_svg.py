import sys
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize

def convert_svg(svg_path, png_path, color_hex):
    renderer = QSvgRenderer(svg_path)
    # create a QImage with transparent background
    img = QImage(32, 32, QImage.Format_ARGB32)
    img.fill(0) # transparent
    
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()

    # Apply color overlay roughly by mutating pixel colors (actually, easier to just manipulate the SVG XML directly!)
    pass

import xml.etree.ElementTree as ET

def create_colored_png(in_svg, out_png, fill_color):
    tree = ET.parse(in_svg)
    root = tree.getroot()
    # SVGs can have multiple namespaces, let's just replace fill="#000000" string entirely for simplicity
    with open(in_svg, 'r', encoding='utf-8') as f:
        svg_content = f.read()
    
    # replace black fill with our target color
    svg_content = svg_content.replace('fill="#000000"', f'fill="{fill_color}"')
    
    # write temporary colored SVG
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.svg', delete=False, encoding='utf-8') as tf:
        tf.write(svg_content)
        temp_svg = tf.name

    renderer = QSvgRenderer(temp_svg)
    img = QImage(32, 32, QImage.Format_ARGB32)
    img.fill(0)
    
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    
    img.save(out_png)

create_colored_png("assets/svg/cummins-logo.svg", "assets/icons/cummins-logo_dark.png", "#E0E0E0") # light gray for dark mode
create_colored_png("assets/svg/cummins-logo.svg", "assets/icons/cummins-logo_light.png", "#202020") # dark gray for light mode
print("Conversion done.")
