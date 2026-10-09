"""Freehand stroke engines, procedural textures and shape styling."""
import math
import random
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, QRect, QPoint
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QBrush, QPolygonF, QRadialGradient,
                           QPainterPath, QPixmap)

from .document import pixels

BRUSHES = [
    ("brush", "Brush"), ("callig1", "Calligraphy brush 1"), ("callig2", "Calligraphy brush 2"),
    ("airbrush", "Airbrush"), ("oil", "Oil brush"), ("crayon", "Crayon"), ("marker", "Marker"),
    ("pencil_nat", "Natural pencil"), ("watercolor", "Watercolor brush"),
]
BRUSH_LABELS = dict(BRUSHES)

SIZES = {
    "pencil": [1, 2, 3, 4], "eraser": [4, 6, 8, 10], "brush": [1, 3, 5, 8],
    "callig1": [3, 5, 8, 10], "callig2": [3, 5, 8, 10], "airbrush": [4, 8, 16, 24],
    "oil": [8, 16, 30, 40], "crayon": [8, 16, 30, 40], "marker": [8, 16, 30, 40],
    "pencil_nat": [8, 16, 30, 40], "watercolor": [8, 16, 30, 40], "shape": [1, 3, 5, 8],
}
DEFAULT_SIZE = {
    "pencil": 1, "eraser": 8, "brush": 5, "callig1": 5, "callig2": 5, "airbrush": 8,
    "oil": 16, "crayon": 16, "marker": 16, "pencil_nat": 16, "watercolor": 16, "shape": 5,
}
MAX_SIZE = 60

STYLES = [("none", "No {}"), ("solid", "Solid color"), ("crayon", "Crayon"), ("marker", "Marker"),
          ("oil", "Oil"), ("pencil", "Natural pencil"), ("watercolor", "Watercolor")]


def mix(c: QColor, other: QColor, t: float) -> QColor:
    return QColor(int(c.red() + (other.red() - c.red()) * t),
                  int(c.green() + (other.green() - c.green()) * t),
                  int(c.blue() + (other.blue() - c.blue()) * t))


# ----------------------------------------------------------------- textures --
_alpha_cache = {}
_brush_cache = {}
TEX = 128


def _smooth(n, passes=1):
    for _ in range(passes):
        n = (n + np.roll(n, 1, 0) + np.roll(n, -1, 0) + np.roll(n, 1, 1) + np.roll(n, -1, 1)) / 5.0
    return n


def _alpha_map(kind):
    a = _alpha_cache.get(kind)
    if a is not None:
        return a
    rng = np.random.default_rng({"crayon": 11, "pencil": 23, "oil": 37, "water": 53}[kind])
    shade = None
    if kind == "crayon":
        n = _smooth(rng.random((TEX, TEX)))
        alpha = np.clip((n - 0.43) * 9.0, 0, 1)
    elif kind == "pencil":
        n = rng.random((TEX, TEX)) * 0.7 + _smooth(rng.random((TEX, TEX))) * 0.3
        alpha = np.clip((n - 0.5) * 5.0, 0, 1) * 0.92
    elif kind == "oil":
        rows = _smooth(rng.random((TEX, 1)).repeat(TEX, axis=1) * 0.75 + rng.random((TEX, TEX)) * 0.25)
        alpha = np.clip(0.55 + (rows - 0.35) * 2.2, 0.0, 1.0)
        shade = 0.82 + 0.36 * rng.random((TEX, 1)).repeat(TEX, axis=1)
    else:  # water
        small = rng.random((8, 8)).astype(np.float32)
        img = QImage((small * 255).astype(np.uint8).tobytes(), 8, 8, 8, QImage.Format_Grayscale8)
        big = img.scaled(TEX, TEX, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(
            QImage.Format_Grayscale8)
        n = np.frombuffer(big.constBits(), np.uint8).reshape(TEX, big.bytesPerLine())[:, :TEX] / 255.0
        alpha = 0.30 + 0.28 * n
    a = (alpha.astype(np.float32), None if shade is None else shade.astype(np.float32))
    _alpha_cache[kind] = a
    return a


def texture_brush(kind: str, color: QColor) -> QBrush:
    key = (kind, color.rgb())
    b = _brush_cache.get(key)
    if b is not None:
        return b
    alpha, shade = _alpha_map(kind)
    out = np.empty((TEX, TEX, 4), np.uint8)
    s = shade if shade is not None else 1.0
    out[..., 0] = np.clip(color.blue() * s, 0, 255) * alpha
    out[..., 1] = np.clip(color.green() * s, 0, 255) * alpha
    out[..., 2] = np.clip(color.red() * s, 0, 255) * alpha
    out[..., 3] = alpha * 255
    img = QImage(out.tobytes(), TEX, TEX, TEX * 4, QImage.Format_ARGB32_Premultiplied).copy()
    b = QBrush(img)
    if len(_brush_cache) > 64:
        _brush_cache.clear()
    _brush_cache[key] = b
    return b


def style_brush(style: str, color: QColor) -> QBrush:
    if style == "solid":
        return QBrush(color)
    if style == "marker":
        c = QColor(color)
        c.setAlpha(140)
        return QBrush(c)
    if style == "watercolor":
        return texture_brush("water", color)
    return texture_brush(style, color)


def render_shape(p: QPainter, path: QPainterPath, width: int, outline_style: str, outline_color: QColor,
                 fill_style: str, fill_color: QColor, closed=True, crisp=False, round_join=False):
    """Draw a gallery shape with the chosen outline and fill styles."""
    p.save()
    try:
        p.setRenderHint(QPainter.Antialiasing, not crisp)
        p.setBrushOrigin(0, 0)
        if closed and fill_style != "none":
            p.setPen(Qt.NoPen)
            p.setBrush(style_brush(fill_style, fill_color))
            p.drawPath(path)
        if outline_style != "none":
            pen = QPen(style_brush(outline_style, outline_color), width)
            pen.setJoinStyle(Qt.MiterJoin if (closed and not round_join) else Qt.RoundJoin)
            pen.setMiterLimit(6)
            pen.setCapStyle(Qt.RoundCap if not closed else Qt.SquareCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
    finally:
        p.restore()


# ------------------------------------------------------------------ strokes --
def _line_points(x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


class Stroke:
    needs_timer = False

    def __init__(self, img: QImage, color: QColor, size: int):
        self.img = img
        self.color = QColor(color)
        self.size = max(1, int(size))
        self.last = None

    def start(self, pt: QPointF):
        self.last = QPointF(pt)
        self.segment(pt, pt)

    def line_to(self, pt: QPointF):
        if self.last is None:
            return self.start(pt)
        self.segment(self.last, pt)
        self.last = QPointF(pt)

    def segment(self, a, b):
        raise NotImplementedError

    def tick(self):
        pass

    def finish(self):
        pass


class PencilStroke(Stroke):
    """Hard-edged square dabs (pencil and eraser)."""

    def segment(self, a, b):
        n = self.size
        off = n // 2
        p = QPainter(self.img)
        for x, y in _line_points(int(math.floor(a.x())), int(math.floor(a.y())),
                                 int(math.floor(b.x())), int(math.floor(b.y()))):
            p.fillRect(x - off, y - off, n, n, self.color)
        p.end()


class ReplaceStroke(Stroke):
    """Right-button eraser: turns pixels of `match` colour into `color`."""

    def __init__(self, img, color, size, match: QColor):
        super().__init__(img, color, size)
        self.match = np.uint32(0xFF000000 | (match.rgb() & 0xFFFFFF))
        self.new = np.uint32(0xFF000000 | (color.rgb() & 0xFFFFFF))

    def segment(self, a, b):
        n = self.size
        off = n // 2
        x0, y0 = int(math.floor(a.x())), int(math.floor(a.y()))
        x1, y1 = int(math.floor(b.x())), int(math.floor(b.y()))
        left, top = min(x0, x1) - off, min(y0, y1) - off
        w, h = abs(x1 - x0) + n, abs(y1 - y0) + n
        mask = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        mask.fill(0)
        p = QPainter(mask)
        for x, y in _line_points(x0, y0, x1, y1):
            p.fillRect(x - off - left, y - off - top, n, n, QColor(255, 255, 255))
        p.end()
        r = QRect(left, top, w, h).intersected(self.img.rect())
        if r.isEmpty():
            return
        m = pixels(mask)[r.top() - top:r.top() - top + r.height(), r.left() - left:r.left() - left + r.width()] != 0
        px = pixels(self.img)
        region = px[r.top():r.top() + r.height(), r.left():r.left() + r.width()]
        hit = m & ((region | np.uint32(0xFF000000)) == self.match)
        region[hit] = self.new


class RoundStroke(Stroke):
    def segment(self, a, b):
        p = QPainter(self.img)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self.color, self.size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        if a == b:
            p.drawPoint(a)
        else:
            p.drawLine(a, b)
        p.end()


class CalligraphyStroke(Stroke):
    def __init__(self, img, color, size, forward=True):
        super().__init__(img, color, size)
        k = self.size / 2.0 * 0.7071
        self.d = QPointF(k, -k) if forward else QPointF(k, k)

    def segment(self, a, b):
        p = QPainter(self.img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(self.color, 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(self.color)
        d = self.d
        p.drawPolygon(QPolygonF([a - d, a + d, b + d, b - d]))
        p.end()


class AirbrushStroke(Stroke):
    needs_timer = True

    def segment(self, a, b):
        self._spray(b)

    def tick(self):
        if self.last is not None:
            self._spray(self.last)

    def _spray(self, c):
        radius = max(2.0, self.size)
        n = max(6, int(self.size * 1.4))
        p = QPainter(self.img)
        for _ in range(n):
            r = radius * math.sqrt(random.random())
            t = random.random() * 6.2832
            p.fillRect(int(c.x() + r * math.cos(t)), int(c.y() + r * math.sin(t)), 1, 1, self.color)
        p.end()


class OilStroke(Stroke):
    def __init__(self, img, color, size, rng=None):
        super().__init__(img, color, size)
        rng = rng or random.Random()
        self.travel = 0.0
        self.bristles = []
        n = max(8, int(self.size * 2.2))
        white, black = QColor(255, 255, 255), QColor(0, 0, 0)
        reach = 900.0 + self.size * 30.0
        for _ in range(n):
            r = self.size / 2.0 * math.sqrt(rng.random())
            t = rng.random() * 6.2832
            s = rng.random()
            col = mix(self.color, white, (s - 0.6) * 0.45) if s > 0.6 else mix(self.color, black, (0.6 - s) * 0.3)
            life = reach * (0.3 + 0.7 * rng.random())
            self.bristles.append((QPointF(r * math.cos(t), r * math.sin(t)), col, 1.0 + rng.random() * 1.6, life))

    def segment(self, a, b):
        self.travel += math.hypot(b.x() - a.x(), b.y() - a.y())
        p = QPainter(self.img)
        p.setRenderHint(QPainter.Antialiasing, True)
        for off, col, w, life in self.bristles:
            if self.travel > life:
                continue
            p.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            if a == b:
                p.drawPoint(a + off)
            else:
                p.drawLine(a + off, b + off)
        p.end()


class TextureStroke(Stroke):
    """Crayon / natural pencil: a pen that draws through a paper-anchored grain."""

    def __init__(self, img, color, size, kind):
        super().__init__(img, color, size)
        self.brush = texture_brush(kind, self.color)
        self.width = self.size if kind == "crayon" else max(2.0, self.size * 0.5)

    def segment(self, a, b):
        p = QPainter(self.img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrushOrigin(0, 0)
        p.setPen(QPen(self.brush, self.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if a == b:
            p.drawPoint(a)
        else:
            p.drawLine(a, b)
        p.end()


class LayerStroke(Stroke):
    """Base for strokes painted on a private layer and blended at fixed opacity."""
    opacity = 0.5

    def __init__(self, img, color, size):
        super().__init__(img, color, size)
        self.base = QImage(img)                       # shared until img is painted
        self.layer = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
        self.layer.fill(0)

    def paint_layer(self, p, a, b):
        raise NotImplementedError

    def segment(self, a, b):
        p = QPainter(self.layer)
        p.setRenderHint(QPainter.Antialiasing, True)
        self.paint_layer(p, a, b)
        p.end()
        m = self.size / 2.0 + 3
        r = QRectF(a, b).normalized().adjusted(-m, -m, m, m).toAlignedRect().intersected(self.img.rect())
        if r.isEmpty():
            return
        p = QPainter(self.img)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(r.topLeft(), self.base, r)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setOpacity(self.opacity)
        p.drawImage(r.topLeft(), self.layer, r)
        p.end()


class MarkerStroke(LayerStroke):
    opacity = 0.55

    def paint_layer(self, p, a, b):
        p.setPen(QPen(self.color, self.size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if a == b:
            p.drawPoint(a)
        else:
            p.drawLine(a, b)


class WatercolorStroke(LayerStroke):
    opacity = 0.62

    def __init__(self, img, color, size):
        super().__init__(img, color, size)
        self.travel = 0.0
        self.fade = 420.0 + self.size * 7.0
        self.carry = 0.0

    def _dab(self, p, c, strength):
        if strength <= 0.01:
            return
        r = self.size / 2.0
        g = QRadialGradient(c, r)
        col = QColor(self.color)
        col.setAlphaF(min(1.0, 0.34 * strength))
        edge = QColor(self.color)
        edge.setAlpha(0)
        g.setColorAt(0.0, col)
        g.setColorAt(0.72, col)
        g.setColorAt(1.0, edge)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, r, r)

    def paint_layer(self, p, a, b):
        step = max(1.0, self.size / 8.0)
        dist = math.hypot(b.x() - a.x(), b.y() - a.y())
        if dist == 0:
            self._dab(p, a, 1.0 - self.travel / self.fade)
            return
        t = self.carry
        while t <= dist:
            k = t / dist
            c = QPointF(a.x() + (b.x() - a.x()) * k, a.y() + (b.y() - a.y()) * k)
            self._dab(p, c, 1.0 - (self.travel + t) / self.fade)
            t += step
        self.carry = t - dist
        self.travel += dist


def make_stroke(kind: str, img: QImage, color: QColor, size: int) -> Stroke:
    if kind in ("pencil", "eraser"):
        return PencilStroke(img, color, size)
    if kind == "brush":
        return RoundStroke(img, color, size)
    if kind == "callig1":
        return CalligraphyStroke(img, color, size, True)
    if kind == "callig2":
        return CalligraphyStroke(img, color, size, False)
    if kind == "airbrush":
        return AirbrushStroke(img, color, size)
    if kind == "oil":
        return OilStroke(img, color, size)
    if kind == "crayon":
        return TextureStroke(img, color, size, "crayon")
    if kind == "pencil_nat":
        return TextureStroke(img, color, size, "pencil")
    if kind == "marker":
        return MarkerStroke(img, color, size)
    if kind == "watercolor":
        return WatercolorStroke(img, color, size)
    raise ValueError(kind)


_preview_cache = {}


def preview(kind: str, size=40) -> QPixmap:
    """Sample squiggle used in the brush gallery."""
    pm = _preview_cache.get((kind, size))
    if pm is not None:
        return pm
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    widths = {"brush": 4, "callig1": 8, "callig2": 8, "airbrush": 5, "oil": 9, "crayon": 9,
              "marker": 9, "pencil_nat": 12, "watercolor": 11}
    state = random.getstate()
    random.seed(7)
    color = QColor(30, 58, 110)
    if kind == "oil":
        st = OilStroke(img, color, widths[kind], random.Random(3))
    else:
        st = make_stroke(kind, img, color, widths[kind])
    pts = []
    for i in range(0, 41):
        t = i / 40.0
        x = 7 + t * (size - 14)
        y = size / 2 + math.sin(t * 6.2832) * (size * 0.24)
        pts.append(QPointF(x, y))
    st.start(pts[0])
    for pt in pts[1:]:
        st.line_to(pt)
        if kind == "airbrush":
            st.tick()
    st.finish()
    random.setstate(state)
    pm = QPixmap.fromImage(img)
    _preview_cache[(kind, size)] = pm
    return pm
