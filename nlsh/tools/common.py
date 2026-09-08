"""
Small, dependency-free helpers shared between the up-front context gatherers
in ``nlsh/tools/`` and the on-demand, model-callable functions in
``nlsh/local_tools.py``.

These helpers are intentionally low-level and have no awareness of security
posture, whitelists, or output caps that differ between the two call sites —
each caller remains responsible for its own validation and truncation. This
keeps the DRY win limited to genuinely identical mechanics (directory
scanning, size formatting, PATH formatting) without merging the two modules,
which have different security requirements.
"""

import os


def scan_visible_entries(path: str) -> list["os.DirEntry"]:
    """Scan a directory and return non-hidden entries.

    Args:
        path: Directory path to scan.

    Returns:
        list[os.DirEntry]: Entries whose name does not start with ``.``.

    Raises:
        OSError: If the directory cannot be scanned (propagated so each
            caller can format its own error message).
    """
    with os.scandir(path) as it:
        return [e for e in it if not e.name.startswith(".")]


def format_size(size_bytes: float) -> str:
    """Format a byte count in a human-readable form (e.g. ``1.20 KB``).

    Args:
        size_bytes: File size in bytes.

    Returns:
        str: Human-readable size.
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024 or unit == "TB":
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    # Unreachable in practice (the loop always returns at "TB"), but keeps the
    # return type honest so callers never interpolate ``None`` into output.
    return f"{size_bytes:.2f} TB"


def format_path_entries(max_entries: int, bullet: str = "") -> list[str]:
    """Format a capped, human-readable preview of the ``PATH`` variable.

    Args:
        max_entries: Maximum number of PATH entries to include.
        bullet: Optional prefix for each entry line (e.g. ``"- "``).

    Returns:
        list[str]: Lines: a header line followed by up to ``max_entries``
            entry lines.
    """
    path = os.environ.get("PATH", "")
    entries = [e for e in path.split(os.pathsep) if e]
    shown = entries[:max_entries]
    lines = [f"PATH entries ({len(entries)} total, first {len(shown)} shown):"]
    lines.extend(f"{bullet}{e}" for e in shown)
    return lines
