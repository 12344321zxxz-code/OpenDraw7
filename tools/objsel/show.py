"""python show.py seed... -> /tmp/o/show_<seed>.png: scene, background mask (red = object), selection of each group."""
import sys, numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import make_scene, groups, O, QImage, QPainter, QColor
from opendraw7.document import pixels
for seed in map(int, sys.argv[1:]):
    sc = make_scene(seed); a = sc["a"]; h, w = a.shape
    bg = O.background(a)
    gs = groups(sc["cover"])
    tiles = []
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied); pixels(img)[:] = a; tiles.append(img)
    t = QImage(w, h, QImage.Format_ARGB32_Premultiplied); px = pixels(t); px[:] = a; px[~bg] = 0xFFFF0000; tiles.append(t)
    for idx, cov in gs:
        ys, xs = np.nonzero(cov > 0.99)
        k = len(ys) // 2
        m, al = O.select_object(a, int(xs[k]), int(ys[k]), bg)
        t = QImage(w, h, QImage.Format_ARGB32_Premultiplied); px = pixels(t); px[:] = a
        if m is not None: px[m] = 0xFF00C000
        px[max(0, ys[k]-3):ys[k]+4, max(0, xs[k]-3):xs[k]+4] = 0xFFFF00FF
        tiles.append(t)
    out = QImage(sum(min(400, w) + 6 for _ in tiles), int(h * min(400, w) / w), QImage.Format_RGB32); out.fill(QColor(40, 40, 40))
    p = QPainter(out); x = 0
    for t in tiles:
        s = t.scaledToWidth(min(400, w)); p.drawImage(x, 0, s); x += s.width() + 6
    p.end(); out.save(f"/tmp/o/show_{seed}.png")
    print(seed, sc["bkind"], [o["kind"] for o in sc["objs"]], "model", [(c.round().astype(int).tolist(), round(float(r),1), bool(ac), bool(so)) for c, r, ac, so in zip(*O.edge_model(a))], "noise", O.noise_level(O._bytes(a)))
