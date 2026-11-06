"""The Layers pane: docked at the right of the canvas, in the ribbon's pale-blue style.

One row per layer, top layer first: an eye to show or hide it, a small preview and its name.
Click a row to draw on that layer, double-click the name to rename it, right-click for the menu.
Below the list: new, duplicate, delete, move up, move down and merge down, and the opacity of the
selected layer.
"""
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QTimer, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush, QPixmap, QFontMetrics, QPainterPath
from PySide6.QtWidgets import QWidget, QScrollArea, QLineEdit, QSlider, QLabel, QFrame

from . import theme as T
from .ribbon import RButton, RMenu, tip_html

PANE_W = 214
ROW_H = 46
THUMB_W, THUMB_H = 48, 36
HEADER_H = 24


def _checker(p, r):
    p.fillRect(r, QColor(255, 255, 255))
    s = 4
    for y in range(r.top(), r.bottom() + 1, s):
        for x in range(r.left() + ((y - r.top()) // s % 2) * s, r.right() + 1, 2 * s):
            p.fillRect(QRect(x, y, s, s).intersected(r), QColor(214, 214, 214))


def _eye(p, cx, cy, on):
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    if on:
        path = QPainterPath()
        path.moveTo(cx - 7, cy)
        path.quadTo(cx, cy - 7, cx + 7, cy)
        path.quadTo(cx, cy + 7, cx - 7, cy)
        p.setPen(QPen(QColor(48, 72, 110), 1.2))
        p.setBrush(QColor(255, 255, 255))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(48, 98, 170))
        p.drawEllipse(QRectF(cx - 2.8, cy - 2.8, 5.6, 5.6))
        p.setBrush(QColor(20, 30, 50))
        p.drawEllipse(QRectF(cx - 1.2, cy - 1.2, 2.4, 2.4))
    else:
        p.setPen(QPen(QColor(150, 160, 175), 1, Qt.DotLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(cx - 7, cy - 6, 14, 12), 2, 2)
    p.restore()


class LayerList(QWidget):
    """The rows, top layer first."""
    activated = Signal(int)          # layer index
    toggled = Signal(int)            # eye clicked
    renameRequested = Signal(int)
    menuRequested = Signal(int, QPoint)

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setFont(T.ui_font())
        self.setMouseTracking(True)
        self._hover = None
        self._thumbs = {}
        self.setFocusPolicy(Qt.NoFocus)

    def rows(self):
        return len(self.doc.layers)

    def index_at_row(self, row):
        return self.rows() - 1 - row

    def row_rect(self, row):
        return QRect(3, 3 + row * (ROW_H + 2), self.width() - 6, ROW_H)

    def eye_rect(self, row):
        r = self.row_rect(row)
        return QRect(r.left() + 2, r.top(), 22, r.height())

    def name_rect(self, row):
        r = self.row_rect(row)
        x = r.left() + 26 + THUMB_W + 8
        return QRect(x, r.top() + 5, r.right() - x - 4, 18)

    def sizeHint(self):
        return QSize(PANE_W - 20, 6 + self.rows() * (ROW_H + 2))

    def relayout(self):
        self.setMinimumHeight(6 + self.rows() * (ROW_H + 2))
        self.update()

    def _row_at(self, pos):
        for row in range(self.rows()):
            if self.row_rect(row).adjusted(0, 0, 0, 2).contains(pos):
                return row
        return None

    def thumb(self, layer):
        img = layer.image
        key = (img.cacheKey(), img.width(), img.height())
        pm = self._thumbs.get(id(layer))
        if pm is not None and pm[0] == key:
            return pm[1]
        scaled = img.scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        out = QPixmap(THUMB_W, THUMB_H)
        out.fill(Qt.transparent)
        p = QPainter(out)
        r = QRect(QPoint((THUMB_W - scaled.width()) // 2, (THUMB_H - scaled.height()) // 2), scaled.size())
        _checker(p, r)
        p.drawImage(r.topLeft(), scaled)
        p.setPen(QPen(QColor(140, 150, 165), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(-1, -1, 0, 0))
        p.end()
        self._thumbs[id(layer)] = (key, out)
        if len(self._thumbs) > 200:
            self._thumbs.clear()
        return out

    # -- input --------------------------------------------------------------------
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        row = self._row_at(pos)
        if row is None:
            return
        i = self.index_at_row(row)
        if e.button() == Qt.LeftButton and self.eye_rect(row).contains(pos):
            self.toggled.emit(i)
            return
        if e.button() in (Qt.LeftButton, Qt.RightButton):
            self.activated.emit(i)
        if e.button() == Qt.RightButton:
            self.menuRequested.emit(i, e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        pos = e.position().toPoint()
        row = self._row_at(pos)
        if row is not None and not self.eye_rect(row).contains(pos):
            self.renameRequested.emit(self.index_at_row(row))

    def mouseMoveEvent(self, e):
        row = self._row_at(e.position().toPoint())
        if row != self._hover:
            self._hover = row
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    # -- painting -----------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        fm = QFontMetrics(self.font())
        small = T.ui_font(11)
        for row in range(self.rows()):
            i = self.index_at_row(row)
            ly = self.doc.layers[i]
            r = self.row_rect(row)
            if i == self.doc.active:
                T.draw_hot(p, r, "checked")
            elif row == self._hover:
                T.draw_hot(p, r, "hover")
            er = self.eye_rect(row)
            _eye(p, er.center().x(), er.center().y(), ly.visible)
            tx = r.left() + 26
            p.drawPixmap(tx, r.top() + (ROW_H - THUMB_H) // 2, self.thumb(ly))
            nr = self.name_rect(row)
            p.setFont(self.font())
            p.setPen(T.TEXT_BLACK if ly.visible else T.TEXT_DISABLED)
            p.drawText(nr, Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(ly.name, Qt.ElideRight, nr.width()))
            info = []
            if ly.opacity < 1.0:
                info.append(f"{round(ly.opacity * 100)}%")
            if not ly.visible:
                info.append("Hidden")
            if i == 0 and len(self.doc.layers) > 1 and not info:
                info.append("Bottom")
            if info:
                p.setFont(small)
                p.setPen(QColor(110, 120, 135))
                p.drawText(nr.translated(0, 17), Qt.AlignLeft | Qt.AlignVCenter, ", ".join(info))
        p.end()


class LayersPane(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.doc = win.doc
        self.setFixedWidth(PANE_W)
        self.setFont(T.ui_font())
        self._opacity_undo = False
        self._editor = None

        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: white; } QScrollArea > QWidget > QWidget { background: white; }")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list = LayerList(self.doc)
        self.scroll.setWidget(self.list)
        self.list.activated.connect(self.activate)
        self.list.toggled.connect(self.toggle_visible)
        self.list.renameRequested.connect(self.rename)
        self.list.menuRequested.connect(self._menu)

        self.buttons = []
        spec = [("layer_new", "New layer", "Add an empty layer above the selected one.", self.add),
                ("layer_dup", "Duplicate layer", "Make a copy of the selected layer.", self.duplicate),
                ("layer_del", "Delete layer", "Remove the selected layer.", self.delete),
                ("layer_up", "Move layer up", "Move the selected layer above the one over it.", lambda: self.move(1)),
                ("layer_down", "Move layer down", "Move the selected layer below the one under it.",
                 lambda: self.move(-1)),
                ("layer_merge", "Merge layer down", "Blend the selected layer into the one below it.", self.merge)]
        for icon, name, body, slot in spec:
            b = RButton("", icon, "icon", tip=tip_html(name, body), parent=self)
            b.clicked.connect(slot)
            self.buttons.append(b)
        self.b_new, self.b_dup, self.b_del, self.b_up, self.b_down, self.b_merge = self.buttons

        self.op_label = QLabel("Opacity:", self)
        self.op_label.setFont(self.font())
        self.op_value = QLabel("100%", self)
        self.op_value.setFont(self.font())
        self.op_value.setFixedWidth(36)
        self.op_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 100)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.valueChanged.connect(self._opacity_changed)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.list.update)
        self.doc.layersChanged.connect(self.refresh)
        self.doc.changed.connect(self._refresh_timer.start)
        self.refresh()

    # -- layout and painting ------------------------------------------------------------
    def resizeEvent(self, e):
        w, h = self.width(), self.height()
        bottom = 64
        self.scroll.setGeometry(1, HEADER_H + 1, w - 1, h - HEADER_H - bottom - 1)
        self.list.relayout()
        y = h - bottom + 6
        for k, b in enumerate(self.buttons):
            b.move(6 + k * (T.ROW_H + 3), y)
        y += T.ROW_H + 6
        self.op_label.setGeometry(8, y, 54, 22)
        self.op_value.setGeometry(w - 44, y, 36, 22)
        self.slider.setGeometry(62, y, w - 62 - 48, 22)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(245, 248, 252))
        g.setColorAt(1, QColor(227, 234, 244))
        p.fillRect(r, QBrush(g))
        hg = QLinearGradient(0, 0, 0, HEADER_H)
        hg.setColorAt(0, QColor(250, 252, 254))
        hg.setColorAt(1, QColor(220, 230, 243))
        p.fillRect(QRect(0, 0, r.width(), HEADER_H), QBrush(hg))
        p.setPen(QPen(QColor(160, 175, 195), 1))
        p.drawLine(0, 0, 0, r.height())
        p.drawLine(0, HEADER_H, r.width(), HEADER_H)
        p.drawLine(0, r.height() - 64, r.width(), r.height() - 64)
        p.setFont(T.ui_font(12, bold=True))
        p.setPen(QColor(30, 57, 91))
        p.drawText(QRect(9, 0, r.width() - 10, HEADER_H), Qt.AlignLeft | Qt.AlignVCenter, "Layers")
        p.end()

    def refresh(self):
        d = self.doc
        n = len(d.layers)
        self.list.relayout()
        self.b_del.setEnabled(n > 1)
        self.b_up.setEnabled(d.active < n - 1)
        self.b_down.setEnabled(d.active > 0)
        self.b_merge.setEnabled(d.active > 0)
        self.slider.blockSignals(True)
        self.slider.setValue(round(d.layer.opacity * 100))
        self.slider.blockSignals(False)
        self.op_value.setText(f"{round(d.layer.opacity * 100)}%")
        row = n - 1 - d.active
        self.scroll.ensureVisible(10, self.list.row_rect(row).center().y(), 10, ROW_H)

    # -- commands -----------------------------------------------------------------------
    def _settle(self):
        """Put any work in progress (moved selection, shape, text) into the layer it belongs to."""
        self._close_editor()
        self.win.canvas.commit_pending()

    def activate(self, i):
        if i != self.doc.active:
            self._settle()
            self.doc.set_active(i)
            self.win.refresh()

    def toggle_visible(self, i):
        self._settle()
        self.doc.set_layer_props(i, visible=not self.doc.layers[i].visible)

    def add(self):
        self._settle()
        self.doc.add_layer()

    def duplicate(self):
        self._settle()
        self.doc.duplicate_layer()

    def delete(self):
        self._settle()
        self.doc.delete_layer()

    def move(self, d):
        self._settle()
        self.doc.move_layer(d)

    def merge(self):
        self._settle()
        self.doc.merge_down()

    def flatten(self):
        self._settle()
        self.doc.flatten_layers(self.win.state.color2)

    def _slider_pressed(self):
        self._settle()
        self.doc.push_undo()
        self._opacity_undo = True

    def _slider_released(self):
        self._opacity_undo = False

    def _opacity_changed(self, v):
        self.op_value.setText(f"{v}%")
        if not self._opacity_undo:          # keyboard or click on the groove: one undo step each
            self._settle()
        self.doc.set_layer_props(self.doc.active, opacity=v / 100.0, undo=not self._opacity_undo)

    # -- renaming -------------------------------------------------------------------------
    def rename(self, i):
        self._close_editor()
        self.doc.set_active(i)
        row = len(self.doc.layers) - 1 - i
        r = self.list.name_rect(row)
        ed = QLineEdit(self.list)
        ed.setFont(self.font())
        ed.setText(self.doc.layers[i].name)
        ed.setGeometry(r.left() - 3, r.top() - 2, r.width() + 4, r.height() + 4)
        ed.selectAll()
        ed.show()
        ed.setFocus()
        ed.editingFinished.connect(lambda: self._finish_rename(i))
        self._editor = (ed, i)

    def _finish_rename(self, i):
        if self._editor is None:
            return
        ed, idx = self._editor
        self._editor = None
        name = ed.text().strip()
        ed.deleteLater()
        if name and idx < len(self.doc.layers) and name != self.doc.layers[idx].name:
            self.doc.set_layer_props(idx, name=name[:80])
        self.win.canvas.setFocus()

    def _close_editor(self):
        if self._editor is not None:
            self._finish_rename(self._editor[1])

    # -- menu -----------------------------------------------------------------------------
    def _menu(self, i, gpos):
        d = self.doc
        n = len(d.layers)
        m = RMenu(self)
        m.add_item("New layer", "layer_new", self.add)
        m.add_item("Duplicate layer", "layer_dup", self.duplicate)
        m.add_item("Delete layer", "layer_del", self.delete, enabled=n > 1)
        m.addSeparator()
        m.add_item("Move layer up", "layer_up", lambda: self.move(1), enabled=d.active < n - 1)
        m.add_item("Move layer down", "layer_down", lambda: self.move(-1), enabled=d.active > 0)
        m.add_item("Merge layer down", "layer_merge", self.merge, enabled=d.active > 0)
        m.add_item("Flatten picture", "blank", self.flatten, enabled=n > 1)
        m.addSeparator()
        m.add_item("Rename", "blank", lambda: self.rename(d.active))
        m.add_item("Show layer" if not d.layer.visible else "Hide layer", "blank",
                   lambda: self.toggle_visible(d.active))
        m.exec(gpos)
