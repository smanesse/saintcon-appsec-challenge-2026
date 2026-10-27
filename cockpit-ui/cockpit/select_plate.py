"""Point the combined manifest at the grading plate this run just wrote.

Stdlib only, so a test can call it without Blender. grading_station.py calls
this after the station plate exists. A missing plate leaves the manifest
untouched and fails the process.
"""

from __future__ import annotations

import json
import os


def select_generated_plate(
    manifest_path,
    plate_path,
    plate_value="combined/grading_station_plate.png",
):
    manifest_path = os.path.abspath(manifest_path)
    plate_path = os.path.abspath(plate_path)
    if not os.path.isfile(plate_path):
        raise SystemExit("grading plate was not written")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest["plate"] = plate_value
    temporary = manifest_path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1)
        handle.write("\n")
    os.replace(temporary, manifest_path)
    print("SELECTED", plate_value)
    return plate_value
