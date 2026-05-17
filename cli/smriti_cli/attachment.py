"""Durable project <-> Smriti space attachment.

A repo is "attached" to a Smriti space by a `.smriti.json` file at its root.
Once attached, the CLI resolves the space automatically: agents and humans
stop passing `<space>` on every command, and a session opened anywhere in
the repo connects to the right space.

The file is intentionally tiny and git-committable. It records the space
*name* — the portable, human-meaningful key — plus the space id as a hint.
Resolution walks up from the working directory, the way git finds `.git`,
so any subdirectory of an attached repo resolves the same space.

A malformed or unreadable attachment is treated as "not attached" rather
than an error: a broken file must never make a command crash.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

ATTACHMENT_FILENAME = ".smriti.json"
ATTACHMENT_VERSION = 1


def find_attachment_file(start: str | os.PathLike[str] | None = None) -> Optional[Path]:
    """Walk up from `start` (default: cwd) for a `.smriti.json` file.

    Returns the Path of the first one found, or None. Mirrors how git
    locates `.git`, so the CLI resolves the space from any subdirectory
    of an attached repo.
    """
    try:
        current = Path(start or os.getcwd()).resolve()
    except OSError:
        return None
    for directory in (current, *current.parents):
        candidate = directory / ATTACHMENT_FILENAME
        if candidate.is_file():
            return candidate
    return None


def read_attachment(start: str | os.PathLike[str] | None = None) -> Optional[dict]:
    """Return the attachment record for the repo containing `start`, or None.

    The record has at least a `space` (name); it may also carry `space_id`
    and `version`. A malformed file resolves to None — never raises.
    """
    path = find_attachment_file(start)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("space"):
        return None
    return data


def write_attachment(
    repo_dir: str | os.PathLike[str],
    space_name: str,
    space_id: str | None = None,
) -> Path:
    """Write `.smriti.json` into `repo_dir`, recording the repo->space binding.

    Returns the path written. Overwrites any existing attachment — re-attaching
    a repo to a different space is a supported, explicit action.
    """
    path = Path(repo_dir) / ATTACHMENT_FILENAME
    record: dict = {"version": ATTACHMENT_VERSION, "space": space_name}
    if space_id:
        record["space_id"] = space_id
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path
