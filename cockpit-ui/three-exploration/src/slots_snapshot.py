"""
Shared slot placement for module props. READ-ONLY to module agents.

Every slot returns (location, euler) with ONE convention, so a prop modelled
once can be dropped on any surface:

    local +Z  =  outward surface normal (points toward the pilot/camera)
    local +Y  =  "up" along the surface
    local +X  =  "right" along the surface

So: model your control as if it sits on a panel in the XY plane facing +Z, put
it at the origin, then apply the returned location/euler. No per-surface math.
"""
import math
from mathutils import Vector

# Which module lives on which surface, and where.
# Surfaces were chosen to match each module's character:
#   dash   - hands-on controls you operate directly
#   fascia - the tall vertical console front; things that EMIT (tape, mail)
#   ceiling- hanging watch/listen infrastructure
#   pillar - narrow vertical: stacked racks, a periscope you pull down
SLOTS = {
    "FMM":  {"surface": "dash",    "angle": -40.0, "t": 0.46},
    "KVS":  {"surface": "dash",    "angle":  34.0, "t": 0.46},
    "LOG":  {"surface": "fascia",  "angle": -15.0, "z": 0.50},
    "MTA":  {"surface": "fascia",  "angle":  13.0, "z": 0.50},
    "MQB":  {"surface": "ceiling", "angle": -34.0, "r": 0.74, "drop": 0.30},
    "DNSM": {"surface": "ceiling", "angle":  27.0, "r": 0.66, "drop": 0.34},
    "OTA":  {"surface": "pillar",  "pillar": 0, "z": 1.42},
    "IPM":  {"surface": "pillar",  "pillar": 1, "z": 1.46},
    # The packet transmitter ("Signal Harpoon") — the offensive centrepiece.
    # Added after the eight defensive modules; PKT/build.py currently calls
    # slots.dash(P, 0.0, 0.40) directly and exports the same under manifest.slot.
    "PKT":  {"surface": "dash",    "angle":   0.0, "t": 0.40},
}


def dash(P, angle_deg, t=0.46, lift=0.0):
    """On the raked dash face. t=0 near edge (toward pilot), t=1 far edge."""
    R = P["radius"]
    r_near, r_far = R - P["dash_run"], R - 0.05
    z_near, z_far = P["dash_near_z"], P["dash_top_z"]
    r = r_near + (r_far - r_near) * t
    z = z_near + (z_far - z_near) * t
    rake = math.atan2(z_far - z_near, r_far - r_near)
    a = math.radians(angle_deg)
    r -= lift * math.sin(rake)
    z += lift * math.cos(rake)
    return Vector((r * math.sin(a), r * math.cos(a), z)), (rake, 0.0, -a)


def fascia(P, angle_deg, z=0.50, lift=0.0):
    """On the tall vertical console front, below the dash lip."""
    r = P["radius"] - P["dash_run"] - 0.025 - lift
    a = math.radians(angle_deg)
    return Vector((r * math.sin(a), r * math.cos(a), z)), (math.pi / 2, 0.0, -a)


def ceiling(P, angle_deg, r_frac=0.72, drop=0.30, lift=0.0):
    """Hanging from the ceiling, face pointing down at the pilot."""
    r = P["radius"] * r_frac
    a = math.radians(angle_deg)
    z = P["ceiling"] - drop + lift
    return Vector((r * math.sin(a), r * math.cos(a), z)), (math.pi, 0.0, -a)


def pillar(P, index, z=1.42, lift=0.0):
    """On the inboard face of a column (the side the pilot sees)."""
    n = P["pillar_count"]
    spread = P["pillar_spread"]
    angles = [0.0] if n == 1 else [
        -spread + 2 * spread * i / (n - 1) for i in range(n)]
    a = math.radians(angles[index])
    r = P["radius"] - P["pillar_inset"] - P["pillar_radius"] - lift
    return Vector((r * math.sin(a), r * math.cos(a), z)), (math.pi / 2, 0.0, -a)


def place(P, code, lift=0.0):
    """Resolve a module code to (location, euler) via the SLOTS table."""
    s = SLOTS[code]
    k = s["surface"]
    if k == "dash":
        return dash(P, s["angle"], s["t"], lift)
    if k == "fascia":
        return fascia(P, s["angle"], s["z"], lift)
    if k == "ceiling":
        return ceiling(P, s["angle"], s["r"], s["drop"], lift)
    if k == "pillar":
        return pillar(P, s["pillar"], s["z"], lift)
    raise ValueError(k)
