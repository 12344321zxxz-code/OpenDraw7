"""Randomized stress test: random tool, mouse, key, menu, layer and file actions on the real window.

    QT_QPA_PLATFORM=offscreen python tools/fuzz.py <seed> [actions]

Prints "SEED n: OK ..." or the failing action and traceback. Environment switches:
  UNDO_CHECK=1     after every action that changes the picture, undo must restore the exact pixels of
                   every layer and redo must bring the change back
  CHECK_PREMULT=1  no see-through layer may hold a colour channel above its alpha
  HANG=seconds     dump the stack and quit if nothing moves for this long (default 40)
Menus, dialogs and message boxes are stubbed out (they would wait for input for ever). Run a few
dozen seeds in each mode after any change to tools, selections, layers, undo or files.
"""
import sys, random, traceback, io, os, math, faulthandler
faulthandler.dump_traceback_later(int(os.environ.get("HANG", "40")), exit=True)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from opendraw7.app import create_app
app = create_app([])
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, QSize, QRect, QSettings
import tempfile
QSettings.setDefaultFormat(QSettings.IniFormat)          # keep the user's own settings out of it
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp())
from PySide6.QtGui import QMouseEvent, QColor, QImage, QGuiApplication
from PySide6.QtTest import QTest
from opendraw7.mainwindow import MainWindow
from opendraw7.brushes import BRUSHES, STYLES
from opendraw7.shapes import SHAPES
import numpy as np
from opendraw7.document import const_pixels

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
rng = random.Random(seed)
from PySide6.QtWidgets import QMenu, QMessageBox, QDialog
QMenu.exec = lambda self, *a, **k: None          # menus and dialogs would wait for input forever
import opendraw7.ribbon as _rb
_rb.RMenu.exec = lambda self, *a, **k: None
QMessageBox.exec = lambda self, *a, **k: 0
QDialog.exec = lambda self, *a, **k: 0
for name in ("warning", "information", "question", "critical"):
    setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.No))
win = MainWindow(); win.show(); app.processEvents()
st, c, doc = win.state, win.canvas, win.doc
vpw = c.viewport()
errors = []
real_stderr = sys.stderr
class Tee(io.StringIO):
    def write(self, s):
        if "Traceback" in s or "Error" in s:
            errors.append((len(log), s))
        return super().write(s)
cap = Tee(); sys.stderr = cap
sys.excepthook = lambda t, v, tb: real_stderr.write(''.join(traceback.format_exception(t, v, tb)))
log = []

def rp():
    w, h = doc.width(), doc.height()
    return (rng.randint(-20, w + 20), rng.randint(-20, h + 20))

def vp(x, y):
    p = c.to_view(QPointF(x, y)); return QPoint(int(p.x()), int(p.y()))

def mods():
    return rng.choice([Qt.NoModifier]*4 + [Qt.ShiftModifier, Qt.ControlModifier])

def drag(n=None):
    b = rng.choice([Qt.LeftButton]*3 + [Qt.RightButton])
    m = mods()
    pts = [rp() for _ in range(n or rng.randint(2, 6))]
    QTest.mousePress(vpw, b, m, vp(*pts[0]))
    for pt in pts[1:]:
        ev = QMouseEvent(QEvent.MouseMove, QPointF(vp(*pt)), QPointF(vpw.mapToGlobal(vp(*pt))), Qt.NoButton, b, m)
        app.sendEvent(vpw, ev)
    QTest.mouseRelease(vpw, b, m, vp(*pts[-1]))

def click():
    QTest.mouseClick(vpw, rng.choice([Qt.LeftButton, Qt.RightButton]) if rng.random() < .2 else Qt.LeftButton, mods(), vp(*rp()))

def dbl():
    QTest.mouseDClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(*rp()))

from PySide6.QtGui import QKeyEvent
def type_text(t):
    for ch in t:
        for typ in (QEvent.KeyPress, QEvent.KeyRelease):
            app.sendEvent(c, QKeyEvent(typ, Qt.Key_A if ch.isascii() and ch.isalpha() else Qt.Key_unknown, Qt.NoModifier, ch))

def ora_roundtrip():
    import tempfile
    c.commit_pending()
    before = c.display_image().convertToFormat(QImage.Format_ARGB32_Premultiplied)
    path = os.path.join(tempfile.mkdtemp(), "f.ora")
    win._write(path, "ora")
    win.open_path(path)
    after = c.display_image().convertToFormat(QImage.Format_ARGB32_Premultiplied)
    if not np.array_equal(const_pixels(before), const_pixels(after)):
        A, B = const_pixels(before), const_pixels(after)
        info = "size %s vs %s" % (A.shape, B.shape)
        if A.shape == B.shape:
            d = np.abs(A.view(np.uint8).astype(int) - B.view(np.uint8).astype(int))
            info += " maxdiff %d, pixels %d; layers %s" % (d.max(), int((A != B).sum()), [(ly.visible, ly.opacity, ly.image.format().value) for ly in doc.layers])
            if d.max() <= 1:
                return          # known: semi-transparent pixels can come back 1/255 off (Qt's unpremultiply)
        raise AssertionError("ORA round trip changed the picture: " + info)

def hover():
    pt = rp()
    app.sendEvent(vpw, QMouseEvent(QEvent.MouseMove, QPointF(vp(*pt)), QPointF(vpw.mapToGlobal(vp(*pt))), Qt.NoButton, Qt.NoButton, mods()))

def poly_clicks():
    for _ in range(rng.randint(2, 6)):
        QTest.mouseClick(vpw, Qt.LeftButton, mods(), vp(*rp()))
        if rng.random() < .4:
            hover()
    r = rng.random()
    if r < .4:
        QTest.keyClick(c, Qt.Key_Return)
    elif r < .6:
        dbl()

def fmt_roundtrip():
    """Save in a random format and open the file again; what can be kept must come back."""
    import tempfile
    from opendraw7.document import FORMAT_BY_KEY, has_transparency
    c.commit_pending()
    fmt = rng.choice(["png", "png", "tiff", "bmp24", "jpeg", "gif", "bmp8", "bmp4", "bmp1", "ora"])
    flat = doc.flattened()
    before = flat.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    clear = has_transparency(flat)
    n_layers = len(doc.layers)
    path = os.path.join(tempfile.mkdtemp(), "f." + FORMAT_BY_KEY[fmt][1][0])
    doc.save(path, fmt)
    if not win.open_path(path):
        raise AssertionError(f"could not reopen a {fmt} file Paint wrote")
    after = doc.flattened().convertToFormat(QImage.Format_ARGB32_Premultiplied)
    if after.size() != before.size():
        raise AssertionError(f"{fmt} round trip changed the size {before.size()} -> {after.size()}")
    if fmt == "ora" and len(doc.layers) != n_layers:
        raise AssertionError(f"ora round trip changed the number of layers {n_layers} -> {len(doc.layers)}")
    exact = fmt in ("png", "tiff", "ora") or (fmt == "bmp24" and not clear)
    if exact:
        A, B = const_pixels(before), const_pixels(after)
        d = np.abs(A.view(np.uint8).astype(int) - B.view(np.uint8).astype(int))
        if d.max() > 0:
            raise AssertionError(f"{fmt} round trip changed the picture: maxdiff {d.max()}, pixels {int((A != B).sum())}, clear={clear}")

actions = [
    ("fmt_rt", fmt_roundtrip),
    ("hover", hover), ("polyclicks", poly_clicks), ("polyclicks", poly_clicks),
    ("tool", lambda: st.set_tool(rng.choice(["pencil", "fill", "text", "eraser", "picker", "magnifier", "select", "brush"]))),
    ("brush", lambda: st.set_tool("brush", brush=rng.choice(BRUSHES)[0])),
    ("shape", lambda: st.set_tool("shape", shape=rng.choice(SHAPES)[0])),
    ("selmode", lambda: (st.set_sel_mode(rng.choice(["rect", "free", "wand", "object", "poly", "poly", "poly"])), st.set_tool("select"))),
    ("outline", lambda: st.set_outline(rng.choice(STYLES)[0])),
    ("fillstyle", lambda: st.set_fill(rng.choice(STYLES)[0])),
    ("size", lambda: st.set_size(rng.choice([1, 2, 3, 5, 8, 16, 40]))),
    ("color", lambda: st.set_color(rng.choice([1, 2]), QColor(rng.randint(0,255), rng.randint(0,255), rng.randint(0,255)))),
    ("transpsel", lambda: st.set_transparent(rng.random() < .5)),
    ("drag", drag), ("drag", drag), ("drag", drag), ("click", click), ("click", click), ("dbl", dbl),
    ("undo", c.undo), ("redo", c.redo),
    ("zoom", lambda: c.set_zoom(rng.choice([0.125, 0.25, 0.5, 1, 2, 3, 8]))),
    ("fit", c.zoom_to_fit),
    ("rotate", lambda: c.rotate(rng.choice(["r90", "l90", "180", "flipv", "fliph"]))),
    ("resize", lambda: c.resize_skew(rng.randint(1, 900), rng.randint(1, 700), rng.choice([0, 0, 10, -20]), rng.choice([0, 0, 15]))),
    ("invertc", c.invert_colors),
    ("selall", c.select_all), ("invsel", c.invert_selection), ("delete", c.delete_selection),
    ("crop", c.crop), ("copy", c.copy), ("cut", c.cut), ("paste", c.paste),
    ("transparent", lambda: doc.set_transparent(rng.random() < .5)),
    ("canvas", lambda: doc.resize_canvas(rng.randint(1, 1000), rng.randint(1, 800), st.color2)),
    ("new", lambda: doc.new(rng.randint(1, 900), rng.randint(1, 700))),
    ("key", lambda: QTest.keyClick(c, rng.choice([Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Escape,
                                                  Qt.Key_Delete, Qt.Key_Return, Qt.Key_Backspace, Qt.Key_A, Qt.Key_X]),
                                    rng.choice([Qt.NoModifier, Qt.NoModifier, Qt.ShiftModifier, Qt.ControlModifier]))),
    ("type", lambda: type_text(rng.choice(["hello", "a b", "שלום", "123"]))),
    ("commit", c.commit_pending),
    ("font", lambda: st.set_font(size=rng.choice([8, 11, 36, 72]), bold=rng.random() < .5)),
    ("textbg", lambda: st.set_text_opaque(rng.random() < .5)),
    ("grab", lambda: win.grab()),
    ("narrow", lambda: win.resize(rng.choice([520, 700, 1100, 1400]), rng.choice([360, 600, 900]))),
    ("refresh", win.refresh),
    ("l_add", lambda: win.layers_pane.add()), ("l_add", lambda: win.layers_pane.add()),
    ("l_dup", lambda: win.layers_pane.duplicate()), ("l_del", lambda: win.layers_pane.delete()),
    ("l_up", lambda: win.layers_pane.move(1)), ("l_down", lambda: win.layers_pane.move(-1)),
    ("l_merge", lambda: win.layers_pane.merge()), ("l_flat", lambda: win.layers_pane.flatten()),
    ("l_pick", lambda: win.layers_pane.activate(rng.randrange(len(doc.layers)))),
    ("l_pick", lambda: win.layers_pane.activate(rng.randrange(len(doc.layers)))),
    ("l_eye", lambda: win.layers_pane.toggle_visible(rng.randrange(len(doc.layers)))),
    ("l_opacity", lambda: win.layers_pane.slider.setValue(rng.choice([0, 30, 50, 100]))),
    ("l_pane", lambda: win.set_layers_pane(rng.random() < .7)),
    ("l_ora", lambda: ora_roundtrip()),
    ("keytips", lambda: [QTest.keyClick(c, Qt.Key_F10)] + [QTest.keyClick(c, rng.choice([Qt.Key_H, Qt.Key_V, Qt.Key_P, Qt.Key_F,
        Qt.Key_T, Qt.Key_E, Qt.Key_K, Qt.Key_M, Qt.Key_G, Qt.Key_R, Qt.Key_I, Qt.Key_O, Qt.Key_W, Qt.Key_Escape, Qt.Key_1, Qt.Key_2]))
        for _ in range(rng.randint(1, 3))] + [win.keytips.hide()]),
]
def snap():
    c.commit_pending()
    head = tuple((ly.image.width(), ly.image.height(), ly.image.format().value, ly.name, ly.visible,
                  round(ly.opacity, 4)) for ly in doc.layers) + (doc.active,)
    return (head, 0, 0, [const_pixels(ly.image).copy() for ly in doc.layers])
def same(a, b):
    return a[0] == b[0] and len(a[3]) == len(b[3]) and all(np.array_equal(x, y) for x, y in zip(a[3], b[3]))
UNDO_CHECK = os.environ.get("UNDO_CHECK") == "1"
skip_undo = {"fmt_rt", "hover", "l_pick", "l_pane", "l_ora", "keytips", "undo", "redo", "new", "zoom", "fit", "grab", "narrow", "refresh", "tool", "brush", "shape", "selmode",
             "outline", "fillstyle", "size", "color", "transpsel", "font", "textbg", "copy"}
for i in range(N):
    name, fn = rng.choice(actions)
    if UNDO_CHECK and name not in skip_undo:
        before = snap()
        depth = len(doc.undo_stack)
        try:
            fn(); app.processEvents()
        except Exception:
            errors.append((i, traceback.format_exc())); break
        after = snap()
        if name == "polyclicks" and len(doc.undo_stack) >= 50:
            log.append(name); continue        # the undo list is full, so its several edits cannot be counted
        if not same(before, after):
            if len(doc.undo_stack) <= depth and depth < 50:
                errors.append((i, f"UNDO: action {name!r} changed the picture but added no undo step\n"))
                break
            steps = max(1, len(doc.undo_stack) - depth)      # polyclicks can make several edits
            for _ in range(steps):
                c.undo()
            app.processEvents()
            back = snap()
            if not same(back, before):
                diff = "layers/size/format" if back[0] != before[0] else "pixels"
                nd = [int((x != y).sum()) for x, y in zip(back[3], before[3])] if back[0] == before[0] else None
                errors.append((i, f"UNDO: undoing {name!r} did not restore the picture ({diff}) tool={st.tool} shape={st.shape} selmode={st.sel_mode} depth={depth} now={len(doc.undo_stack)} steps={steps} diffpx={nd} layers={len(doc.layers)} active={doc.active} fmt={doc.image.format().value}\n")); break
            for _ in range(steps):
                c.redo()
            app.processEvents()
            again = snap()
            if not same(again, after):
                diff = "layers/size/format" if again[0] != after[0] else "pixels"
                errors.append((i, f"UNDO: redoing {name!r} did not bring the change back ({diff})\n")); break
        log.append(name)
        continue
    log.append(name); real_stderr.write(f"{i} {name}\n"); real_stderr.flush()
    try:
        fn()
        app.processEvents()
        c.display_image(); vpw.repaint()
        if os.environ.get("CHECK_PREMULT") == "1":
            for li, ly in enumerate(doc.layers):
                if ly.image.format() == QImage.Format_ARGB32_Premultiplied:
                    v = const_pixels(ly.image)
                    al = v >> 24
                    bad = (((v >> 16) & 255) > al) | (((v >> 8) & 255) > al) | ((v & 255) > al)
                    if bad.any():
                        yy, xx = np.nonzero(bad)
                        raise AssertionError(f"PREMULT: after {name!r} layer {li} has {int(bad.sum())} pixels with a channel above alpha, e.g. {hex(int(v[yy[0], xx[0]]))}; tool={st.tool} brush={st.brush} shape={st.shape} selmode={st.sel_mode} outline={st.outline} fill={st.fill} transpsel={st.transparent_sel}")
                elif ly.image.format() == QImage.Format_RGB32:
                    v = const_pixels(ly.image)
                    if ((v >> 24) != 255).any():
                        raise AssertionError(f"PREMULT: after {name!r} RGB32 layer {li} has non-opaque alpha bytes; tool={st.tool} selmode={st.sel_mode}")
    except Exception:
        errors.append((len(log), traceback.format_exc()))
    if errors:
        break
sys.stderr = real_stderr
if errors:
    print(f"SEED {seed}: error after {len(log)} actions; last actions: {log[-12:]}")
    print("".join(e[1] for e in errors)[-3000:])
    print("captured:", cap.getvalue()[-3000:])
else:
    print(f"SEED {seed}: OK {N} actions, doc {doc.size().width()}x{doc.size().height()} transparent={doc.transparent}")
doc.modified = False
