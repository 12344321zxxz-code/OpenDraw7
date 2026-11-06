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
- `colordialog.py` Edit Colors, `helpwindow.py` Help, `keytips.py` Alt key tips, `recovery.py`
  autosave and crash recovery, `scanner.py` From scanner or camera.

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
- numpy 2.5 wheels need glibc 2.38 and silently raise the package's floor. Build with
  `numpy<2.5` (manylinux_2_28) unless the floor is meant to move.
- Brush strokes and shape outlines are anti-aliased, so an exact-colour flood fill stopped at their
  soft rim and left a pale ring. `flood_fill` now also recolours that rim (`_fill_soft_edge`): it
  swaps only the background's share of each rim pixel and grows outwards only while pixels get
  darker, so it cannot step across a thin line. It works on border pixels only; keep it that way,
  a whole-area version took 14 s on a 4000x3000 picture.
- Refilling such an area left specks: rim pixels rounded to a shade a step or two off, and the next
  exact-colour fill skipped them. So the fill counts colours within `FILL_TOLERANCE` (3) as the
  clicked one, snaps rim results near the fill colour to it exactly, takes rim pixels within `NEAR`
  of the clicked colour whole, and reaches 4 px (a size-1 brush's soft fade is that wide). When
  testing with a drawn loop, make sure the loop actually closes or the fill leaks for real.
- **Never hand `doc.image` to Qt as a paint device that outlives it.** The text tool used
  `documentLayout().setPaintDevice(doc.image)`; when the text box closed, PySide deleted the
  picture's C++ object if it had been made by `convertToFormat` (every opened file, every
  transparent picture), and everything after failed with "Internal C++ object already deleted".
  It now measures against its own 1x1 image with the picture's DPI.
- Transparency: the picture is see-through exactly when `doc.image` is
  `Format_ARGB32_Premultiplied` (`doc.transparent`); otherwise it is `RGB32`. Undo snapshots carry
  the format, so undo restores it. Create pictures with `doc.blank()` and pass replacements through
  `doc.set_image()` (which calls `doc.conform()`); never build an `RGB32` picture directly.
  `_fill_soft_edge` works on all four premultiplied channels, so filling over clear pixels blends
  the stroke rim over the fill colour.
- Magic wand selections are `Selection.mask` (bool array, local coordinates) instead of a path;
  `_mask_image()`, `_erase_area()` and `doc_mask()` handle both kinds.
- Crash recovery (`recovery.py`): a killed process can stay a zombie for a while and its pid can be
  reused, so "is it still running" reads `/proc/<pid>/stat` and `cmdline`. Set
  `OPENDRAW7_AUTOSAVE_MS` to test it quickly (kill -9, relaunch).
- Key tips (`keytips.py`) are an application event filter plus a transparent overlay. Tab-opening
  tips run immediately (not deferred) so a fast second letter already sees the tab's tips.
- Size limits: every edit that can make the picture bigger (resize/skew, canvas handles, Image
  Properties, pasting something larger) goes through `document.fits()` (25,000 px a side, 120 million
  pixels). Before 0.2.1 a 30000x30000 resize or an 89/89 degree skew ran the machine out of memory
  and the app was killed. Opening files is not limited by `fits()`, but Qt's own 256 MB reader limit
  is raised to 1 GB in `load_image` so large photos open.
- Key tips must not fire after Alt+Shift (keyboard layout switching on many desktops, and the
  desktop may swallow the Shift events): Alt arms only without other modifiers, and its release
  shows tips only if no other modifier is still down.
- A randomized stress test helps: random tool/mouse/key/menu actions on the real window, with
  QMenu/RMenu/QDialog/QMessageBox `exec` stubbed out (they block forever headless; patch `RMenu`
  itself, patching `QMenu` does not reach it), plus an undo check: after every action that changes
  the picture, undo must restore the exact pixels and redo must bring them back.
- The app sets `QT_QPA_PLATFORM=xcb;wayland` on Linux because the custom title bar was only tested
  on X11. Native Wayland is untested.

## Known gaps (also listed in the README)

Not measured against a real copy of the original, so metrics and colours are from memory. Artistic
brushes and shape media are approximations. Open/save/print dialogs are Qt's. Rulers are
pixel-only. Webcam capture is untested on real hardware (only the ffmpeg command was checked).
Key tips do not reach into popup galleries (brushes, sizes) once they are open.
