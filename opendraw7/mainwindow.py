"""Main window: builds the ribbon tabs and wires every command."""
import os
import subprocess
import sys
import tempfile

from PySide6.QtCore import Qt, QPoint, QRect, QSize, QSettings, QTimer, QEvent, QStandardPaths, QUrl
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QLinearGradient, QKeySequence, QShortcut,
                           QFont, QFontMetrics, QImage, QDesktopServices, QGuiApplication, QPageLayout,
                           QFontDatabase)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QFileDialog, QMessageBox, QColorDialog,
                               QFontComboBox, QComboBox, QApplication, QDialog)

from . import theme as T
from . import icons
from . import APP_NAME
from .appmenu import AppMenu
from .brushes import BRUSHES, BRUSH_LABELS, STYLES, preview as brush_preview
from .canvas import Canvas
from .chrome import TitleBar, StatusBar, Ruler, RulerCorner
from .dialogs import (ResizeSkewDialog, PropertiesDialog, AboutDialog, ask_save, FullScreenView,
                      ThumbnailWindow)
from .document import Document, FORMATS, FORMAT_BY_KEY, OPEN_FILTER, LOSSY, format_for_path, reduce_colors
from .ribbon import (Ribbon, RPage, RGroup, RButton, ColorButton, Palette, ShapeGallery, RMenu, GridPopup,
                     SizePopup, tip_html)
from .shapes import SHAPES, SHAPE_LABELS
from .state import PaintState

DEFAULT_W, DEFAULT_H = 800, 600


class RCheck(QWidget):
    """Ribbon check box."""

    def __init__(self, text, tip=None, parent=None):
        super().__init__(parent)
        self.text = text
        self._checked = False
        self._hover = False
        self.on_toggle = None
        self.setFont(T.ui_font())
        self.setMouseTracking(True)
        fm = QFontMetrics(self.font())
        self.setFixedSize(22 + fm.horizontalAdvance(text) + 6, T.ROW_H)
        if tip:
            self.setToolTip(tip)

    def setChecked(self, on):
        self._checked = bool(on)
        self.update()

    def isChecked(self):
        return self._checked

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self._checked = not self._checked
            self.update()
            if self.on_toggle:
                self.on_toggle(self._checked)

    def paintEvent(self, e):
        p = QPainter(self)
        if self._hover and self.isEnabled():
            T.draw_hot(p, self.rect(), "hover")
        box = QRect(4, 4, 13, 13)
        g = QLinearGradient(0, box.top(), 0, box.bottom())
        g.setColorAt(0, QColor(238, 242, 248))
        g.setColorAt(1, QColor(255, 255, 255))
        p.setPen(QPen(QColor(142, 143, 143), 1))
        p.setBrush(QBrush(g))
        p.drawRect(box.adjusted(0, 0, -1, -1))
        if self._checked:
            p.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(30, 57, 91) if self.isEnabled() else T.TEXT_DISABLED, 1.8)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawPolyline([QPoint(7, 10), QPoint(9, 13), QPoint(14, 7)])
            p.setRenderHint(QPainter.Antialiasing, False)
        p.setFont(self.font())
        p.setPen(T.TEXT_BLACK if self.isEnabled() else T.TEXT_DISABLED)
        p.drawText(QRect(22, 0, self.width() - 22, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        p.end()


class MainWindow(QWidget):
    def __init__(self, native_frame=False):
        super().__init__()
        self.native = native_frame
        if not native_frame:
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint |
                                Qt.WindowMinMaxButtonsHint)
        self.setWindowIcon(icons.app_icon())
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.settings = QSettings("OpenDraw7", "OpenDraw7")
        self.state = PaintState(self)
        self.doc = Document(DEFAULT_W, DEFAULT_H, self)
        self.thumb = None
        self._printer = None
        self._color_sets = []

        fams = QFontDatabase.families()
        for cand in ("Segoe UI", "Calibri", "Carlito", "DejaVu Sans", "Liberation Sans", "Noto Sans", "Arial"):
            if cand in fams:
                self.state.font_family = cand
                break

        self.titlebar = TitleBar(self, native_frame)
        self.ribbon = Ribbon(self)
        self.canvas = Canvas(self.doc, self.state, self)
        self.status = StatusBar(self)
        self.hruler = Ruler(self.canvas, True, self)
        self.vruler = Ruler(self.canvas, False, self)
        self.corner = RulerCorner(self)
        for w in (self.hruler, self.vruler, self.corner):
            w.hide()

        center = QWidget(self)
        grid = QGridLayout(center)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self.corner, 0, 0)
        grid.addWidget(self.hruler, 0, 1)
        grid.addWidget(self.vruler, 1, 0)
        grid.addWidget(self.canvas, 1, 1)

        self.vbox = QVBoxLayout(self)
        self.vbox.setSpacing(0)
        self.vbox.addWidget(self.titlebar)
        self.vbox.addWidget(self.ribbon)
        self.vbox.addWidget(center, 1)
        self.vbox.addWidget(self.status)
        self._apply_margins()

        self._build_qat()
        self._build_home()
        self._build_view()
        self._build_text()
        self._build_shortcuts()

        tb = self.titlebar
        tb.minimizeRequested.connect(self.showMinimized)
        tb.maximizeRequested.connect(self._toggle_max)
        tb.closeRequested.connect(self.close)
        self.ribbon.tabbar.appButtonPressed.connect(self._open_app_menu)
        self.ribbon.tabbar.helpClicked.connect(self.about)

        c = self.canvas
        c.cursorMoved.connect(self._cursor_moved)
        c.sizeInfo.connect(self.status.set_sel)
        c.zoomChanged.connect(self._zoom_changed)
        c.stateChanged.connect(self.refresh)
        c.textActive.connect(self._text_active)
        c.textFormat.connect(self._text_format)
        c.viewChanged.connect(self._view_changed)
        c.contextMenuRequested.connect(self._context_menu)
        self.status.zoomer.zoomRequested.connect(c.set_zoom)
        self.status.zoomer.stepRequested.connect(c.zoom_step)
        self.doc.sizeChanged.connect(self._doc_info)
        self.doc.fileChanged.connect(self._doc_info)
        self.doc.historyChanged.connect(self.refresh)
        self.state.changed.connect(self._state_changed)
        QGuiApplication.clipboard().dataChanged.connect(self.refresh)

        self.resize(1100, 760)
        self.setMinimumSize(520, 360)
        self._doc_info()
        self.refresh()
        self.canvas.setFocus()

    # ================================================================ chrome ==
    def _apply_margins(self):
        full = self.native or self.isMaximized() or self.isFullScreen()
        f = 0 if full else T.FRAME_W
        self.vbox.setContentsMargins(f, 0 if full else 1, f, f)
        self.titlebar.maximized = self.isMaximized()
        self.titlebar.update()

    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            self._apply_margins()
        elif e.type() == QEvent.ActivationChange:
            self.titlebar.active = self.isActiveWindow()
            self.titlebar.update()
            self.update()
        super().changeEvent(e)

    def paintEvent(self, e):
        if self.native:
            return
        p = QPainter(self)
        r = self.rect()
        active = self.isActiveWindow()
        p.fillRect(r, T.FRAME_BOTTOM if active else T.FRAME_INACTIVE)
        if active:
            g = QLinearGradient(0, 0, 0, T.TITLE_H)
            g.setColorAt(0, T.FRAME_TOP)
            g.setColorAt(1, T.FRAME_BOTTOM)
            p.fillRect(QRect(0, 0, r.width(), T.TITLE_H + 1), QBrush(g))
        if not (self.isMaximized() or self.isFullScreen()):
            p.setPen(QPen(T.FRAME_BORDER, 1))
            p.drawRect(0, 0, r.width() - 1, r.height() - 1)
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            p.drawRect(1, 1, r.width() - 3, r.height() - 3)
            f = T.FRAME_W
            p.setPen(QPen(QColor(120, 142, 176), 1))
            p.drawRect(f - 1, T.TITLE_H, r.width() - 2 * f + 1, r.height() - T.TITLE_H - f + 1)
        p.end()

    def _edges_at(self, pos):
        if self.native or self.isMaximized() or self.isFullScreen():
            return Qt.Edges()
        r = self.rect()
        f = T.FRAME_W
        corner = 18
        e = Qt.Edges()
        if pos.x() < f or (pos.x() < corner and (pos.y() < f or pos.y() >= r.height() - f)):
            e |= Qt.LeftEdge
        if pos.x() >= r.width() - f or (pos.x() >= r.width() - corner and (pos.y() < f or pos.y() >= r.height() - f)):
            e |= Qt.RightEdge
        if pos.y() >= r.height() - f or (pos.y() >= r.height() - corner and (pos.x() < f or pos.x() >= r.width() - f)):
            e |= Qt.BottomEdge
        if pos.y() < 4:
            e |= Qt.TopEdge
        return e

    @staticmethod
    def _edge_cursor(e):
        if e in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            return Qt.SizeFDiagCursor
        if e in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            return Qt.SizeBDiagCursor
        if e & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if e & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def mouseMoveEvent(self, e):
        self.setCursor(self._edge_cursor(self._edges_at(e.position().toPoint())))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edges = self._edges_at(e.position().toPoint())
            if edges and self.windowHandle() is not None:
                self.windowHandle().startSystemResize(edges)

    def leaveEvent(self, e):
        self.unsetCursor()

    # ============================================================ ribbon: QAT ==
    def _build_qat(self):
        tb = self.titlebar
        self.q_save = tb.add_button(RButton("", "save", "icon", tip=tip_html("Save", "", "Ctrl+S")))
        self.q_undo = tb.add_button(RButton("", "undo", "icon", tip=tip_html("Undo", "", "Ctrl+Z")))
        self.q_redo = tb.add_button(RButton("", "redo", "icon", tip=tip_html("Redo", "", "Ctrl+Y")))
        self.q_more = RButton("", None, "icon", dropdown=True, tip=tip_html("Customize Quick Access Toolbar"))
        self.q_more.setFixedSize(14, T.ROW_H)
        tb.add_button(self.q_more)
        self.q_save.clicked.connect(self.save)
        self.q_undo.clicked.connect(self.canvas_undo)
        self.q_redo.clicked.connect(self.canvas_redo)
        self.q_more.set_menu(self._qat_menu)

    def _qat_menu(self):
        m = RMenu(self)
        m.add_header("Customize Quick Access Toolbar")
        for key, btn, text in (("save", self.q_save, "Save"), ("undo", self.q_undo, "Undo"),
                               ("redo", self.q_redo, "Redo")):
            m.add_item(text, checked=not btn.isHidden(), slot=lambda b=btn: self._toggle_qat(b))
        m.addSeparator()
        m.add_item("Minimize the Ribbon", checked=self.ribbon.minimized,
                   slot=lambda: self.ribbon.set_minimized(not self.ribbon.minimized))
        return m

    def _toggle_qat(self, btn):
        btn.setVisible(btn.isHidden())
        self.titlebar.layout_qat()

    # =========================================================== ribbon: Home ==
    def _clipboard_group(self):
        g = RGroup("Clipboard")
        paste = RButton("Paste", "paste32", "large", split=True,
                        tip=tip_html("Paste", "Insert what is on the Clipboard.", "Ctrl+V"))
        cut = RButton("Cut", "cut", "small",
                      tip=tip_html("Cut", "Remove the selection and put it on the Clipboard.", "Ctrl+X"))
        copy = RButton("Copy", "copy", "small",
                       tip=tip_html("Copy", "Copy the selection and put it on the Clipboard.", "Ctrl+C"))
        g.add(paste, 0, 0)
        g.add(cut, paste.width() + 2, 0)
        g.add(copy, paste.width() + 2, T.ROW_H)
        paste.clicked.connect(self.canvas.paste)
        cut.clicked.connect(self.canvas.cut)
        copy.clicked.connect(self.canvas.copy)

        def menu():
            m = RMenu(self)
            m.add_item("Paste", "paste", self.canvas.paste, enabled=self.canvas.can_paste())
            m.add_item("Paste from", "open", self.paste_from)
            return m
        paste.set_menu(menu)
        return g, paste, cut, copy

    def _colors_group(self):
        g = RGroup("Colors")
        c1 = ColorButton("Color\n1", 30, tip_html(
            "Color 1 (foreground color)", "Click here, then pick a color from the palette. "
            "This color is used with the pencil and brushes, and for shape outlines."))
        c2 = ColorButton("Color\n2", 22, tip_html(
            "Color 2 (background color)", "Click here, then pick a color from the palette. "
            "This color is used with the eraser and for shape fills."))
        pal = Palette()
        edit = RButton("Edit\ncolors", "editcolors32", "large",
                       tip=tip_html("Edit colors", "Pick a color from the full color range."))
        g.add(c1, 0, 0)
        g.add(c2, c1.width() + 2, 0)
        g.add(pal, c1.width() + c2.width() + 6, 0)
        g.add(edit, c1.width() + c2.width() + 6 + pal.width() + 4, 0)
        c1.clicked.connect(lambda: self.state.set_active(1))
        c2.clicked.connect(lambda: self.state.set_active(2))
        pal.picked.connect(self._palette_picked)
        edit.clicked.connect(self.edit_colors)
        self._color_sets.append((c1, c2, pal))
        return g

    def _palette_picked(self, color, button):
        if button == 2:
            self.state.set_color(2, color)
        else:
            self.state.set_active_color(color)

    def _build_home(self):
        st = self.state
        page = RPage()
        g, self.paste_btn, self.cut_btn, self.copy_btn = self._clipboard_group()
        g_clip = page.add_group(g, "paste32")

        # -- Image
        g = RGroup("Image")
        self.select_btn = RButton("Select", "select32", "large", split=True, checkable=True, tip=tip_html(
            "Selection", "Select a part of the picture."))
        self.crop_btn = RButton("Crop", "crop", "small", tip=tip_html(
            "Crop", "Crop the picture so it contains only the current selection.", "Ctrl+Shift+X"))
        self.resize_btn = RButton("Resize", "resize", "small", tip=tip_html(
            "Resize and skew", "Resize and skew the picture or selection.", "Ctrl+W"))
        self.rotate_btn = RButton("Rotate", "rotate", "small", dropdown=True, tip=tip_html(
            "Rotate or flip", "Rotate or flip the picture or selection."))
        g.add(self.select_btn, 0, 0)
        x = self.select_btn.width() + 2
        g.add(self.crop_btn, x, 0)
        g.add(self.resize_btn, x, T.ROW_H)
        g.add(self.rotate_btn, x, 2 * T.ROW_H)
        self.select_btn.clicked.connect(lambda: st.set_tool("select"))
        self.select_btn.set_menu(self._select_menu)
        self.crop_btn.clicked.connect(self.canvas.crop)
        self.resize_btn.clicked.connect(self.resize_skew)
        self.rotate_btn.set_menu(self._rotate_menu)
        g_image = page.add_group(g, "select32")

        # -- Tools
        g = RGroup("Tools")
        self.tool_btns = {}
        tools = [
            ("pencil", "pencil", "Pencil", "Draw a free-form line with the selected line width."),
            ("fill", "fill", "Fill with color", "Click an area on the canvas to fill it with color 1; "
                                                "right-click to fill it with color 2."),
            ("text", "text", "Text", "Insert text into the picture."),
            ("eraser", "eraser", "Eraser", "Erase part of the picture and replace it with color 2."),
            ("picker", "picker", "Color picker", "Pick a color from the picture and use it for drawing."),
            ("magnifier", "magnifier", "Magnifier", "Change the magnification for a part of the picture."),
        ]
        for i, (tid, icon, name, body) in enumerate(tools):
            b = RButton("", icon, "icon", checkable=True, tip=tip_html(name, body))
            g.add(b, (i % 3) * 23, (i // 3) * 23)
            b.clicked.connect(lambda t=tid: st.set_tool(t))
            self.tool_btns[tid] = b
        g_tools = page.add_group(g, "tools32")

        # -- Brushes
        g = RGroup("")
        self.brush_btn = RButton("Brushes", "brush32", "large", split=True, checkable=True, tip=tip_html(
            "Brushes", "Draw with different kinds of brushes."))
        g.add(self.brush_btn, 0, 0)
        self.brush_btn.clicked.connect(lambda: st.set_tool("brush"))
        self.brush_btn.set_menu(self._brush_menu)
        page.add_group(g)

        # -- Shapes
        g = RGroup("Shapes")
        self.gallery = ShapeGallery(SHAPES)
        self.outline_btn = RButton("Outline", "outline", "small", dropdown=True, tip=tip_html(
            "Shape outline", "Select the medium for the shape outline."))
        self.fill_btn = RButton("Fill", "fillstyle", "small", dropdown=True, tip=tip_html(
            "Shape fill", "Select the medium for the shape fill."))
        g.add(self.gallery, 0, 2)
        x = self.gallery.width() + 4
        g.add(self.outline_btn, x, 0)
        g.add(self.fill_btn, x, T.ROW_H)
        self.gallery.picked.connect(lambda sid: st.set_tool("shape", shape=sid))
        self.outline_btn.set_menu(lambda: self._style_menu("outline"))
        self.fill_btn.set_menu(lambda: self._style_menu("fill"))
        g_shapes = page.add_group(g, "shapes32")

        # -- Size
        g = RGroup("")
        self.size_btn = RButton("Size", "size32", "large", dropdown=True, tip=tip_html(
            "Size", "Select the width for the selected tool.", "Ctrl++, Ctrl+-"))
        g.add(self.size_btn, 0, 0)
        self.size_btn.set_menu(self._size_menu)
        page.add_group(g)

        g_colors = page.add_group(self._colors_group(), "editcolors32")
        page.set_collapse_order([g_shapes, g_colors, g_image, g_tools, g_clip])
        self.home_page = page
        self.home_idx = self.ribbon.add_page("Home", page)

    def _select_menu(self):
        st, c = self.state, self.canvas
        m = RMenu(self)
        m.add_header("Selection shapes")
        m.add_item("Rectangular selection", "sel_rect", lambda: self._set_sel_mode("rect"))
        m.add_item("Free-form selection", "sel_free", lambda: self._set_sel_mode("free"))
        m.add_header("Selection options")
        m.add_item("Select all", "sel_all", c.select_all, shortcut="Ctrl+A")
        m.add_item("Invert selection", "sel_invert", c.invert_selection, enabled=c.has_selection())
        m.add_item("Delete", "delete", c.delete_selection, enabled=c.has_selection(), shortcut="Del")
        m.add_item("Transparent selection", checked=st.transparent_sel,
                   slot=lambda: st.set_transparent(not st.transparent_sel))
        return m

    def _set_sel_mode(self, mode):
        self.state.set_sel_mode(mode)
        self.state.set_tool("select")

    def _rotate_menu(self):
        c = self.canvas
        m = RMenu(self)
        m.add_item("Rotate right 90°", "rot_right", lambda: c.rotate("r90"))
        m.add_item("Rotate left 90°", "rot_left", lambda: c.rotate("l90"))
        m.add_item("Rotate 180°", "rot_180", lambda: c.rotate("180"))
        m.add_item("Flip vertical", "flip_v", lambda: c.rotate("flipv"))
        m.add_item("Flip horizontal", "flip_h", lambda: c.rotate("fliph"))
        return m

    def _brush_menu(self):
        items = [(bid, label, brush_preview(bid)) for bid, label in BRUSHES]
        pop = GridPopup(items, 4, 46, self.state.brush if self.state.tool == "brush" else None, self)
        pop.picked.connect(lambda bid: self.state.set_tool("brush", brush=bid))
        return pop

    def _style_menu(self, which):
        st = self.state
        cur = st.outline if which == "outline" else st.fill
        m = RMenu(self)
        for sid, label in STYLES:
            text = label.format(which)
            m.add_item(text, checked=(sid == cur),
                       slot=lambda s=sid: (st.set_outline(s) if which == "outline" else st.set_fill(s)))
        return m

    def _size_menu(self):
        choices = self.state.size_choices()
        if not choices:
            return None
        pop = SizePopup(choices, self.state.size(), self)
        pop.picked.connect(self.state.set_size)
        return pop

    # =========================================================== ribbon: View ==
    def _build_view(self):
        c = self.canvas
        page = RPage()
        g = RGroup("Zoom")
        zin = RButton("Zoom\nin", "zoomin32", "large", tip=tip_html("Zoom in", "Zoom in on the picture.", "Ctrl+PgUp"))
        zout = RButton("Zoom\nout", "zoomout32", "large",
                       tip=tip_html("Zoom out", "Zoom out on the picture.", "Ctrl+PgDn"))
        z100 = RButton("100\n%", "zoom100_32", "large", tip=tip_html("100%", "Zoom to 100%."))
        g.add(zin, 0, 0)
        g.add(zout, zin.width() + 2, 0)
        g.add(z100, zin.width() + zout.width() + 4, 0)
        zin.clicked.connect(lambda: c.zoom_step(1))
        zout.clicked.connect(lambda: c.zoom_step(-1))
        z100.clicked.connect(lambda: c.set_zoom(1.0))
        self.zoomin_btn, self.zoomout_btn = zin, zout
        page.add_group(g)

        g = RGroup("Show or hide")
        self.rulers_chk = RCheck("Rulers", tip_html("Rulers", "View and use rulers to line up and measure "
                                                              "objects in the picture.", "Ctrl+R"))
        self.grid_chk = RCheck("Gridlines", tip_html("Gridlines", "View and use gridlines to align objects "
                                                                  "in the picture.", "Ctrl+G"))
        self.status_chk = RCheck("Status bar", tip_html("Status bar", "Show or hide the status bar at the "
                                                                      "bottom of the window."))
        self.status_chk.setChecked(True)
        g.add(self.rulers_chk, 0, 0)
        g.add(self.grid_chk, 0, T.ROW_H)
        g.add(self.status_chk, 0, 2 * T.ROW_H)
        self.rulers_chk.on_toggle = self.set_rulers
        self.grid_chk.on_toggle = self.set_grid
        self.status_chk.on_toggle = self.status.setVisible
        page.add_group(g)

        g = RGroup("Display")
        full = RButton("Full\nscreen", "fullscreen32", "large",
                       tip=tip_html("Full screen", "View the picture in full screen.", "F11"))
        self.thumb_btn = RButton("Thumbnail", "thumbnail32", "large", checkable=True, tip=tip_html(
            "Thumbnail", "Show or hide the Thumbnail window."))
        g.add(full, 0, 0)
        g.add(self.thumb_btn, full.width() + 2, 0)
        full.clicked.connect(self.full_screen)
        self.thumb_btn.clicked.connect(self.toggle_thumbnail)
        page.add_group(g)
        self.view_idx = self.ribbon.add_page("View", page)

    # =========================================================== ribbon: Text ==
    def _build_text(self):
        st = self.state
        page = RPage()
        g, self.t_paste, self.t_cut, self.t_copy = self._clipboard_group()
        t_clip = page.add_group(g, "paste32")

        g = RGroup("Font")
        self.font_combo = QFontComboBox()
        self.font_combo.setFont(T.ui_font())
        self.font_combo.setFixedSize(150, 22)
        self.font_combo.setFocusPolicy(Qt.ClickFocus)
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.setFont(T.ui_font())
        self.size_combo.setFixedSize(52, 22)
        self.size_combo.setFocusPolicy(Qt.ClickFocus)
        self.size_combo.addItems([str(s) for s in (8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)])
        g.add(self.font_combo, 0, 6)
        g.add(self.size_combo, 154, 6)
        self.fmt_btns = {}
        for i, (key, label, name, sc) in enumerate((("bold", "B", "Bold", "Ctrl+B"), ("italic", "I", "Italic", "Ctrl+I"),
                                                    ("underline", "U", "Underline", "Ctrl+U"),
                                                    ("strike", "abc", "Strikethrough", ""))):
            b = RButton(label, None, "icon", checkable=True, tip=tip_html(name, "", sc))
            f = T.ui_font(12, bold=(key == "bold"), italic=(key == "italic"))
            f.setUnderline(key == "underline")
            f.setStrikeOut(key == "strike")
            b.setFont(f)
            if key == "strike":
                b.setFixedSize(30, T.ROW_H)
            g.add(b, i * 24, 36)
            b.clicked.connect(lambda k=key: st.set_font(**{k: not getattr(st, k)}))
            self.fmt_btns[key] = b
        self.font_combo.setCurrentFont(QFont(st.font_family))
        self.size_combo.setCurrentText(str(st.font_size))
        self.font_combo.currentFontChanged.connect(self._font_picked)
        self.size_combo.currentTextChanged.connect(self._font_size_picked)
        self.size_combo.activated.connect(lambda _i: self.canvas.setFocus())
        self.font_combo.activated.connect(lambda _i: self.canvas.setFocus())
        t_font = page.add_group(g, "font32")

        g = RGroup("Background")
        self.opaque_btn = RButton("Opaque", "opaque", "small", checkable=True, tip=tip_html(
            "Opaque", "Fill the text box with color 2."))
        self.transp_btn = RButton("Transparent", "transparent", "small", checkable=True, tip=tip_html(
            "Transparent", "Let the picture show through behind the text."))
        g.add(self.opaque_btn, 0, 10)
        g.add(self.transp_btn, 0, 10 + T.ROW_H)
        self.opaque_btn.clicked.connect(lambda: st.set_text_opaque(True))
        self.transp_btn.clicked.connect(lambda: st.set_text_opaque(False))
        t_bg = page.add_group(g, "opaque")

        t_colors = page.add_group(self._colors_group(), "editcolors32")
        page.set_collapse_order([t_colors, t_font, t_bg, t_clip])
        self._font_sync = False
        self.text_idx = self.ribbon.add_page("Text", page, contextual=True, visible=False)

    def _font_picked(self, font):
        if not self._font_sync:
            self.state.set_font(family=font.family())

    def _font_size_picked(self, text):
        if self._font_sync:
            return
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            return
        if 1 <= v <= 400:
            self.state.set_font(size=v if v != int(v) else int(v))

    def _text_active(self, on):
        self.ribbon.set_tab_visible(self.text_idx, on)
        self.ribbon.set_current(self.text_idx if on else self.home_idx)
        QTimer.singleShot(0, self._place_context)
        self.refresh()

    def _place_context(self):
        tb = self.ribbon.tabbar
        if tb.tabs[self.text_idx]["visible"] and not self.native:
            r = tb.tab_rects()[self.text_idx]
            x0 = tb.mapTo(self, r.topLeft()).x() - self.titlebar.x()
            fm = QFontMetrics(self.titlebar.font())
            w = max(r.width(), fm.horizontalAdvance("Text Tools") + 16)
            self.titlebar.set_context((x0, x0 + w, "Text Tools"))
        else:
            self.titlebar.set_context(None)

    def _text_format(self, fmt):
        """Caret moved into differently formatted text: mirror it in the ribbon."""
        st = self.state
        f = fmt.font()
        st.font_family = f.family()
        size = f.pointSizeF()
        if size > 0:
            st.font_size = int(size) if size == int(size) else size
        st.bold, st.italic, st.underline, st.strike = f.bold(), f.italic(), f.underline(), f.strikeOut()
        self._sync_font_widgets()

    def _sync_font_widgets(self):
        st = self.state
        self._font_sync = True
        self.font_combo.setCurrentFont(QFont(st.font_family))
        self.size_combo.setCurrentText(f"{st.font_size:g}")
        self._font_sync = False
        for k, b in self.fmt_btns.items():
            b.setChecked(getattr(st, k))
        self.opaque_btn.setChecked(st.text_opaque)
        self.transp_btn.setChecked(not st.text_opaque)

    # ============================================================= shortcuts ==
    def _build_shortcuts(self):
        c = self.canvas
        table = [
            ("Ctrl+N", self.new), ("Ctrl+O", self.open), ("Ctrl+S", self.save), ("F12", self.save_as),
            ("Ctrl+P", self.print_), ("Ctrl+Z", self.canvas_undo), ("Ctrl+Y", self.canvas_redo),
            ("Ctrl+A", c.select_all), ("Ctrl+X", c.cut), ("Ctrl+C", c.copy), ("Ctrl+V", c.paste),
            ("Ctrl+W", self.resize_skew), ("Ctrl+E", self.properties), ("Ctrl+Shift+X", c.crop),
            ("Ctrl+Shift+I", c.invert_colors),
            ("Ctrl+R", lambda: self.set_rulers(not self.hruler.isVisible())),
            ("Ctrl+G", lambda: self.set_grid(not c.show_grid)),
            ("Ctrl+PgUp", lambda: c.zoom_step(1)), ("Ctrl+PgDown", lambda: c.zoom_step(-1)),
            ("F11", self.full_screen), ("F1", self.about),
            ("Ctrl+F1", lambda: self.ribbon.set_minimized(not self.ribbon.minimized)),
            ("Ctrl++", lambda: self._bump_size(1)), ("Ctrl+=", lambda: self._bump_size(1)),
            ("Ctrl+-", lambda: self._bump_size(-1)), ("Alt+F4", self.close),
        ]
        self._shortcuts = []
        for seq, slot in table:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

    def _bump_size(self, d):
        if self.state.size_key():
            self.state.set_size(self.state.size() + d)

    # ================================================================ refresh ==
    def _state_changed(self, what):
        if what in ("font", "textbg"):
            self._sync_font_widgets()
        self.refresh()

    def refresh(self):
        st, c, d = self.state, self.canvas, self.doc
        sel = c.has_selection()
        text = c.text_editing()
        has_text_sel = text and c.text_tool.cur.hasSelection()
        can_copy = sel or has_text_sel
        can_paste = c.can_paste()
        for b in (self.cut_btn, self.copy_btn, self.t_cut, self.t_copy):
            b.setEnabled(bool(can_copy) or text)
        for b in (self.paste_btn, self.t_paste):
            b.setEnabled(True)
        self.crop_btn.setEnabled(sel)
        self.q_undo.setEnabled(d.can_undo() or c.tool.has_pending())
        self.q_redo.setEnabled(d.can_redo())
        self.select_btn.setChecked(st.tool == "select")
        self.select_btn.set_icon("select_free32" if st.sel_mode == "free" else "select32")
        for tid, b in self.tool_btns.items():
            b.setChecked(st.tool == tid)
        self.brush_btn.setChecked(st.tool == "brush")
        shape = st.tool == "shape"
        self.gallery.set_current(st.shape if shape else None)
        self.outline_btn.setEnabled(shape)
        self.fill_btn.setEnabled(shape and st.shape not in ("line", "curve"))
        self.size_btn.setEnabled(st.size_key() is not None)
        for c1, c2, pal in self._color_sets:
            c1.set_color(st.color1)
            c2.set_color(st.color2)
            c1.setChecked(st.active == 1)
            c2.setChecked(st.active == 2)
        self.thumb_btn.setEnabled(c.zoom > 1 or self.thumb is not None)
        self.thumb_btn.setChecked(self.thumb is not None)
        self.rulers_chk.setChecked(self.hruler.isVisible())
        self.grid_chk.setChecked(c.show_grid)
        self.zoomin_btn.setEnabled(c.zoom < 8)
        self.zoomout_btn.setEnabled(c.zoom > 0.125)

    def _doc_info(self):
        self.status.set_image_size(self.doc.size())
        self.status.set_file_size(self.doc.file_size if self.doc.path else None)
        title = f"{self.doc.title()} - Paint"
        self.setWindowTitle(title)
        self.titlebar.set_title(title)

    def _cursor_moved(self, pt):
        self.status.set_pos(pt)
        if self.hruler.isVisible():
            self.hruler.set_mark(pt)
            self.vruler.set_mark(pt)

    def _zoom_changed(self, z):
        self.status.zoomer.set_zoom(z)
        self.refresh()

    def _view_changed(self):
        if self.hruler.isVisible():
            self.hruler.update()
            self.vruler.update()

    def resizeEvent(self, e):
        QTimer.singleShot(0, self._place_context)
        super().resizeEvent(e)

    # ================================================================ commands ==
    def canvas_undo(self):
        self.canvas.undo()

    def canvas_redo(self):
        self.canvas.redo()

    def set_rulers(self, on):
        for w in (self.hruler, self.vruler, self.corner):
            w.setVisible(on)
        self.refresh()

    def set_grid(self, on):
        self.canvas.show_grid = on
        self.canvas.viewport().update()
        self.refresh()

    def full_screen(self):
        self.canvas.commit_pending()
        v = FullScreenView(self.doc.image)
        self._fullscreen = v
        v.showFullScreen()

    def toggle_thumbnail(self):
        if self.thumb is not None:
            t, self.thumb = self.thumb, None
            t.close()
        else:
            self.thumb = ThumbnailWindow(self.canvas, self)
            self.thumb.closed.connect(self._thumb_closed)
            g = self.geometry()
            self.thumb.move(g.right() - 260, g.top() + 170)
            self.thumb.show()
        self.refresh()

    def _thumb_closed(self):
        self.thumb = None
        self.refresh()

    def _context_menu(self, gpos):
        c = self.canvas
        sel = c.has_selection()
        m = RMenu(self)
        m.add_item("Cut", "cut", c.cut, enabled=sel)
        m.add_item("Copy", "copy", c.copy, enabled=sel)
        m.add_item("Paste", "paste", c.paste, enabled=c.can_paste())
        m.addSeparator()
        m.add_item("Crop", "crop", c.crop, enabled=sel)
        m.add_item("Select all", "sel_all", c.select_all)
        m.add_item("Invert selection", "sel_invert", c.invert_selection, enabled=sel)
        m.add_item("Delete", "delete", c.delete_selection, enabled=sel)
        m.addSeparator()
        rot = RMenu(m)
        rot.setTitle("Rotate")
        rot.setIcon(icons.qicon("rotate"))
        for text, icon, kind in (("Rotate right 90°", "rot_right", "r90"), ("Rotate left 90°", "rot_left", "l90"),
                                 ("Rotate 180°", "rot_180", "180"), ("Flip vertical", "flip_v", "flipv"),
                                 ("Flip horizontal", "flip_h", "fliph")):
            rot.add_item(text, icon, lambda k=kind: c.rotate(k))
        m.addMenu(rot)
        m.add_item("Resize", "resize", self.resize_skew)
        m.add_item("Invert color", "blank", c.invert_colors)
        m.exec(gpos)

    def resize_skew(self):
        c = self.canvas
        if not c.has_selection():
            c.commit_pending()
        dlg = ResizeSkewDialog(c.target_size(), self)
        if dlg.exec() == QDialog.Accepted:
            w, h, sh, sv = dlg.values()
            c.resize_skew(w, h, sh, sv)

    def edit_colors(self):
        st = self.state
        dlg = QColorDialog(st.color1 if st.active == 1 else st.color2, self)
        dlg.setWindowTitle("Edit Colors")
        dlg.setOption(QColorDialog.DontUseNativeDialog, True)
        pal = self._color_sets[0][2]
        for i, col in enumerate(pal.custom):
            QColorDialog.setCustomColor(i, col if col is not None else QColor(255, 255, 255))
        if dlg.exec() == QDialog.Accepted:
            col = dlg.currentColor()
            for _c1, _c2, p in self._color_sets:
                p.add_custom(col)
            st.set_active_color(col)

    def properties(self):
        self.canvas.commit_pending()
        dlg = PropertiesDialog(self.doc, self)
        if dlg.exec() != QDialog.Accepted:
            return
        w, h, bw = dlg.values()
        if bw:
            r = QMessageBox.warning(self, "Paint", "Converting to black and white cannot be undone. This action "
                                    "affects the current file and may cause some color information to be lost.\n\n"
                                    "Do you want to continue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r == QMessageBox.Yes:
                self.doc.push_undo()
                self.doc.set_image(reduce_colors(self.doc.image, "bmp1"))
        self.doc.resize_canvas(w, h, self.state.color2)

    def about(self):
        AboutDialog(self).exec()

    # -- files -------------------------------------------------------------------
    def _recent(self):
        v = self.settings.value("recent", [])
        if isinstance(v, str):
            v = [v]
        return [p for p in (v or []) if os.path.exists(p)]

    def _add_recent(self, path):
        lst = [path] + [p for p in self._recent() if p != path]
        self.settings.setValue("recent", lst[:9])

    def _start_dir(self):
        d = self.settings.value("dir", "")
        if d and os.path.isdir(d):
            return d
        return QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~")

    def maybe_save(self):
        """True if it is fine to discard the current picture."""
        self.canvas.commit_pending()
        if not self.doc.modified:
            return True
        r = ask_save(self, self.doc.title())
        if r == "save":
            return self.save()
        return r == "discard"

    def new(self):
        if not self.maybe_save():
            return
        self.doc.new(DEFAULT_W, DEFAULT_H)
        self.canvas.set_zoom(1.0)

    def open(self):
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open", self._start_dir(), OPEN_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            self.doc.load(path)
        except Exception as ex:
            QMessageBox.warning(self, "Paint", f"Paint cannot read this file.\n\n{path}\n{ex}")
            return False
        self.settings.setValue("dir", os.path.dirname(os.path.abspath(path)))
        self._add_recent(os.path.abspath(path))
        self.canvas.set_zoom(1.0)
        self.canvas.horizontalScrollBar().setValue(0)
        self.canvas.verticalScrollBar().setValue(0)
        return True

    def save(self):
        self.canvas.commit_pending()
        if not self.doc.path:
            return self.save_as()
        return self._write(self.doc.path, self.doc.fmt)

    def save_as(self, fmt=None):
        self.canvas.commit_pending()
        fmt = fmt or (self.doc.fmt if self.doc.path else "png")
        filters = [label for _k, label, _e in FORMATS]
        start = self.doc.path or os.path.join(self._start_dir(), "Untitled")
        base = os.path.splitext(start)[0] + "." + FORMAT_BY_KEY[fmt][1][0]
        dlg = QFileDialog(self, "Save As", base)
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        dlg.setNameFilters(filters)
        dlg.selectNameFilter(FORMAT_BY_KEY[fmt][0])
        dlg.selectFile(base)
        if dlg.exec() != QDialog.Accepted or not dlg.selectedFiles():
            return False
        path = dlg.selectedFiles()[0]
        chosen = next((k for k, label, _e in FORMATS if label == dlg.selectedNameFilter()), fmt)
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if not ext:
            path += "." + FORMAT_BY_KEY[chosen][1][0]
        elif ext not in FORMAT_BY_KEY[chosen][1]:
            chosen = format_for_path(path, chosen)
        return self._write(path, chosen)

    def _write(self, path, fmt):
        if fmt in LOSSY:
            r = QMessageBox.warning(self, "Paint", "The color quality might be reduced if you save the picture "
                                    "in this format.\n\nDo you want to continue?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r != QMessageBox.Yes:
                return False
        try:
            self.doc.save(path, fmt)
        except Exception as ex:
            QMessageBox.warning(self, "Paint", f"Paint could not save this file.\n\n{path}\n{ex}")
            return False
        self.settings.setValue("dir", os.path.dirname(os.path.abspath(path)))
        self._add_recent(os.path.abspath(path))
        return True

    def paste_from(self):
        path, _ = QFileDialog.getOpenFileName(self, "Paste From", self._start_dir(), OPEN_FILTER)
        if path:
            try:
                self.canvas.paste_from(path)
            except Exception as ex:
                QMessageBox.warning(self, "Paint", f"Paint cannot read this file.\n\n{path}\n{ex}")

    # -- printing ------------------------------------------------------------------
    def _get_printer(self):
        from PySide6.QtPrintSupport import QPrinter
        if self._printer is None:
            self._printer = QPrinter(QPrinter.HighResolution)
            if self.doc.width() > self.doc.height():
                self._printer.setPageOrientation(QPageLayout.Landscape)
        return self._printer

    def _render_page(self, printer):
        p = QPainter(printer)
        page = printer.pageLayout().paintRectPixels(printer.resolution())
        img = self.doc.image
        dpi_scale = printer.resolution() / 96.0
        w, h = img.width() * dpi_scale, img.height() * dpi_scale
        k = min(1.0, page.width() / w, page.height() / h)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(QRect(0, 0, int(w * k), int(h * k)), img)
        p.end()

    def print_(self):
        from PySide6.QtPrintSupport import QPrintDialog
        self.canvas.commit_pending()
        printer = self._get_printer()
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QDialog.Accepted:
            self._render_page(printer)

    def page_setup(self):
        from PySide6.QtPrintSupport import QPageSetupDialog
        QPageSetupDialog(self._get_printer(), self).exec()

    def print_preview(self):
        from PySide6.QtPrintSupport import QPrintPreviewDialog
        self.canvas.commit_pending()
        dlg = QPrintPreviewDialog(self._get_printer(), self)
        dlg.paintRequested.connect(self._render_page)
        dlg.resize(820, 640)
        dlg.exec()

    # -- sharing -------------------------------------------------------------------
    def _export_copy(self, name):
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or tempfile.gettempdir()
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, name)
        self.canvas.commit_pending()
        self.doc.image.save(path, "PNG")
        return path

    def send_email(self):
        path = self._export_copy((os.path.splitext(self.doc.title())[0] or "picture") + ".png")
        try:
            subprocess.Popen(["xdg-email", "--attach", path])
        except OSError:
            QDesktopServices.openUrl(QUrl("mailto:?subject=" + os.path.basename(path)))

    def set_wallpaper(self, mode):
        path = self._export_copy("wallpaper.png")
        uri = QUrl.fromLocalFile(path).toString()
        attempts = []
        if sys.platform == "darwin":
            attempts.append(["osascript", "-e",
                             f'tell application "System Events" to set picture of every desktop to "{path}"'])
        else:
            opt = {"fill": "zoom", "tile": "wallpaper", "center": "centered"}[mode]
            attempts.append(["sh", "-c",
                             f"gsettings set org.gnome.desktop.background picture-uri '{uri}' && "
                             f"gsettings set org.gnome.desktop.background picture-uri-dark '{uri}' && "
                             f"gsettings set org.gnome.desktop.background picture-options '{opt}'"])
            attempts.append(["plasma-apply-wallpaperimage", path])
            attempts.append(["sh", "-c", "xfconf-query -c xfce4-desktop -l | grep last-image | "
                                         f"xargs -I{{}} xfconf-query -c xfce4-desktop -p {{}} -s '{path}'"])
            feh = {"fill": "--bg-fill", "tile": "--bg-tile", "center": "--bg-center"}[mode]
            attempts.append(["feh", feh, path])
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "kde" in desktop:
            attempts.insert(0, attempts.pop(1))
        elif "xfce" in desktop:
            attempts.insert(0, attempts.pop(2))
        for cmd in attempts:
            try:
                if subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                continue
        QMessageBox.information(self, "Paint", "The desktop background could not be set automatically on this "
                                f"desktop. The picture was saved here so you can set it yourself:\n\n{path}")

    # -- application menu ----------------------------------------------------------
    def _open_app_menu(self):
        tb = self.ribbon.tabbar
        menu = AppMenu(self._recent(), self)
        tb.app_open = True
        tb.update()

        def closed():
            tb.app_open = False
            tb.update()
        menu.closed.connect(closed)
        menu.triggered.connect(self._app_action)
        menu.move(tb.mapToGlobal(QPoint(0, 0)))
        menu.show()
        menu.setFocus()

    def _app_action(self, action):
        if action.startswith("recent:"):
            if self.maybe_save():
                self.open_path(action[7:])
            return
        if action.startswith("saveas:"):
            self.save_as(action[7:])
            return
        if action.startswith("desktop:"):
            self.set_wallpaper(action[8:])
            return
        handlers = {
            "new": self.new, "open": self.open, "save": self.save, "saveas": self.save_as,
            "print": self.print_, "print:setup": self.page_setup, "print:preview": self.print_preview,
            "email": self.send_email, "properties": self.properties, "about": self.about, "exit": self.close,
        }
        fn = handlers.get(action)
        if fn:
            fn()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                e.acceptProposedAction()
                if self.maybe_save():
                    self.open_path(u.toLocalFile())
                return

    def closeEvent(self, e):
        if self.maybe_save():
            if self.thumb is not None:
                self.thumb.close()
            e.accept()
        else:
            e.ignore()
