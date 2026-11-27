# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: Sticky Role Classification, State Isolation & Prompt Builders (#110, #111).

Consumes `harness.trajectory` SSOT metrics and transcripts rather than re-parsing SQLite
or protobufs, pins roles per `(conversation_id, checkpoint_index)` at Turn 0 / compaction,
eliminates mid-flight Pillar 2 auto-flipping, and isolates per-CID state files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.hooks.role_prompts import (
    ROLE_PERSONA_PROMPTS,
    build_compaction_advisory,
    build_post_compaction_persona_prompt,
    build_role_persona_prompt,
    build_role_reanchor_advisory,
)
from harness.trajectory import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    ROLE_DEEP_EXECUTION,
    ROLE_FLIGHT_DIRECTOR,
    ROLE_FORENSIC_AUDITOR,
    ROLE_SWARM_ORCHESTRATOR,
    TrajectoryMetrics,
    extract_role_from_text,
    find_transcript_path,
    load_transcript_steps,
    normalize_cid,
    normalize_role_str,
    read_conversation_lineage,
    read_db_trajectory_state,
)
from harness.trajectory.sqlite_step_parser import _is_sdk_injection_text
from harness.utils.context import (
    get_active_brain_dir,
    get_active_conversation_id,
    is_in_live_home_gemini,
    is_in_temp_dir,
)

_ORIG_GET_ACTIVE_BRAIN_DIR = get_active_brain_dir

DEFAULT_ROLE_PINNING_CADENCE: int = 10
_UUID_EXTRACT_RE = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")
_EPHEMERAL_CIDS = frozenset({"", "default", "test", "conv_test"})
_CANONICAL_ROLE_BUCKETS = frozenset({
    ROLE_FLIGHT_DIRECTOR,
    ROLE_SWARM_ORCHESTRATOR,
    ROLE_DEEP_EXECUTION,
    ROLE_FORENSIC_AUDITOR,
})

NATIVE_SYSTEM_SLASH_COMMANDS: frozenset[str] = frozenset({
    "compact", "clear", "reset", "goal", "plan", "boost",
    "teamwork", "teamwork-preview", "grill-me", "browser",
    "schedule", "learn", "automation", "plugin",
    "context", "model", "usage", "quota", "thinking",
    "config", "skills", "swarm", "btw",
})

ORCHESTRATOR_KEYWORDS: Tuple[str, ...] = (
    "/cockpit-director", "/subagent-router", "/subagent-ladder",
    "/teamwork-preview", "/teamwork", "/plan", "/grill-me",
    "/boost", "/goal", "orchestrate", "coordinate swarm",
)

REVIEWER_AUDITOR_KEYWORDS: Tuple[str, ...] = (
    "code review", "hammer review", "read-only", "strictly read-only",
    "root cause analysis", "rca", "qa audit", "defects ledger",
    "audit report", "victory auditor",
)

CODING_KEYWORDS: Tuple[str, ...] = (
    "fix", "bug", "bugfix", "issue", "error", "repair", "patch",
    "implement", "refactor", "test", "tests", "unit test",
    "write code", "feature", "compile", "build", "coding",
    "debug", "modify", "update", "/fix", "/test", "/code",
)

TEST_RUNNER_KEYWORDS: Tuple[str, ...] = (
    "pytest", "unittest", "-m unittest", "cargo test", "go test",
    "npm test", "pnpm test", "yarn test", "jest", "vitest",
    "harness.cli test", "agyis test", "./agyis test",
    "python3 -m unittest", "python -m unittest",
)


def get_role_pinning_cadence(override: Optional[int] = None) -> int:
    """Returns effective cadence for intra-checkpoint periodic role re-anchors (default 10)."""
    for candidate in (override, os.environ.get("AGYIS_ROLE_PINNING_CADENCE")):
        if candidate is not None:
            try:
                val = int(str(candidate).strip())
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
    return DEFAULT_ROLE_PINNING_CADENCE


def is_native_slash_command(text: str) -> bool:
    """Checks if user input begins with an Antigravity native system slash command."""
    if not text or not isinstance(text, str):
        return False
    cleaned = re.sub(r"</?USER_REQUEST>", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    if not cleaned.startswith("/"):
        return False
    m = re.match(r"^/([a-zA-Z0-9_-]+)(?:\s|$)", cleaned)
    return bool(m and m.group(1).lower() in NATIVE_SYSTEM_SLASH_COMMANDS)


def resolve_conv_and_brain(payload: Dict[str, Any], conversation_id: str = "") -> Tuple[str, Optional[Path]]:
    """Extracts normalized conversation_id and artifact brain directory from payload or env."""
    cid = normalize_cid(conversation_id or str(payload.get("conversationId") or payload.get("conversation_id") or ""))
    brain_path: Optional[Path] = None
    for k in ("artifactDirectoryPath", "artifact_directory_path", "artifactDirectory", "artifact_dir", "transcriptPath", "transcript_path"):
        val = payload.get(k)
        if isinstance(val, str) and val.strip():
            expanded = Path(os.path.expanduser(val.strip()))
            if "artifact" in k.lower() and brain_path is None:
                brain_path = expanded
            if not cid or cid == "default":
                if m := _UUID_EXTRACT_RE.search(val):
                    cid = normalize_cid(m.group(1).lower())
    explicit_null_cid = (
        ("conversationId" in payload and payload["conversationId"] is None and not payload.get("conversation_id"))
        or ("conversation_id" in payload and payload["conversation_id"] is None and not payload.get("conversationId"))
    )
    if (not cid or cid == "default") and not explicit_null_cid and (active_cid := get_active_conversation_id()):
        agyis_cid = (os.environ.get("AGYIS_CONVERSATION_ID") or "").strip()
        gemini_cid = (os.environ.get("GEMINI_CONVERSATION_ID") or "").strip()
        ambient_run_cmd = False
        if meta_raw := (os.environ.get("ANTIGRAVITY_SOURCE_METADATA") or "").strip():
            try:
                meta_obj = json.loads(meta_raw)
                tool_dict = meta_obj.get("tool") if isinstance(meta_obj, dict) else None
                tc = tool_dict.get("toolCall") if isinstance(tool_dict, dict) else None
                meta_cid = (
                    str(tool_dict.get("conversationId") or tool_dict.get("conversation_id") or "").strip()
                    if isinstance(tool_dict, dict)
                    else ""
                )
                ambient_run_cmd = (
                    isinstance(tc, dict)
                    and tc.get("name") == "run_command"
                    and (not meta_cid or meta_cid == active_cid)
                )
            except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
                pass
        if not ambient_run_cmd:
            cid = normalize_cid(active_cid)
        elif agyis_cid or gemini_cid:
            cid = normalize_cid(agyis_cid or gemini_cid)
    return cid or "default", brain_path


def _resolve_isolated_brain_root(
    workspace_dir: Optional[Path] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Path], str]:
    """Resolves brain root while ignoring host ~/.gemini ambient env under temp isolation."""
    state_root = (os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR") or "").strip()
    state_is_temp = is_in_temp_dir(Path(os.path.expanduser(state_root))) if state_root else False
    cwd_is_temp = is_in_temp_dir(Path.cwd())
    ws_is_temp = is_in_temp_dir(workspace_dir) if workspace_dir is not None else False
    payload_paths = _collect_search_paths(payload, None, include_cwd=False) if payload else []
    payload_is_temp = any(is_in_temp_dir(p) for p in payload_paths)
    isolated = state_is_temp or cwd_is_temp or ws_is_temp or payload_is_temp

    agyis_brain = (os.environ.get("AGYIS_BRAIN_DIR") or "").strip()
    if agyis_brain:
        return Path(os.path.expanduser(agyis_brain)), state_root
    agyis_app = (os.environ.get("AGYIS_APP_DATA_DIR") or "").strip()
    if agyis_app:
        return Path(os.path.expanduser(agyis_app)) / "brain", state_root

    if get_active_brain_dir is not _ORIG_GET_ACTIVE_BRAIN_DIR:
        return get_active_brain_dir(), state_root

    ag_brain = (os.environ.get("ANTIGRAVITY_BRAIN_DIR") or "").strip()
    if ag_brain:
        p = Path(os.path.expanduser(ag_brain))
        if not (isolated and is_in_live_home_gemini(p)):
            return p, state_root

    ag_app = (os.environ.get("ANTIGRAVITY_APP_DATA_DIR") or "").strip()
    if ag_app:
        p = Path(os.path.expanduser(ag_app))
        if not (isolated and is_in_live_home_gemini(p)):
            return p / "brain", state_root

    if (os.environ.get("GEMINI_BRAIN_DIR") or "").strip() or not isolated:
        return get_active_brain_dir(), state_root
    return None, state_root


def resolve_cid_state_dir(
    conv_id: str,
    workspace_dir: Optional[Path] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Resolves isolated per-conversation state directory (never shared global workspace or CWD)."""
    norm_cid = normalize_cid(conv_id)
    if norm_cid in _EPHEMERAL_CIDS:
        return None
    if payload:
        _, art_dir = resolve_conv_and_brain(payload, norm_cid)
        if art_dir is not None and art_dir.name == norm_cid:
            return art_dir / ".agyis"
    brain_root, state_root = _resolve_isolated_brain_root(workspace_dir=workspace_dir, payload=payload)
    if brain_root is not None and (session_brain := brain_root / norm_cid).is_dir():
        return session_brain / ".agyis"
    if workspace_dir is not None:
        return workspace_dir / ".agents" / "artifacts" / "checkpoints" / norm_cid
    return (Path(os.path.expanduser(state_root)) / "checkpoints" / norm_cid) if state_root else None


def load_sticky_role_state(state_dir: Optional[Path], conv_id: str) -> Optional[Dict[str, Any]]:
    """Loads persisted sticky role state for a specific conversation ID."""
    if not state_dir:
        return None
    path = state_dir / f"role_state_{normalize_cid(conv_id)}.json"
    try:
        if path.is_file() and 0 < path.stat().st_size <= 65_536:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(data, dict) and data.get("conversation_id") == normalize_cid(conv_id):
                return data
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        sys.stderr.write(f"[AGYIS ROLE PINNING] Failed loading sticky role state '{path}': {exc}\n")
    return None


def save_sticky_role_state(state_dir: Optional[Path], state: Dict[str, Any]) -> None:
    """Atomically persists per-conversation sticky role state."""
    if not state_dir or not state.get("conversation_id"):
        return
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        cid = normalize_cid(str(state["conversation_id"]))
        target = state_dir / f"role_state_{cid}.json"
        tmp = state_dir / f".role_state_{cid}.tmp.{os.getpid()}"
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        pass


def has_parent_conversation(
    payload: Union[Dict[str, Any], str],
    conv_id: Union[str, Dict[str, Any]] = "",
    *,
    brain_dir: Optional[Path] = None,
    db_dir: Optional[Path] = None,
) -> bool:
    """Returns True when the active conversation is a spawned child subagent."""
    if isinstance(payload, str):
        eff_conv_id = payload
        eff_payload: Dict[str, Any] = conv_id if isinstance(conv_id, dict) else {}
    else:
        eff_payload = payload if isinstance(payload, dict) else {}
        eff_conv_id = conv_id if isinstance(conv_id, str) else ""

    for k in ("parentConversationId", "parent_conversation_id", "parentId", "parent_id",
              "subagentRole", "subagent_role", "subagentType", "subagent_type"):
        if isinstance(eff_payload.get(k), str) and eff_payload[k].strip():
            return True
    for pk in ("agent", "subagent", "metadata"):
        pd = eff_payload.get(pk)
        if isinstance(pd, dict):
            for k in ("parentConversationId", "parent_conversation_id", "subagentRole", "subagent_role", "subagentType"):
                if isinstance(pd.get(k), str) and pd[k].strip():
                    return True
    norm_cid = normalize_cid(eff_conv_id)
    if norm_cid in _EPHEMERAL_CIDS:
        return False

    eff_brain_dir = brain_dir
    if eff_brain_dir is None:
        _, art_brain = resolve_conv_and_brain(eff_payload, norm_cid)
        if art_brain is not None and art_brain.name == norm_cid:
            eff_brain_dir = art_brain.parent
        elif get_active_brain_dir is not _ORIG_GET_ACTIVE_BRAIN_DIR:
            eff_brain_dir = get_active_brain_dir()

    parent_cid, _, depth = read_conversation_lineage(norm_cid, brain_dir=eff_brain_dir, db_dir=db_dir)
    return bool(parent_cid or depth > 0)


def _collect_search_paths(
    payload: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
    *,
    include_cwd: bool = True,
) -> List[Path]:
    paths: List[Path] = []

    def _add(val: Any) -> None:
        s = val if isinstance(val, str) else (val.get("path") if isinstance(val, dict) else None)
        if isinstance(s, str) and s.strip() and (p := Path(os.path.expanduser(s.strip()))) not in paths:
            paths.append(p)

    if workspace_dir:
        _add(str(workspace_dir))
    for k in ("workspace", "worktree", "cwd", "workspacePath", "workspaceDir", "worktreePath", "path",
              "artifactDirectoryPath", "artifact_directory_path", "artifactDirectory", "artifact_dir"):
        _add(payload.get(k))
    for k in ("activeWorkspaces", "workspacePaths", "active_workspaces", "workspace_paths"):
        if isinstance((lst := payload.get(k)), (list, tuple)):
            for item in lst:
                _add(item)
    if include_cwd and Path.cwd() not in paths:
        paths.append(Path.cwd())
    return paths


def _read_role_json_file(cand: Path, expected_cid: str = "") -> Optional[str]:
    try:
        if cand.is_file() and 0 < cand.stat().st_size <= 65_536:
            data = json.loads(cand.read_text(encoding="utf-8", errors="ignore").strip() or "{}")
            if isinstance(data, dict):
                file_cid = str(data.get("conversation_id") or "").strip()
                if expected_cid and expected_cid != "default" and file_cid and file_cid != expected_cid:
                    return None
                for rk in ("role", "agent_role", "session_role", "archetype"):
                    if matched := normalize_role_str(data.get(rk)):
                        return matched
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        sys.stderr.write(f"[AGYIS ROLE PINNING] Failed reading role JSON '{cand}': {exc}\n")
    return None


def check_pillar_3_explicit_role(
    payload: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
    conversation_id: str = "",
    *,
    is_child: Optional[bool] = None,
) -> Optional[str]:
    """Pillar 3: Checks CID-scoped/workspace session_role.json, active plan, and role env vars."""
    search_dirs = _collect_search_paths(payload, workspace_dir)
    eff_cid, art_brain_dir = resolve_conv_and_brain(payload, conversation_id)
    if is_child is None:
        is_child = has_parent_conversation(payload, eff_cid)

    folders: List[str] = [eff_cid] if (eff_cid and eff_cid != "default") else (
        [] if is_child else ([env_cid] if (env_cid := get_active_conversation_id()) else []) + ["session"]
    )
    expected_role_cid = eff_cid if (eff_cid and eff_cid != "default") else (folders[0] if folders else "")
    for root in search_dirs:
        cands: List[Path] = [root / ".agents" / "artifacts" / "checkpoints" / f / "session_role.json" for f in folders]
        if not is_child:
            cands.extend([
                root / ".agents" / "session_role.json", root / ".agents" / "artifacts" / "session_role.json",
                root / "session_role.json", root / ".agents" / "artifacts" / "plan.json",
                root / ".agents" / "plan.json", root / "plan.json",
            ])
        for cand in cands:
            if matched := _read_role_json_file(cand, expected_cid=expected_role_cid):
                return matched

    if eff_cid and eff_cid != "default":
        brain_base, _ = _resolve_isolated_brain_root(workspace_dir=workspace_dir, payload=payload)
        if brain_base is not None:
            for b_cand in (brain_base / eff_cid / ".agyis" / "session_role.json", brain_base / eff_cid / "session_role.json"):
                if matched := _read_role_json_file(b_cand):
                    return matched

    try:
        from harness.utils.plan_parser import find_active_plan
        plan_ws = None if is_child else (workspace_dir or (search_dirs[0] if search_dirs else None))
        if not is_child or eff_cid != "default" or art_brain_dir is not None:
            plan_path = find_active_plan(conv_id=eff_cid if eff_cid != "default" else None, workspace_root=plan_ws, brain_dir=art_brain_dir)
            if is_child and plan_path is not None and not (eff_cid != "default" and eff_cid in str(plan_path)) and not (art_brain_dir is not None and art_brain_dir in plan_path.parents):
                plan_path = None
            if plan_path and plan_path.is_file() and 0 < plan_path.stat().st_size <= 65_536:
                if plan_path.suffix == ".json":
                    if matched := _read_role_json_file(plan_path):
                        return matched
                else:
                    txt = plan_path.read_text(encoding="utf-8", errors="ignore")[:8192]
                    for pat in (r"(?:^|\n)\s*(?:\*\*)?[Rr]ole(?:\*\*)?:\s*([a-zA-Z0-9_\-]+)", r"<!--\s*role:\s*([a-zA-Z0-9_\-]+)\s*-->"):
                        if m := re.search(pat, txt, re.IGNORECASE):
                            if matched := normalize_role_str(m.group(1).strip()):
                                return matched
    except Exception as exc:
        sys.stderr.write(f"[AGYIS ROLE PINNING] Failed inspecting active plan role: {exc}\n")

    env_role = os.environ.get("AGYIS_ROLE") or os.environ.get("PSL_AGENT_ROLE") or os.environ.get("ANTIGRAVITY_AGENT_ROLE")
    return normalize_role_str(env_role) if env_role else None


def check_pillar_1_intent(
    payload: Dict[str, Any],
    conversation_id: str = "",
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
    db_metrics: Optional[TrajectoryMetrics] = None,
) -> Optional[str]:
    """Pillar 1: Early-turn intent classification using prompt + SSOT Turn-0 SQLite/transcript."""
    snippets: List[str] = []
    for k in ("lastUserInput", "last_user_input", "prompt", "user_prompt", "userPrompt", "message", "query", "input", "initial_prompt", "task"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip() and not _is_sdk_injection_text(v):
            snippets.append(v.strip())
    steps = payload.get("steps")
    if isinstance(steps, list):
        for s in steps[:5]:
            if isinstance(s, dict):
                if str(s.get("source") or "").strip().upper() == "SYSTEM_SDK":
                    continue
                for sk in ("lastUserInput", "prompt", "user_input", "userPrompt", "message", "text", "query", "input", "step_data"):
                    sv = s.get(sk)
                    if isinstance(sv, str) and sv.strip() and not _is_sdk_injection_text(sv):
                        snippets.append(sv.strip())
            elif isinstance(s, str) and s.strip() and not _is_sdk_injection_text(s):
                snippets.append(s.strip())

    eff_cid, art_brain = resolve_conv_and_brain(payload, conversation_id)
    metrics = db_metrics
    if metrics is None and eff_cid and eff_cid != "default":
        metrics = read_db_trajectory_state(eff_cid, db_dir=db_dir, timeout=timeout)
    if metrics is not None:
        if metrics.turn0_prompt and not _is_sdk_injection_text(metrics.turn0_prompt):
            snippets.append(metrics.turn0_prompt)
        if metrics.latest_user_prompt and not snippets and not _is_sdk_injection_text(metrics.latest_user_prompt):
            snippets.append(metrics.latest_user_prompt)

    if not snippets and eff_cid and eff_cid != "default":
        b_dir = (
            art_brain.parent if (art_brain is not None and art_brain.name == eff_cid)
            else (get_active_brain_dir() if get_active_brain_dir is not _ORIG_GET_ACTIVE_BRAIN_DIR else None)
        )
        t_path, _ = find_transcript_path(eff_cid, brain_dir=b_dir)
        if t_path is not None:
            t_steps, _, _ = load_transcript_steps(t_path)
            for ts in t_steps[:5]:
                if not isinstance(ts, dict) or str(ts.get("source") or "").strip().upper() == "SYSTEM_SDK":
                    continue
                content = ts.get("content") or ts.get("userInput") or ""
                if isinstance(content, str) and content.strip():
                    if _is_sdk_injection_text(content) or "PreInvocation hook" in content:
                        continue
                    snippets.append(content.strip())
                    role_hint = extract_role_from_text(content)
                    if role_hint:
                        matched = normalize_role_str(role_hint)
                        if matched:
                            return matched

    if not snippets:
        return None
    combined = " ".join(snippets).lower()
    if any(kw in combined for kw in ORCHESTRATOR_KEYWORDS):
        return ROLE_FLIGHT_DIRECTOR
    if any(kw in combined for kw in REVIEWER_AUDITOR_KEYWORDS):
        return ROLE_FORENSIC_AUDITOR
    if any(kw in combined for kw in CODING_KEYWORDS):
        return ROLE_DEEP_EXECUTION
    return None


def _collect_tool_pairs(
    payload: Dict[str, Any],
    eff_cid: str,
    db_dir: Optional[Path],
    timeout: Optional[float],
    db_metrics: Optional[TrajectoryMetrics],
) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    if db_metrics is not None and db_metrics.recent_tools:
        pairs.extend(db_metrics.recent_tools)
    elif eff_cid and eff_cid != "default":
        m = read_db_trajectory_state(eff_cid, db_dir=db_dir, timeout=timeout)
        if m.recent_tools:
            pairs.extend(m.recent_tools)
    for item in (payload.get("tool_calls") or payload.get("tools") or []):
        if isinstance(item, str) and item.strip():
            pairs.append((item, ""))
        elif isinstance(item, dict):
            tn = item.get("tool_name") or item.get("tool") or item.get("name") or ""
            args = item.get("arguments") or item.get("command") or item.get("args") or ""
            if tn:
                pairs.append((str(tn), str(args)))
    return pairs


def check_pillar_2_behavior(
    payload: Dict[str, Any],
    conversation_id: str = "",
    tokens: int = 0,
    db_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
    db_metrics: Optional[TrajectoryMetrics] = None,
) -> Optional[str]:
    """
    Behavioral diagnostic (stateless fallback & drift check only; never overrides pinned Turn-0 role,
    and never promotes child subagents or `send_message` calls into root orchestrators).
    """
    try:
        payload_tok = next(
            (int(v) for k in ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens")
             if isinstance((v := payload.get(k)), (int, float)) and int(v) > 0),
            0,
        )
        eff_cid, art_brain = resolve_conv_and_brain(payload, conversation_id)
        m = db_metrics or (read_db_trajectory_state(eff_cid, db_dir=db_dir, timeout=timeout) if eff_cid and eff_cid != "default" else None)
        cur_tokens = max(tokens, payload_tok, m.tokens if m else 0)
        step_val = payload.get("step_count") or payload.get("stepCount") or payload.get("initialNumSteps") or 0
        total_steps = max(int(step_val) if isinstance(step_val, (int, float)) else 0, m.total_steps if m else 0)
        raw_win = payload.get("maxContextTokens") or payload.get("max_context_tokens")
        eff_win = int(raw_win) if isinstance(raw_win, (int, float)) and int(raw_win) > 0 else (
            m.max_context_tokens if m and m.max_context_tokens > 0 else DEFAULT_CONTEXT_WINDOW_TOKENS
        )
        if cur_tokens < int(round(eff_win * 200_000 / DEFAULT_CONTEXT_WINDOW_TOKENS)) and total_steps < 100 and not payload.get("force_pillar_2"):
            return None
        pairs = _collect_tool_pairs(payload, eff_cid, db_dir, timeout, m)
        if not pairs:
            return None

        eff_brain_dir = art_brain.parent if (art_brain is not None and art_brain.name == eff_cid) else None
        is_child = has_parent_conversation(payload, eff_cid, brain_dir=eff_brain_dir, db_dir=db_dir)
        subagent_spawns = edit_test = explicit_audit = read_grep = 0
        is_swarm = False
        edit_tools = ("edit_file", "write_file", "create_file", "insert_edit_into_file", "replace_file_content", "multi_replace_file_content", "write_to_file", "apply_diff")
        for tool_name, args in pairs:
            tn, al = tool_name.lower().strip(), args.lower()
            if not is_child and (tn in ("invoke_subagent", "manage_task", "schedule", "swarm", "run_workflow") or "subagent" in tn):
                subagent_spawns += 1
                if any(k in al or k in tn for k in ("swarm", "mesh", "strand")):
                    is_swarm = True
            elif tn in edit_tools:
                edit_test += 1
            elif tn in ("run_command", "bash", "terminal", "exec_command", "shell"):
                if any(kw in al for kw in TEST_RUNNER_KEYWORDS):
                    edit_test += 1
                elif any(kw in al for kw in ("audit", "verify", "doctor", "inspect")):
                    explicit_audit += 1
            elif any(kw in tn for kw in ("pytest", "unittest", "test_runner")):
                edit_test += 1
            elif any(k in tn for k in ("audit", "verify", "doctor", "inspect")):
                explicit_audit += 1
            elif tn in ("read_file", "view_file", "read_url_content", "read_browser_page", "grep_search", "find_by_name", "file_search"):
                read_grep += 1

        if subagent_spawns > 0:
            return ROLE_SWARM_ORCHESTRATOR if is_swarm else ROLE_FLIGHT_DIRECTOR
        if explicit_audit >= 3 and explicit_audit > edit_test:
            return ROLE_FORENSIC_AUDITOR
        if edit_test > 0:
            return ROLE_DEEP_EXECUTION
        if explicit_audit > 0 or read_grep > 0:
            return ROLE_FORENSIC_AUDITOR
    except Exception as exc:
        sys.stderr.write(f"[AGYIS ROLE PINNING] Pillar 2 behavior check error: {exc}\n")
    return None


def classify_agent_role_details(
    payload: Dict[str, Any],
    conversation_id: str = "",
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    tokens: int = 0,
    timeout: Optional[float] = None,
    db_metrics: Optional[TrajectoryMetrics] = None,
    is_post_compaction: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """Classifies role and returns (canonical_role, lineage_metadata) across priority tiers."""
    parent_cid: Optional[str] = None
    native_agent_name: Optional[str] = None
    explicit_keys = (
        "agentName", "agent_name", "subagentType", "subagent_role", "subagentRole",
        "typeName", "agentType", "agent_type", "archetype", "role",
    )
    try:
        holders = [payload, *(pd for pk in ("agent", "subagent", "metadata", "context") if isinstance((pd := payload.get(pk)), dict))]
        for holder in holders:
            for key in explicit_keys:
                raw_v = holder.get(key)
                if isinstance(raw_v, str) and (matched := normalize_role_str(raw_v)):
                    ag = raw_v.strip() if raw_v.strip().lower() not in _CANONICAL_ROLE_BUCKETS else None
                    pid = holder.get("parentConversationId") or holder.get("parent_conversation_id")
                    return matched, {"agent_name": ag, "parent_conversation_id": pid, "source": "explicit", "is_fallback": False}

        eff_cid, art_brain_dir = resolve_conv_and_brain(payload, conversation_id)
        eff_brain_dir = (
            art_brain_dir.parent if (art_brain_dir is not None and art_brain_dir.name == eff_cid)
            else (get_active_brain_dir() if get_active_brain_dir is not _ORIG_GET_ACTIVE_BRAIN_DIR else None)
        )
        parent_cid, native_agent_name, depth = read_conversation_lineage(
            eff_cid, brain_dir=eff_brain_dir, db_dir=db_dir, timeout=timeout or 0.5,
        )
        is_child = bool(parent_cid or depth > 0 or has_parent_conversation(payload, eff_cid, brain_dir=eff_brain_dir, db_dir=db_dir))

        p3 = check_pillar_3_explicit_role(payload, workspace_dir=workspace_dir, conversation_id=eff_cid, is_child=is_child)
        if p3:
            return p3, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "pillar_3", "is_fallback": False}

        if native_agent_name and (native_role := normalize_role_str(native_agent_name)):
            return native_role, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "lineage", "is_fallback": False}

        if not is_post_compaction and eff_cid not in _EPHEMERAL_CIDS:
            sticky = load_sticky_role_state(resolve_cid_state_dir(eff_cid, workspace_dir, payload), eff_cid)
            cp_idx = db_metrics.checkpoint_index if db_metrics is not None else 0
            if sticky and int(sticky.get("checkpoint", sticky.get("epoch", 0))) == cp_idx:
                pinned = normalize_role_str(sticky.get("role"))
                sticky_agent = sticky.get("agent_name")
                sticky_agent_role = normalize_role_str(sticky_agent) if isinstance(sticky_agent, str) else None
                invalidated = bool(
                    (is_child and pinned == ROLE_FLIGHT_DIRECTOR and sticky_agent_role != ROLE_FLIGHT_DIRECTOR)
                    or (sticky_agent_role is not None and pinned != sticky_agent_role)
                    or sticky.get("is_fallback")
                )
                if pinned and not invalidated:
                    return pinned, {"agent_name": sticky_agent or native_agent_name, "parent_conversation_id": parent_cid or sticky.get("parent_conversation_id"), "source": "sticky", "is_fallback": False}

        if p1 := check_pillar_1_intent(payload, conversation_id=eff_cid, db_dir=db_dir, timeout=timeout, db_metrics=db_metrics):
            return p1, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "pillar_1", "is_fallback": False}

        if p2 := check_pillar_2_behavior(payload, conversation_id=eff_cid, tokens=tokens, db_dir=db_dir, timeout=timeout, db_metrics=db_metrics):
            return p2, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "pillar_2", "is_fallback": False}

        for root in _collect_search_paths(payload, workspace_dir, include_cwd=False):  # Exclude generic Path.cwd() tail
            if (matched := normalize_role_str(str(root))) and not (is_child and matched == ROLE_FLIGHT_DIRECTOR):
                return matched, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "workspace", "is_fallback": False}

        if is_child:
            return ROLE_DEEP_EXECUTION, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "child_fallback", "is_fallback": True}
    except Exception as exc:
        sys.stderr.write(f"[AGYIS ROLE PINNING] Role classification fallback error: {exc}\n")
    return ROLE_FLIGHT_DIRECTOR, {"agent_name": native_agent_name, "parent_conversation_id": parent_cid, "source": "root_fallback", "is_fallback": True}


def classify_agent_role(
    payload: Dict[str, Any],
    conversation_id: str = "",
    db_dir: Optional[Path] = None,
    workspace_dir: Optional[Path] = None,
    tokens: int = 0,
    timeout: Optional[float] = None,
    db_metrics: Optional[TrajectoryMetrics] = None,
    is_post_compaction: bool = False,
) -> str:
    """Sticky role classification across explicit metadata, Pillar 3, native lineage, sticky pin, and behavior."""
    role, _ = classify_agent_role_details(
        payload, conversation_id=conversation_id, db_dir=db_dir, workspace_dir=workspace_dir,
        tokens=tokens, timeout=timeout, db_metrics=db_metrics, is_post_compaction=is_post_compaction,
    )
    return role
