"""All icons are drawn here in code (original artwork, no bitmap assets)."""
import math
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, QPoint
from PySide6.QtGui import (QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF,
                           QLinearGradient, QRadialGradient, QFont, QImage, QIcon, QCursor,
                           QTransform)

from .shapes import shape_path

_cache = {}
_drawers = {}


def icon_fn(name, grid=16):
    def deco(f):
        _drawers[name] = (grid, f)
        return f
    return deco


def has(name):
    return name in _drawers


def image(name, size=None, enabled=True) -> QImage:
    grid, fn = _drawers[name]
    size = size or grid
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.scale(size / grid, size / grid)
    fn(p)
    p.end()
    if not enabled:
        img = grayed(img)
    return img


def pixmap(name, size=None, enabled=True) -> QPixmap:
    key = (name, size, enabled)
    pm = _cache.get(key)
    if pm is None:
        pm = QPixmap.fromImage(image(name, size, enabled))
        _cache[key] = pm
    return pm


def qicon(name, size=None) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, True), QIcon.Normal)
    ic.addPixmap(pixmap(name, size, False), QIcon.Disabled)
    return ic


def grayed(img: QImage) -> QImage:
    img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    h, w = img.height(), img.width()
    a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, :w * 4]
    a = a.reshape(h, w, 4).astype(np.float32)
    g = a[..., 0] * 0.11 + a[..., 1] * 0.59 + a[..., 2] * 0.30
    g = g * 0.55 + a[..., 3] * 0.45
    out = np.empty((h, w, 4), np.uint8)
    out[..., 0] = out[..., 1] = out[..., 2] = np.clip(g * 0.5, 0, 255)
    out[..., 3] = np.clip(a[..., 3] * 0.5, 0, 255)
    res = QImage(out.tobytes(), w, h, w * 4, QImage.Format_ARGB32_Premultiplied)
    return res.copy()


# ----------------------------------------------------------------- helpers --
def pen(c, w=1.0, cap=Qt.RoundCap, join=Qt.RoundJoin):
    q = QPen(QColor(c), w)
    q.setCapStyle(cap)
    q.setJoinStyle(join)
    return q


def poly(*xy):
    return QPolygonF([QPointF(xy[i], xy[i + 1]) for i in range(0, len(xy), 2)])


def lg(x1, y1, x2, y2, *stops):
    g = QLinearGradient(x1, y1, x2, y2)
    for pos, c in stops:
        g.setColorAt(pos, QColor(c))
    return QBrush(g)


def crisp(p, on=True):
    p.setRenderHint(QPainter.Antialiasing, not on)


INK = "#3b4654"
BLUE = "#2a62b8"
PAGE_EDGE = "#6b7f99"


def _page(p, x, y, w, h, fold=3.0, fill=None):
    path = QPainterPath()
    path.moveTo(x, y)
    path.lineTo(x + w - fold, y)
    path.lineTo(x + w, y + fold)
    path.lineTo(x + w, y + h)
    path.lineTo(x, y + h)
    path.closeSubpath()
    p.setPen(pen(PAGE_EDGE, 1, join=Qt.MiterJoin))
    p.setBrush(fill or lg(x, y, x, y + h, (0, "#ffffff"), (1, "#e4ecf7")))
    p.drawPath(path)
    p.setBrush(QColor("#c9d8ee"))
    p.drawPolygon(poly(x + w - fold, y, x + w - fold, y + fold, x + w, y + fold))


def _pencil(p):
    """Pencil along +x, tip at origin, length ~15."""
    p.setPen(pen("#6b5318", 0.6))
    p.setBrush(lg(0, -1.7, 0, 1.7, (0, "#ffe873"), (0.55, "#f6c62b"), (1, "#d9981a")))
    p.drawRect(QRectF(3.2, -1.7, 8.2, 3.4))
    p.setBrush(QColor("#f0d6aa"))
    p.drawPolygon(poly(0, 0, 3.2, -1.7, 3.2, 1.7))
    p.setBrush(QColor("#2d2d2d"))
    p.setPen(Qt.NoPen)
    p.drawPolygon(poly(0, 0, 1.3, -0.7, 1.3, 0.7))
    p.setPen(pen("#6b6b6b", 0.6))
    p.setBrush(lg(0, -1.7, 0, 1.7, (0, "#f2f2f2"), (1, "#9aa3ad")))
    p.drawRect(QRectF(11.4, -1.7, 1.4, 3.4))
    p.setPen(pen("#9c4a5c", 0.6))
    p.setBrush(lg(0, -1.7, 0, 1.7, (0, "#f7b1bf"), (1, "#dd7088")))
    p.drawRoundedRect(QRectF(12.8, -1.7, 2.2, 3.4), 0.8, 0.8)


def _bucket(p):
    """Tilted bucket pouring blue paint, on a 16 grid."""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(lg(9, 5, 15, 13, (0, "#58a6f0"), (1, "#1f5fc4")))
    blob = QPainterPath()
    blob.moveTo(8.6, 5.0)
    blob.cubicTo(12.0, 4.2, 15.2, 6.2, 15.0, 9.5)
    blob.cubicTo(14.9, 11.2, 14.4, 12.6, 13.8, 13.2)
    blob.cubicTo(13.4, 11.0, 12.6, 8.6, 9.2, 7.8)
    blob.closeSubpath()
    p.drawPath(blob)
    p.translate(6.6, 8.6)
    p.rotate(-38)
    p.setPen(pen("#4d5661", 0.8, join=Qt.MiterJoin))
    p.setBrush(lg(-4, 0, 4, 0, (0, "#fdfdfd"), (0.6, "#cfd6de"), (1, "#8f99a5")))
    p.drawPolygon(poly(-4, -3.4, 4, -3.4, 3.2, 4.4, -3.2, 4.4))
    p.setBrush(QColor("#2f7cd6"))
    p.drawEllipse(QRectF(-4, -4.6, 8, 2.4))
    p.setBrush(Qt.NoBrush)
    p.setPen(pen("#4d5661", 0.8))
    arc = QPainterPath()
    arc.moveTo(-4, -3.4)
    arc.cubicTo(-5.2, -8.0, 5.2, -8.0, 4, -3.4)
    p.drawPath(arc)
    p.restore()


def _lens(p, cx, cy, r, hx, hy, hw):
    p.setPen(pen("#7a5330", hw, cap=Qt.RoundCap))
    k = r * 0.72
    p.drawLine(QPointF(cx + k, cy + k), QPointF(hx, hy))
    g = QRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 1.3)
    g.setColorAt(0, QColor("#ffffff"))
    g.setColorAt(1, QColor("#9fcdf0"))
    p.setBrush(QBrush(g))
    p.setPen(pen("#56677a", max(1.2, r * 0.3)))
    p.drawEllipse(QPointF(cx, cy), r, r)


def _curved_arrow(p, color=BLUE, w=2.2):
    """Undo-style arrow on a 16 grid (points left)."""
    p.setPen(pen(color, w, cap=Qt.FlatCap))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(13.4, 13.0)
    path.cubicTo(13.6, 8.0, 10.5, 5.6, 6.2, 5.6)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon(poly(6.8, 1.6, 1.4, 5.6, 6.8, 9.6))


def _dashed_rect(p, r, color="#2b4e8c", dash=2.0, w=1.0, fill=None):
    q = QPen(QColor(color), w)
    q.setDashPattern([dash / w, dash / w])
    q.setCapStyle(Qt.FlatCap)
    q.setJoinStyle(Qt.MiterJoin)
    p.setPen(q)
    p.setBrush(fill if fill is not None else Qt.NoBrush)
    crisp(p)
    p.drawRect(r)
    crisp(p, False)


def _picture(p, r):
    """Tiny landscape picture inside r."""
    p.setPen(Qt.NoPen)
    p.setBrush(lg(r.left(), r.top(), r.left(), r.bottom(), (0, "#8fc7ff"), (1, "#e3f3ff")))
    p.drawRect(r)
    hill = QPainterPath()
    hill.moveTo(r.left(), r.bottom())
    hill.lineTo(r.left(), r.top() + r.height() * 0.7)
    hill.cubicTo(r.left() + r.width() * 0.3, r.top() + r.height() * 0.35,
                 r.left() + r.width() * 0.55, r.top() + r.height() * 0.9,
                 r.right(), r.top() + r.height() * 0.55)
    hill.lineTo(r.right(), r.bottom())
    hill.closeSubpath()
    p.setBrush(QColor("#5cb85c"))
    p.drawPath(hill)
    p.setBrush(QColor("#ffd94a"))
    rr = min(r.width(), r.height()) * 0.14
    p.drawEllipse(QPointF(r.left() + r.width() * 0.74, r.top() + r.height() * 0.28), rr, rr)


def _letter(p, ch, rect, color="#1a1a1a", family=("DejaVu Serif", "Liberation Serif", "Times New Roman", "serif"),
            bold=True, italic=False):
    f = QFont()
    f.setFamilies(list(family))
    f.setPixelSize(100)
    f.setBold(bold)
    f.setItalic(italic)
    path = QPainterPath()
    path.addText(0, 0, f, ch)
    b = path.boundingRect()
    s = min(rect.width() / b.width(), rect.height() / b.height())
    t = QTransform()
    t.translate(rect.center().x(), rect.center().y())
    t.scale(s, s)
    t.translate(-b.center().x(), -b.center().y())
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(t.map(path))


# ------------------------------------------------------------- 16px icons --
@icon_fn("cut")
def _(p):
    p.setPen(pen("#5a6470", 1.5))
    p.drawLine(QPointF(4.6, 1.2), QPointF(10.2, 10.2))
    p.drawLine(QPointF(11.4, 1.2), QPointF(5.8, 10.2))
    p.setPen(pen("#2b4e8c", 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(4.4, 12.4), 2.1, 2.1)
    p.drawEllipse(QPointF(11.6, 12.4), 2.1, 2.1)


@icon_fn("copy")
def _(p):
    _page(p, 1.5, 1.5, 8, 10, 2.5)
    _page(p, 6.5, 4.5, 8, 10, 2.5)
    p.setPen(pen("#9db7dc", 1, cap=Qt.FlatCap))
    for y in (8.5, 10.5, 12.5):
        p.drawLine(QPointF(8.2, y), QPointF(12.8, y))


def _clipboard(p, s):
    """Clipboard on an s-unit grid (s = 16 or 32)."""
    k = s / 16.0
    p.setPen(pen("#7a5a2a", 0.9 * k ** 0.5, join=Qt.MiterJoin))
    p.setBrush(lg(0, 2 * k, 0, 15 * k, (0, "#e3b56c"), (1, "#b9813a")))
    p.drawRoundedRect(QRectF(2.5 * k, 2.5 * k, 11 * k, 12.5 * k), 1.2 * k, 1.2 * k)
    p.setPen(pen("#8a97a8", 0.8 * k ** 0.5, join=Qt.MiterJoin))
    p.setBrush(lg(0, 4 * k, 0, 14 * k, (0, "#ffffff"), (1, "#e6edf6")))
    p.drawRect(QRectF(4.5 * k, 5 * k, 7 * k, 8.5 * k))
    p.setPen(pen("#5a6470", 0.8 * k ** 0.5, join=Qt.MiterJoin))
    p.setBrush(lg(0, 1 * k, 0, 5 * k, (0, "#f4f6f9"), (1, "#a3adba")))
    p.drawRoundedRect(QRectF(5.5 * k, 1.2 * k, 5 * k, 3.4 * k), 1.0 * k, 1.0 * k)
    if k > 1.5:
        p.setPen(pen("#9db7dc", 1.2, cap=Qt.FlatCap))
        for y in (13.5, 16.5, 19.5, 22.5):
            p.drawLine(QPointF(11.5, y), QPointF(20.5, y))


@icon_fn("paste")
def _(p):
    _clipboard(p, 16)


@icon_fn("paste32", 32)
def _(p):
    _clipboard(p, 32)


@icon_fn("crop")
def _(p):
    p.setPen(pen(INK, 1.6, cap=Qt.SquareCap, join=Qt.MiterJoin))
    crisp(p)
    p.drawPolyline(poly(4, 1.5, 4, 12, 14.5, 12))
    p.drawPolyline(poly(1.5, 4, 12, 4, 12, 14.5))
    crisp(p, False)
    p.fillRect(QRectF(5.2, 5.2, 5.6, 5.6), QColor(140, 190, 240, 150))


@icon_fn("resize")
def _(p):
    _dashed_rect(p, QRectF(1.5, 1.5, 13, 13), "#5a6f8f")
    crisp(p)
    p.setPen(pen("#2b4e8c", 1, join=Qt.MiterJoin))
    p.setBrush(lg(0, 7, 0, 15, (0, "#eaf3fd"), (1, "#a9cbf0")))
    p.drawRect(QRectF(1.5, 7.5, 7, 7))
    crisp(p, False)
    p.setPen(pen(INK, 1.3))
    p.drawLine(QPointF(9, 7), QPointF(12.6, 3.4))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(INK))
    p.drawPolygon(poly(13.6, 2.4, 13.4, 6.2, 9.8, 2.6))


@icon_fn("rotate")
def _(p):
    p.setPen(pen("#2b4e8c", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 6, 0, 14, (0, "#eaf3fd"), (1, "#9cc3ee")))
    p.drawPolygon(poly(1.5, 14.5, 1.5, 6.5, 9.5, 14.5))
    p.setPen(pen(INK, 1.5, cap=Qt.FlatCap))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(6.0, 3.2)
    path.cubicTo(10.0, 2.4, 13.0, 5.0, 12.8, 9.0)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(INK))
    p.drawPolygon(poly(10.2, 8.4, 15.4, 8.4, 12.8, 12.2))


@icon_fn("pencil")
def _(p):
    p.translate(1.8, 14.2)
    p.rotate(-45)
    _pencil(p)


@icon_fn("fill")
def _(p):
    _bucket(p)


@icon_fn("text")
def _(p):
    _letter(p, "A", QRectF(2.5, 2, 11, 12))


@icon_fn("eraser")
def _(p):
    p.translate(8, 8.4)
    p.rotate(-38)
    p.setPen(pen("#8c4a57", 0.8, join=Qt.MiterJoin))
    p.setBrush(lg(0, -3.2, 0, 3.2, (0, "#f9bcc8"), (1, "#dc6f86")))
    p.drawRoundedRect(QRectF(-6.4, -3.2, 12.8, 6.4), 1.3, 1.3)
    p.setPen(Qt.NoPen)
    p.setBrush(lg(0, -3.2, 0, 3.2, (0, "#ffffff"), (1, "#d9dfe8")))
    p.drawRoundedRect(QRectF(1.4, -2.7, 4.5, 5.4), 1.0, 1.0)


@icon_fn("picker")
def _(p):
    p.translate(1.6, 14.4)
    p.rotate(-45)
    p.setPen(pen("#3c4652", 0.7, join=Qt.MiterJoin))
    p.setBrush(lg(0, -1, 0, 1, (0, "#eef8ff"), (1, "#a9d3f0")))
    p.drawPolygon(poly(0, 0, 1.6, -1.0, 8.2, -1.0, 8.2, 1.0, 1.6, 1.0))
    p.setBrush(QColor("#2e333b"))
    p.drawRect(QRectF(8.2, -2.2, 1.7, 4.4))
    p.setBrush(lg(0, -1.9, 0, 1.9, (0, "#6c7684"), (0.5, "#30353d"), (1, "#1c1f24")))
    p.drawRoundedRect(QRectF(9.9, -1.9, 6.6, 3.8), 1.7, 1.7)


@icon_fn("magnifier")
def _(p):
    _lens(p, 6.4, 6.4, 4.4, 14.0, 14.0, 2.6)


@icon_fn("outline")
def _(p):
    crisp(p)
    p.setPen(pen("#1e3a6e", 2, join=Qt.MiterJoin))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(2, 6, 9, 8))
    crisp(p, False)
    p.translate(6.5, 8.8)
    p.rotate(-45)
    p.scale(0.66, 0.66)
    _pencil(p)


@icon_fn("fillstyle")
def _(p):
    crisp(p)
    p.setPen(pen("#1e3a6e", 1, join=Qt.MiterJoin))
    p.setBrush(lg(0, 6, 0, 14, (0, "#7db4ee"), (1, "#3f7fd0")))
    p.drawRect(QRectF(1.5, 5.5, 10, 9))
    crisp(p, False)
    p.translate(6.2, -0.6)
    p.scale(0.62, 0.62)
    _bucket(p)


@icon_fn("save")
def _(p):
    p.setPen(pen("#2a3f78", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 1, 0, 15, (0, "#7c9ada"), (1, "#3c5aa2")))
    p.drawRoundedRect(QRectF(1.5, 1.5, 13, 13), 1.2, 1.2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(4, 2.2, 8, 5.2))
    p.setBrush(QColor("#d5dce8"))
    p.drawRect(QRectF(4.6, 9.8, 6.8, 4.5))
    p.setBrush(QColor("#34497f"))
    p.drawRect(QRectF(8.6, 10.6, 1.7, 3.0))
    p.setPen(pen("#9db7dc", 0.8, cap=Qt.FlatCap))
    p.drawLine(QPointF(5, 4), QPointF(11, 4))
    p.drawLine(QPointF(5, 5.8), QPointF(11, 5.8))


@icon_fn("undo")
def _(p):
    _curved_arrow(p)


@icon_fn("redo")
def _(p):
    p.translate(16, 0)
    p.scale(-1, 1)
    _curved_arrow(p)


@icon_fn("new")
def _(p):
    _page(p, 3.5, 1.5, 9, 13, 3)


@icon_fn("open")
def _(p):
    p.setPen(pen("#a0761c", 0.9, join=Qt.MiterJoin))
    p.setBrush(QColor("#e2ae3f"))
    p.drawPolygon(poly(1.5, 3.5, 6, 3.5, 7.4, 5.2, 13, 5.2, 13, 13.2, 1.5, 13.2))
    p.setBrush(lg(0, 7, 0, 13, (0, "#fff0a8"), (1, "#f2bd45")))
    p.drawPolygon(poly(1.5, 13.2, 3.8, 7.4, 15.2, 7.4, 13, 13.2))


@icon_fn("print")
def _(p):
    p.setPen(pen(PAGE_EDGE, 0.8, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(4.5, 1.5, 7, 4.5))
    p.setPen(pen("#4a5560", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 5, 0, 12, (0, "#eef1f5"), (1, "#a4aebb")))
    p.drawRoundedRect(QRectF(1.5, 5.5, 13, 6.5), 1.2, 1.2)
    p.setPen(pen(PAGE_EDGE, 0.8, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(4, 9.5, 8, 5))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4fc04f"))
    p.drawEllipse(QPointF(12.6, 7.4), 0.8, 0.8)
    p.setPen(pen("#9db7dc", 0.8, cap=Qt.FlatCap))
    p.drawLine(QPointF(5.5, 11.3), QPointF(10.5, 11.3))
    p.drawLine(QPointF(5.5, 13), QPointF(10.5, 13))


@icon_fn("email")
def _(p):
    p.setPen(pen(PAGE_EDGE, 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 3, 0, 13, (0, "#ffffff"), (1, "#dfe8f4")))
    p.drawRect(QRectF(1.5, 3.5, 13, 9))
    p.setBrush(Qt.NoBrush)
    p.drawPolyline(poly(1.5, 3.5, 8, 9, 14.5, 3.5))
    p.setPen(pen("#b3c1d4", 0.8))
    p.drawLine(QPointF(1.5, 12.5), QPointF(6, 8))
    p.drawLine(QPointF(14.5, 12.5), QPointF(10, 8))


@icon_fn("desktop")
def _(p):
    p.setPen(pen("#3c4652", 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#3c4652"))
    p.drawRect(QRectF(6.5, 11.5, 3, 2))
    p.drawRect(QRectF(4.5, 13.5, 7, 1))
    p.setBrush(QColor("#dfe6ee"))
    p.drawRoundedRect(QRectF(1.5, 1.5, 13, 10), 1, 1)
    _picture(p, QRectF(3, 3, 10, 7))


@icon_fn("scanner")
def _(p):
    p.setPen(pen("#2e333b", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 4, 0, 13, (0, "#8b95a3"), (1, "#474f5a")))
    p.drawRect(QRectF(5.5, 2.5, 4.5, 2.5))
    p.drawRoundedRect(QRectF(1.5, 4.5, 13, 8.5), 1.2, 1.2)
    g = QRadialGradient(7.4, 8.2, 3.4)
    g.setColorAt(0, QColor("#e8f6ff"))
    g.setColorAt(1, QColor("#4e9be0"))
    p.setBrush(QBrush(g))
    p.setPen(pen("#1e232a", 0.9))
    p.drawEllipse(QPointF(8, 8.8), 2.8, 2.8)


@icon_fn("properties")
def _(p):
    _page(p, 2.5, 1.5, 9, 13, 3)
    p.setPen(pen("#d22b2b", 1.8))
    p.drawPolyline(poly(7.2, 10.2, 9.6, 12.8, 14.2, 6.4))


@icon_fn("about")
def _(p):
    p.setPen(pen("#1c4a9a", 0.9))
    p.setBrush(lg(0, 1, 0, 15, (0, "#6aa6ee"), (1, "#2a62b8")))
    p.drawEllipse(QPointF(8, 8), 6.5, 6.5)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(8, 4.6), 1.1, 1.1)
    p.drawRoundedRect(QRectF(7.0, 6.6, 2.0, 5.6), 0.5, 0.5)


@icon_fn("help")
def _(p):
    p.setPen(pen("#1c4a9a", 0.9))
    p.setBrush(lg(0, 1, 0, 15, (0, "#6aa6ee"), (1, "#2a62b8")))
    p.drawEllipse(QPointF(8, 8), 6.5, 6.5)
    _letter(p, "?", QRectF(5.2, 3.4, 5.6, 9.2), "#ffffff", family=("DejaVu Sans", "Liberation Sans", "sans-serif"))


@icon_fn("exit")
def _(p):
    p.setPen(pen("#8f1f1f", 0.9))
    p.setBrush(lg(0, 2, 0, 14, (0, "#f08a7a"), (1, "#c5392b")))
    p.drawRoundedRect(QRectF(1.5, 1.5, 13, 13), 2, 2)
    p.setPen(pen("#ffffff", 2.0))
    p.drawLine(QPointF(5, 5), QPointF(11, 11))
    p.drawLine(QPointF(11, 5), QPointF(5, 11))


@icon_fn("delete")
def _(p):
    p.setPen(pen("#d22b2b", 2.4))
    p.drawLine(QPointF(3.5, 3.5), QPointF(12.5, 12.5))
    p.drawLine(QPointF(12.5, 3.5), QPointF(3.5, 12.5))


@icon_fn("sel_rect")
def _(p):
    _dashed_rect(p, QRectF(1.5, 3.5, 13, 9), fill=lg(0, 3, 0, 12, (0, "#ffffff"), (1, "#dcebfa")))


@icon_fn("sel_free")
def _(p):
    q = QPen(QColor("#2b4e8c"), 1.1)
    q.setDashPattern([2, 1.6])
    p.setPen(q)
    p.setBrush(lg(0, 2, 0, 14, (0, "#ffffff"), (1, "#dcebfa")))
    path = QPainterPath()
    path.moveTo(3, 6)
    path.cubicTo(3, 1.5, 9, 0.8, 11.5, 3.5)
    path.cubicTo(15.5, 5, 14.5, 10.5, 11.5, 11.5)
    path.cubicTo(9, 15, 3.5, 14.8, 3.2, 11.5)
    path.cubicTo(0.6, 9.5, 1.2, 7, 3, 6)
    p.drawPath(path)


@icon_fn("sel_all")
def _(p):
    _dashed_rect(p, QRectF(1.5, 1.5, 13, 13), fill=QColor("#bcd8f6"))
    crisp(p)
    p.setPen(pen("#2b4e8c", 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    for x, y in ((0.5, 0.5), (12.5, 0.5), (0.5, 12.5), (12.5, 12.5)):
        p.drawRect(QRectF(x, y, 3, 3))
    crisp(p, False)


@icon_fn("sel_invert")
def _(p):
    crisp(p)
    p.fillRect(QRectF(1, 1, 14, 14), QColor("#bcd8f6"))
    p.fillRect(QRectF(4, 4, 8, 8), QColor("#ffffff"))
    crisp(p, False)
    _dashed_rect(p, QRectF(1.5, 1.5, 13, 13))
    _dashed_rect(p, QRectF(4.5, 4.5, 7, 7))


def _rot_page(p):
    crisp(p)
    p.setPen(pen("#2b4e8c", 1, join=Qt.MiterJoin))
    p.setBrush(lg(0, 6, 0, 15, (0, "#f4f9ff"), (1, "#a9cbf0")))
    p.drawRect(QRectF(1.5, 7.5, 9, 7))
    crisp(p, False)


def _arc_arrow(p, cw=True):
    p.save()
    if not cw:
        p.translate(16, 0)
        p.scale(-1, 1)
    p.setPen(pen(INK, 1.5, cap=Qt.FlatCap))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(5.0, 3.6)
    path.cubicTo(9.0, 1.6, 13.4, 3.4, 13.2, 7.4)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(INK))
    p.drawPolygon(poly(10.6, 7.0, 15.6, 7.0, 13.1, 10.8))
    p.restore()


@icon_fn("rot_right")
def _(p):
    _rot_page(p)
    _arc_arrow(p, True)


@icon_fn("rot_left")
def _(p):
    p.translate(16, 0)
    p.scale(-1, 1)
    _rot_page(p)
    _arc_arrow(p, True)


@icon_fn("rot_180")
def _(p):
    crisp(p)
    p.setPen(pen("#2b4e8c", 1, join=Qt.MiterJoin))
    p.setBrush(lg(0, 5, 0, 11, (0, "#f4f9ff"), (1, "#a9cbf0")))
    p.drawRect(QRectF(4.5, 5.5, 7, 5))
    crisp(p, False)
    for flip in (False, True):
        p.save()
        if flip:
            p.translate(16, 16)
            p.scale(-1, -1)
        p.setPen(pen(INK, 1.4, cap=Qt.FlatCap))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(3.2, 3.2)
        path.cubicTo(7, 0.8, 11.5, 1.2, 13.2, 3.6)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(INK))
        p.drawPolygon(poly(11.2, 5.4, 15.4, 5.0, 14.4, 1.0))
        p.restore()


def _flip(p):
    """Flip-vertical pictogram (mirror across horizontal axis)."""
    p.setPen(pen("#2b4e8c", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 1, 0, 7, (0, "#f4f9ff"), (1, "#8fbbec")))
    p.drawPolygon(poly(2.5, 6.5, 2.5, 1.5, 10.5, 6.5))
    p.setBrush(QColor("#e9f1fb"))
    q = QPen(QColor("#6f8fbd"), 0.9)
    q.setDashPattern([1.6, 1.4])
    p.setPen(q)
    p.drawPolygon(poly(2.5, 9.5, 2.5, 14.5, 10.5, 9.5))
    q2 = QPen(QColor(INK), 1)
    q2.setDashPattern([2, 1.5])
    p.setPen(q2)
    p.drawLine(QPointF(0.5, 8), QPointF(15.5, 8))
    p.setPen(pen(INK, 1.2))
    p.drawLine(QPointF(13.2, 3.4), QPointF(13.2, 12.6))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(INK))
    p.drawPolygon(poly(11.4, 4.2, 15.0, 4.2, 13.2, 1.4))
    p.drawPolygon(poly(11.4, 11.8, 15.0, 11.8, 13.2, 14.6))


@icon_fn("flip_v")
def _(p):
    _flip(p)


@icon_fn("flip_h")
def _(p):
    p.translate(0, 16)
    p.rotate(-90)
    _flip(p)


@icon_fn("pos")
def _(p):
    crisp(p)
    p.setPen(pen("#4a5560", 1, cap=Qt.FlatCap))
    p.drawLine(QPointF(8.5, 2), QPointF(8.5, 15))
    p.drawLine(QPointF(2, 8.5), QPointF(15, 8.5))
    crisp(p, False)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4a5560"))
    p.drawPolygon(poly(8.5, 0.5, 6, 3.6, 11, 3.6))
    p.drawPolygon(poly(8.5, 16.5, 6, 13.4, 11, 13.4))
    p.drawPolygon(poly(0.5, 8.5, 3.6, 6, 3.6, 11))
    p.drawPolygon(poly(16.5, 8.5, 13.4, 6, 13.4, 11))


@icon_fn("selsize")
def _(p):
    _dashed_rect(p, QRectF(2.5, 3.5, 11, 9), "#4a5560")


@icon_fn("imgsize")
def _(p):
    crisp(p)
    p.setPen(pen("#4a5560", 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(2.5, 3.5, 11, 9))
    crisp(p, False)
    p.setPen(pen("#4a5560", 1))
    p.drawLine(QPointF(5.5, 10), QPointF(10.5, 6))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4a5560"))
    p.drawPolygon(poly(11.8, 5, 8.6, 5.4, 10.8, 8))
    p.drawPolygon(poly(4.2, 11, 7.4, 10.6, 5.2, 8))


@icon_fn("disk")
def _(p):
    p.setPen(pen("#4a5560", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 2, 0, 14, (0, "#c5ccd6"), (1, "#8590a0")))
    p.drawRoundedRect(QRectF(2.5, 2.5, 11, 11), 1, 1)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(4.6, 3.2, 6.8, 4.2))
    p.setBrush(QColor("#e4e8ee"))
    p.drawRect(QRectF(5.2, 9.6, 5.6, 3.6))


@icon_fn("opaque")
def _(p):
    crisp(p)
    p.setPen(pen("#6b7f99", 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#9fc3ee"))
    p.drawRect(QRectF(1.5, 1.5, 13, 13))
    crisp(p, False)
    _letter(p, "A", QRectF(3.5, 3, 9, 10))


@icon_fn("transparent")
def _(p):
    crisp(p)
    for i in range(4):
        for j in range(4):
            if (i + j) % 2 == 0:
                p.fillRect(QRectF(2 + i * 3, 2 + j * 3, 3, 3), QColor("#d6dde6"))
    crisp(p, False)
    _dashed_rect(p, QRectF(1.5, 1.5, 13, 13), "#6b7f99")
    _letter(p, "A", QRectF(3.5, 3, 9, 10))


@icon_fn("zoomin16")
def _(p):
    _lens(p, 6.4, 6.4, 4.6, 14.0, 14.0, 2.4)
    p.setPen(pen("#1c4a9a", 1.5, cap=Qt.FlatCap))
    p.drawLine(QPointF(4, 6.4), QPointF(8.8, 6.4))
    p.drawLine(QPointF(6.4, 4), QPointF(6.4, 8.8))


@icon_fn("zoomout16")
def _(p):
    _lens(p, 6.4, 6.4, 4.6, 14.0, 14.0, 2.4)
    p.setPen(pen("#1c4a9a", 1.5, cap=Qt.FlatCap))
    p.drawLine(QPointF(4, 6.4), QPointF(8.8, 6.4))


@icon_fn("check")
def _(p):
    p.setPen(pen("#1e395b", 1.9))
    p.drawPolyline(poly(3.6, 8.4, 6.6, 11.6, 12.6, 4.6))


@icon_fn("blank")
def _(p):
    pass


@icon_fn("pin")
def _(p):
    p.setPen(pen("#5a6470", 1.2))
    p.drawLine(QPointF(8, 9), QPointF(8, 14))
    p.setPen(pen("#3c4652", 0.9, join=Qt.MiterJoin))
    p.setBrush(lg(0, 2, 0, 9, (0, "#dfe6ee"), (1, "#8b95a3")))
    p.drawPolygon(poly(5.5, 2, 10.5, 2, 9.8, 6.5, 12, 9, 4, 9, 6.2, 6.5))


# ------------------------------------------------------------- 32px icons --
@icon_fn("select32", 32)
def _(p):
    _dashed_rect(p, QRectF(3.5, 6.5, 25, 19), dash=3.0,
                 fill=lg(0, 6, 0, 26, (0, "#ffffff"), (1, "#d3e6fa")))


@icon_fn("select_free32", 32)
def _(p):
    q = QPen(QColor("#2b4e8c"), 1.2)
    q.setDashPattern([3, 2.4])
    p.setPen(q)
    p.setBrush(lg(0, 4, 0, 28, (0, "#ffffff"), (1, "#d3e6fa")))
    path = QPainterPath()
    path.moveTo(6, 12)
    path.cubicTo(6, 3, 18, 1.6, 23, 7)
    path.cubicTo(31, 10, 29, 21, 23, 23)
    path.cubicTo(18, 30, 7, 29.6, 6.4, 23)
    path.cubicTo(1.2, 19, 2.4, 14, 6, 12)
    p.drawPath(path)


@icon_fn("brush32", 32)
def _(p):
    p.translate(4.5, 27.5)
    p.rotate(-45)
    tip = QPainterPath()
    tip.moveTo(0, 0)
    tip.cubicTo(3.5, -0.6, 6.0, -3.6, 9.5, -3.4)
    tip.lineTo(9.5, 3.4)
    tip.cubicTo(6.0, 3.6, 3.5, 0.6, 0, 0)
    p.setPen(pen("#3a2a18", 0.7))
    p.setBrush(lg(0, -3.4, 0, 3.4, (0, "#7a5c3a"), (0.5, "#4a3520"), (1, "#2c1f12")))
    p.drawPath(tip)
    p.setPen(pen("#5a6470", 0.7, join=Qt.MiterJoin))
    p.setBrush(lg(0, -3.2, 0, 3.2, (0, "#fbfcfd"), (0.5, "#c3cad3"), (1, "#8590a0")))
    p.drawRect(QRectF(9.5, -3.2, 4.6, 6.4))
    p.setPen(pen("#7a4a12", 0.7, join=Qt.MiterJoin))
    p.setBrush(lg(0, -2.8, 0, 2.8, (0, "#f3c98a"), (0.5, "#d9a04e"), (1, "#a86b2d")))
    p.drawPolygon(poly(14.1, -2.8, 31.0, -1.5, 32.2, 0, 31.0, 1.5, 14.1, 2.8))


@icon_fn("shapes32", 32)
def _(p):
    p.setPen(pen("#2b4e8c", 1.3, join=Qt.MiterJoin))
    p.setBrush(lg(0, 4, 0, 18, (0, "#ffffff"), (1, "#bcd8f6")))
    p.drawEllipse(QRectF(3.5, 4.5, 15, 13))
    p.setBrush(lg(0, 12, 0, 28, (0, "#fff6c4"), (1, "#f2c94c")))
    p.drawRect(QRectF(13.5, 13.5, 15, 13))
    p.setBrush(lg(0, 16, 0, 29, (0, "#d9f2c9"), (1, "#7cc56a")))
    p.drawPolygon(poly(2.5, 28.5, 9.5, 16.5, 16.5, 28.5))


@icon_fn("tools32", 32)
def _(p):
    p.save()
    p.translate(4, 28)
    p.rotate(-45)
    p.scale(1.9, 1.9)
    _pencil(p)
    p.restore()


@icon_fn("font32", 32)
def _(p):
    _letter(p, "A", QRectF(5, 4, 22, 24))


@icon_fn("size32", 32)
def _(p):
    crisp(p)
    for y, h in ((6, 1), (11, 2), (17, 4), (25, 6)):
        p.fillRect(QRectF(5, y - h / 2.0 if h > 1 else y, 22, h), QColor("#000000"))
    crisp(p, False)


@icon_fn("editcolors32", 32)
def _(p):
    r = QRectF(4.5, 4.5, 23, 23)
    g = QLinearGradient(r.left(), 0, r.right(), 0)
    for i in range(7):
        g.setColorAt(i / 6.0, QColor.fromHsvF(min(i / 6.0, 0.999) * 0.85, 1.0, 1.0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawRect(r)
    p.setBrush(lg(0, r.top(), 0, r.bottom(), (0, QColor(255, 255, 255, 190)), (0.45, QColor(255, 255, 255, 0)),
                  (0.55, QColor(0, 0, 0, 0)), (1, QColor(0, 0, 0, 150))))
    p.drawRect(r)
    crisp(p)
    p.setPen(pen("#7a7a7a", 1, join=Qt.MiterJoin))
    p.setBrush(Qt.NoBrush)
    p.drawRect(r)
    crisp(p, False)


@icon_fn("zoomin32", 32)
def _(p):
    _lens(p, 13, 13, 9.2, 28, 28, 4.4)
    p.setPen(pen("#1c4a9a", 2.6, cap=Qt.FlatCap))
    p.drawLine(QPointF(8, 13), QPointF(18, 13))
    p.drawLine(QPointF(13, 8), QPointF(13, 18))


@icon_fn("zoomout32", 32)
def _(p):
    _lens(p, 13, 13, 9.2, 28, 28, 4.4)
    p.setPen(pen("#1c4a9a", 2.6, cap=Qt.FlatCap))
    p.drawLine(QPointF(8, 13), QPointF(18, 13))


@icon_fn("zoom100_32", 32)
def _(p):
    p.setPen(pen(PAGE_EDGE, 1, join=Qt.MiterJoin))
    p.setBrush(lg(0, 3, 0, 29, (0, "#ffffff"), (1, "#dfe9f6")))
    p.drawRect(QRectF(3.5, 5.5, 25, 21))
    _letter(p, "100", QRectF(6, 9.5, 20, 9), "#1c4a9a", family=("DejaVu Sans", "Liberation Sans", "sans-serif"))
    _letter(p, "%", QRectF(12.5, 19.5, 7, 5), "#56677a", family=("DejaVu Sans", "Liberation Sans", "sans-serif"))


@icon_fn("fullscreen32", 32)
def _(p):
    p.setPen(pen("#3c4652", 1.2, join=Qt.MiterJoin))
    p.setBrush(QColor("#3c4652"))
    p.drawRect(QRectF(13.5, 23.5, 5, 3))
    p.drawRect(QRectF(9.5, 26.5, 13, 1.6))
    p.setBrush(QColor("#dfe6ee"))
    p.drawRoundedRect(QRectF(2.5, 3.5, 27, 20), 1.5, 1.5)
    _picture(p, QRectF(5, 6, 22, 15))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    for (x, y, dx, dy) in ((6.5, 7.5, 1, 1), (25.5, 7.5, -1, 1), (6.5, 19.5, 1, -1), (25.5, 19.5, -1, -1)):
        p.drawPolygon(poly(x, y, x + 5 * dx, y, x, y + 5 * dy))


@icon_fn("thumbnail32", 32)
def _(p):
    _dashed_rect(p, QRectF(2.5, 3.5, 27, 22), "#5a6f8f", dash=3.0)
    p.setPen(pen("#3c4652", 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(13.5, 13.5, 17, 15))
    p.fillRect(QRectF(14, 14, 16, 3.4), QColor("#6a9bdc"))
    _picture(p, QRectF(15.5, 19, 13, 8))


def _big_page(p):
    _page(p, 6.5, 2.5, 19, 27, 6)


@icon_fn("new32", 32)
def _(p):
    _big_page(p)


@icon_fn("open32", 32)
def _(p):
    p.setPen(pen("#a0761c", 1.2, join=Qt.MiterJoin))
    p.setBrush(QColor("#e2ae3f"))
    p.drawPolygon(poly(2.5, 6.5, 12, 6.5, 14.8, 10, 26, 10, 26, 26.5, 2.5, 26.5))
    p.setBrush(lg(0, 14, 0, 27, (0, "#fff0a8"), (1, "#f2bd45")))
    p.drawPolygon(poly(2.5, 26.5, 7.5, 14.5, 30.5, 14.5, 26, 26.5))


def _big_floppy(p):
    p.setPen(pen("#2a3f78", 1.2, join=Qt.MiterJoin))
    p.setBrush(lg(0, 3, 0, 29, (0, "#7c9ada"), (1, "#3c5aa2")))
    p.drawRoundedRect(QRectF(3.5, 3.5, 25, 25), 2, 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(8, 4.6, 16, 10.4))
    p.setBrush(QColor("#d5dce8"))
    p.drawRect(QRectF(9.4, 19.4, 13.2, 8.6))
    p.setBrush(QColor("#34497f"))
    p.drawRect(QRectF(17.2, 21, 3.4, 5.8))
    p.setPen(pen("#9db7dc", 1.2, cap=Qt.FlatCap))
    for y in (7.5, 10, 12.5):
        p.drawLine(QPointF(10, y), QPointF(22, y))


@icon_fn("save32", 32)
def _(p):
    _big_floppy(p)


@icon_fn("saveas32", 32)
def _(p):
    _big_floppy(p)
    p.translate(15, 31)
    p.rotate(-45)
    p.scale(1.25, 1.25)
    _pencil(p)


@icon_fn("print32", 32)
def _(p):
    p.setPen(pen(PAGE_EDGE, 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(9.5, 3.5, 13, 9))
    p.setPen(pen("#4a5560", 1.2, join=Qt.MiterJoin))
    p.setBrush(lg(0, 11, 0, 24, (0, "#eef1f5"), (1, "#a4aebb")))
    p.drawRoundedRect(QRectF(3.5, 11.5, 25, 12.5), 2, 2)
    p.setPen(pen(PAGE_EDGE, 1, join=Qt.MiterJoin))
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(8.5, 19.5, 15, 9))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4fc04f"))
    p.drawEllipse(QPointF(25, 15), 1.4, 1.4)
    p.setPen(pen("#9db7dc", 1.2, cap=Qt.FlatCap))
    for y in (22.5, 25.5):
        p.drawLine(QPointF(11, y), QPointF(21, y))


@icon_fn("scanner32", 32)
def _(p):
    p.setPen(pen("#2e333b", 1.2, join=Qt.MiterJoin))
    p.setBrush(lg(0, 8, 0, 26, (0, "#8b95a3"), (1, "#474f5a")))
    p.drawRect(QRectF(11.5, 5.5, 9, 4.5))
    p.drawRoundedRect(QRectF(3.5, 9.5, 25, 16.5), 2, 2)
    g = QRadialGradient(15, 16.4, 7)
    g.setColorAt(0, QColor("#e8f6ff"))
    g.setColorAt(1, QColor("#4e9be0"))
    p.setBrush(QBrush(g))
    p.setPen(pen("#1e232a", 1.4))
    p.drawEllipse(QPointF(16, 17.6), 5.6, 5.6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffd94a"))
    p.drawRect(QRectF(23, 11.5, 3.4, 2))


@icon_fn("email32", 32)
def _(p):
    p.setPen(pen(PAGE_EDGE, 1.2, join=Qt.MiterJoin))
    p.setBrush(lg(0, 7, 0, 25, (0, "#ffffff"), (1, "#dfe8f4")))
    p.drawRect(QRectF(3.5, 7.5, 25, 17.5))
    p.setBrush(Qt.NoBrush)
    p.drawPolyline(poly(3.5, 7.5, 16, 18, 28.5, 7.5))
    p.setPen(pen("#b3c1d4", 1))
    p.drawLine(QPointF(3.5, 25), QPointF(12.4, 15.2))
    p.drawLine(QPointF(28.5, 25), QPointF(19.6, 15.2))


@icon_fn("desktop32", 32)
def _(p):
    p.setPen(pen("#3c4652", 1.2, join=Qt.MiterJoin))
    p.setBrush(QColor("#3c4652"))
    p.drawRect(QRectF(13.5, 23.5, 5, 3))
    p.drawRect(QRectF(9.5, 26.5, 13, 1.6))
    p.setBrush(QColor("#dfe6ee"))
    p.drawRoundedRect(QRectF(2.5, 3.5, 27, 20), 1.5, 1.5)
    _picture(p, QRectF(5, 6, 22, 15))


@icon_fn("properties32", 32)
def _(p):
    _big_page(p)
    p.setPen(pen("#9db7dc", 1.2, cap=Qt.FlatCap))
    for y in (10.5, 14.5, 18.5):
        p.drawLine(QPointF(10, y), QPointF(20, y))
    p.setPen(pen("#d22b2b", 3.2))
    p.drawPolyline(poly(14, 21, 19, 26.5, 28.5, 13))


@icon_fn("exit32", 32)
def _(p):
    p.setPen(pen("#8f1f1f", 1.2))
    p.setBrush(lg(0, 4, 0, 28, (0, "#f08a7a"), (1, "#c5392b")))
    p.drawRoundedRect(QRectF(4.5, 4.5, 23, 23), 3.5, 3.5)
    p.setPen(pen("#ffffff", 3.4))
    p.drawLine(QPointF(11, 11), QPointF(21, 21))
    p.drawLine(QPointF(21, 11), QPointF(11, 21))


@icon_fn("app", 32)
def _(p):
    """Palette-and-brush application icon."""
    pal = QPainterPath()
    pal.moveTo(16, 5)
    pal.cubicTo(26, 5, 30.5, 11, 30.5, 16.5)
    pal.cubicTo(30.5, 22, 26, 24.2, 22.6, 22.4)
    pal.cubicTo(19.8, 21, 18, 22.4, 18.6, 24.8)
    pal.cubicTo(19.2, 27.6, 16.6, 29, 13, 28.2)
    pal.cubicTo(6, 26.6, 1.5, 21.6, 1.5, 15.6)
    pal.cubicTo(1.5, 9.6, 7.6, 5, 16, 5)
    hole = QPainterPath()
    hole.addEllipse(QPointF(24.4, 17.2), 2.3, 2.3)
    pal = pal.subtracted(hole)
    p.setPen(pen("#8a5a1c", 1.1))
    p.setBrush(lg(0, 5, 0, 28, (0, "#f8dba0"), (1, "#d9a04e")))
    p.drawPath(pal)
    p.setPen(Qt.NoPen)
    for (x, y, c) in ((8.2, 12.4, "#ed1c24"), (14.2, 9.4, "#fff200"), (20.6, 10.4, "#22b14c"),
                      (7.2, 18.6, "#00a2e8"), (11.6, 23.4, "#a349a4")):
        p.setBrush(QColor(c))
        p.drawEllipse(QPointF(x, y), 2.4, 2.4)
    p.save()
    p.translate(13.5, 18.5)
    p.rotate(-52)
    p.scale(0.62, 0.62)
    tip = QPainterPath()
    tip.moveTo(0, 0)
    tip.cubicTo(3.5, -0.6, 6.0, -3.6, 9.5, -3.4)
    tip.lineTo(9.5, 3.4)
    tip.cubicTo(6.0, 3.6, 3.5, 0.6, 0, 0)
    p.setPen(pen("#3a2a18", 0.8))
    p.setBrush(QColor("#3f6fd0"))
    p.drawPath(tip)
    p.setBrush(lg(0, -3.2, 0, 3.2, (0, "#fbfcfd"), (1, "#8590a0")))
    p.drawRect(QRectF(9.5, -3.2, 4.6, 6.4))
    p.setBrush(lg(0, -2.8, 0, 2.8, (0, "#c9483f"), (1, "#8f2620")))
    p.drawPolygon(poly(14.1, -2.8, 31.0, -1.5, 32.2, 0, 31.0, 1.5, 14.1, 2.8))
    p.restore()


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(pixmap("app", s))
    return ic


# ------------------------------------------------------- shape glyph icons --
def shape_glyph(name, size=16, color="#34465e") -> QPixmap:
    key = ("shape", name, size, color)
    pm = _cache.get(key)
    if pm is not None:
        return pm
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(pen(color, 1.0, join=Qt.MiterJoin))
    p.setBrush(Qt.NoBrush)
    r = QRectF(2.5, 2.5, size - 5, size - 5)
    if name == "line":
        p.drawLine(QPointF(2.5, 2.5), QPointF(size - 2.5, size - 2.5))
    elif name == "curve":
        path = QPainterPath()
        path.moveTo(2.5, size - 4)
        path.cubicTo(size * 0.3, -size * 0.25, size * 0.6, size * 1.25, size - 2.5, 4)
        p.drawPath(path)
    elif name == "polygon":
        p.drawPolygon(poly(2.5, 5.5, 8.5, 2.5, size - 2.5, 6.5, size - 5.5, size - 2.5, 5.5, size - 3.5, 8, 8.5))
    elif name in ("rect", "roundrect"):
        rr = QRectF(1.5, 3.5, size - 3, size - 7)
        p.setRenderHint(QPainter.Antialiasing, name == "roundrect")
        p.drawPath(shape_path(name, rr))
    elif name == "oval":
        p.drawEllipse(QRectF(1.5, 3.5, size - 3, size - 7))
    else:
        p.drawPath(shape_path(name, r))
    p.end()
    pm = QPixmap.fromImage(img)
    _cache[key] = pm
    return pm


# ------------------------------------------------------------------ cursors --
_cursors = {}


def _cursor_from(img: QImage, hx, hy):
    return QCursor(QPixmap.fromImage(img), hx, hy)


def cursor(name) -> QCursor:
    c = _cursors.get(name)
    if c is not None:
        return c
    if name == "cross":
        img = QImage(25, 25, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        for col, w in ((QColor(255, 255, 255), 3), (QColor(0, 0, 0), 1)):
            p.setPen(QPen(col, w))
            o = 0 if w == 3 else 0
            p.drawLine(12, 1 + o, 12, 8)
            p.drawLine(12, 16, 12, 23 - o)
            p.drawLine(1 + o, 12, 8, 12)
            p.drawLine(16, 12, 23 - o, 12)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.drawPoint(12, 12)
        p.end()
        c = _cursor_from(img, 12, 12)
    elif name in ("pencil", "fill", "picker", "magnifier"):
        base = image(name, 24)
        img = QImage(28, 28, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        # white halo so the cursor stays visible on dark pictures
        halo = base.copy()
        hp = QPainter(halo)
        hp.setCompositionMode(QPainter.CompositionMode_SourceIn)
        hp.fillRect(halo.rect(), QColor(255, 255, 255))
        hp.end()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawImage(2 + dx, 2 + dy, halo)
        p.drawImage(2, 2, base)
        p.end()
        hot = {"pencil": (4, 24), "fill": (22, 21), "picker": (4, 24), "magnifier": (11, 11)}[name]
        c = _cursor_from(img, *hot)
    else:
        c = QCursor(Qt.ArrowCursor)
    _cursors[name] = c
    return c
