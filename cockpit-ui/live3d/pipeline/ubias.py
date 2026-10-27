"""`ubias_m` -- the depth-composite stand-off tolerance, measured properly.

    import ubias
    dep = T.render_depth(scene, OUT + "/depth.bin", hide=live + content)
    liv = T.render_depth(scene, OUT + "/_depth_live.bin", hide=content)
    U = ubias.measure(dep, liv, W, H)
    ubias.report(U)                       # print it -- the DISTRIBUTION is the
    S["ubias_m"] = U["ubias_m"]           # point, not the single number

WHY THIS FILE EXISTS.  CONVERSION_BRIEF step 3 used to print the derivation
inline, as

    gaps = [b - l for b, l in zip(dep, liv) if b < 1e9 and 1e-6 < b - l < 1.0]
    S["ubias_m"] = round(0.7 * min(gaps), 6)

and `min(gaps)` OVER EVERY PIXEL is not a stand-off.  It is almost always a
SILHOUETTE pixel: where a live object's edge partially covers a pixel the depth
buffer keeps one sample from somewhere inside that coverage, so `baked - live`
there is a partial-coverage artefact of a surface nothing actually stands off
by.  Two independent modules measured it:

  * **IPM (a prop standing PROUD).**  Raw minimum **0.090 mm** against a real
    minimum of **1.001 mm** -- the literal recipe ships a uBias 11x too small.
    Eroding the live-nearer mask by one pixel (4-neighbour) drops all 28
    sub-0.9 mm pixels and leaves a plateau of 2,754 px at 1.0010 mm, which is
    `ipm_dev_*` at z 0.0285 over `ipm_tray_plate` at 0.0275 -- the AUTHORED
    value, recovered from the render to a micron.  IPM NOTES 8.1.
  * **FMM (a prop EMERGING from a baked one).**  Its lamp domes are seated in
    their brass rings and its skid trucks run through the rail bed, so the gap
    sweeps continuously through zero at the intersection curve and the minimum
    is the last pixel before the crossing: **1 um against a 1st percentile of
    1.108 mm.**  Erosion cannot fully remove this one -- the crossing is an
    interior curve, not a silhouette -- so the tell is the SHAPE of the
    distribution, not the value: IPM's minimum is a plateau holding 100% of
    the set, FMM's is the tail of a continuum holding under 2%.  `measure()`
    computes that fraction and `report()` names the case.  FMM NOTES 8.6.

PKT's 1.15 mm came out of the raw formula and is probably right by luck: its
header bar's silhouette is a straight edge against a coplanar frame.  A module
with curved live geometry -- DNSM's chart drum, LOG's ribbon -- has silhouette
pixels everywhere and should expect the raw minimum to be meaningless.

WHICH NUMBER TO SHIP.  `ubias_m` = 0.7 x the ERODED minimum, which is the same
rule as before applied to a set that means something.  Ship it in BOTH cases.  Err small: too small
only risks z-fighting on a genuinely coplanar prop, which is visible and noisy;
too big DELETES geometry and is silent (PKT: 2 mm discarded a 208x20 px
emissive strip and cost 5.7 rms with no warning).  Where there is no plateau at the bottom you are in FMM's
emerging case, the minimum is a rim artefact, and `report()` says so -- ship it
anyway, and sweep `__occ.ubias` on the real page to confirm the sweep is flat
or monotone (FMM's is: 1e-06 IS its sweep optimum).

Stdlib only, so it runs inside Blender and outside it.  `python3 ubias.py
--selftest` reproduces both modules' published numbers from constructed fields.
"""

FAR = 1e9
LO, HI = 1e-6, 1.0


def gaps_and_mask(dep, liv, W, H, lo=LO, hi=HI):
    """(gap per pixel or None, live-nearer mask) -- the raw field.

    A pixel is in the mask when the baked depth is finite and the live depth is
    NEARER by more than `lo` and less than `hi`.  Those two bounds are the
    brief's own and they matter: `< hi` drops pixels where the live object is
    in front of the BACKGROUND rather than in front of anything, and `> lo`
    drops exact ties.
    """
    n = W * H
    assert len(dep) == n and len(liv) == n, (len(dep), len(liv), n)
    g = [None] * n
    m = bytearray(n)
    for i in range(n):
        b = dep[i]
        if b >= FAR:
            continue
        d = b - liv[i]
        if lo < d < hi:
            g[i] = d
            m[i] = 1
    return g, m


def erode4(m, W, H):
    """One-pixel 4-neighbour erosion of a flat bytearray mask.

    This is the whole fix, and it is not a tolerance -- it is the same "keep
    only INTERIOR pixels" idea `check_occlusion.py` already uses for its
    `partial front` allowance.  A pixel survives only if its four edge
    neighbours are also live-nearer, which is exactly the condition "this pixel
    is not on the live object's silhouette".  Border pixels are dropped.
    """
    out = bytearray(W * H)
    for y in range(1, H - 1):
        r = y * W
        for x in range(1, W - 1):
            i = r + x
            if m[i] and m[i - 1] and m[i + 1] and m[i - W] and m[i + W]:
                out[i] = 1
    return out


def _pct(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def measure(dep, liv, W, H, frac=0.7, lo=LO, hi=HI):
    """Everything the author has to see, in one dict.  Never just a number."""
    g, m = gaps_and_mask(dep, liv, W, H, lo, hi)
    raw = sorted(v for v in g if v is not None)
    inner_mask = erode4(m, W, H)
    inner = sorted(g[i] for i in range(W * H) if inner_mask[i])
    src = inner or raw
    U = {
        "n_raw": len(raw), "n_inner": len(inner),
        "raw_min": raw[0] if raw else float("nan"),
        "min": src[0] if src else float("nan"),
        "p1": _pct(src, 1.0), "p5": _pct(src, 5.0),
        "median": _pct(src, 50.0),
        "max": src[-1] if src else float("nan"),
        "eroded": bool(inner),
        "frac": frac,
    }
    U["ubias_m"] = round(frac * U["min"], 6) if src else 0.0
    U["ubias_p1_m"] = round(frac * U["p1"], 6) if src else 0.0
    # The plateau: how many interior pixels sit within 1% of the minimum.  On a
    # module whose live prop stands proud of one baked surface this is most of
    # the set (IPM: 2,754 of 2,754) and the number is an AUTHORED constant
    # recovered from the render.  On a module where the prop emerges through
    # its baked seat there is no plateau at the bottom at all.
    U["plateau"] = sum(1 for v in src if v <= U["min"] * 1.01) if src else 0
    U["plateau_frac"] = U["plateau"] / float(len(src)) if src else 0.0
    # IS THE MINIMUM A PLATEAU OR A TAIL?  That is the whole question, and it
    # is a SHAPE, not a threshold on the value.  A prop standing proud of one
    # baked surface puts almost the entire set at one authored value (IPM:
    # 2,754 of 2,754 within 1%).  A prop EMERGING through its baked seat has no
    # plateau at the bottom at all -- the gap is a continuum that runs down to
    # the intersection curve -- and its minimum is a rim artefact whatever the
    # erosion does, because the crossing is interior geometry and not a
    # silhouette.  FMM NOTES 8.6.
    U["emerging"] = bool(src) and U["plateau_frac"] < 0.02
    U["hist"] = _hist(src)
    return U


def _hist(vals, nb=12):
    if not vals:
        return []
    lo, hi = vals[0], vals[-1]
    if hi <= lo:
        return [(lo, hi, len(vals))]
    out = []
    for b in range(nb):
        a = lo + (hi - lo) * b / nb
        z = lo + (hi - lo) * (b + 1) / nb
        c = sum(1 for v in vals if (a <= v < z) or (b == nb - 1 and v == hi))
        out.append((a, z, c))
    return out


def report(U, prefix="  "):
    p = prefix
    print("%subias: %d live-nearer px, %d after 4-neighbour erosion"
          % (p, U["n_raw"], U["n_inner"]))
    if not U["eroded"]:
        print("%s  !! erosion left NOTHING -- every live-nearer pixel is on a "
              "silhouette.  The numbers below are the RAW set and the minimum "
              "is not a stand-off.  Sweep __occ.ubias on the page." % p)
    print("%s  raw min %.6f m   eroded min %.6f m   (raw/eroded %.2fx)"
          % (p, U["raw_min"], U["min"],
             (U["min"] / U["raw_min"]) if U["raw_min"] else float("nan")))
    print("%s  p1 %.6f   p5 %.6f   median %.6f   max %.6f"
          % (p, U["p1"], U["p5"], U["median"], U["max"]))
    print("%s  plateau within 1%% of the minimum: %d px (%.1f%% of the set)"
          % (p, U["plateau"], 100.0 * U["plateau_frac"]))
    for a, z, c in U["hist"]:
        print("%s    %8.6f .. %8.6f  %7d %s"
              % (p, a, z, c, "#" * min(40, c * 40 // max(1, U["n_inner"] or 1))))
    if U["emerging"]:
        print("%s  !! NO PLATEAU AT THE MINIMUM (%.1f%% of the set is within "
              "1%% of it, against 100%% for a prop standing proud of one baked "
              "surface).  That is FMM's EMERGING case: a live prop passing "
              "THROUGH a baked one -- lamp domes seated in their rings, skid "
              "trucks running through the rail bed -- whose gap sweeps "
              "continuously through zero at the intersection.  The minimum is "
              "a rim artefact, not a stand-off, and erosion cannot remove it "
              "because the crossing is an interior curve.  p1 is %.6f m, "
              "%.0fx the minimum; 0.7 x p1 would be %.6f.  SHIP THE SMALL ONE "
              "(too small only z-fights, too big deletes geometry silently), "
              "say so in NOTES, and sweep __occ.ubias on the page to confirm "
              "the sweep is flat or monotone."
              % (p, 100.0 * U["plateau_frac"], U["p1"],
                 U["p1"] / max(1e-12, U["min"]), U["ubias_p1_m"]))
    print("%s  -> ubias_m = %.2f x %.6f = %.6f"
          % (p, U["frac"], U["min"], U["ubias_m"]))


# --------------------------------------------------------------------------
def _selftest():
    """Reproduce both published cases from constructed depth fields."""
    W, H = 64, 64
    ok = True

    # ---- IPM's case: a flat prop standing 1.001 mm proud of a plate, with an
    # antialiased silhouette one pixel wide whose depth samples land part way
    # through the step.  The raw minimum is a silhouette pixel; the interior is
    # a plateau at the authored value.
    dep = [1.1000] * (W * H)
    liv = list(dep)
    STAND = 0.001001
    for y in range(8, 56):
        for x in range(8, 56):
            liv[y * W + x] = dep[y * W + x] - STAND
    for y in range(7, 57):            # the silhouette ring: partial coverage
        for x in range(7, 57):
            if 8 <= x < 56 and 8 <= y < 56:
                continue
            liv[y * W + x] = dep[y * W + x] - 0.000090
    U = measure(dep, liv, W, H)
    print("IPM-shaped:")
    report(U)
    ok &= abs(U["raw_min"] - 0.000090) < 1e-9
    ok &= abs(U["min"] - STAND) < 1e-9
    ok &= U["ubias_m"] == round(0.7 * STAND, 6)
    ok &= not U["emerging"] and U["plateau_frac"] > 0.99
    print("   raw min 0.090 mm -> eroded min %.4f mm, plateau %d px : %s"
          % (1000 * U["min"], U["plateau"], "OK" if ok else "FAIL"))

    # ---- FMM's case: a DOME emerging from its baked ring.  The gap is the
    # dome's own height above its seat, so it goes to zero on the seat CIRCLE
    # -- an interior curve, not a silhouette -- and erosion cannot help.  Most
    # of the dome stands 1-2 mm proud; only a hair-thin annulus is near zero,
    # which is exactly why the minimum and the 1st percentile differ by three
    # orders (FMM measured 1 um against p1 1.108 mm).
    import math as _m
    dep = [1.1000] * (W * H)
    liv = list(dep)
    cx, cy, R = 31.5, 31.5, 24.0
    for y in range(H):
        for x in range(W):
            r = _m.hypot(x - cx, y - cy) / R
            if r >= 1.0:
                continue
            liv[y * W + x] = dep[y * W + x] - max(1e-6,
                                                  0.0022 * _m.sqrt(1 - r * r))
    V = measure(dep, liv, W, H)
    print("FMM-shaped:")
    report(V)
    ok2 = V["emerging"] and V["plateau_frac"] < 0.02
    print("   min %.6f m, p1 %.6f m, plateau %.2f%% of the set, flagged "
          "emerging=%s : %s"
          % (V["min"], V["p1"], 100.0 * V["plateau_frac"], V["emerging"],
             "OK" if ok2 else "FAIL"))

    # ---- the NEGATIVE CONTROL: a genuinely coplanar prop.  Erosion must NOT
    # invent a stand-off that is not there; the answer has to stay ~0.
    dep = [1.1000] * (W * H)
    liv = list(dep)
    for y in range(8, 56):
        for x in range(8, 56):
            liv[y * W + x] = dep[y * W + x] - 0.00002
    C = measure(dep, liv, W, H)
    ok3 = (abs(C["min"] - 0.00002) < 1e-9
           and C["ubias_m"] == round(0.7 * 2e-5, 6)
           and not C["emerging"])
    print("COPLANAR control: eroded min %.6f m -> ubias_m %.6f : %s"
          % (C["min"], C["ubias_m"], "OK" if ok3 else "FAIL"))
    return 0 if (ok and ok2 and ok3) else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
