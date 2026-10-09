# OpenDraw7 - notes for whoever works on this next

A paint program for Linux that reproduces the look and behaviour of the Paint from Windows 7
(ribbon era). Python + PySide6 (Qt 6), no bitmap assets: every icon is drawn in `opendraw7/icons.py`.
Owner: Ariel. Goal he set: everything that is not copyrighted should match the original as closely
as possible; icons and cursors are redrawn because the originals are copyrighted.

## Run, test, build

```sh
python run.py                                             # needs PySide6-Essentials, numpy
QT_QPA_PLATFORM=offscreen python tests/smoke_test.py      # must print "OK - N checks passed"
QT_QPA_PLATFORM=offscreen python tools/shot.py out.png    # screenshot of the main window
packaging/build.sh                                        # dist/OpenDraw7-<ver>-linux-x86_64.tar.gz
```

Run the smoke test after any change. Look at a screenshot after any visual change.
`opendraw7 --self-test` runs checks inside the program itself; `packaging/build.sh` runs it on the
packaged build and refuses to archive a build that fails.

## How it is put together

- `state.py` PaintState: tool, colours, sizes, styles. The ribbon writes it, the canvas listens.
- `document.py`: the QImage, undo stack (whole-image snapshots, copy-on-write), flood fill, BMP and
  GIF writers (Qt cannot write GIF or low-colour BMP).
- `canvas.py` Canvas: scroll area, zoom, and the edit commands. `tools.py`: one class per tool.
  A tool with something in progress (floating selection, adjustable shape, text box) reports
  `has_pending()`, draws it through `composite()`/`paint()`, and writes it into the picture in
  `commit()`. Undo first commits whatever is pending, then undoes.
- `ribbon.py`: custom-painted widgets placed by hand (no layouts) so the metrics stay fixed.
  `mainwindow.py` builds the tabs and wires commands; `refresh()` updates every enabled/checked state.
- `chrome.py`: the frameless window's title bar (holds the quick access toolbar), status bar, rulers.

## Things learned the hard way

- **Test with a real mouse too.** Offscreen tests missed that a `Qt.Popup` receives the *release* of
  the click that opened it and closed itself. `Popup.takes_release()` guards this. For real input:
  `Xvfb :77` + `openbox` + `xdotool` + ImageMagick `import -window root shot.png` (apt has all of
  them). Give xdotool ~0.3 s between steps or window moves and drags misfire.
- **Test the packaged build, not just the source.** 0.1.0 shipped without the stdlib module
  `secrets`, which `numpy.random` imports from compiled code where PyInstaller cannot see it. Every
  textured brush and shape style failed on the user's machine while all source tests passed. The
  spec now lists it as a hidden import and `--self-test` exists to catch the next one.
- A tool that raises inside `paintEvent` used to blank the canvas for good. `Canvas` now catches
  tool failures, drops the in-progress object and keeps painting. Keep it that way.
- Do not `pkill -f` a pattern that appears in your own command line; it kills the shell.
- `QPainterPath.united()` flattens curves with an absolute tolerance. Build boolean shapes at a
  large scale and scale down (see the callouts in `shapes.py`).
- After `p.setBrush(gradient)` a later `drawRect` fills with it. Reset to `Qt.NoBrush`.
- Qt's X11 plugin needs `libxcb-cursor.so.0`, which many desktops lack. The package ships it
  (`packaging/fetch_vendor.sh`). Every other system library is deliberately *not* bundled: the
  build machine's copies need its newer glibc and would break older distros. The package's glibc
  floor is PySide6's (2.34 with PySide6 6.12). Check with `objdump -T` over the bundle.
- The app sets `QT_QPA_PLATFORM=xcb;wayland` on Linux because the custom title bar was only tested
  on X11. Native Wayland is untested.

## Known gaps (also listed in the README)

Not measured against a real copy of the original, so metrics and colours are from memory. Artistic
brushes and shape media are approximations. No Alt key tips. Scanner import is disabled. Dialogs
are Qt's. Rulers are pixel-only.
