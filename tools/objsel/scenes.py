import sys, math, numpy as np
import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..', '..'))
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QColor, QPainter, QPainterPath, QPen, QLinearGradient, QBrush, QRadialGradient
from opendraw7.document import const_pixels

def character(p, cx, cy, s, body, truth=False):
    """A cartoon figure: round head with eyes and smile, body, arms, legs, black outlines."""
    ol = QPen(QColor(0, 0, 0) if not truth else QColor(255, 255, 255), 3 * s)
    ol.setJoinStyle(Qt.RoundJoin); ol.setCapStyle(Qt.RoundCap)
    W = QColor(255, 255, 255)
    def fill(col): return W if truth else col
    p.setPen(ol)
    # legs and arms (thick strokes)
    for (x0, y0, x1, y1) in ((-12, 55, -18, 95), (12, 55, 18, 95), (-25, 15, -55, 40), (25, 15, 55, 40)):
        p.setPen(QPen(QColor(0, 0, 0) if not truth else W, 11 * s, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + x0 * s, cy + y0 * s), QPointF(cx + x1 * s, cy + y1 * s))
        p.setPen(QPen(fill(QColor(255, 214, 170)), 6 * s, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + x0 * s, cy + y0 * s), QPointF(cx + x1 * s, cy + y1 * s))
    p.setPen(ol)
    p.setBrush(fill(body))
    p.drawRoundedRect(QRectF(cx - 28 * s, cy - 5 * s, 56 * s, 65 * s), 14 * s, 14 * s)
    p.setBrush(fill(QColor(255, 214, 170)))
    p.drawEllipse(QRectF(cx - 32 * s, cy - 70 * s, 64 * s, 64 * s))
    # eyes: white with black pupils, smile
    for ex in (-12, 12):
        p.setPen(QPen(fill(QColor(0, 0, 0)), 2 * s))
        p.setBrush(W)
        p.drawEllipse(QRectF(cx + (ex - 7) * s, cy - 52 * s, 14 * s, 16 * s))
        p.setPen(Qt.NoPen); p.setBrush(fill(QColor(0, 0, 0)))
        p.drawEllipse(QRectF(cx + (ex - 3) * s, cy - 46 * s, 6 * s, 7 * s))
    p.setPen(QPen(fill(QColor(160, 40, 40)), 2.5 * s, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(cx - 14 * s, cy - 40 * s, 28 * s, 20 * s), 200 * 16, 140 * 16)

def scene(kind, w=640, h=420):
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied if kind == "transparent" else QImage.Format_RGB32)
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing, True)
    if kind == "white":
        p.fillRect(0, 0, w, h, QColor(255, 255, 255))
    elif kind == "sky":
        g = QLinearGradient(0, 0, 0, h); g.setColorAt(0, QColor(70, 140, 230)); g.setColorAt(0.65, QColor(190, 225, 255))
        g.setColorAt(0.651, QColor(90, 180, 70)); g.setColorAt(1, QColor(50, 130, 40)); p.fillRect(0, 0, w, h, QBrush(g))
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 230, 60)); p.drawEllipse(QRectF(w - 110, 20, 70, 70))  # sun, touches nothing
    elif kind == "transparent":
        img.fill(0)
    elif kind == "flat_color":
        p.fillRect(0, 0, w, h, QColor(255, 220, 230))
    elif kind == "night":
        g = QLinearGradient(0, 0, 0, h); g.setColorAt(0, QColor(8, 12, 40)); g.setColorAt(1, QColor(30, 40, 90)); p.fillRect(0, 0, w, h, QBrush(g))
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 220))
        for i in range(40): p.drawEllipse(QRectF((i * 97) % w, (i * 53) % (h // 2), 2, 2))   # stars
    p.end()
    figs = [(200, 220, 1.4, QColor(40, 90, 210)), (470, 230, 1.1, QColor(220, 60, 60))]
    if kind == "edge_cut":
        p = QPainter(img); p.fillRect(0, 0, w, h, QColor(255, 255, 255)); p.end()
        figs = [(200, 330, 1.6, QColor(40, 160, 90)), (470, 230, 1.1, QColor(220, 60, 60))]   # legs run off the bottom
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing, True)
    for f in figs: character(p, *f)
    p.end()
    truths = []
    for f in figs:
        t = QImage(w, h, QImage.Format_ARGB32_Premultiplied); t.fill(0)
        q = QPainter(t); q.setRenderHint(QPainter.Antialiasing, True); character(q, *f, truth=True); q.end()
        truths.append((const_pixels(t) >> 24).astype(np.float32) / 255.0)   # coverage 0..1
    return img, truths, figs
