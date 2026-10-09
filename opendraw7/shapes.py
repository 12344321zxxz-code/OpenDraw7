"""Geometry for the 23 gallery shapes."""
import math
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPolygonF, QTransform

# (id, label) in gallery order
SHAPES = [
    ("line", "Line"), ("curve", "Curve"), ("oval", "Oval"), ("rect", "Rectangle"),
    ("roundrect", "Rounded rectangle"), ("polygon", "Polygon"), ("triangle", "Triangle"),
    ("righttriangle", "Right triangle"), ("diamond", "Diamond"), ("pentagon", "Pentagon"),
    ("hexagon", "Hexagon"), ("arrow_right", "Right arrow"), ("arrow_left", "Left arrow"),
    ("arrow_up", "Up arrow"), ("arrow_down", "Down arrow"), ("star4", "Four-point star"),
    ("star5", "Five-point star"), ("star6", "Six-point star"),
    ("callout_round", "Rounded rectangular callout"), ("callout_oval", "Oval callout"),
    ("callout_cloud", "Cloud callout"), ("heart", "Heart"), ("lightning", "Lightning"),
]
SHAPE_LABELS = dict(SHAPES)


def _norm(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return [((x - x0) / (x1 - x0), (y - y0) / (y1 - y0)) for x, y in points]


def _star(n, inner):
    pts = []
    for i in range(2 * n):
        r = 1.0 if i % 2 == 0 else inner
        a = -math.pi / 2 + i * math.pi / n
        pts.append((r * math.cos(a), r * math.sin(a)))
    return _norm(pts)


def _regular(n):
    return _norm([(math.cos(-math.pi / 2 + i * 2 * math.pi / n),
                   math.sin(-math.pi / 2 + i * 2 * math.pi / n)) for i in range(n)])


_ARROW = [(0, 0.25), (0.5, 0.25), (0.5, 0), (1, 0.5), (0.5, 1), (0.5, 0.75), (0, 0.75)]

_POLYS = {
    "triangle": [(0.5, 0), (1, 1), (0, 1)],
    "righttriangle": [(0, 0), (1, 1), (0, 1)],
    "diamond": [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)],
    "pentagon": _regular(5),
    "hexagon": [(0.5, 0), (1, 0.25), (1, 0.75), (0.5, 1), (0, 0.75), (0, 0.25)],
    "arrow_right": _ARROW,
    "arrow_left": [(1 - x, y) for x, y in _ARROW],
    "arrow_up": [(y, 1 - x) for x, y in _ARROW],
    "arrow_down": [(y, x) for x, y in _ARROW],
    "star4": _star(4, 0.38),
    "star5": _star(5, 0.382),
    "star6": _star(6, 0.577),
    "lightning": [(0.39, 0), (0.6, 0.29), (0.51, 0.33), (0.77, 0.56), (0.69, 0.6), (1, 1),
                  (0.46, 0.69), (0.56, 0.64), (0.24, 0.42), (0.36, 0.36), (0, 0.12)],
}


def _unit_path(name):
    p = QPainterPath()
    if name in _POLYS:
        p.addPolygon(QPolygonF([QPointF(x, y) for x, y in _POLYS[name]]))
        p.closeSubpath()
    elif name == "heart":
        p.moveTo(0.5, 0.25)
        p.cubicTo(0.5, 0.08, 0.36, 0.0, 0.25, 0.0)
        p.cubicTo(0.1, 0.0, 0.0, 0.12, 0.0, 0.3)
        p.cubicTo(0.0, 0.58, 0.3, 0.76, 0.5, 1.0)
        p.cubicTo(0.7, 0.76, 1.0, 0.58, 1.0, 0.3)
        p.cubicTo(1.0, 0.12, 0.9, 0.0, 0.75, 0.0)
        p.cubicTo(0.64, 0.0, 0.5, 0.08, 0.5, 0.25)
        p.closeSubpath()
    elif name == "callout_oval":
        # boolean ops flatten curves with a fixed tolerance, so work at a large scale
        k = 1000.0
        body = QPainterPath()
        body.addEllipse(QRectF(0, 0, k, 0.8 * k))
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(0.2 * k, 0.62 * k), QPointF(0.12 * k, k), QPointF(0.42 * k, 0.74 * k)]))
        tail.closeSubpath()
        p = QTransform.fromScale(1 / k, 1 / k).map(body.united(tail))
    elif name == "callout_cloud":
        k = 1000.0
        blobs = [(0.02, 0.22, 0.34, 0.34), (0.18, 0.04, 0.36, 0.36), (0.44, 0.0, 0.34, 0.36),
                 (0.66, 0.14, 0.34, 0.36), (0.6, 0.36, 0.36, 0.34), (0.34, 0.42, 0.36, 0.34),
                 (0.08, 0.38, 0.36, 0.34), (0.22, 0.18, 0.56, 0.44)]
        for x, y, w, h in blobs:
            b = QPainterPath()
            b.addEllipse(QRectF(x * k, y * k, w * k, h * k))
            p = b if p.isEmpty() else p.united(b)
        for x, y, w, h in [(0.16, 0.78, 0.13, 0.1), (0.07, 0.89, 0.09, 0.07), (0.0, 0.955, 0.06, 0.045)]:
            p.addEllipse(QRectF(x * k, y * k, w * k, h * k))
        p = QTransform.fromScale(1 / k, 1 / k).map(p)
    return p


_unit_cache = {}


def shape_path(name: str, rect: QRectF) -> QPainterPath:
    """Outline of the named shape fitted to rect (rect may have negative w/h)."""
    r = QRectF(rect)
    if name == "rect":
        p = QPainterPath()
        p.addRect(r.normalized())
        return p
    if name == "oval":
        p = QPainterPath()
        p.addEllipse(r.normalized())
        return p
    if name == "roundrect":
        n = r.normalized()
        rad = min(n.width(), n.height()) / 6.0
        p = QPainterPath()
        p.addRoundedRect(n, rad, rad)
        return p
    if name == "callout_round":
        n = r.normalized()
        body_h = n.height() * 0.8
        rad = min(n.width(), body_h) / 6.0
        body = QPainterPath()
        body.addRoundedRect(QRectF(n.left(), n.top(), n.width(), body_h), rad, rad)
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([
            QPointF(n.left() + n.width() * 0.17, n.top() + body_h - 1),
            QPointF(n.left() + n.width() * 0.12, n.bottom()),
            QPointF(n.left() + n.width() * 0.42, n.top() + body_h - 1)]))
        tail.closeSubpath()
        p = body.united(tail)
        if r.width() < 0 or r.height() < 0:
            t = QTransform()
            c = n.center()
            t.translate(c.x(), c.y())
            t.scale(-1 if r.width() < 0 else 1, -1 if r.height() < 0 else 1)
            t.translate(-c.x(), -c.y())
            p = t.map(p)
        return p
    up = _unit_cache.get(name)
    if up is None:
        up = _unit_path(name)
        _unit_cache[name] = up
    t = QTransform()
    t.translate(r.left(), r.top())
    t.scale(r.width() if r.width() else 1e-6, r.height() if r.height() else 1e-6)
    return t.map(up)


def is_closed(name):
    return name not in ("line", "curve")


def is_curved(name):
    """Shapes whose outline should use round joins (no mitre spikes)."""
    return name in ("oval", "roundrect", "heart", "callout_round", "callout_oval", "callout_cloud")
