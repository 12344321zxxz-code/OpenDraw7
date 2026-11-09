# Object selection evaluation

- `eval.py`: cartoon-style test scenes (white, flat colour, sky gradient with horizon, transparent,
  night, a figure cut off by the edge, JPEG noise) with exact ground truth; prints overlap (IoU),
  missed/extra pixels, leaks into the other figure, edge opacity error, a fringe check (cut-out moved
  onto red) and timing on 4000x3000.
- `photos.py`: real photos from scikit-image's sample data (`pip install scikit-image`; run
  `python -c "from skimage import data"` once and save them as `photo_<name>.npy` as in the script),
  a contact sheet of selections and 40 random clicks per photo.

- `bench.py [N] [first_seed]`: the main benchmark. Random scenes (11 background kinds, 6 object kinds,
  overlaps, cut-offs, JPEG) with exact answers; reports soft IoU by background and object and the
  worst scenes. Tune on seeds 0-329, check on 1000-1329 (never tuned on). `BENCH_DUMP=file.json`
  writes every click's score, to compare two versions scene by scene. `show.py seed...` draws a
  scene, its background mask and each selection to /tmp/o/show_<seed>.png.

Results:
- 0.3.1: bench 0-329 mean 0.830 (17.5 % of clicks below 0.5), 1000-1329 mean 0.798 (21.4 %).
- 0.3.2: bench 0-329 mean 0.973 (1.1 % below 0.5), 1000-1329 mean 0.954 (3.5 %). Weakest: dark and
  JPEG backgrounds; a near-black outline on a near-black sky is background-coloured, so a figure's
  parts may come apart. Photos: good on plain/smooth backgrounds, partial on textured ones, poor
  when the subject fills the frame or touches a long stretch of the edge in background colours.
