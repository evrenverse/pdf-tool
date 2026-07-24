"""Shared helpers for pdf-tool commands.

- :func:`atomic_output` — crash-safe file writes (temp + os.replace)
- :func:`ensure_not_encrypted` — clean error for encrypted PDFs
- :func:`walk_field_chain` / :func:`resolve_inherited` — cycle-guarded
  AcroForm /Parent tree walks
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import typer

# Malformed PDFs can nest /Parent absurdly deep; cap as a backstop besides
# the visited-set cycle guard.
_MAX_PARENT_DEPTH = 64
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_JSON_INPUT_BYTES = 10 * 1024 * 1024
MAX_BATCH_ITEMS = 10_000


def ensure_input_size(file: Path) -> None:
    """Reject oversized attacker-controlled PDF inputs before parsing."""
    try:
        size = file.stat().st_size
    except OSError:
        return
    if size > MAX_INPUT_BYTES:
        typer.echo(
            f"Error: PDF input is {size} bytes; maximum is {MAX_INPUT_BYTES} bytes",
            err=True,
        )
        raise typer.Exit(code=2)


def ensure_json_size(raw: str) -> None:
    """Reject oversized JSON before decoding it into nested Python objects."""
    size = len(raw.encode("utf-8"))
    if size > MAX_JSON_INPUT_BYTES:
        typer.echo(
            f"Error: JSON input is {size} bytes; maximum is {MAX_JSON_INPUT_BYTES} bytes",
            err=True,
        )
        raise typer.Exit(code=2)


@contextmanager
def atomic_output(path: str | Path) -> Iterator[Path]:
    """Yield a temp path next to ``path``; atomically replace on success.

    The destination is never left truncated or half-written: consumers write
    to the yielded temp file (the original stays fully intact and readable —
    crucial for in-place operations where a lazy reader still holds the
    source open), then ``os.replace`` swaps it in. On any exception the temp
    file is removed and the destination is untouched.
    """
    target = Path(path)
    original_mode = target.stat().st_mode if target.exists() else None
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent) or ".",
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        yield tmp_path
        # Writers have closed the file when control returns. Flush the bytes to
        # disk before publishing the new name, and preserve existing mode bits.
        # Windows rejects fsync on a read-only handle with EBADF, so open the
        # file for writing even though only its flush is needed.
        sync_fd = os.open(tmp_path, os.O_RDWR)
        try:
            os.fsync(sync_fd)
        finally:
            os.close(sync_fd)
        if original_mode is not None:
            os.chmod(tmp_path, original_mode & 0o777)
        os.replace(tmp_path, target)
        if os.name == "posix":
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_not_encrypted(file: Path) -> None:
    """Exit 1 with a clean message if ``file`` is an encrypted PDF.

    Anything that is not positively identified as encrypted passes through —
    unreadable/corrupt files are left to the command's own error handling.
    """
    from pypdf import PdfReader

    try:
        encrypted = PdfReader(str(file)).is_encrypted
    except Exception:
        return
    if encrypted:
        typer.echo("Error: PDF is encrypted — decryption not supported", err=True)
        raise typer.Exit(code=1)


def walk_field_chain(annot: Any) -> Iterator[Any]:
    """Yield ``annot`` followed by its resolved /Parent chain, cycle-guarded.

    Stops on revisited nodes (identity-based) or beyond ``_MAX_PARENT_DEPTH``
    — malformed PDFs can contain /Parent cycles that would otherwise hang
    every field walk.
    """
    seen: set[int] = set()
    current = annot
    depth = 0
    while current is not None and depth < _MAX_PARENT_DEPTH:
        if id(current) in seen:
            return
        seen.add(id(current))
        yield current
        parent = current.get("/Parent")
        current = parent.get_object() if parent is not None else None
        depth += 1


def resolve_inherited(annot: Any, key: str) -> Any:
    """Read an (inheritable) field entry, walking the /Parent chain safely."""
    for node in walk_field_chain(annot):
        value = node.get(key)
        if value is not None:
            return value
    return None
