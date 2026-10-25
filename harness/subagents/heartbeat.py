# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Subagent Ladder stage-aware sequential heartbeat crons and two-tier telemetry (Issue #84).

Provides deterministic lifecycle heartbeat tracking across ladder stages:
- Arming: Atomically initializes ladder_heartbeat.json on stage entry.
- Pulsing: Updates step count, elapsed time, last action, and ISO-8601 timestamp.
- Disarming: Seals completion or terminal stage status upon handoff.
- Reading & Staleness: Validates schema and detects stalled subagent execution (>300s).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

LADDER_HEARTBEAT_PATH: Path = Path(".agents/artifacts/ladder_heartbeat.json")

VALID_STAGES: frozenset[str] = frozenset(
    {"coordinator", "executioner", "hammer", "custodian", "auditor"}
)

VALID_STATUSES: frozenset[str] = frozenset(
    {"dispatched", "in_progress", "verifying", "complete", "failed", "halted", "stale"}
)

HEARTBEAT_PROTOCOL_VERSION: str = "2026.1"
HEARTBEAT_EVENT: str = "ladder_heartbeat"


def validate_heartbeat_schema(data: Any) -> bool:
    """
    Validates a ladder_heartbeat.json dictionary against the typed heartbeat schema.
    Zero external dependencies.
    """
    if not isinstance(data, dict):
        return False

    required_keys = {
        "event",
        "protocol_version",
        "task_id",
        "stage",
        "active_agent_id",
        "subagent_role",
        "step_count",
        "elapsed_s",
        "status",
        "last_action",
        "timestamp",
    }
    if not required_keys.issubset(data.keys()):
        return False

    event = data.get("event")
    if not isinstance(event, str) or not event.strip():
        return False

    proto = data.get("protocol_version")
    if not isinstance(proto, str) or not proto.strip():
        return False

    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return False

    stage = data.get("stage")
    if not isinstance(stage, str) or stage not in VALID_STAGES:
        return False

    agent_id = data.get("active_agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return False

    subagent_role = data.get("subagent_role")
    if not isinstance(subagent_role, str) or not subagent_role.strip():
        return False

    step_count = data.get("step_count")
    if isinstance(step_count, bool) or not isinstance(step_count, int) or step_count < 0:
        return False

    elapsed_s = data.get("elapsed_s")
    if isinstance(elapsed_s, bool) or not isinstance(elapsed_s, (int, float)) or elapsed_s < 0.0:
        return False

    status = data.get("status")
    if not isinstance(status, str) or status not in VALID_STATUSES:
        return False

    last_action = data.get("last_action")
    if not isinstance(last_action, str):
        return False

    ts = data.get("timestamp")
    if not isinstance(ts, str) or not ts.strip():
        return False

    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return False
    except Exception:
        return False

    return True


def arm_stage_heartbeat(
    task_id: str,
    stage: str,
    agent_id: str,
    role_title: str,
    workspace_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Atomically writes .agents/artifacts/ladder_heartbeat.json to track stage lifecycle.

    Args:
        task_id: Unique task / phase identifier.
        stage: Ladder stage key (one of VALID_STAGES).
        agent_id: Active subagent identifier (e.g. conversation_id or agent archetype).
        role_title: Descriptive role title (e.g. 'Stage 1: Executioner (agyis_builder)').
        workspace_dir: Optional workspace root path (defaults to Path.cwd()).

    Returns:
        Path to the materialized ladder_heartbeat.json file.

    Raises:
        ValueError: If stage, task_id, agent_id, or role_title are invalid.
    """
    if not isinstance(stage, str) or stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage '{stage}'. Must be one of {sorted(VALID_STAGES)}")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agent_id must be a non-empty string")
    if not isinstance(role_title, str) or not role_title.strip():
        raise ValueError("role_title must be a non-empty string")

    ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
    target_file = ws / LADDER_HEARTBEAT_PATH
    target_dir = target_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "event": HEARTBEAT_EVENT,
        "protocol_version": HEARTBEAT_PROTOCOL_VERSION,
        "task_id": task_id.strip(),
        "stage": stage.strip(),
        "active_agent_id": agent_id.strip(),
        "subagent_role": role_title.strip(),
        "step_count": 0,
        "elapsed_s": 0.0,
        "status": "dispatched",
        "last_action": f"Armed stage {stage.strip()}",
        "timestamp": now.isoformat(),
        "started_at": now.isoformat(),
    }

    tmp_file = target_dir / f".ladder_heartbeat.json.tmp.{os.getpid()}"
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


def pulse_stage_heartbeat(
    step_count: int,
    last_action: str,
    status: str = "in_progress",
    workspace_dir: Optional[Union[str, Path]] = None,
) -> bool:
    """
    Updates the active stage heartbeat with step count, last action, status, and elapsed time.

    Args:
        step_count: Current cumulative step count in the active stage.
        last_action: Description of the latest tool call or action.
        status: Current stage status (one of VALID_STATUSES, defaults to 'in_progress').
        workspace_dir: Optional workspace root path (defaults to Path.cwd()).

    Returns:
        True if heartbeat was successfully updated, False otherwise.
    """
    try:
        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        target_file = ws / LADDER_HEARTBEAT_PATH
        if not target_file.is_file():
            return False

        content = target_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return False

        data = json.loads(content)
        if not validate_heartbeat_schema(data):
            return False

        if status not in VALID_STATUSES:
            return False

        if isinstance(step_count, bool) or not isinstance(step_count, int) or step_count < 0:
            return False

        now = datetime.now(timezone.utc)
        started_at_str = data.get("started_at")
        if started_at_str:
            try:
                started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed = round(max(0.0, (now - started_at).total_seconds()), 2)
            except Exception:
                elapsed = round(float(data.get("elapsed_s", 0.0)), 2)
        else:
            elapsed = round(float(data.get("elapsed_s", 0.0)), 2)

        data["step_count"] = step_count
        data["last_action"] = str(last_action).strip()
        data["status"] = status
        data["elapsed_s"] = elapsed
        data["timestamp"] = now.isoformat()

        target_dir = target_file.parent
        tmp_file = target_dir / f".ladder_heartbeat.json.tmp.{os.getpid()}"
        tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_file.replace(target_file)
        return True
    except Exception:
        return False


def disarm_stage_heartbeat(
    status: str = "complete",
    workspace_dir: Optional[Union[str, Path]] = None,
) -> bool:
    """
    Marks the active stage heartbeat as complete (or given terminal status) and updates timestamp.

    Args:
        status: Terminal status (defaults to 'complete', one of VALID_STATUSES).
        workspace_dir: Optional workspace root path (defaults to Path.cwd()).

    Returns:
        True if heartbeat was successfully updated, False otherwise.
    """
    try:
        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        target_file = ws / LADDER_HEARTBEAT_PATH
        if not target_file.is_file():
            return False

        content = target_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return False

        data = json.loads(content)
        if not validate_heartbeat_schema(data):
            return False

        if status not in VALID_STATUSES:
            return False

        now = datetime.now(timezone.utc)
        started_at_str = data.get("started_at")
        if started_at_str:
            try:
                started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed = round(max(0.0, (now - started_at).total_seconds()), 2)
            except Exception:
                elapsed = round(float(data.get("elapsed_s", 0.0)), 2)
        else:
            elapsed = round(float(data.get("elapsed_s", 0.0)), 2)

        data["status"] = status
        data["elapsed_s"] = elapsed
        data["last_action"] = f"Disarmed stage with status: {status}"
        data["timestamp"] = now.isoformat()

        target_dir = target_file.parent
        tmp_file = target_dir / f".ladder_heartbeat.json.tmp.{os.getpid()}"
        tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_file.replace(target_file)
        return True
    except Exception:
        return False


def read_stage_heartbeat(
    workspace_dir: Optional[Union[str, Path]] = None,
    stale_timeout_s: float = 300.0,
) -> Optional[Dict[str, Any]]:
    """
    Reads and validates .agents/artifacts/ladder_heartbeat.json.
    Detects staleness when time since last pulse exceeds stale_timeout_s.

    Args:
        workspace_dir: Optional workspace root path (defaults to Path.cwd()).
        stale_timeout_s: Maximum duration in seconds before heartbeat is considered stale (default: 300s).

    Returns:
        Parsed heartbeat dictionary with 'is_stale' and 'heartbeat_age_s' annotations,
        or None if file does not exist or schema is invalid.
    """
    try:
        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        target_file = ws / LADDER_HEARTBEAT_PATH
        if not target_file.is_file():
            return None

        size = target_file.stat().st_size
        if size == 0 or size > 65_536:
            return None

        content = target_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return None

        data = json.loads(content)
        if not validate_heartbeat_schema(data):
            return None

        ts_str = data.get("timestamp")
        delta_s = 0.0
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta_s = max(0.0, (now - ts).total_seconds())
        except Exception:
            delta_s = 0.0

        data["heartbeat_age_s"] = delta_s
        if delta_s > stale_timeout_s:
            data["is_stale"] = True
            if data.get("status") not in {"complete", "failed", "halted"}:
                data["status"] = "stale"
        else:
            data["is_stale"] = False

        return data
    except Exception:
        return None


def clear_stage_heartbeat(
    workspace_dir: Optional[Union[str, Path]] = None,
) -> bool:
    """
    Safely unlinks .agents/artifacts/ladder_heartbeat.json.

    Returns:
        True if the file was deleted, False if it did not exist or could not be removed.
    """
    try:
        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd().resolve()
        target_file = ws / LADDER_HEARTBEAT_PATH
        if target_file.is_file() or target_file.is_symlink():
            target_file.unlink()
            return True
        return False
    except OSError:
        return False
