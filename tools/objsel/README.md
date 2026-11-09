# Object selection evaluation

- `eval.py`: cartoon-style test scenes (white, flat colour, sky gradient with horizon, transparent,
  night, a figure cut off by the edge, JPEG noise) with exact ground truth; prints overlap (IoU),
  missed/extra pixels, leaks into the other figure, edge opacity error, a fringe check (cut-out moved
  onto red) and timing on 4000x3000.
- `photos.py`: real photos from scikit-image's sample data (`pip install scikit-image`; run
  `python -c "from skimage import data"` once and save them as `photo_<name>.npy` as in the script),
  a contact sheet of selections and 40 random clicks per photo.

Results at 0.3.1: cartoons 95-99 % IoU, no leaks between figures, no white fringe; photos good on
plain or smooth backgrounds, partial on textured ones, poor when the subject fills the frame.
