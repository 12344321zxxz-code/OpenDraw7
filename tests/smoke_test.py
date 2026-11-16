"""End-to-end smoke test. Drives the real window with synthetic input.

    QT_QPA_PLATFORM=offscreen python tests/smoke_test.py
"""
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QEvent, QSettings, QSize  # noqa: E402
from PySide6.QtGui import QMouseEvent, QColor, QImage, QGuiApplication, QPainter, QPen  # noqa: E402
import math  # noqa: E402,F811
import numpy as np  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from opendraw7.app import create_app  # noqa: E402

app = create_app(["opendraw7-test"])
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp())

from opendraw7.mainwindow import MainWindow  # noqa: E402
from opendraw7.brushes import BRUSHES, make_stroke  # noqa: E402
from opendraw7.shapes import SHAPES  # noqa: E402
from opendraw7.document import (FORMATS, save_image, load_image, reduce_colors, const_pixels,  # noqa: E402
                                flood_fill)

win = MainWindow()
win.show()
app.processEvents()
st, c, doc = win.state, win.canvas, win.doc
vpw = c.viewport()
checks = 0


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(what)


def vp(x, y):
    p = c.to_view(QPointF(x, y))
    return QPoint(int(p.x()), int(p.y()))


def drag(pts, button=Qt.LeftButton, mods=Qt.NoModifier):
    QTest.mousePress(vpw, button, mods, vp(*pts[0]))
    for pt in pts[1:]:
        ev = QMouseEvent(QEvent.MouseMove, QPointF(vp(*pt)), QPointF(vpw.mapToGlobal(vp(*pt))),
                         Qt.NoButton, button, mods)
        app.sendEvent(vpw, ev)
    QTest.mouseRelease(vpw, button, mods, vp(*pts[-1]))
    app.processEvents()


def px(x, y):
    return QColor(doc.image.pixel(x, y)).name()


def ink():
    """Number of non-white pixels in the picture."""
    return int((const_pixels(doc.image) != 0xFFFFFFFF).sum())


WHITE = "#ffffff"

# ---- start-up state --------------------------------------------------------
ok(doc.size() == QSize(800, 600), "default canvas size")
ok(st.tool == "brush" and st.color1.name() == "#000000" and st.color2.name() == WHITE, "default tool/colours")
ok(win.windowTitle() == "Untitled - Paint", "title")

# ---- every brush leaves ink, and each stroke is one undo step ----------------
for i, (bid, _label) in enumerate(BRUSHES):
    st.set_tool("brush", brush=bid)
    before, depth = ink(), len(doc.undo_stack)
    drag([(20 + k * 6, 30 + i * 50 + math.sin(k / 4.0) * 12) for k in range(50)])
    ok(ink() > before, f"brush {bid} drew nothing")
    ok(len(doc.undo_stack) == depth + 1, f"brush {bid} undo steps")

# ---- pencil sizes and right button uses colour 2 --------------------------------
st.set_tool("pencil")
st.set_size(1)
st.set_color(2, QColor(255, 0, 0))
drag([(400, 20), (500, 20)], button=Qt.RightButton)
ok(px(450, 20) == "#ff0000" and px(450, 21) == WHITE, "pencil right button / 1px")
st.set_size(4)
st.set_color(1, QColor(0, 0, 255))
drag([(400, 40), (500, 40)])
ok(all(px(450, y) == "#0000ff" for y in (38, 39, 40, 41)) and px(450, 42) == WHITE, "pencil 4px")
st.set_color(2, QColor(255, 255, 255))

# ---- eraser: left erases to colour 2, right only replaces colour 1 ---------------
st.set_tool("eraser")
st.set_size(10)
drag([(450, 10), (450, 50)])
ok(px(450, 20) == WHITE and px(450, 40) == WHITE, "eraser")
st.set_color(1, QColor(0, 0, 255))
drag([(480, 10), (480, 50)], button=Qt.RightButton)
ok(px(480, 40) == WHITE and px(480, 20) == "#ff0000", "colour-replace eraser")

# ---- undo / redo ----------------------------------------------------------------
depth = len(doc.undo_stack)
c.undo()
ok(px(480, 40) == "#0000ff" and len(doc.undo_stack) == depth - 1, "undo")
c.redo()
ok(px(480, 40) == WHITE, "redo")

# ---- fill and picker -------------------------------------------------------------
st.set_tool("fill")
st.set_color(1, QColor(181, 230, 29))
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(700, 550))
ok(px(700, 550) == "#b5e61d" and px(790, 590) == "#b5e61d", "fill")
c.undo()
ok(px(700, 550) == WHITE, "fill undo")
st.set_tool("pencil")
st.set_tool("picker")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(430, 20))
ok(st.color1.name() == "#ff0000" and st.tool == "pencil", "picker picks and returns to previous tool")

# ---- all shapes --------------------------------------------------------------------
doc.new(800, 600)
st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 242, 0))
st.set_fill("solid")
st.set_outline("solid")
st.set_size(3)
x, y = 20, 20
for sid, _label in SHAPES:
    if sid in ("curve", "polygon"):
        continue
    st.set_tool("shape", shape=sid)
    before = ink()
    drag([(x, y), (x + 30, y + 25), (x + 60, y + 50)])
    ok(c.tool.has_pending(), f"{sid} stays adjustable")
    QTest.keyClick(c, Qt.Key_Return)
    ok(ink() > before and not c.tool.has_pending(), f"shape {sid}")
    x += 75
    if x > 720:
        x, y = 20, y + 70
st.set_tool("shape", shape="rect")
drag([(600, 400), (650, 430), (700, 500)])
shown = c.display_image()                                  # still adjustable, so not in the picture yet
ok(QColor(shown.pixel(650, 450)).name() == "#fff200" and QColor(shown.pixel(600, 400)).name() == "#000000"
   and QColor(shown.pixel(701, 501)).name() == WHITE and px(650, 450) == WHITE, "rect fill/outline/bounds")
st.set_color(2, QColor(0, 162, 232))                     # recolour while still adjustable
drag([(650, 450), (660, 455), (670, 460)])              # ...and move it by (20, 10)
QTest.keyClick(c, Qt.Key_Return)
ok(px(680, 470) == "#00a2e8" and px(720, 510) == "#000000" and px(605, 405) == WHITE, "adjust pending shape")
st.set_tool("shape", shape="oval")
drag([(300, 400), (350, 450), (400, 500)], mods=Qt.ShiftModifier)
ok(c.tool._bbox().width() == c.tool._bbox().height(), "shift makes a circle")
QTest.keyClick(c, Qt.Key_Escape)
ok(not c.tool.has_pending(), "escape cancels shape")
st.set_tool("shape", shape="curve")
before = ink()
drag([(20, 520), (200, 520)])
drag([(80, 480), (90, 470)])
drag([(150, 570), (160, 580)])
ok(ink() > before and not c.tool.has_pending(), "curve")
st.set_tool("shape", shape="polygon")
before = ink()
drag([(240, 520), (300, 510)])
drag([(330, 560), (335, 570)])
drag([(260, 590), (265, 592)])
QTest.mouseDClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(265, 592))
app.processEvents()
ok(ink() > before and not c.tool.has_pending(), "polygon")

# ---- selections -----------------------------------------------------------------------
doc.new(400, 300)
st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 255, 255))
st.set_tool("shape", shape="rect")
st.set_fill("none")
st.set_tool("pencil")
st.set_size(4)
st.set_color(1, QColor(255, 0, 0))
drag([(20, 20), (60, 20)])
st.set_tool("select")
drag([(10, 10), (40, 20), (70, 30)])
sel = c.select_tool.sel
ok(sel is not None and (sel.rect.x(), sel.rect.y(), sel.rect.width(), sel.rect.height()) == (10, 10, 60, 20), "rect selection")
ok(win.crop_btn.isEnabled() and win.copy_btn.isEnabled(), "ribbon enables crop/copy")
drag([(30, 20), (80, 60), (130, 120)])                  # move by (100, 100)
QTest.keyClick(c, Qt.Key_Escape)
ok(px(140, 120) == "#ff0000" and px(40, 20) == WHITE, "move selection")
drag([(110, 110), (140, 120), (170, 130)])
drag([(130, 120), (180, 120), (230, 120)], mods=Qt.ControlModifier)   # ctrl-drag copy
QTest.keyClick(c, Qt.Key_Escape)
ok(px(140, 120) == "#ff0000" and px(240, 120) == "#ff0000", "ctrl-drag copies")
drag([(110, 110), (140, 120), (170, 130)])
c.copy()
QTest.keyClick(c, Qt.Key_Delete)
ok(px(140, 120) == WHITE and not c.has_selection(), "delete selection")
c.paste()
ok(c.has_selection() and c.select_tool.sel.rect.topLeft() == QPoint(0, 0), "paste lands top-left")
QTest.keyClick(c, Qt.Key_Escape)
ok(px(30, 10) == "#ff0000", "pasted pixels")
c.select_all()
ok(c.select_tool.sel.rect == doc.rect(), "select all")
QTest.keyClick(c, Qt.Key_Escape)
drag([(0, 0), (100, 50), (200, 150)])
c.crop()
ok(doc.size() == QSize(200, 150), "crop")
c.undo()
ok(doc.size() == QSize(400, 300), "crop undo")
st.set_sel_mode("free")
st.set_tool("select")
drag([(50, 50), (150, 50), (150, 150), (50, 150), (50, 60)])
ok(c.select_tool.sel is not None and c.select_tool.sel.path is not None, "free-form selection")
c.invert_selection()
ok(c.select_tool.sel.rect == doc.rect(), "invert selection")
QTest.keyClick(c, Qt.Key_Escape)
st.set_sel_mode("rect")

# ---- whole-picture transforms -----------------------------------------------------------
c.rotate("r90")
ok(doc.size() == QSize(300, 400), "rotate 90")
c.rotate("l90")
c.rotate("fliph")
c.rotate("flipv")
c.rotate("180")
ok(doc.size() == QSize(400, 300), "rotate/flip keep size")
c.resize_skew(200, 150)
ok(doc.size() == QSize(200, 150), "resize")
c.undo()
c.resize_skew(400, 300, 20, 0)
ok(doc.width() > 400, "skew widens")
c.undo()
before = px(5, 5)
c.invert_colors()
ok(px(5, 5) == "#000000" and before == WHITE, "invert colours")
c.undo()

# ---- canvas handle resize ------------------------------------------------------------------
h = c._canvas_handles()["rb"]
QTest.mousePress(vpw, Qt.LeftButton, Qt.NoModifier, h)
pt = QPoint(h.x() - 100, h.y() - 50)
app.sendEvent(vpw, QMouseEvent(QEvent.MouseMove, QPointF(pt), QPointF(vpw.mapToGlobal(pt)),
                               Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
QTest.mouseRelease(vpw, Qt.LeftButton, Qt.NoModifier, pt)
ok(abs(doc.width() - 300) <= 4 and abs(doc.height() - 250) <= 4, f"canvas handle resize {doc.size()}")
c.undo()

# ---- text ------------------------------------------------------------------------------------
doc.new(400, 300)
st.set_tool("text")
st.set_color(1, QColor(136, 0, 21))
drag([(20, 20), (100, 60), (300, 100)])
ok(c.text_editing() and win.ribbon.current() == win.text_idx, "text box opens the Text tab")
QTest.keyClicks(c, "Hello")
QTest.keyClick(c, Qt.Key_B, Qt.ControlModifier)
ok(st.bold and win.fmt_btns["bold"].isChecked(), "ctrl+b toggles bold")
QTest.keyClicks(c, " world")
ok(c.text_tool.tdoc.toPlainText() == "Hello world", "typing")
QTest.keyClick(c, Qt.Key_Backspace)
QTest.keyClick(c, Qt.Key_A, Qt.ControlModifier)
QTest.keyClick(c, Qt.Key_C, Qt.ControlModifier)
ok(QGuiApplication.clipboard().text() == "Hello worl", "text copy")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(350, 250))
ok(not c.text_editing() and win.ribbon.current() == win.home_idx and ink() > 0, "text commits on click-away")
st.set_font(bold=False)
depth = len(doc.undo_stack)
drag([(20, 150), (100, 180), (300, 220)])
QTest.keyClicks(c, "gone")
QTest.keyClick(c, Qt.Key_Escape)
ok(not c.text_editing() and len(doc.undo_stack) == depth, "escape discards text")

# ---- zoom, view options, ribbon ----------------------------------------------------------------
st.set_tool("pencil")
c.set_zoom(8)
ok(c.zoom == 8 and win.status.zoomer.zoom == 8 and not win.zoomin_btn.isEnabled(), "zoom in limit")
c.zoom_step(-1)
ok(c.zoom == 7, "zoom step")
c.set_zoom(1)
win.set_rulers(True)
win.set_grid(True)
ok(win.hruler.isVisible() and c.show_grid and win.rulers_chk.isChecked(), "rulers/grid")
win.set_rulers(False)
win.set_grid(False)
win.ribbon.set_minimized(True)
ok(win.ribbon.height() < 40, "ribbon minimizes")
win.ribbon.set_minimized(False)
win.resize(700, 600)
app.processEvents()
ok(any(s.isVisible() for s in win.home_page._stubs.values()), "groups collapse when narrow")
win.resize(1100, 760)
app.processEvents()
ok(not any(s.isVisible() for s in win.home_page._stubs.values()), "groups expand again")

# ---- popups survive the click that opened them ---------------------------------------------------
st.set_tool("brush", brush="brush")
pop = win._brush_menu()
pop.show()
app.processEvents()
QTest.mouseRelease(pop, Qt.LeftButton, Qt.NoModifier, QPoint(-40, -40))
ok(pop.isVisible(), "gallery stays open after the opening click is released")
QTest.mouseClick(pop, Qt.LeftButton, Qt.NoModifier, pop._rect(5).center())
app.processEvents()
ok(st.brush == "crayon" and st.tool == "brush", "gallery pick")
pop = win._size_menu()
pop.show()
app.processEvents()
QTest.mouseClick(pop, Qt.LeftButton, Qt.NoModifier, pop.rows[3].center())
app.processEvents()
ok(st.size() == 40, "size pick")
st.set_tool("pencil")

# ---- file formats ----------------------------------------------------------------------------------
doc.new(120, 90)
st.set_tool("shape", shape="star5")
st.set_fill("solid")
st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(237, 28, 36))
drag([(10, 10), (60, 50), (110, 80)])
st.set_tool("pencil")
tmp = tempfile.mkdtemp()
for key, _label, exts in FORMATS:
    path = os.path.join(tmp, f"t_{key}.{exts[0]}")
    save_image(doc.image, path, key)
    back = load_image(path)
    ok(back.size() == doc.size(), f"{key} size")
    if key != "jpeg":
        want = reduce_colors(doc.image, key).convertToFormat(QImage.Format_RGB32)
        got = back.convertToFormat(QImage.Format_RGB32)
        ok(bool((const_pixels(want) == const_pixels(got)).all()), f"{key} round trip")
path = os.path.join(tmp, "saved.png")
ok(win._write(path, "png") and not doc.modified and win.windowTitle() == "saved.png - Paint", "save")
ok(win.open_path(os.path.join(tmp, "t_bmp24.bmp")) and win.windowTitle() == "t_bmp24.bmp - Paint", "open")
ok(os.path.join(tmp, "saved.png") in win._recent(), "recent pictures")

big = QImage(1500, 1000, QImage.Format_RGB32)
big.fill(QColor(255, 255, 255))
ok(flood_fill(big, 5, 5, QColor(1, 2, 3)) and QColor(big.pixel(1499, 999)).name() == "#010203", "large fill")
ok(not flood_fill(big, 5, 5, QColor(1, 2, 3)), "fill with same colour is a no-op")

# filling inside a smoothed outline must not leave a pale ring, nor reach past the outline
ring = QImage(200, 160, QImage.Format_RGB32)
ring.fill(QColor(255, 255, 255))
rp = QPainter(ring)
rp.setRenderHint(QPainter.Antialiasing, True)
rp.setPen(QPen(QColor(0, 0, 0), 3))
rp.drawEllipse(QRectF(20, 20, 160, 120))
rp.end()
flood_fill(ring, 100, 80, QColor(255, 0, 0))
ra = const_pixels(ring).astype(np.int64)
rg = (ra >> 8) & 0xFF
ryy, rxx = np.mgrid[0:160, 0:200]
rin = ((rxx - 100) / 80.0) ** 2 + ((ryy - 80) / 60.0) ** 2 < 1.0   # up to the middle of the outline
ok(int((rin & (rg > 60)).sum()) == 0, "fill leaves no pale ring inside a smoothed outline")
ok(QColor(ring.pixel(2, 2)).name() == "#ffffff" and QColor(ring.pixel(100, 3)).name() == "#ffffff",
   "fill stays inside a smoothed outline")
# fill a thin soft brush loop, fill it back to white, then fill everything: no specks may survive
loop = QImage(300, 220, QImage.Format_RGB32)
loop.fill(QColor(255, 255, 255))
dark = QColor(136, 0, 21)
lst = make_stroke("brush", loop, dark, 1)
lpts = [QPointF(150 + 100 * math.cos(k / 60 * 2 * math.pi) + 8 * math.sin(k / 60 * 2 * math.pi * 7),
                110 + 70 * math.sin(k / 60 * 2 * math.pi)) for k in range(61)]
for la, lb in zip(lpts, lpts[1:]):
    lst.segment(la, lb)
flood_fill(loop, 150, 110, dark)
flood_fill(loop, 150, 110, QColor(255, 255, 255))
la_ = const_pixels(loop).astype(np.int64)
ok(int((((la_ >> 8) & 0xFF) < 230).sum()) == 0, "refilling a filled soft shape leaves no specks")
flood_fill(loop, 2, 2, dark)
la_ = const_pixels(loop).astype(np.int64)
ok(int((((la_ >> 8) & 0xFF) > 24).sum()) == 0, "filling everything after a refill leaves no specks")

st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 255, 255))
# ---- zoom to fit ----------------------------------------------------------------
doc.new(1600, 1200)
c.zoom_to_fit()
app.processEvents()
vps = c.viewport().size()
ok(doc.width() * c.zoom <= vps.width() and doc.height() * c.zoom <= vps.height() and c.zoom < 1, "zoom to fit shrinks")
doc.new(100, 80)
c.zoom_to_fit()
ok(c.zoom > 1 and c.zoom == int(c.zoom), "zoom to fit enlarges small pictures to a whole zoom")
c.set_zoom(1.0)


# ---- magic wand ---------------------------------------------------------------
def paint_test_picture():
    doc.new(400, 300)
    p = QPainter(doc.image)
    p.fillRect(40, 40, 100, 60, QColor(255, 0, 0))
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 255))
    p.drawEllipse(QRectF(200, 100, 120, 120))
    p.end()
    doc.changed.emit()
    app.processEvents()


paint_test_picture()
st.set_tool("select")
st.set_sel_mode("wand")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(60, 60))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect == QRect(40, 40, 100, 60), "wand selects the red rectangle")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.ShiftModifier, vp(260, 160))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect.right() >= 318 and s.mask is not None, "shift+wand adds the circle")
ok(len(s.edges()) > 10, "wand selection has an outline")
c.delete_selection()
ok(px(60, 60) == WHITE and px(260, 160) == WHITE and px(10, 10) == WHITE, "deleting a wand selection")
c.undo()
ok(px(60, 60) == "#ff0000" and px(260, 160) == "#0000ff", "undo after wand delete")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(10, 10))
app.processEvents()
c.invert_selection()
s = c.select_tool.sel
ok(s is not None and s.mask is not None and s.mask[60 - s.rect.top(), 60 - s.rect.left()]
   and not s.mask[10 - s.rect.top(), 10 - s.rect.left()] if s.rect.contains(QPoint(10, 10)) else True,
   "invert a wand selection")
c.commit_pending()
# wand selection moves its exact shape: drag the circle and the square stays
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(260, 160))
app.processEvents()
drag([(260, 160), (230, 160), (200, 160)])
c.commit_pending()
ok(px(200, 160) == "#0000ff" and px(60, 60) == "#ff0000" and px(315, 160) == WHITE, "move a wand selection")
st.set_sel_mode("rect")

# ---- shift-drag trail ---------------------------------------------------------------
paint_test_picture()
st.set_tool("select")
drag([(39, 39), (141, 101)])
before = int((const_pixels(doc.image) == 0xFFFF0000).sum())
drag([(80, 70), (110, 70), (140, 70), (170, 70), (200, 70)], mods=Qt.ShiftModifier)
c.commit_pending()
after = int((const_pixels(doc.image) == 0xFFFF0000).sum())
ok(px(60, 60) == "#ff0000" and px(150, 60) == "#ff0000" and after > before * 1.8, "shift-drag leaves a trail")

# ---- transparency -------------------------------------------------------------------
paint_test_picture()
doc.set_transparent(True)
ok(doc.transparent and px(60, 60) == "#ff0000", "turn on transparent background")
st.set_tool("eraser")
drag([(150, 20), (190, 20), (190, 60)])
ok(QColor.fromRgba(doc.image.pixel(170, 20)).alpha() == 0, "eraser clears to transparent")
st.set_tool("select")
drag([(39, 39), (141, 101)])
c.delete_selection()
ok(QColor.fromRgba(doc.image.pixel(60, 60)).alpha() == 0, "delete clears to transparent")
st.set_tool("fill")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(60, 60))
app.processEvents()
ok(QColor.fromRgba(doc.image.pixel(60, 60)).alpha() == 255, "fill a transparent area")
c.undo()
tmp = tempfile.mkdtemp()
for ext, fmt, keeps in (("png", "png", True), ("gif", "gif", True), ("tif", "tiff", True), ("jpg", "jpeg", False),
                        ("bmp", "bmp24", False)):
    path = os.path.join(tmp, "clear." + ext)
    save_image(doc.image, path, fmt)
    back = load_image(path)
    ok(back.hasAlphaChannel() == keeps and (QColor.fromRgba(back.pixel(60, 60)).alpha() == 0) == keeps,
       f"transparency round trip through {ext}")
    ok(QColor.fromRgba(back.pixel(260, 160)).name() in ("#0000ff", "#0000fe", "#0100ff"), f"colours survive {ext}")
c.rotate("r90")
ok(doc.transparent, "rotating keeps transparency")
c.undo()
st.set_tool("select")
drag([(149, 9), (196, 66)])
c.crop()
ok(doc.transparent and doc.size() == QSize(47, 57) and QColor.fromRgba(doc.image.pixel(21, 11)).alpha() == 0,
   "crop keeps transparency")
c.undo()
doc.set_transparent(False)
ok(not doc.transparent and px(60, 60) == WHITE, "turn off transparent background")
c.undo()
ok(doc.transparent, "undo brings transparency back")
c.undo()
c.undo()
doc.new(800, 600)

# ---- autosave and crash recovery ------------------------------------------------------
import json  # noqa: E402
from opendraw7.recovery import AutoSaver, leftovers  # noqa: E402
rdir = tempfile.mkdtemp()
saver = AutoSaver(win, interval=10 ** 9, folder=rdir)
ok(not saver.save_now(wait=True), "nothing to autosave on an unchanged picture")
paint_test_picture()
doc.push_undo()
doc.changed.emit()
ok(saver.save_now(wait=True) and os.path.exists(saver.png) and os.path.exists(saver.json), "autosave writes a copy")
ok(not leftovers(rdir), "a running window's copy is not offered for recovery")
meta = json.load(open(saver.json))
meta["pid"] = 2 ** 22 + 12345                 # pretend it was left by a process that is gone
json.dump(meta, open(saver.json, "w"))
found = leftovers(rdir)
ok(len(found) == 1, "a crashed window's copy is found")
doc.new(800, 600)
ok(not os.path.exists(saver.png), "starting a new picture removes the copy")
from PySide6.QtGui import QImage as _QI  # noqa: E402
from opendraw7.document import load_ora  # noqa: E402
ok(found[0][1].endswith(".ora"), "the recovery copy is an OpenRaster file (keeps layers)")
paint_test_picture()
doc.push_undo()
doc.changed.emit()
saver.save_now(wait=True)
img_copy = load_ora(saver.png)
doc.new(800, 600)
doc.restore(img_copy, "/tmp/somewhere/pic.png", "png")
ok(doc.modified and doc.path == "/tmp/somewhere/pic.png" and px(60, 60) == "#ff0000" and doc.size() == QSize(400, 300),
   "restore brings the picture back unsaved")
saver.clear()
saver.timer.stop()
doc.new(800, 600)

# ---- text on a picture made by convertToFormat (opened file, transparent) keeps the picture alive ----
import gc  # noqa: E402
for transparent in (True, False):
    doc.new(300, 200)
    doc.set_transparent(transparent)
    st.set_tool("text")
    c.text_tool._create(QRect(10, 10, 200, 40))
    c.text_tool.insert_text("Hello")
    win.grab()
    c.commit_pending()
    gc.collect()
    app.processEvents()
    alive = True
    try:
        doc.image.width()
    except RuntimeError:
        alive = False
    ok(alive, f"text keeps the picture alive (transparent={transparent})")
doc.new(800, 600)

# ---- layers -----------------------------------------------------------------------------
def cpx(x, y):
    """Colour of the picture as seen (all layers)."""
    return QColor.fromRgba(c.display_image().pixel(x, y))


st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 255, 255))
c.set_zoom(1.0)
doc.new(400, 300)
win.set_layers_pane(True)
pane = win.layers_pane
pp = QPainter(doc.image)
pp.fillRect(0, 0, 200, 300, QColor(255, 0, 0))
pp.end()
doc.changed.emit()
pane.add()
ok(len(doc.layers) == 2 and doc.active == 1 and doc.transparent, "new layer is see-through and selected")
st.set_tool("pencil")
st.set_size(4)
drag([(150, 50), (250, 50)])
ok(QColor.fromRgba(doc.layers[1].image.pixel(200, 50)).name() == "#000000"
   and QColor(doc.layers[0].image.pixel(200, 50)).name() == WHITE, "drawing goes on the selected layer only")
ok(cpx(200, 50).name() == "#000000" and cpx(100, 200).name() == "#ff0000", "the picture shows both layers")
st.set_tool("fill")
st.set_color(1, QColor(0, 0, 255))
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(350, 250))
app.processEvents()
ok(QColor.fromRgba(doc.layers[1].image.pixel(100, 200)).name() == "#0000ff"
   and QColor(doc.layers[0].image.pixel(100, 200)).name() == "#ff0000", "fill looks only at the selected layer")
c.undo()
ok(QColor.fromRgba(doc.layers[1].image.pixel(100, 200)).alpha() == 0, "undo a fill on a layer")
st.set_tool("picker")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(100, 200))
ok(st.color1.name() == "#ff0000", "the colour picker takes the colour you see")
st.set_tool("pencil")
pane.toggle_visible(1)
ok(not doc.layers[1].visible and cpx(200, 50).name() == WHITE, "hide a layer")
c.undo()
ok(doc.layers[1].visible and cpx(200, 50).name() == "#000000", "undo hiding a layer")
doc.set_layer_props(1, opacity=0.5)
ok(abs(cpx(200, 50).red() - 128) <= 2, "layer opacity blends")
doc.set_layer_props(1, opacity=1.0)
pane.duplicate()
ok(len(doc.layers) == 3 and doc.layers[2].name.endswith("copy") and doc.active == 2, "duplicate a layer")
pane.delete()
ok(len(doc.layers) == 2 and doc.active == 1, "delete a layer")
pane.move(-1)
ok(doc.active == 0 and doc.layers[1].name == "Background" and doc.layers[1].image.format() == QImage.Format_ARGB32_Premultiplied,
   "move a layer down; the one moved up becomes see-through")
c.undo()
ok(doc.active == 1 and doc.layers[0].name == "Background" and doc.layers[0].image.format() == QImage.Format_RGB32,
   "undo moving a layer")
pane.activate(0)
ok(doc.active == 0 and not doc.transparent, "select the background layer")
pane.activate(1)
# whole-picture commands act on every layer
c.rotate("r90")
ok(all(ly.image.size() == QSize(300, 400) for ly in doc.layers), "rotate turns every layer")
c.undo()
ok(doc.resize_canvas(500, 350, QColor(255, 255, 255)) and all(ly.image.size() == QSize(500, 350) for ly in doc.layers)
   and QColor.fromRgba(doc.layers[1].image.pixel(450, 320)).alpha() == 0
   and QColor(doc.layers[0].image.pixel(450, 320)).name() == WHITE, "canvas size changes every layer")
c.undo()
st.set_tool("select")
st.set_sel_mode("rect")
drag([(100, 20), (300, 120)])
c.crop()
ok(all(ly.image.size() == QSize(200, 100) for ly in doc.layers) and QColor(doc.layers[0].image.pixel(50, 50)).name() == "#ff0000"
   and QColor.fromRgba(doc.layers[1].image.pixel(100, 30)).name() == "#000000", "crop cuts every layer")
c.undo()
ok(doc.size() == QSize(400, 300) and len(doc.layers) == 2, "undo crop of every layer")
# saving
tmpd = tempfile.mkdtemp()
doc.set_layer_props(1, name="Ink", opacity=0.75)
pane.add()
doc.set_layer_props(2, visible=False)
orap = os.path.join(tmpd, "layers.ora")
win._write(orap, "ora")
ok(doc.path == orap and not doc.modified, "save as OpenRaster")
seen = c.display_image().copy()
doc.new(10, 10)
ok(win.open_path(orap) and len(doc.layers) == 3, "open an OpenRaster file")
ok([ly.name for ly in doc.layers] == ["Background", "Ink", "Layer 3"] and abs(doc.layers[1].opacity - 0.75) < 0.01
   and not doc.layers[2].visible and doc.layers[0].image.format() == QImage.Format_RGB32, "layers come back as saved")
ok(const_pixels(c.display_image().convertToFormat(QImage.Format_ARGB32_Premultiplied)).tolist() ==
   const_pixels(seen.convertToFormat(QImage.Format_ARGB32_Premultiplied)).tolist(), "the reopened picture looks the same")
ok(not pane.isHidden(), "opening a layered file shows the Layers pane")
pngp = os.path.join(tmpd, "flat.png")
from PySide6.QtWidgets import QMessageBox as _MB  # noqa: E402
_asked = []
_orig_warn = _MB.warning
_MB.warning = staticmethod(lambda *a, **k: _asked.append(a[2]) or _MB.No)
ok(not win._write(pngp, "png") and len(_asked) == 1 and "layers" in _asked[0] and not os.path.exists(pngp)
   and doc.path == orap, "saving layers to a file type that cannot keep them asks first; No saves nothing")
_MB.warning = staticmethod(lambda *a, **k: _asked.append(a[2]) or _MB.Yes)
ok(win._write(pngp, "png") and len(_asked) == 2, "Yes saves the merged picture")
ok(win._write(pngp, "png") and len(_asked) == 2, "the same file is not asked about twice")
_MB.warning = _orig_warn
flat = load_image(pngp)
ok(len(doc.layers) == 3 and QColor(flat.pixel(200, 50)).name() == cpx(200, 50).name(), "PNG saves the picture as seen")
pane.merge()
pane.activate(1)
pane.merge()
ok(len(doc.layers) == 1 and QColor(doc.image.pixel(200, 50)).red() == cpx(200, 50).red(), "merge down")
c.undo()
c.undo()
pane.flatten()
ok(len(doc.layers) == 1 and doc.image.format() == QImage.Format_RGB32, "flatten picture")
c.undo()
pane.rename(1)
pane._editor[0].setText("Lines")
pane._finish_rename(1)
ok(doc.layers[1].name == "Lines", "rename a layer")
# autosave keeps layers
lsaver = AutoSaver(win, interval=10 ** 9, folder=tempfile.mkdtemp())
doc.changed.emit()
lsaver.save_now(wait=True)
ok(len(load_ora(lsaver.png)) == 3, "the recovery copy keeps every layer")
lsaver.clear()
lsaver.timer.stop()
win.set_layers_pane(False)
doc.new(800, 600)
ok(len(doc.layers) == 1, "a new picture has one layer")

# ---- object selection ---------------------------------------------------------------------
def figure(p, cx, cy, s, body):
    p.setPen(QPen(QColor(0, 0, 0), 3 * s))
    p.setBrush(body)
    p.drawRoundedRect(QRectF(cx - 28 * s, cy - 5 * s, 56 * s, 65 * s), 14 * s, 14 * s)
    p.setBrush(QColor(255, 214, 170))
    p.drawEllipse(QRectF(cx - 32 * s, cy - 70 * s, 64 * s, 64 * s))
    for ex in (-12, 12):                     # white eyes with pupils: enclosed, same colour as the background
        p.setPen(QPen(QColor(0, 0, 0), 2 * s))
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(cx + (ex - 7) * s, cy - 52 * s, 14 * s, 16 * s))


st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 255, 255))
doc.new(600, 400)
pp = QPainter(doc.image)
pp.setRenderHint(QPainter.Antialiasing, True)
pp.fillRect(400, 0, 200, 400, QColor(255, 255, 255))
figure(pp, 150, 200, 1.4, QColor(40, 90, 210))
figure(pp, 330, 220, 1.0, QColor(220, 60, 60))
pp.end()
doc.changed.emit()
c.set_zoom(1.0)
st.set_tool("select")
st.set_sel_mode("object")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(150, 230))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.mask is not None and s.soft is not None, "object selection makes a soft-edged selection")
r = s.rect
ok(abs(r.left() - 103) <= 3 and abs(r.right() - 197) <= 3 and abs(r.top() - 100) <= 3 and abs(r.bottom() - 286) <= 3,
   f"object selection covers the whole first figure ({r.left()},{r.top()})-({r.right()},{r.bottom()})")
ok(bool(s.mask[133 - r.top(), 133 - r.left()]), "the enclosed white eye is part of the object")
ok(not s.mask[110 - r.top(), 110 - r.left()] if r.contains(QPoint(110, 110)) else True,
   "the background beside the head is not part of the object")
# move it onto a red area: no white fringe
pp = QPainter(doc.image)
pp.fillRect(420, 0, 180, 400, QColor(255, 0, 0))
pp.end()
doc.changed.emit()
drag([(150, 230), (300, 230), (450 + 0, 230)])
c.commit_pending()
a_ = const_pixels(doc.image).astype(np.int64)
reg = a_[100:290, 424:500]                   # the part that landed on red
R_, G_, B_ = (reg >> 16) & 255, (reg >> 8) & 255, reg & 255
whitish = (G_ > 150) & (B_ > 150) & (np.abs(G_ - B_) < 25)     # skin and body colours are not whitish
eyes = np.zeros_like(whitish)
eyes[20:50, :] = True                                             # rows of the white eyes
ok(int((whitish & ~eyes).sum()) < 10,
   "a moved object carries no fringe of the old background")
ok(px(150, 230) == WHITE, "the old place is filled with colour 2")
c.undo()
ok(px(150, 230) == "#2a5bd2" or QColor(doc.image.pixel(150, 230)).blue() > 150, "undo the move")
# shift+click adds the other figure; clicking the background takes every object
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(150, 230))
QTest.mouseClick(vpw, Qt.LeftButton, Qt.ShiftModifier, vp(330, 240))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect.left() <= 105 and s.rect.right() >= 355, "shift+click adds another object")
c.commit_pending()
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(20, 20))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect.left() <= 105 and s.rect.right() >= 355 and s.rect.right() < 420,
   "clicking the background selects every object")
c.copy()
clip = QGuiApplication.clipboard().image()
ok(not clip.isNull() and clip.size() == s.rect.size(), "copy an object selection")
c.commit_pending()
# ctrl+click takes an object out of the selection; ctrl+drag still moves a copy
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(150, 230))
QTest.mouseClick(vpw, Qt.LeftButton, Qt.ShiftModifier, vp(330, 240))
QTest.mouseClick(vpw, Qt.LeftButton, Qt.ControlModifier, vp(150, 230))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect.left() > 250 and s.soft is not None, "ctrl+click removes an object from the selection")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.ControlModifier, vp(330, 240))
app.processEvents()
ok(c.select_tool.sel is None, "removing the last object leaves nothing selected")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(330, 240))
app.processEvents()
drag([(330, 240), (360, 240), (400, 240), (440, 240)], mods=Qt.ControlModifier)
c.commit_pending()
ok(QColor(doc.image.pixel(330, 240)).red() > 180 and QColor(doc.image.pixel(440, 240)).red() > 180,
   "ctrl+drag on an object selection moves a copy")
c.undo()
st.set_sel_mode("rect")

# ---- polygon selection (0.3.3) -----------------------------------------------------------
def click(x, y, mods=Qt.NoModifier, button=Qt.LeftButton):
    QTest.mouseClick(vpw, button, mods, vp(x, y))
    app.processEvents()


def hover(x, y, mods=Qt.NoModifier):
    app.sendEvent(vpw, QMouseEvent(QEvent.MouseMove, QPointF(vp(x, y)), QPointF(vpw.mapToGlobal(vp(x, y))),
                                   Qt.NoButton, Qt.NoButton, mods))
    app.processEvents()


doc.new(400, 300)
RED = QColor(200, 30, 30)
doc.image.fill(RED)
doc.changed.emit()
st.set_color(2, QColor(255, 255, 255))
st.set_sel_mode("poly")
st.set_tool("select")
sel = c.select_tool
click(50, 50)
ok(sel.building and len(sel.poly) == 1 and sel.sel is None, "first click starts a polygon selection")
hover(120, 80)
ok(sel.poly_cur == QPoint(120, 80), "the next side follows the mouse between clicks")
click(150, 50)
click(50, 150)
ok(len(sel.poly) == 3 and sel.building, "each click adds a corner")
hover(51, 51)
ok(sel.hover_closes(), "the first corner lights up under the mouse")
vpw.repaint()
click(51, 51)
ok(not sel.building and sel.sel is not None and sel.sel.rect == QRect(50, 50, 100, 100)
   and sel.sel.path is not None and len(sel.sel.outline) == 3, "clicking the first corner closes the polygon")
vpw.repaint()
QTest.keyClick(c, Qt.Key_Delete)
ok(px(60, 60) == WHITE and px(140, 140) == RED.name() and px(40, 40) == RED.name(),
   "delete clears the polygon, not its bounding rectangle")
c.undo()
ok(px(60, 60) == RED.name(), "undo brings the deleted polygon back")
# double-click closes
for pt in ((200, 50), (300, 50), (300, 150)):
    click(*pt)
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(200, 150))
QTest.mouseDClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(200, 150))
app.processEvents()
ok(not sel.building and sel.sel is not None and sel.sel.rect == QRect(200, 50, 100, 100),
   "double-click closes the polygon")
# moving it moves only the polygon's pixels
doc.image.fill(RED)
drag([(250, 100), (250, 150), (250, 200)])
c.commit_pending()
ok(px(250, 60) == WHITE and px(250, 260) == RED.name(), "a polygon selection can be moved")
c.undo()
ok(px(250, 60) == RED.name(), "undo of the move")
# Enter, Backspace, Ctrl+Z, Esc, right-click
for pt in ((20, 200), (80, 200), (80, 260), (20, 260)):
    click(*pt)
QTest.keyClick(c, Qt.Key_Backspace)
ok(sel.building and len(sel.poly) == 3, "backspace takes back the last corner")
can = doc.can_undo()
before = QImage(doc.image)
c.undo()
ok(sel.building and len(sel.poly) == 2 and doc.image == before and doc.can_undo() == can,
   "ctrl+z takes back a corner instead of undoing the picture")
ok(win.q_undo.isEnabled(), "undo is available while a polygon is being made")
click(80, 260)
QTest.keyClick(c, Qt.Key_Return)
ok(not sel.building and sel.sel is not None and sel.sel.rect == QRect(20, 200, 60, 60), "enter closes the polygon")
QTest.keyClick(c, Qt.Key_Escape)
ok(sel.sel is None, "esc drops the selection")
click(20, 20)
click(60, 20)
QTest.keyClick(c, Qt.Key_Return)
ok(not sel.building and sel.sel is None, "two corners select nothing")
click(20, 20)
click(60, 20)
click(60, 60)
QTest.keyClick(c, Qt.Key_Escape)
ok(not sel.building and sel.sel is None and not sel.poly, "esc cancels a polygon being made")
click(20, 20)
click(60, 20)
click(60, 60, button=Qt.RightButton)
ok(not sel.building and sel.sel is None, "right-click cancels a polygon being made")
click(20, 20)
QTest.keyClick(c, Qt.Key_Backspace)
ok(not sel.building, "backspace on the only corner cancels")
# Shift keeps sides straight or at 45 degrees
click(100, 100)
click(200, 108, mods=Qt.ShiftModifier)
click(260, 175, mods=Qt.ShiftModifier)
click(262, 280, mods=Qt.ShiftModifier)
ok(sel.poly[1] == QPoint(200, 100) and sel.poly[2].x() - 200 == sel.poly[2].y() - 100
   and sel.poly[3].x() == sel.poly[2].x(), "shift snaps sides to straight and 45-degree lines")
st.set_sel_mode("rect")
ok(not sel.building and not sel.poly, "changing the selection shape drops the unfinished polygon")
st.set_sel_mode("poly")
click(100, 100)
click(200, 100)
st.set_tool("pencil")
ok(not sel.building, "changing tool drops the unfinished polygon")
st.set_tool("select")
# corners outside the picture are pulled in; a line selects nothing
drag([(350, 250), (500, 250)])
click(500, 400)
QTest.keyClick(c, Qt.Key_Return)
ok(sel.sel is not None and sel.sel.rect == QRect(350, 250, 50, 50), "corners stay inside the picture")
QTest.keyClick(c, Qt.Key_Escape)
click(10, 10)
click(50, 50)
click(90, 90)
QTest.keyClick(c, Qt.Key_Return)
ok(sel.sel is None, "three corners in a line select nothing")
# on a layer: delete clears to see-through
doc.add_layer()
doc.image.fill(QColor(0, 0, 255))
doc.changed.emit()
for pt in ((100, 100), (200, 100), (100, 200)):
    click(*pt)
QTest.keyClick(c, Qt.Key_Return)
QTest.keyClick(c, Qt.Key_Delete)
ok((doc.image.pixel(110, 110) >> 24) == 0
   and (doc.image.pixel(190, 190) >> 24) == 255, "polygon delete on a layer clears to see-through")
ok(QColor(c.display_image().pixel(110, 110)).name() == RED.name(), "the layer below shows through the hole")
c.undo()
c.undo()
ok(len(doc.layers) == 1, "undo removes the layer again")
c.invert_selection()
for pt in ((100, 100), (200, 100), (100, 200)):
    click(*pt)
QTest.keyClick(c, Qt.Key_Return)
c.invert_selection()
ok(sel.sel is not None and sel.sel.rect == doc.rect(), "invert a polygon selection")
QTest.keyClick(c, Qt.Key_Delete)
ok(px(110, 110) == RED.name() and px(190, 190) == WHITE and px(5, 5) == WHITE, "delete everything but the polygon")
c.undo()
st.set_sel_mode("rect")

# ---- copying a shaped selection keeps its surround see-through (0.3.4) ---------------------
def alpha(img, x, y):
    return (img.pixel(x, y) >> 24) & 0xFF


def clip_image():
    return QGuiApplication.clipboard().image().convertToFormat(QImage.Format_ARGB32)


BLUE = QColor(20, 40, 220)
doc.new(400, 300)
doc.image.fill(RED)
doc.changed.emit()
st.set_sel_mode("poly")
st.set_tool("select")
for pt in ((50, 50), (150, 50), (50, 150)):
    click(*pt)
QTest.keyClick(c, Qt.Key_Return)
c.copy()
clip = clip_image()
ok(clip.size() == QSize(100, 100) and alpha(clip, 10, 10) == 255 and QColor(clip.pixel(10, 10)).name() == RED.name()
   and alpha(clip, 90, 90) == 0, "copying a polygon leaves the rest of its rectangle see-through")
QTest.keyClick(c, Qt.Key_Escape)
doc.image.fill(BLUE)
doc.changed.emit()
c.paste()
QTest.keyClick(c, Qt.Key_Escape)
ok(px(10, 10) == RED.name() and px(90, 90) == BLUE.name(), "pasting a copied polygon pastes only the polygon")
# cut from the background, paste on a new layer (what the user did)
doc.image.fill(RED)
doc.changed.emit()
for pt in ((50, 50), (150, 50), (50, 150)):
    click(*pt)
QTest.keyClick(c, Qt.Key_Return)
c.cut()
ok(px(60, 60) == WHITE and px(140, 140) == RED.name(), "cutting a polygon leaves a polygon-shaped hole")
doc.add_layer()
c.paste()
QTest.keyClick(c, Qt.Key_Escape)
ok(alpha(doc.image, 10, 10) == 255 and alpha(doc.image, 90, 90) == 0 and alpha(doc.image, 200, 200) == 0,
   "a cut polygon pasted on a new layer has no rectangle around it")
ok(alpha(doc.image, 90, 30) == 0 and QColor(c.display_image().pixel(90, 30)).name() == RED.name(),
   "the background shows around the pasted polygon")
c.undo()
c.undo()
c.undo()
ok(len(doc.layers) == 1 and px(60, 60) == RED.name(), "undo the paste, the layer and the cut")
# a moved (lifted) polygon keeps its shape on the clipboard too
for pt in ((50, 50), (150, 50), (50, 150)):
    click(*pt)
QTest.keyClick(c, Qt.Key_Return)
drag([(70, 70), (100, 100), (170, 170)])
c.copy()
clip = clip_image()
ok(alpha(clip, 10, 10) == 255 and alpha(clip, 90, 90) == 0, "a moved polygon is copied without its rectangle")
c.undo()
# free-form and magic wand
st.set_sel_mode("free")
drag([(50, 50), (150, 50), (50, 150), (50, 60)])
c.copy()
clip = clip_image()
ok(alpha(clip, 10, 10) == 255 and alpha(clip, clip.width() - 5, clip.height() - 5) == 0,
   "copying a free-form selection leaves the rest see-through")
QTest.keyClick(c, Qt.Key_Escape)
doc.new(400, 300)
p = QPainter(doc.image)
p.setBrush(RED)
p.setPen(Qt.NoPen)
p.drawEllipse(100, 100, 100, 100)
p.end()
doc.changed.emit()
st.set_sel_mode("wand")
click(150, 150)
c.copy()
clip = clip_image()
ok(alpha(clip, clip.width() // 2, clip.height() // 2) == 255 and alpha(clip, 1, 1) == 0,
   "copying a magic wand selection leaves the rest see-through")
QTest.keyClick(c, Qt.Key_Escape)
# a plain rectangle is still a plain picture
st.set_sel_mode("rect")
drag([(90, 90), (150, 150), (210, 210)])
c.copy()
raw = QGuiApplication.clipboard().image()
ok(not raw.hasAlphaChannel() and raw.size() == QSize(120, 120), "a rectangular copy is a plain picture")
QTest.keyClick(c, Qt.Key_Escape)

# ---- polygon shape: preview line, backspace, shift (0.3.3) --------------------------------
doc.new(400, 300)
st.set_tool("shape", shape="polygon")
st.set_color(1, QColor(0, 0, 0))
tool = c.tool
drag([(50, 50), (150, 50)])
shown = int((const_pixels(c.display_image()) != 0xFFFFFFFF).sum())
hover(150, 150)
ok(int((const_pixels(c.display_image()) != 0xFFFFFFFF).sum()) > shown * 1.5 and ink() == 0,
   "polygon shape: the next side follows the mouse between clicks")
click(150, 150)
click(52, 157, mods=Qt.ShiftModifier)
ok(tool.pts[-1] == QPoint(52, 150), "polygon shape: shift keeps the side straight")
QTest.keyClick(c, Qt.Key_Backspace)
ok(len(tool.pts) == 3 and tool.has_pending(), "polygon shape: backspace takes back the last corner")
hover(300, 280)
QTest.keyClick(c, Qt.Key_Return)
ok(not tool.has_pending() and ink() > 0 and px(300, 280) == WHITE and px(250, 240) == WHITE,
   "polygon shape: the preview side is not drawn into the picture")
c.undo()
ok(ink() == 0, "polygon shape undo")
click(50, 50)
QTest.keyClick(c, Qt.Key_Backspace)
ok(not tool.pts, "polygon shape: backspace on the only corner cancels")
st.set_tool("select")

# ---- 0.2.1 regressions -----------------------------------------------------------------
from PySide6.QtWidgets import QMessageBox  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from opendraw7.brushes import ReplaceStroke  # noqa: E402
_warned = []
_orig_warning = QMessageBox.warning
QMessageBox.warning = staticmethod(lambda *a, **k: _warned.append(a[2]) or QMessageBox.Ok)
doc.new(800, 600)
c.resize_skew(30000, 30000)
ok(doc.size() == QSize(800, 600) and _warned, "a too-large resize is refused with a message")
_warned.clear()
c.resize_skew(800, 600, 89, 89)
ok(doc.size() == QSize(800, 600) and _warned, "a too-large skew is refused with a message")
ok(not doc.resize_canvas(30000, 30000, QColor(255, 255, 255)) and doc.size() == QSize(800, 600),
   "a too-large canvas is refused")
c.resize_skew(1600, 1200)
ok(doc.size() == QSize(1600, 1200), "ordinary resizes still work")
c.undo()
QMessageBox.warning = _orig_warning
# right-button eraser leaves see-through pixels alone
doc.new(200, 100)
doc.set_transparent(True)
pp = QPainter(doc.image)
pp.setCompositionMode(QPainter.CompositionMode_Clear)
pp.fillRect(0, 0, 100, 100, QColor(0, 0, 0))
pp.end()
rs = ReplaceStroke(doc.image, QColor(255, 255, 255), 10, QColor(0, 0, 0))
rs.start(QPointF(50, 50))
rs.line_to(QPointF(60, 50))
ok(doc.image.pixel(50, 50) == 0, "right-button eraser keeps see-through pixels see-through")
doc.new(800, 600)
# big photos open (Qt refuses over 256 MB by default)
bigp = os.path.join(tempfile.mkdtemp(), "big.png")
bimg = QImage(12000, 6000, QImage.Format_RGB32)
bimg.fill(QColor(10, 20, 30))
bimg.save(bigp)
del bimg
ok(load_image(bigp).size() == QSize(12000, 6000), "a 12000 x 6000 photo opens")
# zoom label after fit to window
lab = win.status.zoomer.label
ok(lab(0.634722) == "63%" and lab(0.125) == "12.5%" and lab(0.25) == "25%" and lab(8) == "800%",
   "zoom label is rounded")

# ---- key tips -------------------------------------------------------------------------
win.activateWindow()
QTest.qWait(100)
if win.isActiveWindow():
    QTest.keyPress(c, Qt.Key_Alt)
    QTest.keyRelease(c, Qt.Key_Alt)
    ok(win.keytips.level == 1 and {"F", "H", "V"} <= {t.keys for t in win.keytips.overlay.tips}, "alt shows key tips")
    QTest.keyClick(c, Qt.Key_H)
    QTest.keyClick(c, Qt.Key_P)
    QTest.qWait(30)
    ok(st.tool == "pencil" and win.keytips.level == 0, "key tips H, P pick the pencil")
    QTest.keyClick(c, Qt.Key_F10)
    QTest.keyClick(c, Qt.Key_V)
    QTest.keyClick(c, Qt.Key_G)
    QTest.qWait(30)
    ok(c.show_grid and win.ribbon.current() == win.view_idx, "key tips F10, V, G show gridlines")
    win.set_grid(False)
    win.ribbon.set_current(win.home_idx)
    QTest.keyClick(c, Qt.Key_F10)
    QTest.keyClick(c, Qt.Key_Escape)
    ok(win.keytips.level == 0, "esc hides key tips")
    for seq in ([(QEvent.KeyPress, Qt.Key_Alt, Qt.NoModifier), (QEvent.KeyRelease, Qt.Key_Alt, Qt.AltModifier | Qt.ShiftModifier)],
                [(QEvent.KeyPress, Qt.Key_Shift, Qt.NoModifier), (QEvent.KeyPress, Qt.Key_Alt, Qt.ShiftModifier),
                 (QEvent.KeyRelease, Qt.Key_Alt, Qt.AltModifier | Qt.ShiftModifier)]):
        for typ, key, mod in seq:
            app.sendEvent(c, QKeyEvent(typ, key, mod))
        ok(win.keytips.level == 0, "alt+shift (keyboard layout switch) does not show key tips")
        win.keytips.hide()

# ---- 0.3.5: review fixes ------------------------------------------------------------------
import stat  # noqa: E402
import opendraw7.document as _docmod  # noqa: E402
from opendraw7.document import load_ora, replace_file  # noqa: E402
from opendraw7.tools import snap45  # noqa: E402
_told = []
_orig_info, _orig_warn2 = _MB.information, _MB.warning
_MB.information = staticmethod(lambda *a, **k: _told.append(a[2]) or _MB.Ok)
_MB.warning = staticmethod(lambda *a, **k: _told.append(a[2]) or _MB.Yes)
# the colour picker leaves the colour alone on a see-through pixel (it used to pick black)
doc.new(100, 100)
doc.set_transparent(True)
doc.image.fill(0)
p = QPainter(doc.image)
p.fillRect(60, 60, 20, 20, QColor(0, 200, 0, 128))
p.end()
doc.changed.emit()
st.set_color(1, QColor(255, 0, 0))
st.set_tool("pencil")
st.set_tool("picker")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(20, 20))
ok(st.color1.name() == "#ff0000", "the colour picker ignores see-through pixels")
st.set_tool("picker")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(70, 70))
ok(st.color1.green() >= 198 and st.color1.red() <= 2 and st.color1.alpha() == 255,
   "the colour picker takes a half see-through pixel's own colour")
# undo keeps its steps on a layered picture: layers a step did not change are not counted again
doc.new(400, 300)
for _ in range(3):
    doc.add_layer()
doc.undo_stack.clear()
_old_bytes = _docmod.UNDO_BYTES
_docmod.UNDO_BYTES = 4 * 1024 * 1024               # one layer is 0.46 MB, the four together 1.8 MB
st.set_tool("pencil")
st.set_color(1, QColor(0, 0, 0))
for k in range(8):
    drag([(10 + 10 * k, 10), (10 + 10 * k, 200)])
ok(len(doc.undo_stack) == 8, "undo keeps every step it has room for on a picture with layers")
for k in range(30):
    drag([(100 + 5 * k, 20), (100 + 5 * k, 220)])
ok(3 <= len(doc.undo_stack) < 38 and doc._undo_bytes() <= _docmod.UNDO_BYTES + doc.image.sizeInBytes(), "undo still lets go of the oldest steps")
_docmod.UNDO_BYTES = _old_bytes
# text is the same size whatever DPI the opened file claims, on every layer, before and after saving
tmp5 = tempfile.mkdtemp()
hi = QImage(400, 200, QImage.Format_RGB32)
hi.fill(QColor(255, 255, 255))
hi.setDotsPerMeterX(11811)
hi.setDotsPerMeterY(11811)
hi.save(os.path.join(tmp5, "dpi300.png"))


def text_height():
    st.set_tool("text")
    c.text_tool._create(QRect(10, 10, 300, 60))
    c.text_tool.insert_text("Hg")
    before = const_pixels(doc.image).copy()
    c.commit_pending()
    ys = np.flatnonzero((const_pixels(doc.image) != before).any(axis=1))
    c.undo()
    return int(ys[-1] - ys[0] + 1) if len(ys) else 0


doc.new(400, 200)
plain = text_height()
ok(win.open_path(os.path.join(tmp5, "dpi300.png")) and doc.image.dotsPerMeterX() == 11811, "a 300 DPI file opens")
on_photo = text_height()
doc.add_layer()
on_layer = text_height()
c.undo()
ok(plain > 5 and plain == on_photo == on_layer, "text is the same size on a 300 DPI photo and on its layers")
doc.save(os.path.join(tmp5, "again.png"), "png")
ok(doc.image.dotsPerMeterX() == 11811 and text_height() == plain, "saving does not change the picture's DPI or the text size")
# a save that fails leaves the old file alone; links and permissions survive a good one
keep = os.path.join(tmp5, "keep.png")
with open(keep, "wb") as f:
    f.write(b"old contents")
try:
    save_image(QImage(), keep, "png")
    failed = False
except OSError:
    failed = True
ok(failed and open(keep, "rb").read() == b"old contents" and sorted(os.listdir(tmp5)) == ["again.png", "dpi300.png", "keep.png"],
   "a failed save leaves the old file and no leftovers")


def _half(tmp):
    with open(tmp, "wb") as f:
        f.write(b"half")
    raise OSError("disk full")


try:
    replace_file(keep, _half)
except OSError:
    pass
ok(open(keep, "rb").read() == b"old contents" and len(os.listdir(tmp5)) == 3, "a save cut short leaves the old file")
os.chmod(keep, 0o600)
link = os.path.join(tmp5, "link.png")
os.symlink(keep, link)
save_image(doc.image, link, "png")
ok(os.path.islink(link) and load_image(keep).size() == doc.size() and stat.S_IMODE(os.stat(keep).st_mode) == 0o600,
   "saving through a link keeps the link and the file's permissions")
for fmt_key in ("bmp24", "gif", "jpeg", "tiff", "ora"):
    out_path = os.path.join(tmp5, "f." + fmt_key)
    save_image(doc.image, out_path, fmt_key)
    ok(os.path.getsize(out_path) > 0, f"save {fmt_key} through a temporary file")
ok(not [n for n in os.listdir(tmp5) if n.endswith(".tmp")], "no temporary files are left behind")
# broken OpenRaster files are refused cleanly and leave the open picture as it was
import zipfile  # noqa: E402
bad = {}
for name, files in (("nostack", {"mimetype": "image/openraster"}),
                    ("nosize", {"stack.xml": "<image><stack/></image>"}),
                    ("badxml", {"stack.xml": "<image w='5' h='5'><stack>"}),
                    ("empty", {"stack.xml": "<image w='5' h='5'><stack/></image>"}),
                    ("huge", {"stack.xml": "<image w='900000' h='900000'><stack><layer src='a.png'/></stack></image>",
                              "a.png": open(os.path.join(tmp5, "again.png"), "rb").read()}),
                    ("zero", {"stack.xml": "<image w='0' h='0'><stack><layer src='a.png'/></stack></image>"})):
    bad[name] = os.path.join(tmp5, name + ".ora")
    with zipfile.ZipFile(bad[name], "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
bad["text"] = os.path.join(tmp5, "text.ora")
with open(bad["text"], "w") as f:
    f.write("not a zip file")
doc.new(123, 77)
for name, path5 in bad.items():
    try:
        load_ora(path5)
        raised = False
    except OSError:
        raised = True
    except Exception:
        raised = False
    ok(raised, f"a broken OpenRaster file ({name}) is reported as unreadable")
    _told.clear()
    ok(not win.open_path(path5) and _told and doc.size() == QSize(123, 77) and doc.image.format() == QImage.Format_RGB32,
       f"opening a broken OpenRaster file ({name}) leaves the picture alone")
# Shift on the Line shape: the end stays beside the mouse on diagonals
ok(snap45(QPoint(100, 100), QPoint(200, 190)) == QPoint(195, 195) and snap45(QPoint(0, 0), QPoint(-40, 3)) == QPoint(-40, 0)
   and snap45(QPoint(0, 0), QPoint(2, -50)) == QPoint(0, -50) and snap45(QPoint(0, 0), QPoint(-30, 34)) == QPoint(-32, 32),
   "snapping to 45-degree lines")
doc.new(400, 300)
st.set_tool("shape", shape="line")
drag([(100, 100), (150, 140), (200, 190)], mods=Qt.ShiftModifier)
ok(c.tool.p1 == QPoint(195, 195), "a Shift line ends beside the mouse, not short of it")
c.tool.cancel()
# a hidden layer cannot be drawn on by mistake
doc.new(200, 150)
doc.add_layer()
doc.set_layer_props(1, visible=False)
doc.undo_stack.clear()
st.set_tool("pencil")
_told.clear()
before5 = const_pixels(doc.image).copy()
drag([(20, 20), (100, 100)])
ok(len(_told) == 1 and "hidden" in _told[0] and np.array_equal(before5, const_pixels(doc.image)) and not doc.undo_stack,
   "drawing on a hidden layer is refused with a message")
doc.set_layer_props(1, visible=True, opacity=0.0)
_told.clear()
drag([(20, 20), (100, 100)])
ok(len(_told) == 1 and "opacity" in _told[0] and np.array_equal(before5, const_pixels(doc.image)),
   "drawing on a layer with no opacity is refused with a message")
doc.set_layer_props(1, opacity=1.0)
_told.clear()
drag([(20, 20), (100, 100)])
ok(not _told and (doc.image.pixel(60, 60) >> 24) == 255, "a shown layer can be drawn on again")
# what is painted on screen is the blend of the layers
doc.new(300, 200)
doc.image.fill(QColor(250, 240, 200))
doc.add_layer()
p = QPainter(doc.image)
p.fillRect(40, 30, 120, 90, QColor(200, 30, 30))
p.end()
doc.set_layer_props(1, opacity=0.6)
doc.add_layer()
p = QPainter(doc.image)
p.fillRect(100, 60, 120, 90, QColor(20, 60, 220, 150))
p.end()
doc.set_active(1)
doc.changed.emit()
c.set_zoom(1.0)
app.processEvents()
shot = vpw.grab().toImage().convertToFormat(QImage.Format_RGB32)
want = c.display_image()
o5 = c.origin()
worst = 0
for x5, y5 in ((10, 10), (60, 50), (120, 80), (200, 130), (150, 100), (290, 190)):
    a5, b5 = QColor(shot.pixel(o5.x() + x5, o5.y() + y5)), QColor(want.pixel(x5, y5))
    worst = max(worst, abs(a5.red() - b5.red()), abs(a5.green() - b5.green()), abs(a5.blue() - b5.blue()))
ok(worst <= 2 and QColor(want.pixel(120, 80)).name() not in (WHITE, "#faf0c8"), "the screen shows the layers blended")
# renaming from the pane first lands a moved selection on its own layer
doc.new(200, 150)
doc.add_layer()
p = QPainter(doc.image)
p.fillRect(20, 20, 40, 40, QColor(0, 0, 0))
p.end()
doc.changed.emit()
st.set_tool("select")
st.set_sel_mode("rect")
drag([(10, 10), (70, 70)])
drag([(40, 40), (80, 60), (120, 80)])
pane.rename(0)
pane._close_editor()
ok(doc.active == 0 and (doc.layers[1].image.pixel(120, 80) >> 24) == 255 and px(120, 80) == WHITE,
   "renaming another layer drops a moved selection on its own layer first")
# desktop background: the file name reaches the desktop's tool whole, whatever characters it has
import stat as _stat  # noqa: E402
fake = tempfile.mkdtemp()
logf = os.path.join(fake, "log.txt")
with open(os.path.join(fake, "gsettings"), "w") as f:
    f.write('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a" >> "' + logf + '"; done\n')
os.chmod(os.path.join(fake, "gsettings"), 0o755)
odd = os.path.join(tempfile.mkdtemp(), "it's a $(touch x) picture.png")
_old_export, _old_path, _old_desk = win._export_copy, os.environ.get("PATH", ""), os.environ.get("XDG_CURRENT_DESKTOP")
win._export_copy = lambda name: odd
os.environ["PATH"] = fake + os.pathsep + _old_path
os.environ["XDG_CURRENT_DESKTOP"] = "GNOME"
_told.clear()
win.set_wallpaper("fill")
os.environ["PATH"] = _old_path
if _old_desk is None:
    del os.environ["XDG_CURRENT_DESKTOP"]
else:
    os.environ["XDG_CURRENT_DESKTOP"] = _old_desk
win._export_copy = _old_export
logged = open(logf).read().splitlines() if os.path.exists(logf) else []
from PySide6.QtCore import QUrl  # noqa: E402
ok(not _told and QUrl.fromLocalFile(odd).toString() in logged and "zoom" in logged and not os.path.exists("x"),
   "the desktop background command gets an awkward file name intact")
# Image Properties on a layered picture shows the background's own setting (it used to show the
# selected layer's, and OK then made the background see-through)
from opendraw7.dialogs import PropertiesDialog  # noqa: E402
doc.new(200, 150)
doc.add_layer()
dlg5 = PropertiesDialog(doc, win)
ok(doc.transparent and not dlg5.c_clear.isChecked() and dlg5.values()[3] is False,
   "Image Properties shows the background as not see-through while a layer is selected")
doc.set_transparent(dlg5.values()[3])
ok(not doc.background_transparent and doc.layers[0].image.format() == QImage.Format_RGB32,
   "OK in Image Properties leaves the background as it was")
dlg5.deleteLater()
# pictures from a scanner or camera do not pile up in the temporary folder
from opendraw7.scanner import AcquireDialog, discard  # noqa: E402
dlg6 = AcquireDialog(win)
scan_dir = os.path.dirname(dlg6.out)
with open(dlg6.out, "wb") as f:
    f.write(b"x")
discard(dlg6.out)
other = os.path.join(tmp5, "acquired.png")
discard(other)
discard(None)
ok(not os.path.exists(scan_dir) and os.path.isdir(tmp5), "an acquired picture's temporary folder is removed, and only that")
dlg6.deleteLater()
# moving or deleting an object selection leaves no pale ghost of its soft edge behind
for layered5 in (False, True):
    doc.new(400, 300)
    if layered5:
        doc.add_layer()
    else:
        p = QPainter(doc.image)                       # stripes that must come through untouched
        for x5 in range(0, 400, 20):
            p.fillRect(x5, 0, 10, 300, QColor(225, 235, 250))
        p.end()
    p = QPainter(doc.image)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(200, 30, 30))
    p.drawEllipse(QPointF(100.3, 150.2), 40.5, 40.5)
    p.end()
    doc.changed.emit()
    clean5 = QImage(doc.image)
    p = QPainter(clean5)                              # the same picture without the disc
    p.setCompositionMode(QPainter.CompositionMode_Source)
    for x5 in range(40, 160):
        p.fillRect(x5, 100, 1, 100, QColor(0, 0, 0, 0) if layered5 else
                   (QColor(225, 235, 250) if (x5 // 10) % 2 == 0 else QColor(255, 255, 255)))
    p.end()
    st.set_tool("select")
    st.set_sel_mode("object")
    QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(100, 150))
    app.processEvents()
    hole5 = c.select_tool.doc_mask()
    QTest.keyClick(c, Qt.Key_Delete)
    left5 = (const_pixels(doc.image) != const_pixels(clean5)) & ~hole5
    ok(hole5.sum() > 4000 and int(left5.sum()) == 0,
       "deleting an object leaves no ghost of its edge" + (" on a layer" if layered5 else " and the stripes whole"))
    c.undo()
    ok((doc.image.pixel(100, 150) & 0xFFFFFF) == 0xC81E1E, "undo brings the object back")
st.set_sel_mode("rect")
_MB.information, _MB.warning = _orig_info, _orig_warn2

doc.modified = False
win.close()
print(f"OK - {checks} checks passed")
