import sys, time, numpy as np
import os; HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..'))
from PySide6.QtGui import QGuiApplication, QImage, QColor
app = QGuiApplication([])
from scenes import scene
from opendraw7.document import const_pixels
from opendraw7 import objectselect as O
import tempfile, os
kinds = sys.argv[1:] or ("white", "flat_color", "sky", "transparent", "night", "edge_cut", "jpeg")
for kind in kinds:
    img, truths, figs = scene("sky" if kind == "jpeg" else kind)
    if kind == "jpeg":
        path = os.path.join(tempfile.mkdtemp(), "s.jpg"); img.save(path, "JPG", 70); img = QImage(path)
    a = const_pixels(img.convertToFormat(QImage.Format_ARGB32_Premultiplied)).copy()
    t0 = time.time()
    bg = O.background(a)
    for i, (cx, cy, s, _c) in enumerate(figs):
        x, y = int(cx), int(cy + 20 * s)          # click on the body
        mask, alpha = O.select_object(a, x, y, bg)
        tr = truths[i]
        solid = tr > 0.5
        inter = (mask & solid).sum(); union = (mask | solid).sum()
        other = truths[1 - i] > 0.5
        print(f"{kind:12s} figure {i+1}: IoU {inter/union:.4f}  missed {int((solid & ~mask).sum())}px  extra {int((mask & ~solid).sum())}px"
              f"  took other figure {int((mask & other).sum())}px  alpha err {np.abs(np.where(mask, alpha, 0) - tr)[tr > 0.02].mean():.3f}")
    mask, alpha = O.select_object(a, 5, 5, bg)
    both = (truths[0] > 0.5) | (truths[1] > 0.5)
    print(f"{kind:12s} click background: IoU {(mask & both).sum() / (mask | both).sum():.4f}  ({time.time()-t0:.2f}s)")

# fringe check: cut the character out of a white background and put it on red
from opendraw7.objectselect import cutout
img, truths, figs = scene("white")
a = const_pixels(img.convertToFormat(QImage.Format_ARGB32_Premultiplied)).copy()
mask, alpha = O.select_object(a, 200, 248)
cut = cutout(a, mask, alpha)
A = (cut >> 24).astype(np.float32) / 255
ch = lambda v, sh: ((v >> sh) & 255).astype(np.float32)
over = lambda prem, bgc: prem + (1 - A) * bgc
R, G, B = over(ch(cut, 16), 255), over(ch(cut, 8), 0), over(ch(cut, 0), 0)
rim = mask & (A > 0.02) & (A < 0.98)
whiteish = rim & (G > 90) & (B > 90)        # a white fringe would show as pink/white pixels on red
print(f"fringe check on red: {int(rim.sum())} rim pixels, {int(whiteish.sum())} look whitish")
# naive cut (no soft edge): how many whitish pixels a plain cut would leave
Rn = np.where(mask, ch(a, 16), 255); Gn = np.where(mask, ch(a, 8), 0); Bn = np.where(mask, ch(a, 0), 0)
print(f"  for comparison, a plain hard cut leaves {int((mask & (Gn > 90) & (Bn > 90) & ~(truths[0] > 0.98)).sum())} whitish rim pixels")
# big picture
big = QImage(4000, 3000, QImage.Format_RGB32); big.fill(QColor(255, 255, 255))
from PySide6.QtGui import QPainter
p = QPainter(big); p.drawImage(1500, 1200, img); p.end()
ab = const_pixels(big).copy()
t = time.time(); m, al = O.select_object(ab, 1700, 1448); print(f"4000x3000 picture: {time.time() - t:.2f}s, selected {int(m.sum())} px")
