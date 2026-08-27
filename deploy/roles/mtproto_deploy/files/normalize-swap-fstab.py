#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
from pathlib import Path


CANONICAL_ENTRY = "/swapfile none swap sw 0 0"
MANAGED_ENTRY = re.compile(
    r"^[ \t]*(?:/swapfile|/2G_swapfile)(?:[ \t][^\r\n]*)?(?:\r?\n)?$"
)


def normalize(lines: list[str]) -> list[str]:
    normalized = []
    canonical_written = False
    for line in lines:
        if MANAGED_ENTRY.fullmatch(line) is None:
            normalized.append(line)
            continue
        if canonical_written:
            continue

        if line.endswith("\r\n"):
            newline = "\r\n"
        elif line.endswith("\n"):
            newline = "\n"
        else:
            newline = ""
        normalized.append(f"{CANONICAL_ENTRY}{newline}")
        canonical_written = True

    if not canonical_written:
        if normalized and not normalized[-1].endswith(("\n", "\r")):
            normalized[-1] += "\n"
        normalized.append(f"{CANONICAL_ENTRY}\n")
    return normalized


def configure(fstab_path: Path) -> bool:
    original = fstab_path.read_text()
    updated = "".join(normalize(original.splitlines(keepends=True)))
    if updated == original:
        return False

    metadata = fstab_path.stat()
    descriptor, temporary_name = tempfile.mkstemp(
        dir=fstab_path.parent,
        prefix=f".{fstab_path.name}.",
    )
    try:
        with os.fdopen(descriptor, "w") as temporary:
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, stat.S_IMODE(metadata.st_mode))
        os.chown(temporary_name, metadata.st_uid, metadata.st_gid)
        os.replace(temporary_name, fstab_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} FSTAB_PATH")
    print("changed" if configure(Path(sys.argv[1])) else "unchanged")
