"""
Combiner: builds the ONE main plate with every module's props present, and emits
a merged manifest for the combined frontend.

Per the two-tier model the main view is a single baked render, so occlusion and
shadows between modules are resolved natively here rather than by compositing
eight separate sprites.

Run:  blender --background --python combine.py
"""
import bpy, os, sys, json, glob, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shell, slots                                   # noqa: E402

OUT = os.path.join(HERE, "combined")
os.makedirs(OUT, exist_ok=True)


def load_module_builder(code):
    path = os.path.join(HERE, "modules", code, "build.py")
    spec = importlib.util.spec_from_file_location(f"mod_{code}", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def main():
    codes = sorted(d for d in os.listdir(os.path.join(HERE, "modules"))
                   if os.path.isdir(os.path.join(HERE, "modules", d))
                   and os.path.exists(os.path.join(HERE, "modules", d, "build.py")))
    print("MODULES:", codes)

    P = dict(shell.PARAMS)
    P["exterior"] = 0                      # window stays an alpha hole
    # A/B hooks (env, so the normal invocation is unchanged):
    #   CKPT_RAYTRACE=1   enable EEVEE screen-space raytracing
    #   CKPT_PLATE=name   write combined/<name>.png and skip the manifest
    # Default from shell.PARAMS, NOT a hardcoded 0 -- otherwise this silently
    # overrides the project default and bakes an un-raytraced plate.
    P["raytrace"] = int(os.environ.get("CKPT_RAYTRACE", shell.PARAMS["raytrace"]))
    plate_name = os.environ.get("CKPT_PLATE", "main_plate")
    scene = shell.build(P)
    scene.render.film_transparent = True
    mats = {"brass": bpy.data.materials["brass"],
            "hull": bpy.data.materials["hull"],
            "hull_d": bpy.data.materials["hull_d"]}

    added = {}
    dress_objs = []
    for code in codes:
        try:
            mod = load_module_builder(code)
            added[code] = mod.add_props(P, mats)
            print(f"  + {code}: ok")
        except Exception as e:                      # noqa: BLE001
            print(f"  ! {code}: FAILED {type(e).__name__}: {e}")

    # --- set dressing: non-interactive props, no glow / hotspot / manifest.
    # Discovered dynamically so tiers can land in any order. They must be present
    # in this scene both because they are baked into the plate AND because they
    # act as a second occluder class when hero glow masks are re-rendered.
    tiers = sorted(glob.glob(os.path.join(HERE, "dressing", "tier*.py")))
    for tf in tiers:
        name = os.path.splitext(os.path.basename(tf))[0]
        try:
            spec = importlib.util.spec_from_file_location(f"dr_{name}", tf)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            fn = getattr(mod, f"add_{name}", None)
            if fn is None:
                print(f"  ! {name}: no add_{name}(), skipped")
                continue
            got = fn(P, mats)
            objs = got.get("dress", []) if isinstance(got, dict) else []
            dress_objs.extend(objs)
            print(f"  + dressing/{name}: {len(objs)} objects")
        except Exception as e:                       # noqa: BLE001
            print(f"  ! dressing/{name}: FAILED {type(e).__name__}: {e}")
    print(f"  dressing total: {len(dress_objs)} objects")

    # NOTE: several modules deliberately set hide_render=True on alternate text /
    # state objects so the wide shot shows one resting state. We must NOT reset it.
    scene.render.filepath = os.path.join(OUT, f"{plate_name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"WROTE {plate_name}.png")
    if plate_name != "main_plate":
        print("A/B plate only -- manifest not rewritten")
        return

    # merge the per-module manifests, rewriting asset paths to be root-relative
    merged = {"canvas": {"w": scene.render.resolution_x,
                         "h": scene.render.resolution_y},
              "plate": "combined/main_plate.png", "modules": {}}
    for code in codes:
        mf = os.path.join(HERE, "modules", code, "out", "manifest.json")
        if not os.path.exists(mf):
            print(f"  ! {code}: no manifest, skipped")
            continue
        m = json.load(open(mf))
        base = f"modules/{code}/out/"
        far = dict(m["far"])
        far["prop"] = base + far["prop"]
        far["glow"] = base + far["glow"]
        close = {"canvas": m["close"].get("canvas", merged["canvas"]),
                 "plate": base + m["close"]["plate"], "controls": {}}
        for cid, c in m["close"]["controls"].items():
            c = dict(c)
            if "frames" in c:
                c["frames"] = [base + f for f in c["frames"]]
            if "image" in c:
                c["image"] = base + c["image"]
            if "states" in c:
                c["states"] = {k: base + v for k, v in c["states"].items()}
            close["controls"][cid] = c
        merged["modules"][code] = {
            "code": code, "name": m.get("name", code),
            "surface": m.get("surface", "?"), "far": far, "close": close}

    # Dressing deliberately contributes NO manifest surface: no far glow, no
    # hotspot, no close-up, nothing clickable. It exists only in the plate.
    merged["dressing_objects"] = len(dress_objs)

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(merged, f, indent=1)
    print("WROTE combined/manifest.json with", len(merged["modules"]), "modules")


main()
