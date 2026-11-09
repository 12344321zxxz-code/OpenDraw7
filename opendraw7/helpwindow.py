"""Help: a small topic browser with search. All text here is written for OpenDraw7."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QTextBrowser,
                               QLineEdit, QLabel)

from . import theme as T

TOPICS = [
    ("Getting started", """
<p>OpenDraw7 opens with a blank white picture. Pick a tool on the <b>Home</b> tab, pick a colour, and
draw on the picture with the mouse.</p>
<ul>
<li><b>Color 1</b> is used when you draw with the left mouse button, <b>Color 2</b> when you draw with
the right one. Click Color 1 or Color 2, then click a colour in the palette.</li>
<li>Every action can be undone with <b>Undo</b> (Ctrl+Z) in the title bar, and redone with Ctrl+Y.</li>
<li>Drag the small square handles at the right and bottom edges of the picture to make the canvas
bigger or smaller.</li>
</ul>"""),
    ("Pencil, brushes and eraser", """
<p>The <b>Pencil</b> draws one-pixel-sharp lines. <b>Brushes</b> draw soft lines; click the arrow under
Brushes to choose a brush such as calligraphy, airbrush, oil, crayon, marker, natural pencil or
watercolor. Choose the line width with <b>Size</b>, or press Ctrl++ and Ctrl+-.</p>
<p>The <b>Eraser</b> paints with Color 2 (or makes the picture see-through, if the picture has a
transparent background). Drag with the right mouse button to replace only Color 1 with Color 2.</p>"""),
    ("Shapes", """
<p>Pick a shape in the <b>Shapes</b> gallery and drag on the picture. Hold <b>Shift</b> to draw a
perfect square, circle or a 45° line.</p>
<p>Until you click somewhere else, the shape stays adjustable: drag its handles to resize it, drag it
to move it, or change the colours, size, <b>Outline</b> and <b>Fill</b> styles.</p>
<p>The <b>Curve</b> is drawn in steps: drag a straight line, then click or drag up to twice to bend it.
The <b>Polygon</b> is drawn by clicking corner after corner; double-click to close it.</p>"""),
    ("Fill with color", """
<p>Click an area with the <b>Fill with color</b> bucket to fill it with Color 1 (right-click for
Color 2). The fill covers the area of the colour you clicked, and also blends into the soft edges of
brush strokes and shapes so no pale rim is left around the filled area.</p>
<p>If the fill spreads further than you expected, the outline around the area has a gap. Undo, close
the gap with the pencil, and fill again.</p>"""),
    ("Colors", """
<p>Click a colour in the palette to make it Color 1 (or Color 2, if Color 2 is selected). Use the
<b>Color picker</b> to take a colour from the picture.</p>
<p><b>Edit colors</b> opens a window with every colour: click in the spectrum to choose a hue and
saturation, drag the arrow beside the bar to make it lighter or darker, or type exact Red, Green and
Blue values. <b>Add to Custom Colors</b> keeps it for later. The colour you choose is also added to the
bottom row of the palette.</p>"""),
    ("Selecting", """
<p>Click the arrow under <b>Select</b> to choose how to select:</p>
<ul>
<li><b>Rectangular selection</b>: drag a rectangle.</li>
<li><b>Free-form selection</b>: draw around the part you want.</li>
<li><b>Magic wand selection</b>: click an area to select all the connected pixels of a similar
colour. Hold <b>Shift</b> and click more areas to add them to the selection.</li>
<li><b>Object selection</b>: click a character or object to select all of it without the
background: every colour in it, enclosed details such as eyes, and its soft edge. Paint works out the
background from the colours along the picture's edges. Hold <b>Shift</b> and click another object to
add it; click the background to select every object. It works best on drawings and on photos with a
plain or smooth background.</li>
</ul>
<p>Drag a selection to move it. Hold <b>Ctrl</b> while dragging to move a copy and leave the original
where it was. Hold <b>Shift</b> while dragging to leave a trail of copies behind. The arrow keys move a
selection one pixel at a time.</p>
<p><b>Transparent selection</b> (in the Select menu) leaves out the parts of the selection that are
Color 2 when you move or paste it. <b>Invert selection</b> selects everything that was not selected.
<b>Crop</b> (Ctrl+Shift+X) keeps only the selection.</p>"""),
    ("Text", """
<p>Pick <b>Text</b> (the A) and drag a box on the picture, then type. The <b>Text</b> tab appears while
you type: choose the font, size, bold, italic, underline and strikethrough, and whether the box has a
background (<b>Opaque</b>, in Color 2) or not (<b>Transparent</b>). The text becomes part of the
picture when you click outside the box.</p>"""),
    ("Transparent backgrounds", """
<p>To make a picture with see-through areas, open <b>Properties</b> from the Paint menu (Ctrl+E) and
tick <b>Transparent background</b>. After that, the eraser, <b>Delete</b> and <b>Cut</b> leave
see-through areas, which are shown as a grey and white checkerboard. The parts you have already drawn,
the white background included, stay as they are; erase or delete them to make them see-through.</p>
<p>PNG, GIF and TIFF files keep see-through areas. JPEG and BMP files cannot, so they are saved over
white. Pictures you open that already have see-through areas keep them.</p>"""),
    ("Layers", """
<p>Layers are like sheets of clear film stacked on the picture: you can draw on one without touching
the others. Turn on <b>Layers</b> on the <b>View</b> tab (Ctrl+L) to show the Layers pane at the
right.</p>
<ul>
<li>Click a layer to draw on it. Everything you draw, fill, erase, select or type goes on the selected
layer; the colour picker takes the colour you see.</li>
<li>Click the eye to hide or show a layer. Double-click its name to rename it. Right-click a layer for
more commands, such as <b>Flatten picture</b>.</li>
<li>The buttons under the list add a new layer, duplicate, delete, move the layer up or down, and
merge it into the layer below. <b>Opacity</b> makes the selected layer partly see-through.</li>
<li>Rotating, flipping, resizing, skewing, cropping and changing the canvas size act on every layer
together. Invert color acts on the selected layer.</li>
</ul>
<p>To keep the layers, save as <b>OpenRaster (*.ora)</b>; GIMP and Krita open these files too. Every
other file type saves the picture as you see it, with the layers merged.</p>"""),
    ("Zoom and view", """
<p>Zoom with the slider in the status bar, with Ctrl and the mouse wheel, with Ctrl+PgUp and Ctrl+PgDn,
or on the <b>View</b> tab. <b>Fit to window</b> (Ctrl+0) shows the whole picture. The <b>Magnifier</b>
zooms in where you click (right-click zooms out).</p>
<p>The View tab also shows rulers (Ctrl+R) and gridlines (Ctrl+G), a thumbnail of the picture while
you are zoomed in, and the picture on its own on the whole screen (F11).</p>"""),
    ("Saving and file types", """
<p><b>Save</b> (Ctrl+S) saves to the picture's file; <b>Save as</b> (F12) lets you choose a name and a
type. PNG keeps every colour exactly and is the best choice for drawings. JPEG is smaller and suits
photographs, but blurs sharp edges a little. Monochrome, 16-colour and 256-colour BMP and GIF reduce
the number of colours, and Paint warns you before saving in them.</p>"""),
    ("Getting a picture back after a crash", """
<p>While a picture has unsaved changes, OpenDraw7 quietly keeps a copy every two minutes. If the
program or the computer stops before you saved, the next time you start OpenDraw7 it offers to
<b>Restore</b> the picture. Restored pictures are not saved yet: save them to keep them.</p>"""),
    ("Scanner and camera", """
<p><b>From scanner or camera</b> in the Paint menu brings a picture straight in. Scanning uses the
SANE scanner tools (the <i>scanimage</i> program, in the <i>sane-utils</i> package), and taking a
photo with a webcam uses <i>ffmpeg</i>. If either is missing, OpenDraw7 tells you what to install.</p>"""),
    ("Keyboard shortcuts", """
<table cellspacing="0" cellpadding="3">
<tr><td>Ctrl+N, Ctrl+O, Ctrl+S, F12</td><td>New, open, save, save as</td></tr>
<tr><td>Ctrl+P</td><td>Print</td></tr>
<tr><td>Ctrl+Z, Ctrl+Y</td><td>Undo, redo</td></tr>
<tr><td>Ctrl+A, Ctrl+X, Ctrl+C, Ctrl+V, Delete</td><td>Select all, cut, copy, paste, delete</td></tr>
<tr><td>Ctrl+Shift+X</td><td>Crop</td></tr>
<tr><td>Ctrl+W, Ctrl+E</td><td>Resize and skew, image properties</td></tr>
<tr><td>Ctrl+Shift+I</td><td>Invert colours</td></tr>
<tr><td>Ctrl+PgUp, Ctrl+PgDn, Ctrl+0</td><td>Zoom in, zoom out, fit to window</td></tr>
<tr><td>Ctrl+R, Ctrl+G</td><td>Rulers, gridlines</td></tr>
<tr><td>Ctrl++, Ctrl+-</td><td>Thicker, thinner line</td></tr>
<tr><td>F11</td><td>Full screen</td></tr>
<tr><td>Ctrl+F1</td><td>Minimize the ribbon</td></tr>
<tr><td>F1</td><td>Help</td></tr>
<tr><td>Alt (or F10)</td><td>Show the key tips: letters on the ribbon you can press instead of clicking.
Press Esc to go back a level.</td></tr>
<tr><td>Shift (while drawing)</td><td>Squares, circles, 45° lines</td></tr>
<tr><td>Esc</td><td>Cancel the shape, text box or selection in progress</td></tr>
</table>"""),
]


class HelpWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paint Help")
        self.setFont(T.ui_font())
        self.resize(760, 520)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search Help")
        self.search.setClearButtonEnabled(True)
        left.addWidget(self.search)
        self.list = QListWidget(self)
        self.list.setFixedWidth(230)
        left.addWidget(self.list, 1)
        lay.addLayout(left)
        right = QVBoxLayout()
        self.heading = QLabel(self)
        self.heading.setFont(T.ui_font(18))
        self.heading.setStyleSheet("color: #1e395b;")
        right.addWidget(self.heading)
        self.view = QTextBrowser(self)
        self.view.setOpenExternalLinks(True)
        self.view.document().setDefaultStyleSheet("p, li, td { line-height: 135%; } td { padding-right: 14px; }")
        right.addWidget(self.view, 1)
        lay.addLayout(right, 1)
        for title, _body in TOPICS:
            self.list.addItem(QListWidgetItem(title))
        self.list.currentRowChanged.connect(self._show)
        self.search.textChanged.connect(self._filter)
        self.list.setCurrentRow(0)

    def _show(self, row):
        item = self.list.item(row)
        if item is None:
            return
        title = item.text()
        body = dict(TOPICS)[title]
        self.heading.setText(title)
        self.view.setHtml(body)

    def _filter(self, text):
        words = text.lower().split()
        first = None
        for i, (title, body) in enumerate(TOPICS):
            hay = (title + " " + body).lower()
            hit = all(w in hay for w in words)
            self.list.item(i).setHidden(not hit)
            if hit and first is None:
                first = i
        if first is not None and (self.list.currentItem() is None or self.list.currentItem().isHidden()):
            self.list.setCurrentRow(first)

    def show_topic(self, title):
        for i, (t, _b) in enumerate(TOPICS):
            if t == title:
                self.list.setCurrentRow(i)
