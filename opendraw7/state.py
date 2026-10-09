"""Shared tool/colour state that the ribbon edits and the canvas reads."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from .brushes import DEFAULT_SIZE, SIZES, MAX_SIZE


class PaintState(QObject):
    # what: 'tool' | 'colors' | 'size' | 'style' | 'selmode' | 'transparent' | 'font' | 'textbg'
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color1 = QColor(0, 0, 0)
        self.color2 = QColor(255, 255, 255)
        self.active = 1
        self.tool = "brush"
        self.prev_tool = "brush"
        self.brush = "brush"
        self.shape = "line"
        self.sel_mode = "rect"
        self.transparent_sel = False
        self.sizes = dict(DEFAULT_SIZE)
        self.outline = "solid"
        self.fill = "none"
        self.font_family = "DejaVu Sans"
        self.font_size = 11
        self.bold = False
        self.italic = False
        self.underline = False
        self.strike = False
        self.text_opaque = False

    # -- tools ---------------------------------------------------------------
    def set_tool(self, tool, brush=None, shape=None):
        if tool not in ("picker",) and self.tool not in ("picker",):
            self.prev_tool = self.tool
        if tool == "picker" and self.tool != "picker":
            self.prev_tool = self.tool
        self.tool = tool
        if brush:
            self.brush = brush
        if shape:
            self.shape = shape
        self.changed.emit("tool")

    def restore_tool(self):
        self.tool = self.prev_tool if self.prev_tool != "picker" else "pencil"
        self.changed.emit("tool")

    def set_sel_mode(self, mode):
        self.sel_mode = mode
        self.changed.emit("selmode")

    def set_transparent(self, on):
        self.transparent_sel = bool(on)
        self.changed.emit("transparent")

    # -- sizes ---------------------------------------------------------------
    def size_key(self):
        if self.tool in ("pencil", "eraser"):
            return self.tool
        if self.tool == "brush":
            return self.brush
        if self.tool == "shape":
            return "shape"
        return None

    def size(self):
        k = self.size_key()
        return self.sizes[k] if k else 1

    def size_choices(self):
        k = self.size_key()
        return SIZES[k] if k else []

    def set_size(self, v):
        k = self.size_key()
        if k:
            self.sizes[k] = max(1, min(MAX_SIZE, int(v)))
            self.changed.emit("size")

    # -- colours -------------------------------------------------------------
    def set_color(self, which, color):
        c = QColor(color)
        c.setAlpha(255)
        if which == 1:
            self.color1 = c
        else:
            self.color2 = c
        self.changed.emit("colors")

    def set_active_color(self, color):
        self.set_color(self.active, color)

    def set_active(self, which):
        self.active = which
        self.changed.emit("colors")

    # -- shapes / text -------------------------------------------------------
    def set_outline(self, style):
        self.outline = style
        self.changed.emit("style")

    def set_fill(self, style):
        self.fill = style
        self.changed.emit("style")

    def set_font(self, **kw):
        for k, v in kw.items():
            setattr(self, {"family": "font_family", "size": "font_size"}.get(k, k), v)
        self.changed.emit("font")

    def set_text_opaque(self, on):
        self.text_opaque = bool(on)
        self.changed.emit("textbg")
