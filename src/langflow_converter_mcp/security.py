"""Filesystem and endpoint security boundaries."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


class SecurityError(ValueError):
    """Raised when a caller attempts to escape the configured boundary."""


class Workspace:
    """Restrict all file operations to one canonical workspace root."""

    def __init__(self, root: Path, *, max_file_bytes: int = 5 * 1024 * 1024) -> None:
        """Initialize the boundary and maximum permitted individual file size."""
        self.root = root.resolve(strict=True)
        self.max_file_bytes = max_file_bytes

    def resolve(self, value: str | Path, *, must_exist: bool = True) -> Path:
        """Resolve a path and reject traversal or symlink escapes."""
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve(strict=must_exist)
        except OSError as exc:
            raise SecurityError(f"Cannot resolve path: {value}") from exc
        if not resolved.is_relative_to(self.root):
            raise SecurityError(f"Path escapes workspace root: {value}")
        if must_exist and resolved.is_file() and resolved.stat().st_size > self.max_file_bytes:
            raise SecurityError(f"File exceeds {self.max_file_bytes} bytes: {value}")
        return resolved

    def read_text(self, value: str | Path) -> str:
        """Read a size-limited UTF-8 file inside the workspace."""
        path = self.resolve(value)
        if not path.is_file():
            raise SecurityError(f"Expected a file: {value}")
        return path.read_text(encoding="utf-8")

    def write_text(self, value: str | Path, content: str) -> Path:
        """Write size-limited UTF-8 content inside the workspace."""
        if len(content.encode()) > self.max_file_bytes:
            raise SecurityError("Content exceeds configured file limit")
        path = self.resolve(value, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


def validate_endpoint(url: str) -> str:
    """Accept only explicit HTTP endpoints whose host is allowlisted."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SecurityError("Only explicit HTTP(S) endpoints are allowed")
    allowed = {
        item.strip().lower()
        for item in os.getenv("LFCM_ALLOWED_ENDPOINT_HOSTS", "localhost,127.0.0.1,::1").split(",")
        if item.strip()
    }
    if parsed.hostname.lower() not in allowed:
        raise SecurityError(
            f"Endpoint host {parsed.hostname!r} is not in LFCM_ALLOWED_ENDPOINT_HOSTS"
        )
    return url
