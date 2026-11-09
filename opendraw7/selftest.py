"""Built-in self-test: `opendraw7 --self-test`.

Runs inside the real program (including a packaged build), so it catches modules or
plugins that are missing from a bundle. Exits 0 when everything works.
"""
import os
import tempfile
import traceback

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QGuiApplication


def run(app) -> int:
    from . import icons
    from .appmenu import AppMenu
    from .brushes import BRUSHES, STYLES, make_stroke, preview, render_shape, ReplaceStroke
    from .dialogs import ResizeSkewDialog, PropertiesDialog, AboutDialog
    from .document import FORMATS, save_image, load_image, flood_fill, reduce_colors
    from .mainwindow import MainWindow
    from .ribbon import GridPopup
    from .shapes import SHAPES, shape_path

    win = MainWindow()
    win.show()
    app.processEvents()
    st, c, doc = win.state, win.canvas, win.doc
    failures = []
    count = 0
    tmp = tempfile.mkdtemp(prefix="opendraw7-selftest-")

    def step(name, fn):
        nonlocal count
        count += 1
        try:
            fn()
            app.processEvents()
        except Exception:
            failures.append(name)
            print(f"FAIL {name}")
            traceback.print_exc()

    def all_icons():
        for name, (grid, _fn) in icons._drawers.items():
            assert not icons.pixmap(name).isNull()
            assert not icons.pixmap(name, 32, False).isNull()
        for sid, _ in SHAPES:
            icons.shape_glyph(sid)
        for cur in ("cross", "pencil", "fill", "picker", "magnifier"):
            icons.cursor(cur)
        assert not icons.app_icon().isNull()

    step("icons", all_icons)

    for bid, _label in BRUSHES:
        step(f"brush preview {bid}", lambda b=bid: preview(b))

        def stroke(b=bid):
            s = make_stroke(b, doc.image, QColor(200, 30, 30), 16)
            s.start(QPointF(20.5, 20.5))
            for i in range(1, 20):
                s.line_to(QPointF(20.5 + i * 9, 20.5 + (i % 5) * 7))
                s.tick()
            s.finish()
        step(f"brush stroke {bid}", stroke)
    for kind in ("pencil", "eraser"):
        step(f"stroke {kind}", lambda k=kind: make_stroke(k, doc.image, QColor(0, 0, 0), 4).start(QPointF(5, 5)))
    step("colour-replace eraser",
         lambda: ReplaceStroke(doc.image, QColor(255, 255, 255), 8, QColor(0, 0, 0)).start(QPointF(5, 5)))

    def styles():
        img = QImage(200, 200, QImage.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        for outline, _ in STYLES:
            for fill, _ in STYLES:
                p = QPainter(img)
                try:
                    render_shape(p, shape_path("star5", QRect(20, 20, 150, 150)), 8, outline, QColor(0, 0, 0),
                                 fill, QColor(255, 200, 0))
                finally:
                    p.end()
    step("every outline and fill style", styles)

    def shapes():
        for sid, _ in SHAPES:
            if sid in ("line", "curve", "polygon"):
                continue
            assert not shape_path(sid, QRect(0, 0, 80, 60)).isEmpty(), sid
    step("shape geometry", shapes)

    def pending_shape_paint():
        st.set_tool("shape", shape="heart")
        st.set_outline("crayon")
        st.set_fill("watercolor")
        t = c.tool
        from PySide6.QtCore import QPoint
        t.kind, t.p0, t.p1, t.left, t.moved = "heart", QPoint(300, 100), QPoint(420, 200), True, True
        c.invalidate()
        win.grab()
        c.commit_pending()
        st.set_outline("solid")
        st.set_fill("none")
    step("adjustable shape with textured styles", pending_shape_paint)

    step("flood fill", lambda: flood_fill(doc.image, 700, 500, QColor(10, 200, 90)))

    def wand_and_clear():
        st.set_tool("select")
        c.select_tool.wand(QPoint(5, 5))
        assert c.select_tool.sel is not None
        c.select_tool.invert()
        c.commit_pending()
        doc.set_transparent(True)
        c.select_tool.wand(QPoint(5, 5))
        c.delete_selection()
        assert doc.transparent
        out = os.path.join(tmp, "clear.gif")
        save_image(doc.image, out, "gif")
        assert load_image(out).hasAlphaChannel()
        win.grab()
        doc.set_transparent(False)
        st.set_tool("brush")
    step("magic wand and transparency", wand_and_clear)

    def extras():
        from .helpwindow import HelpWindow
        from .scanner import AcquireDialog
        from .recovery import AutoSaver
        h = HelpWindow(win)
        h.search.setText("wand")
        h.grab()
        h.deleteLater()
        AcquireDialog(win).deleteLater()
        saver = AutoSaver(win, interval=10 ** 9, folder=tmp)
        doc.push_undo()
        doc.changed.emit()
        assert saver.save_now(wait=True)
        saver.clear()
        saver.timer.stop()
        win.keytips.show(1)
        win.keytips.show(2, win.home_idx)
        win.grab()
        win.keytips.hide()
        c.zoom_to_fit()
        c.set_zoom(1.0)
    step("help, devices, autosave, key tips, fit", extras)

    def layers():
        from .document import load_ora
        win.set_layers_pane(True)
        pane = win.layers_pane
        pane.add()
        pane.duplicate()
        pane.move(-1)
        doc.set_layer_props(1, opacity=0.5)
        c.display_image()
        win.grab()
        out = os.path.join(tmp, "layers.ora")
        doc.save(out, "ora")
        assert len(load_ora(out)) == 3
        pane.merge()
        pane.flatten()
        assert len(doc.layers) == 1
        win.set_layers_pane(False)
    step("layers and OpenRaster", layers)

    def object_sel():
        doc.new(300, 200)
        p = QPainter(doc.image)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(0, 0, 0), 3))
        p.setBrush(QColor(240, 180, 60))
        p.drawEllipse(QRectF(60, 40, 120, 110))
        p.end()
        st.set_tool("select")
        st.set_sel_mode("object")
        c.select_tool.object_select(QPoint(120, 95))
        s = c.select_tool.sel
        assert s is not None and s.soft is not None and 55 <= s.rect.left() <= 62
        c.select_tool.lift()
        c.commit_pending()
        st.set_sel_mode("rect")
        doc.new(800, 600)
    step("object selection", object_sel)

    def text():
        st.set_tool("text")
        c.text_tool._create(QRect(40, 300, 260, 40))
        c.text_tool.insert_text("Self-test שלום 123")
        win.grab()
        c.commit_pending()
        assert not c.text_editing()
    step("text", text)

    def selection():
        st.set_tool("select")
        c.select_tool.set_selection(QRect(10, 10, 120, 80))
        c.select_tool.lift()
        st.set_transparent(True)
        c.select_tool.sel.rect = QRect(60, 60, 180, 100)
        win.grab()
        st.set_transparent(False)
        c.rotate("r90")
        c.resize_skew(90, 140, 10, 5)
        c.invert_colors()
        c.copy()
        c.commit_pending()
        c.paste()
        c.commit_pending()
        c.select_all()
        c.crop()
    step("selection, clipboard and transforms", selection)

    def whole_picture():
        c.rotate("l90")
        c.rotate("fliph")
        c.resize_skew(320, 240, 0, 12)
        c.undo()
        c.redo()
    step("whole-picture transforms and undo", whole_picture)

    for key, _label, exts in FORMATS:
        def fmt(k=key, e=exts[0]):
            path = os.path.join(tmp, f"t_{k}.{e}")
            save_image(doc.image, path, k)
            back = load_image(path)
            assert back.size() == doc.size(), "size changed"
            reduce_colors(doc.image, k)
        step(f"format {key}", fmt)

    def menus():
        for m in (win._brush_menu(), win._size_menu() if st.size_key() else None, win._select_menu(),
                  win._rotate_menu(), win._style_menu("outline"), win._style_menu("fill"), win._qat_menu()):
            if m is not None:
                m.grab()
                m.deleteLater()
        am = AppMenu(["/tmp/example.png"], win)
        am._pane = 3
        am.grab()
        am.deleteLater()
        g = GridPopup([(sid, lab, icons.shape_glyph(sid)) for sid, lab in SHAPES], 7, 22, "heart", win)
        g.grab()
        g.deleteLater()
    st.set_tool("brush")
    step("menus and galleries", menus)

    def dialogs():
        from PySide6.QtWidgets import QFileDialog
        from .colordialog import EditColorsDialog
        for d in (ResizeSkewDialog(QSize(800, 600), win), PropertiesDialog(doc, win), AboutDialog(win),
                  EditColorsDialog(QColor(1, 2, 3), [], win)):
            d.grab()
            d.deleteLater()
        fd = QFileDialog(win, "Save As", tmp)
        fd.deleteLater()
    step("dialogs", dialogs)

    def printing():
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPageSetupDialog, QPrintPreviewDialog  # noqa: F401
        pr = QPrinter(QPrinter.HighResolution)
        pr.setOutputFormat(QPrinter.PdfFormat)
        out = os.path.join(tmp, "page.pdf")
        pr.setOutputFileName(out)
        win._render_page(pr)
        assert os.path.getsize(out) > 500
    step("printing to PDF", printing)

    def views():
        for i in (win.view_idx, win.home_idx):
            win.ribbon.set_current(i)
            win.grab()
        win.set_rulers(True)
        win.set_grid(True)
        c.set_zoom(4)
        win.grab()
        c.set_zoom(0.5)
        win.grab()
        c.set_zoom(1)
        win.set_rulers(False)
        win.set_grid(False)
        win.resize(640, 480)
        app.processEvents()
        win.grab()
    step("tabs, zoom, rulers, narrow window", views)

    step("clipboard", lambda: QGuiApplication.clipboard().setImage(doc.image))

    doc.modified = False
    win.close()
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} of {count} steps: {', '.join(failures)}")
        return 1
    print(f"SELF-TEST OK - {count} steps")
    return 0
