# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Native Antigravity Deep-Link Pill Builders & Surface Detection (Track A).

Provides safe, validated URI link builders (`conversation://`, `customization://`,
`sidecar://`) with clean Desktop vs. CLI/headless surface adaptation.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional

_CONV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_INSTALL_DIR_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$")
_VIEW_PATH_RE = re.compile(r"^[A-Za-z0-9._~/?&=+%-]{0,256}$")

_DESKTOP_SURFACES = frozenset({"desktop", "app", "gui", "ide"})
_CLI_SURFACES = frozenset({"cli", "terminal", "tui", "headless"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_desktop_surface(surface: Optional[str] = None) -> bool:
    """Detects whether the active runtime targets Antigravity Desktop/IDE vs. CLI/headless."""
    if surface is not None and str(surface).strip():
        norm = str(surface).strip().lower()
        if norm in _DESKTOP_SURFACES:
            return True
        if norm in _CLI_SURFACES:
            return False
        raise ValueError(f"Unsupported UX surface: {surface!r}")

    for env_key in ("AGYIS_UX_SURFACE", "ANTIGRAVITY_SURFACE"):
        override = (os.environ.get(env_key) or "").strip().lower()
        if override in _DESKTOP_SURFACES:
            return True
        if override in _CLI_SURFACES:
            return False

    for cli_flag in ("ANTIGRAVITY_CLI", "AGY_CLI"):
        if (os.environ.get(cli_flag) or "").strip().lower() in _TRUTHY:
            return False

    for path_key in ("ANTIGRAVITY_APP_DATA_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_PRESENCE_DIR"):
        raw_path = (os.environ.get(path_key) or "").strip().replace("\\", "/").lower()
        if not raw_path:
            continue
        if "antigravity-cli" in raw_path:
            return False
        if "antigravity" in raw_path:
            return True

    if (os.environ.get("AGY_REQUIRE_AUTHENTICATED_UI_BOOTSTRAP") or "").strip():
        return True
    if (os.environ.get("AGY_BROWSER_ACTIVE_PORT_FILE") or "").strip():
        return True
    if (os.environ.get("ANTIGRAVITY_AGENT") or "").strip() and (
        os.environ.get("ANTIGRAVITY_CONVERSATION_ID") or ""
    ).strip():
        return True

    return False


def _sanitize_label(label: Optional[str], fallback: str) -> str:
    """Normalizes pill label text to single-line Markdown-safe characters."""
    raw = str(label or "")
    cleaned = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace("[", "(").replace("]", ")")
    if not cleaned:
        return fallback
    return cleaned[:120]


def _validate_conversation_id(conv_id: str) -> str:
    """Validates a conversation identifier against traversal, flag, and URI injection."""
    cid = str(conv_id or "").strip()
    if not cid or ".." in cid or not _CONV_ID_RE.fullmatch(cid):
        raise ValueError(f"Invalid conversation_id for deep link: {conv_id!r}")
    return cid


def _validate_install_dir(install_dir: str) -> str:
    """Validates a plugin install directory name (single segment, no traversal)."""
    dirname = str(install_dir or "").strip()
    if not dirname or dirname in (".", "..") or ".." in dirname or not _INSTALL_DIR_RE.fullmatch(dirname):
        raise ValueError(f"Invalid install_dir for customization pill: {install_dir!r}")
    return dirname


def _validate_sidecar_target(sidecar_id: str, view_path: str) -> tuple[str, str]:
    """Validates sidecar identifier (`<id>` or `<plugin>/<id>`) and relative view path."""
    sid = str(sidecar_id or "").strip().strip("/")
    parts = sid.split("/") if sid else []
    if not parts or len(parts) > 2:
        raise ValueError(f"Invalid sidecar_id for sidecar pill: {sidecar_id!r}")
    for seg in parts:
        if not seg or seg in (".", "..") or ".." in seg or not _INSTALL_DIR_RE.fullmatch(seg):
            raise ValueError(f"Invalid sidecar_id segment for sidecar pill: {sidecar_id!r}")

    raw_path = str(view_path if view_path is not None else "/").strip()
    if not raw_path:
        raw_path = "/"
    if "\\" in raw_path or ".." in raw_path or "//" in raw_path or not _VIEW_PATH_RE.fullmatch(raw_path):
        raise ValueError(f"Invalid view_path for sidecar pill: {view_path!r}")
    rel_path = raw_path.lstrip("/")
    return "/".join(parts), rel_path


def conversation_pill(
    conv_id: str,
    label: Optional[str] = None,
    *,
    surface: Optional[str] = None,
    include_cli_hint: Optional[bool] = None,
) -> str:
    """
    Builds a clickable `[Label](conversation://<id>)` pill on Desktop surfaces,
    or a clean non-empty CLI fallback (`Label (`agy --conversation <id>`)`) in terminals.
    """
    clean_id = _validate_conversation_id(conv_id)
    default_label = f"Thread {clean_id[:8]}" if len(clean_id) > 12 else clean_id
    clean_label = _sanitize_label(label, default_label)
    desktop = is_desktop_surface(surface)

    if desktop:
        link = f"[{clean_label}](conversation://{clean_id})"
        if include_cli_hint is True:
            return f"{link} (`agy --conversation {clean_id}`)"
        return link

    if include_cli_hint is False:
        return f"{clean_label} ({clean_id})"
    return f"{clean_label} (`agy --conversation {clean_id}`)"


def customization_pill(
    install_dir: str,
    label: Optional[str] = None,
    *,
    surface: Optional[str] = None,
) -> str:
    """
    Builds a clickable `[Label](customization://<dir>)` pill on Desktop surfaces,
    or a readable plugin-dir label on CLI surfaces.
    """
    clean_dir = _validate_install_dir(install_dir)
    clean_label = _sanitize_label(label, clean_dir)
    if is_desktop_surface(surface):
        return f"[{clean_label}](customization://{clean_dir})"
    return f"{clean_label} (plugin dir: `{clean_dir}`)"


def sidecar_pill(
    sidecar_id: str,
    view_path: str = "/",
    label: Optional[str] = None,
    *,
    surface: Optional[str] = None,
) -> str:
    """
    Builds a clickable `[Label](sidecar://<sidecar-id>/<view-path>)` pill on Desktop,
    or a readable sidecar label on CLI surfaces.
    """
    clean_id, rel_path = _validate_sidecar_target(sidecar_id, view_path)
    default_label = clean_id.split("/")[-1]
    clean_label = _sanitize_label(label, default_label)
    if is_desktop_surface(surface):
        return f"[{clean_label}](sidecar://{clean_id}/{rel_path})"
    return f"{clean_label} (sidecar: `{clean_id}/{rel_path}`)"


def render_pill_strip(pills: Iterable[str], sep: str = " · ") -> str:
    """Joins non-empty pill strings with a clean visual separator."""
    cleaned = [str(item).strip() for item in pills if item and str(item).strip()]
    return sep.join(cleaned)


__all__ = [
    "conversation_pill",
    "customization_pill",
    "is_desktop_surface",
    "render_pill_strip",
    "sidecar_pill",
]
