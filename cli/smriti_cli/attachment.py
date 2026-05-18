"""Project attachment — durable repo ↔ space binding.

A project is "attached" to a Smriti space by a small `.smriti.json` file at
the repo root. Once written, every Smriti command run anywhere inside that
directory tree resolves its space from this file, so agents and humans no
longer pass `<space>` explicitly on each call.

The file is meant to be committed: the binding then travels with the repo,
so a fresh clone, a teammate, or a second agent opened in the project all
attach to the same space automatically.

Schema (forward-compatible — unknown keys are preserved on rewrite):

    {
      "space": "smriti-dev",          # required: space name or UUID
      "api_url": "http://localhost:8000",  # optional default backend URL
      "attached_at": "2026-05-19T01:00:00Z"  # optional, informational
    }

`api_url` is only a default — an explicit `--api-url` flag or the
`SMRITI_API_URL` environment variable always wins, so a committed file with
a local-mode URL stays correct across machines.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ATTACHMENT_FILENAME = ".smriti.json"


class AttachmentError(Exception):
    """Raised when an attachment file exists but is malformed."""


class Attachment:
    """A parsed `.smriti.json` and the path it was read from."""

    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data

    @property
    def space(self) -> str | None:
        value = self.data.get("space")
        return value if isinstance(value, str) and value.strip() else None

    @property
    def api_url(self) -> str | None:
        value = self.data.get("api_url")
        return value if isinstance(value, str) and value.strip() else None

    @property
    def root(self) -> Path:
        """The directory the project is attached from (where the file lives)."""
        return self.path.parent


def _candidate_dirs(start: Path) -> list[Path]:
    """Return `start` and every ancestor, nearest first."""
    start = start.resolve()
    return [start, *start.parents]


def find_attachment_file(start: str | os.PathLike[str] | None = None) -> Path | None:
    """Walk up from `start` (default cwd) looking for `.smriti.json`.

    Returns the path to the nearest attachment file, or None if none is
    found between `start` and the filesystem root.
    """
    begin = Path(start) if start is not None else Path.cwd()
    try:
        dirs = _candidate_dirs(begin)
    except OSError:
        return None
    for directory in dirs:
        candidate = directory / ATTACHMENT_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_attachment(start: str | os.PathLike[str] | None = None) -> Attachment | None:
    """Find and parse the nearest `.smriti.json`, or return None.

    Raises AttachmentError if a file is found but cannot be parsed or lacks
    a usable `space` — a corrupt binding should be loud, not silently
    ignored, since every command would otherwise fall back to "no space".
    """
    path = find_attachment_file(start)
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise AttachmentError(f"Could not read attachment file {path}: {e}")
    if not isinstance(raw, dict):
        raise AttachmentError(
            f"Attachment file {path} is not a JSON object."
        )
    attachment = Attachment(path, raw)
    if attachment.space is None:
        raise AttachmentError(
            f"Attachment file {path} is missing a non-empty \"space\" field."
        )
    return attachment


def write_attachment(
    directory: str | os.PathLike[str],
    space: str,
    api_url: str | None = None,
) -> Path:
    """Write (or update) `.smriti.json` in `directory`, returning its path.

    Existing unknown keys are preserved so a newer file written by a future
    CLI version is not clobbered by an older one.
    """
    target_dir = Path(directory)
    path = target_dir / ATTACHMENT_FILENAME

    data: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                data = existing
        except (ValueError, OSError):
            data = {}

    data["space"] = space
    if api_url:
        data["api_url"] = api_url
    data["attached_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    target_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
