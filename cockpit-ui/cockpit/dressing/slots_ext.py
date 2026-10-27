"""
Extra placement surfaces for set dressing.

`slots.py` is READ-ONLY to dressing agents, and it does not cover the two
surfaces the dressing plan needs: the curved hull wall above the window header
(and below the sill), and the ceiling underside inboard of the cove.

Same convention as `slots.py`:

    local +Z  =  outward surface normal (points toward the pilot/camera)
    local +Y  =  "up" along the surface
    local +X  =  "right" along the surface

Both functions return (location, euler) exactly like `slots.dash()` etc.
"""
import math
from mathutils import Vector


def wallband(P, angle_deg, z, lift=0.0):
    """Curved hull wall above the window header (or below the sill)."""
    r = P["radius"] - 0.02 - lift
    a = math.radians(angle_deg)
    return Vector((r * math.sin(a), r * math.cos(a), z)), (math.pi / 2, 0.0, -a)


def dome(P, angle_deg, r, z=None, lift=0.0):
    """Ceiling underside, inboard of the cove. Face points down."""
    a = math.radians(angle_deg)
    z = (P["ceiling"] - 0.13 if z is None else z) - lift
    return Vector((r * math.sin(a), r * math.cos(a), z)), (math.pi, 0.0, -a)


# ---------------------------------------------------------------- convenience
def ring_point(angle_deg, r, z):
    """A bare world-space point on a horizontal ring. Handy for conduit runs."""
    a = math.radians(angle_deg)
    return Vector((r * math.sin(a), r * math.cos(a), z))


def column_xy(P, index):
    """World (x, y) of a shell column axis. Mirrors shell.build()'s own maths."""
    n = P["pillar_count"]
    spread = P["pillar_spread"]
    angles = [0.0] if n == 1 else [
        -spread + 2 * spread * i / (n - 1) for i in range(n)]
    a = math.radians(angles[index])
    r = P["radius"] - P["pillar_inset"]
    return r * math.sin(a), r * math.cos(a), angles[index]
