# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Subagent Ladder stage-role mapping, deterministic materialization, and schema validation (Issue #85).

Maintains deterministic alignment between Subagent Ladder stages (0-4) and
the mainline Role Taxonomy (flight_director, deep_execution, forensic_auditor)
under Pillar 3 Explicit Cognitive Self-Identification.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from harness.trajectory.health import (
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
)
from harness.utils.context import get_active_conversation_id

STAGE_ROLE_MAP: Dict[int, str] = {
    0: ROLE_FLIGHT_DIRECTOR,
    1: ROLE_DEEP_EXECUTION,
    2: ROLE_FORENSIC_AUDITOR,
    3: ROLE_DEEP_EXECUTION,
    4: ROLE_FORENSIC_AUDITOR,
}

STAGE_NAME_MAP: Dict[int, str] = {
    0: "COORDINATION",
    1: "EXECUTION",
    2: "CODE_REVIEW",
    3: "GIT_CUSTODY",
    4: "QA_AUDIT",
}

STAGE_ROLE_SCHEMA_URI: str = "https://json-schema.org/draft/2020-12/schema"


def validate_stage_role_schema(data: Any) -> bool:
    """
    Validates a session_role.json dictionary against the typed stage role schema.
    Zero external dependencies.
    """
    if not isinstance(data, dict):
        return False

    required_keys = {"role", "specialist_agent", "stage", "stage_name", "task_id"}
    if not required_keys.issubset(data.keys()):
        return False

    stage = data.get("stage")
    if not isinstance(stage, int) or stage not in STAGE_ROLE_MAP:
        return False

    if data.get("role") != STAGE_ROLE_MAP[stage]:
        return False

    if data.get("stage_name") != STAGE_NAME_MAP[stage]:
        return False

    specialist = data.get("specialist_agent")
    if not isinstance(specialist, str) or not specialist.strip():
        return False

    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return False

    return True


def _resolve_stage_role_file(
    ws: Path,
    conversation_id: Optional[str] = None,
) -> Tuple[Path, Optional[str]]:
    """Resolves isolated per-conversation session_role.json path (never global shared root)."""
    cid = get_active_conversation_id(conversation_id)
    folder = cid if cid else "session"
    return ws / ".agents" / "artifacts" / "checkpoints" / folder / "session_role.json", cid


def materialize_stage_role(
    stage: int,
    agent_name: str,
    task_id: str,
    workspace_dir: Optional[Union[str, Path]] = None,
    conversation_id: Optional[str] = None,
) -> Path:
    """
    Atomically writes CID-scoped `.agents/artifacts/checkpoints/<cid>/session_role.json`
    to anchor the active specialist's explicit cognitive role under Pillar 3.
    """
    if not isinstance(stage, int) or stage not in STAGE_ROLE_MAP:
        raise ValueError(
            f"Invalid ladder stage: {stage}. Must be one of {list(STAGE_ROLE_MAP.keys())}"
        )
    if not isinstance(agent_name, str) or not agent_name.strip():
        raise ValueError("agent_name must be a non-empty string")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")

    ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    target_file, cid = _resolve_stage_role_file(ws, conversation_id)
    target_dir = target_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = target_dir / f".session_role.json.tmp.{os.getpid()}"

    payload: Dict[str, Any] = {
        "$schema": STAGE_ROLE_SCHEMA_URI,
        "role": STAGE_ROLE_MAP[stage],
        "specialist_agent": agent_name.strip(),
        "stage": stage,
        "stage_name": STAGE_NAME_MAP[stage],
        "task_id": task_id.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if cid:
        payload["conversation_id"] = cid

    try:
        tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_file.replace(target_file)
    except Exception:
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
        raise

    return target_file


def read_stage_role(
    workspace_dir: Optional[Union[str, Path]] = None,
    conversation_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Reads and validates CID-scoped `session_role.json` (with non-clobbering fallback
    when legacy `.agents/session_role.json` belongs to no conflicting conversation).
    """
    try:
        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        scoped_file, cid = _resolve_stage_role_file(ws, conversation_id)
        candidates = [scoped_file]
        if conversation_id is None:
            session_fallback = (
                ws / ".agents" / "artifacts" / "checkpoints" / "session" / "session_role.json"
            )
            if session_fallback != scoped_file:
                candidates.append(session_fallback)
            candidates.append(ws / ".agents" / "session_role.json")

        for target_file in candidates:
            if not target_file.is_file():
                continue
            size = target_file.stat().st_size
            if size == 0 or size > 65_536:
                continue
            content = target_file.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                continue
            data = json.loads(content)
            if not validate_stage_role_schema(data):
                continue
            file_cid = str(data.get("conversation_id") or "").strip()
            if cid and file_cid and file_cid != cid:
                continue
            return data
        return None
    except Exception:
        return None


def clear_stage_role(
    workspace_dir: Optional[Union[str, Path]] = None,
    conversation_id: Optional[str] = None,
) -> bool:
    """Safely removes CID-scoped `session_role.json` upon stage completion or handoff."""
    removed = False
    try:
        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        scoped_file, _ = _resolve_stage_role_file(ws, conversation_id)
        targets = [scoped_file]
        if conversation_id is None:
            targets.append(ws / ".agents" / "session_role.json")
        for target_file in targets:
            if target_file.is_file() or target_file.is_symlink():
                target_file.unlink()
                removed = True
    except OSError:
        return removed
    return removed
