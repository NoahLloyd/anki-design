#!/usr/bin/env python3
"""Build a submittable .ankiaddon package.

An .ankiaddon is a zip of the add-on's files *at the root* (so __init__.py is
at the top level, not inside a folder). AnkiWeb supplies its own manifest, but
keeping name/conflicts in manifest.json is harmless and useful offline.

Usage:  python3 build.py   ->   dist/anki-design.ankiaddon
"""

import fnmatch
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "dist")
OUT = os.path.join(OUT_DIR, "anki-design.ankiaddon")

# Anything matching these (path-relative-to-root) is never shipped.
EXCLUDE_DIRS = {".git", "dist", "__pycache__", "scripts", ".context", "out"}
EXCLUDE_FILES = {
    "meta.json",
    ".DS_Store",
    ".gitignore",
    ".devmode",
    "build.py",
    "Makefile",
}
EXCLUDE_GLOBS = ["*.pyc"]


def _excluded(rel: str) -> bool:
    parts = rel.split(os.sep)
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    base = os.path.basename(rel)
    if base in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(base, g) for g in EXCLUDE_GLOBS)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)

    shipped = []
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [
                d for d in dirnames
                if d not in EXCLUDE_DIRS and not d.startswith(".git")
            ]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                if _excluded(rel):
                    continue
                z.write(full, rel)
                shipped.append(rel)

    print(f"wrote {OUT}")
    for f in sorted(shipped):
        print(f"  {f}")


if __name__ == "__main__":
    main()
