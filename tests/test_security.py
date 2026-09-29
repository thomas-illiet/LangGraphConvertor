"""Test filesystem and network endpoint security boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from langflow_converter_mcp.security import SecurityError, Workspace, validate_endpoint


def test_workspace_rejects_parent_traversal(tmp_path: Path) -> None:
    """Relative parent traversal cannot escape the configured workspace."""
    workspace = Workspace(tmp_path)
    with pytest.raises(SecurityError, match="escapes workspace"):
        workspace.resolve("../outside.txt", must_exist=False)


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    """A symlink to an external file cannot bypass path containment."""
    outside = tmp_path.parent / "outside-target.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    workspace = Workspace(tmp_path)

    with pytest.raises(SecurityError, match="escapes workspace"):
        workspace.read_text("link.txt")


def test_endpoint_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Differential endpoints require an explicitly allowlisted hostname."""
    assert validate_endpoint("http://127.0.0.1:8000/run")
    with pytest.raises(SecurityError, match="not in"):
        validate_endpoint("https://example.com/run")

    monkeypatch.setenv("LFCM_ALLOWED_ENDPOINT_HOSTS", "example.com")
    assert validate_endpoint("https://example.com/run")
