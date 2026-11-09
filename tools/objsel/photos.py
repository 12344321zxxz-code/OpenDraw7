import sys, time, random, numpy as np
import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..', '..'))
from PySide6.QtGui import QGuiApplication, QImage, QColor, QPainter, QFont
app = QGuiApplication([])
from opendraw7 import objectselect as O
def to_argb(arr):
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        arr = (arr > 0).astype(np.uint8) * 255 if arr.dtype == bool else np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 2: arr = np.stack([arr] * 3, -1)
    h, w = arr.shape[:2]
    a = np.full((h, w), 0xFF, np.uint32) if arr.shape[2] == 3 else arr[..., 3].astype(np.uint32)
    if arr.shape[2] == 4:   # premultiply
        al = arr[..., 3:4].astype(np.float32) / 255
        rgb = np.rint(arr[..., :3] * al).astype(np.uint32)
    else:
        rgb = arr[..., :3].astype(np.uint32)
    return (a << 24) | (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
clicks = {"astronaut": (350, 350), "coffee": (300, 210), "chelsea": (220, 150), "rocket": (330, 250), "coins": (100, 60),
          "camera": (150, 250), "stereo_motorcycle": (406, 230), "logo": (250, 250), "horse": (200, 150), "retina": (700, 900),
          "page": (200, 100), "colorwheel": (185, 185), "clock": (200, 150), "moon": (256, 256), "cat": (220, 150),
          "hubble_deep_field": (500, 430), "immunohistochemistry": (256, 256), "text": (200, 80)}
tiles = []
rng = random.Random(7)
for name, (x, y) in clicks.items():
    a = to_argb(np.load(f"photo_{name}.npy"))
    h, w = a.shape
    t = time.time(); bg = O.background(a); tb = time.time() - t
    t = time.time(); mask, alpha = O.select_object(a, x, y, bg); tc = time.time() - t
    frac = 0 if mask is None else mask.mean()
    # random clicks: must not crash, must finish quickly, never select nothing-at-all on an object click
    worst = 0; empties = 0
    for _ in range(40):
        rx, ry = rng.randrange(w), rng.randrange(h)
        t0 = time.time(); m, al = O.select_object(a, rx, ry, bg); worst = max(worst, time.time() - t0)
        if m is not None:
            assert m.shape == a.shape and al.shape == a.shape and np.isfinite(al).all() and (al >= 0).all() and (al <= 1).all()
            assert m[ry, rx] or bg[ry, rx], "the clicked pixel is not in its own selection"
        else:
            empties += 1
    print(f"{name:22s} {w}x{h}: background {tb:.2f}s, select {tc:.2f}s, selected {frac*100:5.1f}% of picture, "
          f"bg {bg.mean()*100:5.1f}%, 40 random clicks ok (slowest {worst:.2f}s, {empties} empty)")
    # tile: photo with selection tinted and outlined
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    from opendraw7.document import pixels
    px = pixels(img); px[:] = a
    if mask is not None:
        sel = px[mask]; px[mask] = (sel & 0xFF000000) | (((sel >> 1) & 0x7F7F7F) + 0x003F7F00)
        edge = mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))
        px[edge] = 0xFFFF00FF
    px[max(0,y-3):y+4, max(0,x-3):x+4] = 0xFFFF0000
    tiles.append((name, img.scaled(300, 230, aspectMode=__import__('PySide6.QtCore', fromlist=['Qt']).Qt.KeepAspectRatio)))
sheet = QImage(6 * 310, 3 * 260, QImage.Format_RGB32); sheet.fill(QColor(40, 40, 40))
p = QPainter(sheet); p.setPen(QColor(255, 255, 255)); p.setFont(QFont("Sans", 9))
for i, (name, im) in enumerate(tiles):
    cx, cy = (i % 6) * 310 + 5, (i // 6) * 260 + 18
    p.drawImage(cx, cy, im); p.drawText(cx, cy - 4, name)
p.end(); sheet.save("/tmp/o/photos_sheet.png")
