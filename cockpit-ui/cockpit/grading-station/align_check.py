"""Seat-plane check for the grading station on dash_fascia.

Prints one JSON object. The seating plane stays on the local fascia frame:
angle at most 0.5 degrees, roll at most 0.5 degrees, raw normal dot negative,
base corners within 1 mm of that plane. The underside center must lie on the
finite fascia and must not float more than 1 mm on the pilot side. The front
face must stay on the pilot side of the curved mesh. Edge burial is recorded
and is not a failure. The support mesh is dash_fascia, not dash_face.

Run under Blender:

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python cockpit/grading-station/align_check.py
"""
import json
import math
import os
import sys


FAIL_ANGLE_DEG = 0.5
FAIL_MM = 1.0


def _unit(v):
    x, y, z = v
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (x / n, y / n, z / n)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def newell(points):
    """Unit normal of a loop. Right-hand rule around the given order."""
    nx = ny = nz = 0.0
    k = len(points)
    for i in range(k):
        x1, y1, z1 = points[i]
        x2, y2, z2 = points[(i + 1) % k]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return _unit((nx, ny, nz))


def plane_mm(normal, origin, point):
    """Signed distance from point to the plane, in millimetres."""
    return _dot(normal, _sub(point, origin)) * 1000.0


def on_fascia_panel(P, point):
    """True when the point sits on the finite vertical fascia, dash_fascia.

    The apron runs from the kick at z = 0.14 up to just under the brass lip.
    t = 0 is that kick and t = 1 is the lip. The radius has to be the fascia
    cylinder, so a sloped-dash pose, including the old t = -0.71 float, fails.
    """
    x, y, z = point
    ang = math.degrees(math.atan2(x, y))
    radius = math.hypot(x, y)
    r_face = P["radius"] - P["dash_run"] - 0.025
    z_lo = 0.14
    z_hi = P["dash_near_z"] - 0.025
    t = (z - z_lo) / (z_hi - z_lo)
    a0 = P["dash_arc_start"]
    a1 = P["dash_arc_end"]
    on = (
        (a0 + 1.0) <= ang <= (a1 - 1.0)
        and 0.02 <= t <= 0.98
        and abs(radius - r_face) <= 0.04
    )
    return on, ang, t


def evaluate(dash, corners, n_base, tangent, P, center, front_mm, edge_mm=None):
    """corners: list of {id, xyz}. n_base: outward normal of the seating face.

    Outward means out of the station, toward the dash. Face to face with the
    dash outward normal, so the raw dot is negative. The facing correction
    compares the dash normal with the flipped base normal; that angle is the
    alignment error. A raw dot that is already positive is a flipped normal
    and does not pass.

    center is {xyz, signed_mm}. Positive signed distance is the pilot side.
    front_mm are signed distances of the working face, iris, and controls.
    edge_mm are underside edge samples. A negative edge is burial and is
    allowed. A center more than 1 mm toward the pilot is a float. A negative
    front sample is a buried face.
    """
    n_dash = _unit(dash["normal"])
    o_dash = tuple(dash["origin"])
    u_dash = _unit(dash["u"])
    n_base = _unit(n_base)
    tangent = _unit(tangent)
    raw = _dot(n_base, n_dash)
    corrected = _dot((-n_base[0], -n_base[1], -n_base[2]), n_dash)
    angle = math.degrees(math.acos(_clamp(corrected, -1.0, 1.0)))
    residuals = []
    panel = []
    for corner in corners:
        xyz = tuple(corner["xyz"])
        mm = plane_mm(n_dash, o_dash, xyz)
        inside, ang, t = on_fascia_panel(P, xyz)
        residuals.append(round(mm, 4))
        panel.append({
            "id": corner["id"],
            "on_panel": bool(inside),
            "angle_deg": round(ang, 4),
            "t": round(t, 4),
            "plane_mm": round(mm, 4),
        })
    # Roll: the seating tangent against the dash tangent, in the dash plane.
    tan_plane = _sub(tangent, (
        n_dash[0] * _dot(tangent, n_dash),
        n_dash[1] * _dot(tangent, n_dash),
        n_dash[2] * _dot(tangent, n_dash)))
    tan_plane = _unit(tan_plane)
    roll_dot = _clamp(abs(_dot(tan_plane, u_dash)), 0.0, 1.0)
    roll = math.degrees(math.acos(roll_dot))
    worst = max(abs(v) for v in residuals) if residuals else 1e9
    c_xyz = tuple(center["xyz"])
    c_mm = center.get("signed_mm")
    c_on, c_ang, c_t = on_fascia_panel(P, c_xyz)
    front_vals = [v for v in (front_mm or []) if v is not None]
    edge_vals = [v for v in (edge_mm or []) if v is not None]
    front_min = min(front_vals) if front_vals else None
    edge_min = min(edge_vals) if edge_vals else None
    # The center has to be seated or deeper. More than 1 mm on the pilot
    # side is a visible float. The front has to stay out of the mesh.
    # Underside edges may pass through the curve.
    ok = (
        raw < 0.0
        and angle <= FAIL_ANGLE_DEG
        and worst <= FAIL_MM
        and roll <= FAIL_ANGLE_DEG
        and c_on
        and c_mm is not None
        and c_mm <= FAIL_MM
        and front_min is not None
        and front_min >= 0.0
    )
    return {
        "ok": bool(ok),
        "dashboard": {
            "face_id": dash["face_id"],
            "origin": [round(c, 6) for c in o_dash],
            "normal": [round(c, 6) for c in n_dash],
            "u": [round(c, 6) for c in u_dash],
            "v": [round(c, 6) for c in _unit(dash["v"])],
        },
        "seating_face": {
            "vertex_ids": [c["id"] for c in corners],
            "world_matrix_row_major": dash.get("seat_matrix"),
            "base_normal": [round(c, 6) for c in n_base],
            "tangent": [round(c, 6) for c in tangent],
        },
        "raw_dot": round(raw, 6),
        "corrected_dot": round(corrected, 6),
        "angle_deg": round(angle, 4),
        "roll_deg": round(roll, 4),
        "corner_mm": residuals,
        "max_abs_mm": round(worst, 4),
        "panel": panel,
        "center": {
            "xyz": [round(c, 6) for c in c_xyz],
            "signed_mm": None if c_mm is None else round(c_mm, 4),
            "on_panel": bool(c_on),
            "angle_deg": round(c_ang, 4),
            "t": round(c_t, 4),
        },
        "front_min_mm": None if front_min is None else round(front_min, 4),
        "edge_min_mm": None if edge_min is None else round(edge_min, 4),
        "limits": {
            "angle_deg": FAIL_ANGLE_DEG,
            "residual_mm": FAIL_MM,
            "center_float_mm": FAIL_MM,
            "front_min_mm": 0.0,
        },
    }


def emit(report):
    text = json.dumps(report)
    print(text)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    cockpit = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if cockpit not in sys.path:
        sys.path.insert(0, cockpit)
    import grading_station
    sys.exit(grading_station.main(check_only=True))
