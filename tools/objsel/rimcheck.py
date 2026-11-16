"""What lifting an object does to the background around it (objectselect.clean_rim).

    QT_QPA_PLATFORM=offscreen python tools/objsel/rimcheck.py 0 120

For every object of the bench scenes with these seeds: select it, erase it and clean its rim, then
count, per background kind, the pure-background pixels that changed (should be few and by small
steps) and the faintly tinted rim pixels that were cleaned (should be nearly all on drawings).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
app = QApplication([])
import numpy as np
import bench as B
from opendraw7 import objectselect as O
stats = {}
for seed in range(int(sys.argv[1]), int(sys.argv[2])):
    sc = B.make_scene(seed)
    a = sc["a"]
    bg = O.background(a)
    allc = np.maximum.reduce(sc["cover"])
    for idx, cov in B.groups(sc["cover"]):
        others = np.zeros_like(cov)
        for j, c in enumerate(sc["cover"]):
            if j not in idx:
                others = np.maximum(others, c)
        ys, xs = np.nonzero((cov > 0.99) & (others < 0.01))
        if not len(ys):
            continue
        mask, alpha = O.select_object(a, int(xs[len(ys) // 2]), int(ys[len(ys) // 2]), bg)
        if mask is None:
            continue
        w = a.copy()
        w[mask] = 0xFFFFFFFF
        before = w.copy()
        O.clean_rim(w, mask, bg)
        ch = w != before
        d = np.abs(O._bytes(w).astype(int) - O._bytes(before).astype(int)).max(axis=2)
        pure = (allc == 0) & ~mask
        faint = (cov > 0) & (cov <= 0.12) & ~mask & (others == 0)
        s = stats.setdefault(sc["bkind"] + (" jpeg" if sc["jpeg"] else ""), [0, 0, 0, 0, 0, 0])
        s[0] += 1
        s[1] += int((ch & pure).sum())
        s[2] = max(s[2], int(d[ch & pure].max()) if (ch & pure).any() else 0)
        s[3] += int(faint.sum())
        s[4] += int((faint & ch).sum())
        s[5] += int(ch.sum())
print(f"{'background':22s} clicks  pure-bg px changed (max step)   faint rim px: cleaned / all   all changed")
for k, s in sorted(stats.items()):
    print(f"{k:22s} {s[0]:5d}  {s[1]:8d} ({s[2]:3d})               {s[4]:6d} / {s[3]:6d}            {s[5]:7d}")
