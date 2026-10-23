"""Feasibility test: how accurately can we measure distance and size from one glasses frame?

For each photo listed in objects.csv:
  1. undistort it with the calibration (calib.json)
  2. click the object (or use --center to aim at the image center, like the app's crosshair)
  3. SAM segments the object under that point (N cycles through its 3 candidate masks, Enter accepts)
  4. a metric depth model estimates distance; size = pixel extent x distance / focal length
  5. compare with the tape-measure values

Prints error stats raw and after the one-time reference correction, and writes results.csv.

    python feasibility/measure_test.py --csv feasibility/objects.csv --images feasibility/captures

objects.csv columns:
    image, true_distance_m, true_width_cm, true_height_cm, ref, notes
  - true_distance_m: tape distance from the glasses to the FRONT face of the object
  - width/height: the face pointing at the camera (leave blank to skip size for that row)
  - ref: 1 for the known-size reference shots (e.g. a box you measured carefully), else 0
         the reference rows are used to correct the global scale and are left out of the
         corrected stats so the test stays honest
"""
import argparse
import csv
import json
import math
import os

import cv2
import numpy as np

DEFAULT_DEPTH = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
DEFAULT_SAM = "facebook/sam-vit-base"


# ---------------------------------------------------------------- geometry (no ML, unit-testable)

def intrinsics(calib_path, w, h, hfov_deg):
    """Return (K, dist). Uses calib.json if present, else a pinhole guess from the field of view."""
    if calib_path and os.path.exists(calib_path):
        c = json.load(open(calib_path))
        K = np.array(c["K"], dtype=np.float64)
        K[0, :] *= w / c["width"]   # rescale if the photos are a different resolution
        K[1, :] *= h / c["height"]
        return K, np.array(c["dist"], dtype=np.float64)
    f = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64), np.zeros(5)


def undistort(img, K, dist):
    h, w = img.shape[:2]
    if not np.any(dist):
        return img, K
    newK, _ = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 0)
    return cv2.undistort(img, K, dist, None, newK), newK


def measure(mask, depth_m, K, erode_px=3):
    """Distance = median depth inside the (slightly eroded) mask, so edge pixels that
    bleed into the background don't drag it. Size = mask pixel extent x distance / focal."""
    m = mask.astype(np.uint8)
    if erode_px > 0:
        core = cv2.erode(m, np.ones((2 * erode_px + 1,) * 2, np.uint8))
        if core.sum() > 50:
            m = core
    vals = depth_m[m.astype(bool)]
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if vals.size == 0:
        return None
    d = float(np.median(vals))

    # extent of the largest connected blob: ignores stray mask specks without
    # shaving the object's real edges (percentile trimming biased sizes ~2% low)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n < 2:
        return None
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    w_px = int(stats[big, cv2.CC_STAT_WIDTH])
    h_px = int(stats[big, cv2.CC_STAT_HEIGHT])
    return {
        "dist_m": d,
        "width_cm": 100 * w_px * d / K[0, 0],
        "height_cm": 100 * h_px * d / K[1, 1],
        "w_px": float(w_px), "h_px": float(h_px),
        "depth_spread_m": float(np.percentile(vals, 90) - np.percentile(vals, 10)),
    }


def pct_err(est, true):
    return 100 * (est - true) / true


# ---------------------------------------------------------------- models

class DepthModel:
    def __init__(self, name, device):
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        self.torch, self.device = torch, device
        self.proc = AutoImageProcessor.from_pretrained(name)
        self.model = AutoModelForDepthEstimation.from_pretrained(name).to(device).eval()

    def __call__(self, rgb):
        from PIL import Image
        torch = self.torch
        h, w = rgb.shape[:2]
        inputs = self.proc(images=Image.fromarray(rgb), return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model(**inputs)
        try:  # newer transformers: resizes back to the input size for us
            d = self.proc.post_process_depth_estimation(out, target_sizes=[(h, w)])[0]["predicted_depth"]
        except Exception:
            d = torch.nn.functional.interpolate(out.predicted_depth.unsqueeze(1), size=(h, w),
                                                mode="bicubic", align_corners=False)[0, 0]
        return d.squeeze().float().cpu().numpy()


class SamSegmenter:
    def __init__(self, name, device):
        import torch
        from transformers import SamModel, SamProcessor
        self.torch, self.device = torch, device
        self.proc = SamProcessor.from_pretrained(name)
        self.model = SamModel.from_pretrained(name).to(device).eval()

    def __call__(self, rgb, x, y, box=None):
        """Returns 3 candidate masks and their quality scores. A box [x0, y0, x1, y1] prompt,
        if given, replaces the point: it tells SAM how big the object is, which stops it
        picking just a part (chair seat) or merging neighbours (chair + guitar case)."""
        from PIL import Image
        torch = self.torch
        prompt = {"input_boxes": [[box]]} if box else {"input_points": [[[x, y]]]}
        inputs = self.proc(Image.fromarray(rgb), **prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model(**inputs)
        masks = self.proc.image_processor.post_process_masks(
            out.pred_masks.cpu(), inputs["original_sizes"].cpu(), inputs["reshaped_input_sizes"].cpu())[0][0]
        scores = out.iou_scores[0, 0].cpu().numpy()
        return [m.numpy().astype(bool) for m in masks], scores


# ---------------------------------------------------------------- interaction

def pick_prompt(img, title):
    """Click = point prompt, drag = box prompt, Enter = center crosshair.
    Returns ((x, y), box) where box is [x0, y0, x1, y1] or None."""
    pt = {}
    view = img.copy()
    h, w = view.shape[:2]
    cv2.drawMarker(view, (w // 2, h // 2), (0, 255, 0), cv2.MARKER_CROSS, 20, 1)
    cv2.putText(view, "click the object, or DRAG a box around it (Enter = crosshair)", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

    def on_mouse(event, x, y, flags, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            pt["down"] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and "down" in pt and flags & cv2.EVENT_FLAG_LBUTTON:
            preview = view.copy()
            cv2.rectangle(preview, pt["down"], (x, y), (0, 255, 255), 1)
            cv2.imshow(title, preview)
        elif event == cv2.EVENT_LBUTTONUP and "down" in pt:
            x0, y0 = pt.pop("down")
            if abs(x - x0) > 8 and abs(y - y0) > 8:  # a drag, not a slightly wobbly click
                pt["box"] = [min(x0, x), min(y0, y), max(x0, x), max(y0, y)]
            else:
                pt["xy"] = (x, y)
    cv2.imshow(title, view)
    cv2.setMouseCallback(title, on_mouse)
    while "xy" not in pt and "box" not in pt:
        k = cv2.waitKey(20) & 0xFF
        if k in (13, 10):
            pt["xy"] = (w // 2, h // 2)
        if k == 27:
            raise SystemExit("aborted")
    if "box" in pt:
        b = pt["box"]
        return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2), b
    return pt["xy"], None


def pick_mask(img, masks, scores, start, title):
    i = start
    while True:
        view = img.copy()
        overlay = view.copy()
        overlay[masks[i]] = (0, 200, 255)
        view = cv2.addWeighted(overlay, 0.45, view, 0.55, 0)
        cv2.putText(view, f"mask {i + 1}/3 score {scores[i]:.2f}  [N]ext  [Enter] accept", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.imshow(title, view)
        k = cv2.waitKey(0) & 0xFF
        if k in (13, 10):
            return i
        if k == ord("n"):
            i = (i + 1) % len(masks)
        if k == 27:
            raise SystemExit("aborted")


# ---------------------------------------------------------------- stats

def summarize(rows, key, label):
    errs = np.array([abs(r[key]) for r in rows if r.get(key) is not None])
    if errs.size == 0:
        return f"  {label:<22} n=0"
    return (f"  {label:<22} n={errs.size:<3} mean {errs.mean():5.1f}%   median {np.median(errs):5.1f}%   "
            f"worst {errs.max():5.1f}%   within 10%: {100 * np.mean(errs <= 10):3.0f}%")


def num(s):
    s = (s or "").strip()
    return float(s) if s else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="feasibility/objects.csv")
    ap.add_argument("--images", default="feasibility/captures")
    ap.add_argument("--calib", default="feasibility/calib.json")
    ap.add_argument("--hfov", type=float, default=70.0, help="only used if there is no calib.json")
    ap.add_argument("--depth-model", default=DEFAULT_DEPTH)
    ap.add_argument("--sam-model", default=DEFAULT_SAM)
    ap.add_argument("--center", action="store_true", help="aim at image center instead of clicking")
    ap.add_argument("--clicks", default="feasibility/clicks.json", help="remembers clicks between runs")
    ap.add_argument("--redo", default="", help="comma-separated image names (or parts of names) to re-pick "
                                               "even if clicks.json already has them")
    ap.add_argument("--out", default="feasibility/results.csv")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()

    import torch
    device = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"loading models on {device} (first run downloads them, a few hundred MB)...")
    depth_model = DepthModel(a.depth_model, device)
    sam = SamSegmenter(a.sam_model, device)

    clicks = json.load(open(a.clicks)) if os.path.exists(a.clicks) else {}
    redo = [s.strip() for s in a.redo.split(",") if s.strip()]
    with open(a.csv, newline="") as f:
        objects = [r for r in csv.DictReader(f) if (r.get("image") or "").strip()]
    if not os.path.exists(a.calib):
        print(f"WARNING: no {a.calib}, guessing focal length from --hfov {a.hfov}. Sizes will be rough.")

    results = []
    for r in objects:
        path = os.path.join(a.images, r["image"].strip())
        img = cv2.imread(path)
        if img is None:
            print(f"skip {r['image']}: can't read {path}")
            continue
        h, w = img.shape[:2]
        K, dist = intrinsics(a.calib, w, h, a.hfov)
        img, K = undistort(img, K, dist)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        name = r["image"].strip()
        saved = None if any(f in name for f in redo) else clicks.get(name)
        if saved:
            x, y, mi, box = saved["x"], saved["y"], saved["mask"], saved.get("box")
        else:
            (x, y), box = ((w // 2, h // 2), None) if a.center else pick_prompt(img, "measure")
            mi = None

        masks, scores = sam(rgb, x, y, box)
        if mi is None:
            mi = int(np.argmax(scores))
            if not a.center:
                mi = pick_mask(img, masks, scores, mi, "measure")
        clicks[name] = {"x": int(x), "y": int(y), "mask": int(mi), **({"box": [int(v) for v in box]} if box else {})}

        depth = depth_model(rgb)
        m = measure(masks[mi], depth, K)
        if m is None:
            print(f"skip {name}: no valid depth inside the mask")
            continue

        td, tw, th = num(r.get("true_distance_m")), num(r.get("true_width_cm")), num(r.get("true_height_cm"))
        row = {"image": name, "ref": (r.get("ref") or "0").strip() == "1", "notes": r.get("notes", ""),
               "true_distance_m": td, "true_width_cm": tw, "true_height_cm": th, **m}
        row["dist_err_pct"] = pct_err(m["dist_m"], td) if td else None
        row["width_err_pct"] = pct_err(m["width_cm"], tw) if tw else None
        row["height_err_pct"] = pct_err(m["height_cm"], th) if th else None
        results.append(row)
        print(f"{name}: dist {m['dist_m']:.2f} m (true {td}), size {m['width_cm']:.1f} x {m['height_cm']:.1f} cm "
              f"(true {tw} x {th})")

    cv2.destroyAllWindows()
    json.dump(clicks, open(a.clicks, "w"), indent=1)
    if not results:
        raise SystemExit("no results")

    # one-time reference correction: fix the global scale using the ref rows
    refs = [r for r in results if r["ref"] and r["true_distance_m"]]
    scale = float(np.mean([r["true_distance_m"] / r["dist_m"] for r in refs])) if refs else None
    for r in results:
        for k in ("dist", "width", "height"):
            r[f"{k}_err_corr_pct"] = None
        if scale and not r["ref"]:
            if r["true_distance_m"]:
                r["dist_err_corr_pct"] = pct_err(r["dist_m"] * scale, r["true_distance_m"])
            if r["true_width_cm"]:
                r["width_err_corr_pct"] = pct_err(r["width_cm"] * scale, r["true_width_cm"])
            if r["true_height_cm"]:
                r["height_err_corr_pct"] = pct_err(r["height_cm"] * scale, r["true_height_cm"])

    with open(a.out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)

    test = [r for r in results if not r["ref"]]
    print(f"\n=== accuracy on {len(test)} test shots (reference shots excluded) ===")
    print("raw model output:")
    print(summarize(test, "dist_err_pct", "distance"))
    print(summarize(test, "width_err_pct", "width"))
    print(summarize(test, "height_err_pct", "height"))
    if scale:
        print(f"after reference correction (scale x{scale:.3f} from {len(refs)} ref shots):")
        print(summarize(test, "dist_err_corr_pct", "distance"))
        print(summarize(test, "width_err_corr_pct", "width"))
        print(summarize(test, "height_err_corr_pct", "height"))
    else:
        print("(no ref=1 rows, so no reference correction)")

    # error vs distance, the curve the professor will want to see
    print("\ndistance error by range (raw):")
    for lo, hi in ((0, 1.5), (1.5, 2.5), (2.5, 9)):
        sel = [r for r in test if r["true_distance_m"] and lo <= r["true_distance_m"] < hi]
        print(summarize(sel, "dist_err_pct", f"{lo}-{hi if hi < 9 else '+'} m"))
    print(f"\nper-shot results written to {a.out}")


if __name__ == "__main__":
    main()
