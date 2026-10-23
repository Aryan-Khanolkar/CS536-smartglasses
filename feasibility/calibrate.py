"""Camera calibration from checkerboard photos (OpenCV).

Finds the glasses camera's focal length, optical center and lens distortion,
and saves them to a JSON file that measure_test.py uses.

    python feasibility/calibrate.py --images feasibility/calib --square-cm 2.5 --cols 9 --rows 6

--cols / --rows are the number of INNER corners (where four squares meet),
not the number of squares. A board with 10 x 7 squares has 9 x 6 inner corners.

Good photos: 15-20 of them, board flat (tape it to cardboard), seen from
different angles and distances, and some with the board near the frame corners.
"""
import argparse
import glob
import json
import math
import os

import cv2
import numpy as np


def find_corners(paths, pattern):
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    found_pts, used, size = [], [], None
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if size is None:
            size = gray.shape[::-1]
        elif gray.shape[::-1] != size:
            print(f"  skip {os.path.basename(p)}: different resolution")
            continue
        ok, corners = cv2.findChessboardCorners(gray, pattern, flags)
        if not ok:
            print(f"  no board found in {os.path.basename(p)}")
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), crit)
        found_pts.append(corners)
        used.append(p)
    return found_pts, used, size


def calibrate(paths, cols, rows, square_m):
    pattern = (cols, rows)
    objp = np.zeros((cols * rows, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_m

    img_pts, used, size = find_corners(paths, pattern)
    if len(img_pts) < 5:
        raise SystemExit(f"only {len(img_pts)} usable photos; need at least 5 (15+ is better)")

    obj_pts = [objp] * len(img_pts)
    rms, K, dist, _, _ = cv2.calibrateCamera(obj_pts, img_pts, size, None, None)
    w, h = size
    hfov = 2 * math.degrees(math.atan(w / (2 * K[0, 0])))
    vfov = 2 * math.degrees(math.atan(h / (2 * K[1, 1])))
    return {
        "width": w, "height": h,
        "K": K.tolist(), "dist": dist.ravel().tolist(),
        "rms_px": float(rms), "hfov_deg": hfov, "vfov_deg": vfov,
        "images_used": len(used),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="feasibility/calib")
    ap.add_argument("--cols", type=int, default=9, help="inner corners per row")
    ap.add_argument("--rows", type=int, default=6, help="inner corners per column")
    ap.add_argument("--square-cm", type=float, required=True, help="measured size of one square")
    ap.add_argument("--out", default="feasibility/calib.json")
    a = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(a.images, "*.jpg")) + glob.glob(os.path.join(a.images, "*.png")))
    print(f"{len(paths)} images in {a.images}")
    res = calibrate(paths, a.cols, a.rows, a.square_cm / 100)

    with open(a.out, "w") as f:
        json.dump(res, f, indent=2)
    K = res["K"]
    print(f"\nused {res['images_used']} images, {res['width']}x{res['height']}")
    print(f"focal length fx={K[0][0]:.1f}px fy={K[1][1]:.1f}px, center=({K[0][2]:.1f}, {K[1][2]:.1f})")
    print(f"field of view {res['hfov_deg']:.1f} x {res['vfov_deg']:.1f} deg")
    print(f"reprojection error {res['rms_px']:.2f} px  (under ~0.5 is good, over 1 means redo with better photos)")
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
