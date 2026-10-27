"""Rasterise a module's LIVE geometry to a linear-view-depth buffer, offline.

    python3 live3d/pipeline/live_depth.py <CODE>

WHY THIS FILE EXISTS.  `ubias_m` is `0.7 x` the smallest INTERIOR stand-off
between a LIVE object and the BAKED surface behind it (`pipeline/ubias.py`),
and measuring it needs the depth pass rendered a SECOND time with the live
objects visible.  Four modules did that inside their exporter and shipped a
value.  Five did not -- KVS, MQB, MTA, OTA and PKT -- and re-running those five
exporters to get it means re-rendering `plate.png`, `depth.bin` and every
`.glb` of a module whose every recorded number was measured against exactly
those files.  Blender's glTF exporter is not byte-deterministic (trap 31), so
that is a real risk taken for one scalar.

Everything needed is already in the repo: the live geometry IS the shipped
`.glb` set, in world coordinates; the camera IS `scene.json -> camera`; the
baked pass IS `depth.bin`.  So this renders the live half here, with the same
projection and the same "linear view depth along -Z_cam" convention
`transliterate.render_depth()` writes, and hands the pair to `ubias.measure()`.

IT IS VALIDATED AGAINST THE FOUR MODULES THAT DID IT IN BLENDER.  `--selftest`
runs DNSM, FMM, IPM and LOG and compares the `ubias_m` this file derives with
the one their exporters measured out of EEVEE.  A rasteriser that disagreed
with EEVEE about where a surface is would show up there first.

Stdlib + numpy only.  No Blender, and nothing under `assets/` is written.
"""
import json, os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ubias                                                     # noqa: E402

FAR = 1e9

# ---------------------------------------------------------------- glb reader
_CT = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
_NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(path):
    """-> (gltf json, bytes of the BIN chunk)."""
    with open(path, 'rb') as f:
        magic, ver, total = struct.unpack('<III', f.read(12))
        assert magic == 0x46546C67, path
        js = bin_ = None
        while f.tell() < total:
            ln, ty = struct.unpack('<II', f.read(8))
            data = f.read(ln)
            if ty == 0x4E4F534A:
                js = json.loads(data.decode('utf-8'))
            elif ty == 0x004E4942:
                bin_ = data
    return js, bin_


def accessor(g, blob, i):
    a = g['accessors'][i]
    n = _NC[a['type']]
    dt = np.dtype('<' + _CT[a['componentType']])
    if 'bufferView' not in a:
        return np.zeros((a['count'], n), dt)
    bv = g['bufferViews'][a['bufferView']]
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride') or (dt.itemsize * n)
    if stride == dt.itemsize * n:
        out = np.frombuffer(blob, dt, a['count'] * n, off).reshape(-1, n)
    else:                                   # interleaved
        raw = np.frombuffer(blob, np.uint8, a['count'] * stride, off)
        raw = raw.reshape(a['count'], stride)[:, :dt.itemsize * n]
        out = np.frombuffer(raw.tobytes(), dt).reshape(-1, n)
    return out


def node_matrix(nd):
    if 'matrix' in nd:
        return np.array(nd['matrix'], np.float64).reshape(4, 4).T
    M = np.eye(4)
    if 'scale' in nd:
        M[:3, :3] = np.diag(nd['scale']) @ M[:3, :3]
    if 'rotation' in nd:
        x, y, z, w = nd['rotation']
        R = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M[:3, :3] = R @ M[:3, :3]
    if 'translation' in nd:
        M[:3, 3] = nd['translation']
    return M


def glb_triangles(path):
    """Every triangle in the file, in WORLD coordinates, as (T,3,3)."""
    g, blob = read_glb(path)
    tris = []

    def walk(i, parent):
        nd = g['nodes'][i]
        M = parent @ node_matrix(nd)
        if 'mesh' in nd:
            for pr in g['meshes'][nd['mesh']].get('primitives', []):
                if pr.get('mode', 4) != 4:
                    continue
                pos = accessor(g, blob, pr['attributes']['POSITION']).astype(np.float64)
                if 'indices' in pr:
                    idx = accessor(g, blob, pr['indices']).reshape(-1).astype(np.int64)
                else:
                    idx = np.arange(len(pos), dtype=np.int64)
                w = pos @ M[:3, :3].T + M[:3, 3]
                tris.append(w[idx].reshape(-1, 3, 3))
        for c in nd.get('children', []):
            walk(c, M)

    for sc in g.get('scenes', [{}]):
        for i in sc.get('nodes', []):
            walk(i, np.eye(4))
    return np.concatenate(tris, 0) if tris else np.zeros((0, 3, 3))


# ------------------------------------------------------------- rasterisation
def camera_basis(S):
    """three.js/glTF world -> camera space.  Same construction the frontend
    uses (module.js section 2): z = -forward, x = up X z, y = z X x."""
    pos = np.array(S['camera']['pos'], np.float64)
    f = np.array(S['camera']['forward'], np.float64)
    up = np.array(S['camera']['up'], np.float64)
    z = -f / np.linalg.norm(f)
    x = np.cross(up, z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return pos, np.stack([x, y, z])          # rows


def render_live_depth(tris, S, W, H):
    """Nearest -Z_cam per pixel, top-down rows, FAR where nothing is drawn.

    A scanline z-buffer over triangles clipped to the near plane.  The depth
    interpolated is 1/w (perspective-correct), which is what a GPU does and
    what `render_depth` reads back."""
    pos, R = camera_basis(S)
    fov_y = np.radians(S['camera']['fov_y_deg'])
    fy = (H / 2.0) / np.tan(fov_y / 2.0)
    fx = fy                                   # square pixels, aspect W/H
    cx, cy = W / 2.0, H / 2.0
    near = max(1e-4, float(S['camera']['clip'][0]))

    V = (tris.reshape(-1, 3) - pos) @ R.T
    V = V.reshape(-1, 3, 3)
    d = -V[:, :, 2]                           # linear view depth, +ve in front

    buf = np.full((H, W), FAR, np.float64)

    keep = (d > near).any(axis=1)
    V, d = V[keep], d[keep]
    for k in range(len(V)):
        v, dz = V[k], d[k]
        if (dz <= near).any():
            v, dz = _clip_near(v, dz, near)
            if v is None:
                continue
        for t in range(1, len(v) - 1):
            _tri(buf, v[[0, t, t + 1]], dz[[0, t, t + 1]], fx, fy, cx, cy, W, H)
    return buf


def _clip_near(v, dz, near):
    """Sutherland-Hodgman against the near plane; returns a fan polygon."""
    ov, od = [], []
    n = len(v)
    for i in range(n):
        a, b = i, (i + 1) % n
        ina, inb = dz[a] > near, dz[b] > near
        if ina:
            ov.append(v[a]); od.append(dz[a])
        if ina != inb:
            t = (dz[a] - near) / (dz[a] - dz[b])
            ov.append(v[a] + t * (v[b] - v[a])); od.append(near)
    if len(ov) < 3:
        return None, None
    return np.array(ov), np.array(od)


def _tri(buf, v, dz, fx, fy, cx, cy, W, H):
    """One triangle, perspective-correct in 1/z, into a nearest-z buffer."""
    sx = cx + v[:, 0] * fx / dz
    sy = cy - v[:, 1] * fy / dz               # CSS/image y is DOWN
    inv = 1.0 / dz
    x0 = max(0, int(np.floor(sx.min())));  x1 = min(W - 1, int(np.ceil(sx.max())))
    y0 = max(0, int(np.floor(sy.min())));  y1 = min(H - 1, int(np.ceil(sy.max())))
    if x1 < x0 or y1 < y0:
        return
    ax, ay = sx[0], sy[0]
    e1x, e1y = sx[1] - ax, sy[1] - ay
    e2x, e2y = sx[2] - ax, sy[2] - ay
    den = e1x * e2y - e1y * e2x
    if abs(den) < 1e-12:
        return
    px = np.arange(x0, x1 + 1) + 0.5
    py = np.arange(y0, y1 + 1) + 0.5
    QX = px[None, :] - ax
    QY = py[:, None] - ay
    u = (QX * e2y - QY * e2x) / den
    w = (QY * e1x - QX * e1y) / den
    m = (u >= 0) & (w >= 0) & (u + w <= 1)
    if not m.any():
        return
    zi = inv[0] + u * (inv[1] - inv[0]) + w * (inv[2] - inv[0])
    z = np.where(zi > 0, 1.0 / np.where(zi == 0, 1e-12, zi), FAR)
    sub = buf[y0:y1 + 1, x0:x1 + 1]
    np.copyto(sub, z, where=m & (z < sub))


# --------------------------------------------------------------------- driver
def measure_code(code, verbose=True):
    A = os.path.join(LIVE3D, 'assets', code)
    S = json.load(open(os.path.join(A, 'scene.json')))
    W, H = S['render']['w'], S['render']['h']
    dep = np.frombuffer(open(os.path.join(A, S['depth']['file']), 'rb').read(),
                        '<f4').astype(np.float64).reshape(H, W)
    globs = sorted(f for f in os.listdir(A) if f.endswith('.glb'))
    tris = [glb_triangles(os.path.join(A, f)) for f in globs]
    tris = np.concatenate(tris, 0)
    if verbose:
        print('%s: %d live triangles over %d glb(s): %s'
              % (code, len(tris), len(globs), ', '.join(globs)))
    liv = np.minimum(render_live_depth(tris, S, W, H), dep)
    U = ubias.measure(dep.reshape(-1).tolist(), liv.reshape(-1).tolist(), W, H)
    if verbose:
        ubias.report(U)
    return U


def _selftest():
    """The four modules whose exporter measured this out of EEVEE.

    `how` is which statistic THAT exporter shipped, not which one is right.
    FMM ran before `ubias.py` existed and shipped `0.7 x raw min` (its own
    NOTES 8.6 says so and calls the degeneracy out); the other three eroded.
    So FMM is compared on the raw minimum -- which is the honest comparison of
    two rasterisers -- and the difference between 1 um and 477 um is the
    erosion, not a disagreement about where any surface is."""
    want = {'DNSM': (0.000292, 'eroded'), 'FMM': (0.000001, 'raw'),
            'IPM': (0.000700, 'eroded'), 'LOG': (0.001546, 'eroded')}
    ok = True
    for code, (w, how) in sorted(want.items()):
        U = measure_code(code, verbose=False)
        got = round(U['frac'] * (U['raw_min'] if how == 'raw' else U['min']), 6)
        rel = abs(got - w) / max(w, 1e-9)
        flag = 'ok' if rel < 0.05 or abs(got - w) < 2e-5 else 'DISAGREES'
        if flag != 'ok':
            ok = False
        print('%-5s [%s] exporter %.6f   this file %.6f   raw_min %.6f  '
              'eroded_min %.6f  n_raw %d  n_inner %d  plateau %d (%.1f%%)  %s'
              % (code, how, w, got, U['raw_min'], U['min'], U['n_raw'],
                 U['n_inner'], U['plateau'], 100 * U['plateau_frac'], flag))
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(0 if _selftest() else 1)
    for c in sys.argv[1:]:
        measure_code(c)
