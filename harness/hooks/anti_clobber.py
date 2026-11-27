#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: PreToolUse Anti-Clobber & Append-Only Monotonic Guard (Issue #93).

Protects workspace files from destructive full-file overwrites across write tools
(`write_file`, `write_to_file`, `create_file`):
1. Layer 1 — Conflict-Marker Clobber Guard: blocks writes introducing or clobbering
   unresolved git merge conflict markers (`<<<<<<<`, `>>>>>>>`, `|||||||`, and
   paired `=======` without false-positiving on Markdown Setext underlines).
2. Layer 1 — Catastrophic Contraction Guard: blocks full-file overwrites that shrink
   non-scratch files (>50 lines) by >50% or >100 lines without explicit override.
3. Layer 2 — Universal Append-Only Monotonic Contract: enforces monotonic `##` section
   preservation on `CHANGELOG.md`, `*ledger*.md`, and files bearing
   `<!-- AGYIS: APPEND-ONLY -->` unless archived (`<!-- ARCHIVED: ... -->`) or
   explicitly overridden.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

WRITE_CLOBBER_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "write_to_file",
    "create_file",
})

TARGET_PATH_KEYS: Tuple[str, ...] = (
    "Path",
    "TargetFile",
    "target_file",
    "FilePath",
    "file_path",
    "AbsolutePath",
    "path",
)

CONTENT_KEYS: Tuple[str, ...] = (
    "Content",
    "CodeContent",
    "content",
    "code_content",
)

CONTRACTION_MIN_ORIG_LINES: int = 50
CONTRACTION_RATIO_THRESHOLD: float = 0.5
CONTRACTION_MAX_DROP_LINES: int = 100

APPEND_ONLY_MARKER: str = "<!-- agyis: append-only -->"
ARCHIVED_MARKER: str = "<!-- archived:"

UNIVERSAL_CLOBBER_TOKENS: Tuple[str, ...] = (
    "<!-- agyis: allow-clobber -->",
    "# agyis: allow-clobber",
)
CONFLICT_OVERRIDE_TOKENS: Tuple[str, ...] = (
    "<!-- agyis: allow-conflict-markers -->",
    "# agyis: allow-conflict-markers",
) + UNIVERSAL_CLOBBER_TOKENS
SHRINK_OVERRIDE_TOKENS: Tuple[str, ...] = (
    "<!-- agyis: allow-shrink -->",
    "# agyis: allow-shrink",
) + UNIVERSAL_CLOBBER_TOKENS
HEADER_DROP_OVERRIDE_TOKENS: Tuple[str, ...] = (
    "<!-- agyis: allow-header-drop -->",
    "# agyis: allow-header-drop",
    ARCHIVED_MARKER,
) + UNIVERSAL_CLOBBER_TOKENS

_CONFLICT_START_RE = re.compile(r"^<{7}(?:\s|$)")
_CONFLICT_END_RE = re.compile(r"^>{7}(?:\s|$)")
_CONFLICT_BASE_RE = re.compile(r"^\|{7}(?:\s|$)")
_CONFLICT_MID_RE = re.compile(r"^={7}\s*$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_H2_HEADER_RE = re.compile(r"^##\s+(.+)$")


def _is_env_clobber_allowed() -> bool:
    """Returns True when AGYIS_ALLOW_CLOBBER environment override is explicitly enabled."""
    return os.environ.get("AGYIS_ALLOW_CLOBBER", "").strip().lower() in ("1", "true", "yes")


def _has_override_token(text: str, tokens: Tuple[str, ...]) -> bool:
    """Case-insensitive token search for explicit anti-clobber bypass directives."""
    if not text:
        return False
    lower = text.lower()
    return any(tok in lower for tok in tokens)


def _parse_optional_bool(value: Any) -> Optional[bool]:
    """Parses optional boolean flag values from hook argument payloads."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in ("true", "1", "yes"):
            return True
        if norm in ("false", "0", "no"):
            return False
    return None


def _extract_write_call_fields(
    payload: Dict[str, Any],
) -> Tuple[str, Optional[str], Optional[str], Optional[bool], bool]:
    """Extracts normalized (tool_lower, target_file, content, overwrite, append_flag) from payload."""
    if not isinstance(payload, dict):
        return ("", None, None, None, False)

    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name") or payload.get("tool_name") or ""
        tool_args = tool_call.get("args")
        if not isinstance(tool_args, dict):
            tool_args = {}
    else:
        tool_name = payload.get("tool_name") or payload.get("toolName") or ""
        tool_args = payload.get("tool_args")
        if not isinstance(tool_args, dict):
            tool_args = {}

    tool_lower = str(tool_name).strip().lower()
    if tool_lower not in WRITE_CLOBBER_TOOLS:
        return (tool_lower, None, None, None, False)

    target: Optional[str] = None
    for src in (tool_args, payload):
        for key in TARGET_PATH_KEYS:
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                target = val.strip()
                break
        if target is not None:
            break

    content: Optional[str] = None
    for src in (tool_args, payload):
        for key in CONTENT_KEYS:
            if key in src and isinstance(src.get(key), str):
                content = src[key]
                break
        if content is not None:
            break

    overwrite: Optional[bool] = None
    for src in (tool_args, payload):
        for key in ("Overwrite", "overwrite"):
            if key in src:
                overwrite = _parse_optional_bool(src.get(key))
                break
        if overwrite is not None:
            break

    append_flag: Optional[bool] = None
    for src in (tool_args, payload):
        for key in ("Append", "append"):
            if key in src:
                parsed = _parse_optional_bool(src.get(key))
                if parsed is not None:
                    append_flag = parsed
                    break
        if append_flag is not None:
            break

    return (tool_lower, target, content, overwrite, bool(append_flag))


def _resolve_workspace_root(
    payload: Dict[str, Any],
    workspace_dir: Optional[Path | str] = None,
    cwd: Optional[Path | str] = None,
) -> Optional[Path]:
    """Resolves workspace root from explicit arguments or hook payload metadata."""
    candidates: List[Any] = [workspace_dir, cwd]
    ws_paths = payload.get("workspacePaths") or payload.get("workspace_paths") or []
    if isinstance(ws_paths, list) and ws_paths:
        candidates.append(ws_paths[0])
    candidates.extend([
        payload.get("workspace_dir"),
        payload.get("workspace"),
        payload.get("cwd"),
        payload.get("working_directory"),
    ])
    for cand in candidates:
        if isinstance(cand, Path):
            return cand.resolve()
        if isinstance(cand, str) and cand.strip():
            return Path(cand.strip()).resolve()
    return None


def _resolve_target_path(target: str, workspace_root: Optional[Path]) -> Path:
    """Resolves relative target file paths against workspace_root (or cwd)."""
    p = Path(target)
    if p.is_absolute():
        return p.resolve()
    base = workspace_root if workspace_root is not None else Path.cwd()
    return (base / p).resolve()


def is_ephemeral_clobber_exempt_path(
    target_path: Path,
    raw_target: str = "",
    workspace_root: Optional[Path] = None,
) -> bool:
    """
    Returns True for ephemeral scratch, checkpoint, system-generated, or out-of-workspace
    temp paths exempted from catastrophic contraction checks.
    """
    resolved = target_path.resolve()
    rel_parts: Tuple[str, ...] = ()
    inside_workspace = False
    if workspace_root is not None:
        ws_resolved = workspace_root.resolve()
        try:
            rel = resolved.relative_to(ws_resolved)
            rel_parts = tuple(p.lower() for p in rel.parts)
            inside_workspace = True
        except ValueError:
            inside_workspace = False

    check_parts = rel_parts if inside_workspace else tuple(p.lower() for p in resolved.parts)
    norm_check = "/".join(check_parts)

    if "scratch" in check_parts or ".system_generated" in check_parts:
        return True
    if ".agents/artifacts/checkpoints" in norm_check:
        return True

    raw_norm = raw_target.replace("\\", "/").strip().lower()
    if raw_norm.startswith(("scratch/", "./scratch/", ".system_generated/", ".agents/artifacts/checkpoints/")):
        return True

    if not inside_workspace:
        temp_roots = [Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()]
        for tmp_root in temp_roots:
            try:
                resolved.relative_to(tmp_root)
                return True
            except ValueError:
                continue

    return False


def detect_conflict_markers(text: str) -> List[str]:
    """
    Detects unresolved git merge conflict markers at line starts.

    Flags `<<<<<<<`, `>>>>>>>`, `|||||||`, and `=======` ONLY when paired with
    `<<<<<<<` or `>>>>>>>` so benign Markdown Setext headings (`Title\\n=======`)
    never trigger false positives.
    """
    if not text:
        return []
    found_start = False
    found_end = False
    found_base = False
    found_mid = False
    for line in text.splitlines():
        if _CONFLICT_START_RE.match(line):
            found_start = True
        elif _CONFLICT_END_RE.match(line):
            found_end = True
        elif _CONFLICT_BASE_RE.match(line):
            found_base = True
        elif _CONFLICT_MID_RE.match(line):
            found_mid = True

    markers: List[str] = []
    if found_start:
        markers.append("<<<<<<<")
    if found_base:
        markers.append("|||||||")
    if found_mid and (found_start or found_end):
        markers.append("=======")
    if found_end:
        markers.append(">>>>>>>")
    return markers


def is_append_only_target(target_path: Path, existing_text: str, new_content: str) -> bool:
    """
    Returns True if the target file is governed by the Layer 2 append-only monotonic contract:
    - Filename is `CHANGELOG.md` or `*ledger*.md` (case-insensitive), OR
    - Existing file or incoming buffer contains `<!-- AGYIS: APPEND-ONLY -->`.
    """
    name_lower = target_path.name.lower()
    if name_lower == "changelog.md":
        return True
    if name_lower.endswith(".md") and "ledger" in name_lower:
        return True
    if APPEND_ONLY_MARKER in existing_text.lower() or APPEND_ONLY_MARKER in new_content.lower():
        return True
    return False


def extract_h2_headers(markdown_text: str) -> List[str]:
    """Extracts level-2 Markdown section headings (`^##\\s+(.+)$`), skipping fenced code blocks."""
    headers: List[str] = []
    fence_char: Optional[str] = None
    fence_len: int = 0

    for line in markdown_text.splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            token = fence_match.group(1)
            char = token[0]
            if fence_char is None:
                fence_char = char
                fence_len = len(token)
                continue
            if char == fence_char and len(token) >= fence_len and line.strip() == token:
                fence_char = None
                fence_len = 0
                continue
        if fence_char is not None:
            continue
        h2_match = _H2_HEADER_RE.match(line)
        if h2_match:
            headers.append(h2_match.group(1).strip())
    return headers


def check_anti_clobber(
    payload: Dict[str, Any],
    workspace_dir: Optional[Path | str] = None,
    cwd: Optional[Path | str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates PreToolUse write payloads against Layer 1 (conflict markers + catastrophic
    contraction) and Layer 2 (append-only monotonic `##` sections).

    Returns:
        `{"decision": "deny", "reason": ...}` when a clobber hazard is detected.
        `None` when the write is permitted or the tool is outside scope.
    """
    tool_lower, raw_target, new_content, overwrite, append_flag = _extract_write_call_fields(payload)
    if tool_lower not in WRITE_CLOBBER_TOOLS or not raw_target or new_content is None:
        return None

    if _is_env_clobber_allowed():
        return None

    ws_root = _resolve_workspace_root(payload, workspace_dir=workspace_dir, cwd=cwd)
    target_path = _resolve_target_path(raw_target, ws_root)

    existing_text: Optional[str] = None
    if target_path.is_file():
        try:
            existing_text = target_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            sys.stderr.write(f"[AGYIS ANTI-CLOBBER] Warning: Could not read '{target_path}': {exc}\n")
            existing_text = None

    is_overwrite = (not append_flag) and (overwrite is not False)

    # Layer 1A: Conflict-Marker Clobber Guard (incoming buffer + existing file when overwriting)
    incoming_markers = detect_conflict_markers(new_content)
    existing_markers = detect_conflict_markers(existing_text) if (is_overwrite and existing_text) else []
    if (incoming_markers or existing_markers) and not _has_override_token(new_content, CONFLICT_OVERRIDE_TOKENS):
        all_markers = list(dict.fromkeys(incoming_markers + existing_markers))
        sources = []
        if incoming_markers:
            sources.append("incoming content")
        if existing_markers:
            sources.append("existing target file")
        src_desc = " and ".join(sources)
        return {
            "decision": "deny",
            "reason": (
                f"[AGYIS ANTI-CLOBBER] Conflict-marker guard blocked '{raw_target}': "
                f"unresolved merge conflict marker(s) ({', '.join(all_markers)}) detected in {src_desc}. "
                "Resolve conflicts surgically with 'edit_file' instead of writing conflicted buffers "
                "(or include '<!-- AGYIS: ALLOW-CONFLICT-MARKERS -->' / AGYIS_ALLOW_CLOBBER=1 if intentional)."
            ),
        }

    if existing_text is None or not is_overwrite:
        return None

    # Layer 1B: Catastrophic Contraction Guard
    if not is_ephemeral_clobber_exempt_path(target_path, raw_target=raw_target, workspace_root=ws_root):
        orig_lines = len(existing_text.splitlines())
        new_lines = len(new_content.splitlines())
        dropped_lines = orig_lines - new_lines
        if orig_lines > CONTRACTION_MIN_ORIG_LINES and (
            new_lines < orig_lines * CONTRACTION_RATIO_THRESHOLD
            or dropped_lines > CONTRACTION_MAX_DROP_LINES
        ):
            if not _has_override_token(new_content, SHRINK_OVERRIDE_TOKENS):
                return {
                    "decision": "deny",
                    "reason": (
                        f"[AGYIS ANTI-CLOBBER] Catastrophic contraction blocked on '{raw_target}': "
                        f"{orig_lines} -> {new_lines} lines (dropped {dropped_lines} lines). "
                        "Use surgical 'edit_file' instead of full-file 'write_file(Overwrite=True)', "
                        "or include '<!-- AGYIS: ALLOW-SHRINK -->' / '# agyis: allow-shrink' / AGYIS_ALLOW_CLOBBER=1."
                    ),
                }

    # Layer 2: Universal Append-Only Monotonic Contract
    if is_append_only_target(target_path, existing_text, new_content):
        existing_h2 = extract_h2_headers(existing_text)
        new_h2_set = set(extract_h2_headers(new_content))
        dropped_headers = list(dict.fromkeys(h for h in existing_h2 if h not in new_h2_set))
        if dropped_headers and not _has_override_token(new_content, HEADER_DROP_OVERRIDE_TOKENS):
            preview = ", ".join(f"'## {h}'" for h in dropped_headers[:5])
            extra = f" (+{len(dropped_headers) - 5} more)" if len(dropped_headers) > 5 else ""
            return {
                "decision": "deny",
                "reason": (
                    f"[AGYIS ANTI-CLOBBER] Append-only monotonic contract violation on '{raw_target}': "
                    f"dropped existing section header(s): {preview}{extra}. "
                    "Append new entries instead of deleting historical sections; if intentionally archiving, "
                    "record '<!-- ARCHIVED: ... -->' (or override with '<!-- AGYIS: ALLOW-HEADER-DROP -->' / AGYIS_ALLOW_CLOBBER=1)."
                ),
            }

    return None


__all__ = [
    "WRITE_CLOBBER_TOOLS",
    "CONTRACTION_MIN_ORIG_LINES",
    "CONTRACTION_RATIO_THRESHOLD",
    "CONTRACTION_MAX_DROP_LINES",
    "detect_conflict_markers",
    "extract_h2_headers",
    "is_append_only_target",
    "is_ephemeral_clobber_exempt_path",
    "check_anti_clobber",
]
