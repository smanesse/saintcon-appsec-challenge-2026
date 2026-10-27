#!/usr/bin/env python3
"""Cockpit availability, derived from the checked-out source tree.

A subsystem is "available" when its source is present in the working copy, and
"not_yet_available" when that source has not been checked out yet. The operator
advances the repository one release at a time (day1 -> day2 -> day3); whatever
the current checkout can build and run is exactly what the cockpit offers.

There is no clock and no schedule file. Availability is a pure function of the
files on disk. Like the old schedule, it reports only available /
not_yet_available and never leaks day numbers or upcoming titles.
"""
from __future__ import annotations

import os


def available_in_checkout(sub, repo_root):
    """True when this subsystem's source is present in the checkout.

    Resolution order:
      * ``sourceDir`` (explicit) — the subsystem's own source directory. The
        A.L.I.E.N. ships use this: they share one ``aliens/docker-compose.yml``
        but ship (and release) one directory at a time, so their availability
        tracks that directory, not the shared compose file.
      * ``composeFile`` — rows that name their own compose file resolve to it.
      * ``service`` (catalog ``service``/``composeService``/code) — modules
        resolve to their source directory.
    Unknown shapes fail open so the cockpit never hides something it cannot
    reason about.
    """
    if not isinstance(sub, dict):
        return True
    source_dir = (sub.get("sourceDir") or "").strip()
    if source_dir:
        return os.path.isdir(os.path.join(repo_root, source_dir))
    compose_file = (sub.get("composeFile") or "").strip()
    if compose_file:
        return os.path.isfile(os.path.join(repo_root, compose_file))
    service = (sub.get("service") or sub.get("composeService")
               or str(sub.get("code") or "").lower())
    if not service:
        return True
    return os.path.isdir(os.path.join(repo_root, service))


# is_released gates interact/power before a module is dialed; availability_for
# is the neutral label the cockpit paints. Both answer the same checkout
# question, so they stay thin wrappers over available_in_checkout.
def is_released(sub, repo_root):
    return available_in_checkout(sub, repo_root)


def availability_for(sub, repo_root):
    return "available" if available_in_checkout(sub, repo_root) else "not_yet_available"


def gate_error():
    return {
        "ok": False,
        "error": "not_yet_available",
        "availability": "not_yet_available",
        "summary": "not yet available",
    }
