"""Colours, fonts and shared painting helpers for the ribbon look."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QBrush

# ---------------------------------------------------------------- metrics --
TITLE_H = 30          # custom caption height
FRAME_W = 8           # window border thickness (resize zone)
TAB_H = 24            # tab strip height
PANEL_H = 93          # ribbon panel height
CONTENT_TOP = 3       # y of the 66px content band inside the panel
CONTENT_H = 66
ROW_H = 22            # small button row height
LABEL_TOP = 72        # y of the group label band
STATUS_H = 23

# ----------------------------------------------------------------- colours --
FRAME_TOP = QColor(185, 209, 234)
FRAME_BOTTOM = QColor(199, 217, 239)
FRAME_BORDER = QColor(84, 108, 148)
FRAME_INACTIVE = QColor(215, 228, 242)

TABSTRIP_BG = QColor(223, 233, 245)
PANEL_TOP = QColor(246, 250, 254)
PANEL_MID = QColor(233, 240, 250)
PANEL_BOTTOM = QColor(219, 229, 243)
PANEL_BORDER = QColor(186, 201, 219)
PANEL_SHADOW = QColor(160, 175, 197)
GROUP_SEP_DARK = QColor(186, 201, 219)
GROUP_SEP_LIGHT = QColor(255, 255, 255, 200)
GROUP_LABEL = QColor(104, 118, 138)
TEXT = QColor(30, 57, 91)
TEXT_BLACK = QColor(0, 0, 0)
TEXT_DISABLED = QColor(141, 141, 141)

WORKSPACE = QColor(201, 211, 226)
STATUS_TOP = QColor(241, 245, 251)
STATUS_BOTTOM = QColor(226, 234, 245)
STATUS_SEP = QColor(186, 201, 219)

HOT_BORDER = QColor(241, 202, 88)
HOT_TOP = QColor(255, 253, 240)
HOT_MID = QColor(255, 240, 187)
HOT_BOTTOM = QColor(255, 231, 159)

DOWN_BORDER = QColor(194, 138, 48)
DOWN_TOP = QColor(248, 212, 155)
DOWN_BOTTOM = QColor(252, 182, 99)

CHECK_BORDER = QColor(194, 155, 41)
CHECK_TOP = QColor(253, 233, 176)
CHECK_BOTTOM = QColor(251, 211, 119)

CHECKHOT_TOP = QColor(253, 222, 150)
CHECKHOT_BOTTOM = QColor(250, 196, 96)

MENU_BG = QColor(251, 252, 253)
MENU_BORDER = QColor(134, 134, 134)
MENU_HEADER_BG = QColor(221, 231, 238)
MENU_HEADER_LINE = QColor(197, 197, 197)

APP_BTN_TOP = QColor(61, 127, 214)
APP_BTN_BOTTOM = QColor(26, 78, 163)
APP_BTN_BORDER = QColor(20, 58, 128)

_FAMILIES = ["Segoe UI", "Selawik", "Noto Sans", "Inter", "Open Sans", "Cantarell",
             "Ubuntu", "DejaVu Sans", "Liberation Sans", "sans-serif"]


def ui_font(px=12, bold=False, italic=False):
    f = QFont()
    f.setFamilies(_FAMILIES)
    f.setPixelSize(px)
    f.setBold(bold)
    f.setItalic(italic)
    return f


def _grad(rect, *stops):
    g = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
    for pos, col in stops:
        g.setColorAt(pos, col)
    return QBrush(g)


def draw_hot(p: QPainter, rect, state: str, radius=2.0):
    """Paint the yellow/orange ribbon highlight frame.

    state: 'hover' | 'down' | 'checked' | 'checked_hover'
    """
    r = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    if state == 'hover':
        border, brush = HOT_BORDER, _grad(r, (0, HOT_TOP), (0.45, HOT_MID), (1, HOT_BOTTOM))
    elif state == 'down':
        border, brush = DOWN_BORDER, _grad(r, (0, DOWN_TOP), (1, DOWN_BOTTOM))
    elif state == 'checked':
        border, brush = CHECK_BORDER, _grad(r, (0, CHECK_TOP), (1, CHECK_BOTTOM))
    else:
        border, brush = DOWN_BORDER, _grad(r, (0, CHECKHOT_TOP), (1, CHECKHOT_BOTTOM))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(border, 1))
    p.setBrush(brush)
    p.drawRoundedRect(r, radius, radius)
    # inner light line
    p.setPen(QPen(QColor(255, 255, 255, 110), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), max(radius - 1, 0.5), max(radius - 1, 0.5))
    p.restore()


def draw_arrow(p: QPainter, cx, cy, color=TEXT_BLACK, size=5):
    """Small filled down-pointing triangle centred on (cx, cy)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing, False)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    half = size // 2
    for i in range(half + 1):
        p.fillRect(int(cx - half + i), int(cy - half // 2 + i), size - 2 * i, 1, color)
    p.restore()


def panel_brush(rect):
    return _grad(QRectF(rect), (0, PANEL_TOP), (0.5, PANEL_MID), (1, PANEL_BOTTOM))


MENU_QSS = """
QMenu {
    background: #fbfcfd; border: 1px solid #868686; padding: 2px;
}
QMenu::item {
    padding: 4px 26px 4px 30px; color: #000; border: 1px solid transparent;
    min-height: 16px;
}
QMenu::item:selected {
    border: 1px solid #f1ca58; border-radius: 2px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fffdf0, stop:0.45 #fff0bb, stop:1 #ffe79f);
    color: #000;
}
QMenu::item:disabled { color: #8d8d8d; }
QMenu::separator { height: 1px; background: #c5c5c5; margin: 3px 2px 3px 30px; }
QMenu::icon { padding-left: 6px; }
QMenu::indicator { width: 16px; height: 16px; left: 6px; }
"""
