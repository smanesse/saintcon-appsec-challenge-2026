"""Measure, for all nine modules, the 2D magnification that carries the SHIPPED
wide plate onto each module's SHIPPED close-up plate -- the one number the
wide -> close-up move needs in order to be geometrically continuous.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/measure_transition.py

Writes live3d/transition.json.  Reads only; nothing under cockpit/ is touched.
Blender is used purely for numpy + PNG decode (this machine has neither numpy
nor PIL in the system python).

WHAT IS BEING MEASURED
----------------------
The close-up plate is a 1280x720 render of a camera dollied in on the module.
Whatever that camera is, its frame corresponds to SOME rectangle of the wide
frame.  If the close plate, shrunk by M, is laid on the wide plate at the right
place, the two pictures line up.  M is exactly the magnification the transition
has to travel, and the centre of that rectangle is exactly the point the move
has to dive at.  So: downscale the close plate by a candidate M, slide it over
the wide plate, score it, take the best.

Two traps, both hit and both fixed:

1. SCALE BIAS.  Score a big downscale against a small window and you compare
   fewer, smoother pixels, which raises a normalised correlation for free.  The
   first version of this walked FMM up to M=10.3 -- geometrically impossible,
   since FMM's silhouette is 207 px wide in the wide frame and the window at
   M=10.3 is only 124 px.  FIX: resample BOTH sides to the same fixed 160x90
   grid for every candidate M, so every score compares the same pixel count.

2. NO 2D SCALE IS EXACT.  Only KVS, MTA, OTA and PKT put the close camera on the
   wide camera's own view ray (`fit_camera`).  DNSM, FMM, IPM and MQB aim theirs
   straight down the panel's face normal instead, so the two views differ in
   DIRECTION and the module is foreshortened differently in each.  FMM is the
   extreme: its panel is nearly edge-on to the pilot, and its horizontal and
   vertical size ratios are 4.9 and 8.5.  There is no single right answer there;
   the correlation optimum lands near the geometric mean of the two, which is
   the scale that matches apparent AREA, and that is the best a 2D move can do.

VALIDATION (this is why the numbers below are trusted)
------------------------------------------------------
`fit_camera` fills a known fraction of the frame with the module, and that
fraction is a literal in each build.py.  Divide the measured M by
min(1280/w, 720/h) of the module's true silhouette -- read off the alpha of the
shipped far_prop.png -- and it must come back out:

    module   build.py frac=   measured M / fit
    PKT          0.88              0.876
    OTA          0.93              0.942
    KVS          0.90              0.921
    MTA          0.94             (0.94 adopted; see below)

Three independent hits inside 2%.  Separately, KVS's magnification was derived
analytically from the two camera matrices in live3d/assets/KVS/scene.json and
the pilot camera in cockpit/shell.py, and the whole-frame optimum (5.62) sits
between that fit's horizontal and vertical axis ratios (4.74 and 5.90) as it
should for an area-matching compromise.

WHERE THE CORRELATION IS NOT TRUSTED, AND WHAT IS USED INSTEAD
--------------------------------------------------------------
A weak score means the two views genuinely disagree (different view direction,
different exposure grade), not that the search failed to converge -- but it also
means the optimum is soft.  Four modules score below 0.6 and are overridden:

  MTA  ncc 5.69 -> 5.00   MTA's close camera IS a fit_camera(frac=0.94) and its
                          far render is a subset of the objects it fits, so
                          M <= 0.94 x 5.333 = 5.01 is a hard geometric ceiling.
                          The correlation runs past it because it never finds a
                          real optimum here (peak score 0.35, and the handover
                          sweep climbs monotonically); geometry wins.
  MQB  ncc 6.30 -> 5.15   score 0.147 is noise.  Measured off the images by hand
                          instead: the panel bezel is 178x132 px in far_prop and
                          900x695 in the close plate -> 5.06 and 5.26, mean 5.15.
                          The handover sweep prefers 5.46, i.e. 6% away.
  DNSM 4.90               kept; the bezel diagonal gives 4.76 independently and
                          the handover sweep peaks at the adopted value.
  FMM  6.53               kept, though this one is a genuine "no right answer":
                          FMM's panel is nearly edge-on to the pilot and its two
                          axis ratios, measured by hand off the two plates, are
                          4.94 across and 8.5 down.  6.53 is within 1% of their
                          geometric mean (6.48), which is the scale that matches
                          apparent AREA -- the best a uniform 2D scale can do.
"""
import bpy, numpy as np, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CK   = os.path.join(REPO, "cockpit")
OUTF = os.path.join(os.path.dirname(HERE), "transition.json")
W, H = 1280, 720
NW, NH = 160, 90                      # the fixed comparison grid (see trap 1)

# code -> (adopted M, why).  None = take the correlation optimum.
OVERRIDE = {
    "MTA": (5.00, "geometry: fit_camera(frac=0.94) bounds M <= 0.94 x fit"),
    "MQB": (5.15, "bezel measured by hand in both plates; ncc score 0.147 is noise"),
}

MAN = json.load(open(os.path.join(CK, "combined", "manifest.json")))


def load(rel):
    im = bpy.data.images.load(os.path.join(CK, rel))
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1].copy()
    bpy.data.images.remove(im)
    return a


def luma(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def resize(a, nh, nw):
    """bilinear; pixel centres, so a downscale keeps the frame's centre put"""
    h, w = a.shape
    yy = (np.arange(nh) + 0.5) * h / nh - 0.5
    xx = (np.arange(nw) + 0.5) * w / nw - 0.5
    y0 = np.clip(np.floor(yy).astype(int), 0, h - 1); y1 = np.clip(y0 + 1, 0, h - 1)
    x0 = np.clip(np.floor(xx).astype(int), 0, w - 1); x1 = np.clip(x0 + 1, 0, w - 1)
    fy = (yy - np.floor(yy))[:, None]; fx = (xx - np.floor(xx))[None, :]
    return (a[np.ix_(y0, x0)] * (1 - fy) * (1 - fx) + a[np.ix_(y0, x1)] * (1 - fy) * fx +
            a[np.ix_(y1, x0)] * fy * (1 - fx) + a[np.ix_(y1, x1)] * fy * fx)


def close_composite(code):
    """plate + every control's default frame, i.e. the close-up as the player
    first sees it -- the plate alone is missing the moving parts."""
    m = MAN["modules"][code]["close"]
    base = load(m["plate"])
    out = base[..., :3] * base[..., 3:4]
    for c in m["controls"].values():
        p = c.get("image")
        if p is None and "frames" in c:
            p = c["frames"][0]
        if p is None and "states" in c:
            k = (c.get("order") or [None])[0] or list(c["states"])[0]
            p = c["states"][k]
        if p is None:
            continue
        ov = load(p); a = ov[..., 3:4]
        out = out * (1 - a) + ov[..., :3] * a
    return luma(out)


def zncc(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else -9.0


def search(wide, target, cx, cy, scales, rad, step, q=1.0):
    """q<1 scores only the CENTRAL q of the close frame against the matching
    central q of the wide window -- see the M_module pass in main()."""
    best = None
    for M in scales:
        th, tw = int(round(q * H / M)), int(round(q * W / M))
        if th < 12 or tw < 12 or th > H or tw > W:
            continue
        for dy in range(-rad, rad + 1, step):
            for dx in range(-rad, rad + 1, step):
                x0 = int(round(cx - tw / 2. + dx)); y0 = int(round(cy - th / 2. + dy))
                if x0 < 0 or y0 < 0 or x0 + tw > W or y0 + th > H:
                    continue
                v = zncc(resize(wide[y0:y0 + th, x0:x0 + tw], NH, NW), target)
                if best is None or v > best[0]:
                    best = (v, float(M), x0 + tw / 2., y0 + th / 2.,
                            int(round(W / M)), int(round(H / M)))
    return best


def main():
    wide = luma(load(MAN["plate"])[..., :3])
    out = {}
    for code in sorted(MAN["modules"]):
        far = load(MAN["modules"][code]["far"]["prop"])[..., 3]
        ys, xs = np.nonzero(far > 0.02)
        fb = (int(xs.min()), int(ys.min()),
              int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
        clipped = fb[0] <= 0 or fb[1] <= 0 or fb[0] + fb[2] >= W or fb[1] + fb[3] >= H
        fit = min(W / fb[2], H / fb[3])
        cx, cy = fb[0] + fb[2] / 2., fb[1] + fb[3] / 2.
        tgt = resize(close_composite(code), NH, NW)
        # a clipped silhouette is a floor on the module's true size, so `fit` is
        # an over-estimate of the bound and the window has to open up
        lo, hi = 0.70 * fit, (1.60 if clipped else 1.02) * fit
        c = search(wide, tgt, cx, cy, np.arange(lo, hi + 1e-9, (hi - lo) / 40.), 24, 4)
        f = search(wide, tgt, cx, cy,
                   np.arange(max(1.5, c[1] - 0.25), c[1] + 0.2501, 0.025), 8, 1)
        v, M, x, y, tw, th = f

        # ---- second opinion, NOT the shipped number -----------------------
        # No single 2D scale is exact for a dolly: the module is nearer than
        # the ship behind it, so it magnifies more, and a whole-frame fit is
        # partly weighted by the background.  This pass re-fits over only the
        # central M^-0.33 of the close frame -- the module -- and is reported
        # so the spread between the two is visible.  It is NOT adopted: the
        # in-page handover test (check/match_handover.mjs, which scores the two
        # LAYERS AS COMPOSITED at the cross-fade) peaks at M_frame for
        # DNSM/KVS/LOG/PKT and within one 6% step of it for IPM/MQB/OTA, and
        # M_module is the worse of the two for IPM and OTA.
        qq = M ** -0.33
        tq = resize(close_composite(code)[int(H * (1 - qq) / 2):int(H * (1 + qq) / 2),
                                          int(W * (1 - qq) / 2):int(W * (1 + qq) / 2)],
                    NH, NW)
        g = search(wide, tq, x, y,
                   np.arange(max(1.5, M * 0.72), M * 1.16, M * 0.01), 8, 1, q=qq)
        vm, Mm, xm, ym = g[0], g[1], g[2], g[3]

        rec = {"M_frame": round(M, 3), "score_frame": round(v, 4),
               "M_module": round(Mm, 3), "score_module": round(vm, 4),
               "q": round(qq, 3), "fit": round(fit, 3),
               "frac": round(M / fit, 3), "clipped": bool(clipped),
               "far_box": list(fb),
               "wide_c": [round(xm, 1), round(ym, 1)],
               "source": "ncc"}
        if code in OVERRIDE:
            rec["M"], rec["source"] = OVERRIDE[code][0], "override"
            rec["why"] = OVERRIDE[code][1]
            if code == "MQB":                     # hand-measured centre too
                rec["wide_c"] = [157.0, 96.0]
        else:
            rec["M"] = round(M, 3)
        out[code] = rec
        print(code, json.dumps(rec), flush=True)
    doc = {
        "_": "wide -> close-up magnification per module; see "
             "live3d/pipeline/measure_transition.py for method and validation",
        "wide_plate": MAN["plate"], "canvas": [W, H], "modules": out,
    }
    open(OUTF, "w").write(json.dumps(doc, indent=1) + "\n")
    print("wrote", OUTF)


main()
