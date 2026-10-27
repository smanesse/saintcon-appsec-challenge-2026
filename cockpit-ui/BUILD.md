# Cockpit UI files

The finished files the cockpit opens are already in this tree. Open the cockpit without running a build. `build_ui.py` and the generator scripts it calls can recreate those files.

```
python3 build_ui.py
```

`build_ui.py` may be started from any working directory. It uses its own folder as the candidate and writes only inside that folder. Set `BLENDER` to override the default binary `/Applications/Blender.app/Contents/MacOS/Blender`.

The acceptance host had Python 3.15.0 and Blender 5.2.0 LTS (build hash `fbe6228777e7`, 2026-07-14). The wrapper uses the Python standard library. Blender is invoked as `--background --factory-startup --python-exit-code 7 --python <absolute script>`. Script modes are passed after `--`: `refit`, then `mast`.

Generators load these machine fonts when they are present. They are not copied into the package:

- `/System/Library/Fonts/Supplemental/Courier New Bold.ttf`
- `/System/Library/Fonts/Supplemental/Andale Mono.ttf`
- `/System/Library/Fonts/Menlo.ttc`

`/Library/Fonts/Courier New Bold.ttf` was not installed on the acceptance host. Custom fonts are not required and are not included.

The same producer order took about 35 minutes on that host. Each stage is limited to 45 minutes. A nonzero exit stops the build and is returned to the caller. The command refuses to start when `cockpit/combined/main_plate.png` is already present.

Order: nine `cockpit/modules/<CODE>/build.py` bakes (DNSM, FMM, IPM, KVS, LOG, MQB, MTA, OTA, PKT), `cockpit/combine.py`, `cockpit/grading_station.py`, then each `live3d/pipeline/export_<code>.py` as main, then `-- refit`, then `-- mast`, then `leaderboard.py`, `standings_plate.py -- depth`, `standings_plate.py -- render`, and `measure_transition.py`.

No screenshot, crop, sketch, or second default exporter pass is part of this command.
