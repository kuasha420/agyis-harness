# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: Sticky Role Classification, State Isolation & Prompt Builders (#110, #111).

Consumes `harness.trajectory` SSOT metrics and transcripts rather than re-parsing SQLite
or protobufs, pins roles per `(conversation_id, epoch_index)` at Turn 0 / compaction,
eliminates mid-flight Pillar 2 auto-flipping, and isolates per-CID state files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from harness.trajectory import (
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
    read_db_trajectory_state,
)
from harness.utils.context import get_active_conversation_id

DEFAULT_ROLE_PINNING_CADENCE: int = 10
_UUID_EXTRACT_RE = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")
_EPHEMERAL_CIDS = frozenset({"", "default", "test", "conv_test"})

NATIVE_SYSTEM_SLASH_COMMANDS: frozenset[str] = frozenset({
    "compact", "clear", "reset", "goal", "plan", "boost",
    "teamwork", "teamwork-preview", "grill-me", "browser",
    "schedule", "learn", "automation", "plugin",
})

ORCHESTRATOR_KEYWORDS: Tuple[str, ...] = (
    "/cockpit-director", "/subagent-router", "/subagent-ladder",
    "/teamwork-preview", "/teamwork", "/plan", "/grill-me",
    "/boost", "/goal", "orchestrate", "coordinate swarm",
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

ROLE_PERSONA_PROMPTS: Dict[str, str] = {
    ROLE_FLIGHT_DIRECTOR: (
        "[AGYIS ROLE PINNING: FLIGHT DIRECTOR / COORDINATOR]\n"
        "You are operating as the Flight Director / Swarm Coordinator (Stage 0: COORDINATION).\n\n"
        "CORE OPERATIONAL INVARIANTS:\n"
        "1. ANTI-CHATBOT SEDUCTION & COGNITIVE STATE FLUSH:\n"
        "   - Never execute multi-component refactorings in raw conversational chat turns.\n"
        "   - Immediately crystallize execution plans into interactive implementation plans in your session brain/artifacts.\n"
        "   - Flush working memory, task rosters, and steering decisions to per-session checkpoints; zero repo pollution.\n"
        "2. ZERO COORDINATOR REMEDIATION:\n"
        "   - You are strictly forbidden from modifying product code, patching files directly, or self-resolving review defects.\n"
        "   - Route all implementation and remediation tasks to specialist subagents (agyis_builder).\n"
        "3. WORK PRESERVATION CONTRACT:\n"
        "   - Preserve all local worktree changes. Strictly prohibit 'git checkout -- .', 'git reset --hard', and 'git clean -fd'.\n"
        "4. NON-POLLING REACTIVE DISCIPLINE:\n"
        "   - Never poll task status in loops. Emit a concise notification and await reactive wakeup."
    ),
    ROLE_DEEP_EXECUTION: (
        "[AGYIS ROLE PINNING: DEEP EXECUTION / EXECUTIONER]\n"
        "You are operating as the Deep Execution Engineer (Stage 1: EXECUTION / Stage 3: GIT_CUSTODY).\n\n"
        "CORE OPERATIONAL INVARIANTS:\n"
        "1. WORK PRESERVATION CONTRACT:\n"
        "   - Strictly prohibit destructive git commands ('git checkout -- .', 'git reset --hard', 'git clean -fd').\n"
        "   - On session wake-up, inspect 'git status' and 'git diff' to verify in-flight modifications.\n"
        "2. SURGICAL CONTIGUOUS EDITS INVARIANT:\n"
        "   - Always make single contiguous block replacements (edit_file / replace_file_content). Never overwrite whole files.\n"
        "   - Preserve surrounding comments, docstrings, imports, and formatting.\n"
        "3. ZERO SCOPE CREEP:\n"
        "   - Implement ONLY the tasks specified in the approved implementation plan. Zero speculative expansions.\n"
        "4. FAST & HERMETIC VERIFICATION:\n"
        "   - Execute native test commands (./agyis test, python3 -m harness.cli test).\n"
        "   - Preserve the sub-second benchmark invariant (<1.0s) and hermetic isolation."
    ),
    ROLE_FORENSIC_AUDITOR: (
        "[AGYIS ROLE PINNING: FORENSIC AUDITOR / THE HAMMER]\n"
        "You are operating as the Forensic Auditor / Victory Auditor (Stage 2: CODE_REVIEW / Stage 4: QA_AUDIT).\n\n"
        "CORE OPERATIONAL INVARIANTS:\n"
        "1. ANTI-FIXING & ZERO ERROR SWALLOWING:\n"
        "   - Never patch code directly or swallow exceptions. Audit diffs line-by-line against canonical rules.\n"
        "   - Emit definitive PASS or REJECT verdicts accompanied by a typed defect ledger.\n"
        "2. DUAL-AUDITOR GATE & CLEAN REVISION INVARIANT:\n"
        "   - Evaluate strictly the clean, committed revision on HEAD. Never evaluate dirty working trees.\n"
        "3. FAST & HERMETIC VERIFICATION:\n"
        "   - Run native test suites (./agyis test, python3 -m harness.cli test) and verify exit code 0.\n"
        "4. CLEANROOM RIGOR:\n"
        "   - Maintain dirty room vs clean room isolation. Derive implementations strictly from formal specifications."
    ),
    ROLE_SWARM_ORCHESTRATOR: (
        "[AGYIS ROLE PINNING: SWARM ORCHESTRATOR]\n"
        "You are operating as the Swarm Orchestrator coordinating distributed strands across the hardware mesh.\n\n"
        "CORE OPERATIONAL INVARIANTS:\n"
        "1. MESH COORDINATION & TOPOLOGY:\n"
        "   - Coordinate tasks across nodes using non-blocking Linda Tuplespace or out-of-band Swarm Council.\n"
        "2. WORK PRESERVATION CONTRACT:\n"
        "   - Preserve local worktrees and branches. Strictly prohibit 'git checkout -- .', 'git reset --hard', and 'git clean -fd'.\n"
        "3. ZERO REPO POLLUTION:\n"
        "   - Persist coordination state strictly to per-session artifacts or scratch spaces."
    ),
}


def get_role_pinning_cadence(override: Optional[int] = None) -> int:
    """Returns effective cadence for intra-epoch periodic role re-anchors (default 10)."""
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
                m = _UUID_EXTRACT_RE.search(val)
                if m:
                    cid = normalize_cid(m.group(1).lower())
    return cid or "default", brain_path


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
    brain_root = Path(os.path.expanduser(os.environ.get("AGYIS_BRAIN_DIR") or "~/.gemini/antigravity/brain"))
    session_brain = brain_root / norm_cid
    if session_brain.is_dir():
        return session_brain / ".agyis"
    if workspace_dir is not None:
        return workspace_dir / ".agents" / "artifacts" / "checkpoints" / norm_cid
    state_root = os.environ.get("PSL_HARNESS_STATE_DIR")
    if state_root:
        return Path(state_root) / "checkpoints" / norm_cid
    return None


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
    except (OSError, Exception):
        pass
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


def has_parent_conversation(payload: Dict[str, Any], conv_id: str) -> bool:
    """Returns True when the active conversation is a spawned child subagent."""
    for k in ("parentConversationId", "parent_conversation_id", "parentId", "parent_id"):
        if isinstance(payload.get(k), str) and payload[k].strip():
            return True
    norm_cid = normalize_cid(conv_id)
    if norm_cid in _EPHEMERAL_CIDS:
        return False
    brain_root = Path(os.path.expanduser(os.environ.get("AGYIS_BRAIN_DIR") or "~/.gemini/antigravity/brain"))
    convo_dir = brain_root / norm_cid
    if convo_dir.is_dir():
        for meta_name in (".metadata", "session_meta.json", "metadata.json"):
            mp = convo_dir / meta_name
            try:
                if mp.is_file() and mp.stat().st_size <= 65_536:
                    data = json.loads(mp.read_text(encoding="utf-8", errors="ignore"))
                    if isinstance(data, dict) and (data.get("parent_conversation_id") or data.get("parentConversationId")):
                        return True
            except Exception:
                pass
    return False


def _collect_search_paths(payload: Dict[str, Any], workspace_dir: Optional[Path]) -> List[Path]:
    paths: List[Path] = []
    if workspace_dir:
        paths.append(Path(os.path.expanduser(str(workspace_dir))))
    for k in ("workspace", "worktree", "cwd", "workspacePath", "workspaceDir", "worktreePath", "path",
              "artifactDirectoryPath", "artifact_directory_path", "artifactDirectory", "artifact_dir"):
        v = payload.get(k)
        s = v if isinstance(v, str) else (v.get("path") if isinstance(v, dict) else None)
        if isinstance(s, str) and s.strip():
            p = Path(os.path.expanduser(s.strip()))
            if p not in paths:
                paths.append(p)
    for k in ("activeWorkspaces", "workspacePaths", "active_workspaces", "workspace_paths"):
        lst = payload.get(k)
        if isinstance(lst, (list, tuple)):
            for item in lst:
                s = item if isinstance(item, str) else (item.get("path") if isinstance(item, dict) else None)
                if isinstance(s, str) and s.strip():
                    p = Path(os.path.expanduser(s.strip()))
                    if p not in paths:
                        paths.append(p)
    if Path.cwd() not in paths:
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
                    matched = normalize_role_str(data.get(rk))
                    if matched:
                        return matched
    except (OSError, Exception):
        pass
    return None


def check_pillar_3_explicit_role(
    payload: Dict[str, Any],
    workspace_dir: Optional[Path] = None,
    conversation_id: str = "",
) -> Optional[str]:
    """Pillar 3: Checks CID-scoped/workspace session_role.json, active plan, and role env vars."""
    search_dirs = _collect_search_paths(payload, workspace_dir)
    eff_cid, art_brain_dir = resolve_conv_and_brain(payload, conversation_id)
    folders: List[str] = []
    if eff_cid and eff_cid != "default":
        folders.append(eff_cid)
    else:
        env_cid = get_active_conversation_id()
        if env_cid:
            folders.append(env_cid)
        folders.append("session")

    expected_role_cid = eff_cid if (eff_cid and eff_cid != "default") else (folders[0] if folders else "")
    for root in search_dirs:
        cands = [
            *(root / ".agents" / "artifacts" / "checkpoints" / f / "session_role.json" for f in folders),
            root / ".agents" / "session_role.json",
            root / ".agents" / "artifacts" / "session_role.json",
            root / "session_role.json",
            root / ".agents" / "artifacts" / "plan.json",
            root / ".agents" / "plan.json",
            root / "plan.json",
        ]
        for cand in cands:
            matched = _read_role_json_file(cand, expected_cid=expected_role_cid)
            if matched:
                return matched

    if eff_cid and eff_cid != "default":
        brain_base = Path(os.path.expanduser(os.environ.get("AGYIS_BRAIN_DIR") or "~/.gemini/antigravity/brain"))
        for b_cand in (brain_base / eff_cid / ".agyis" / "session_role.json", brain_base / eff_cid / "session_role.json"):
            matched = _read_role_json_file(b_cand)
            if matched:
                return matched

    try:
        from harness.utils.plan_parser import find_active_plan
        plan_path = find_active_plan(
            conv_id=eff_cid if eff_cid != "default" else None,
            workspace_root=workspace_dir or (search_dirs[0] if search_dirs else None),
            brain_dir=art_brain_dir,
        )
        if plan_path and plan_path.is_file() and 0 < plan_path.stat().st_size <= 65_536:
            if plan_path.suffix == ".json":
                matched = _read_role_json_file(plan_path)
                if matched:
                    return matched
            else:
                txt = plan_path.read_text(encoding="utf-8", errors="ignore")[:8192]
                m = re.search(r"(?:^|\n)\s*(?:\*\*)?[Rr]ole(?:\*\*)?:\s*([a-zA-Z0-9_\-]+)", txt)
                mc = re.search(r"<!--\s*role:\s*([a-zA-Z0-9_\-]+)\s*-->", txt, re.IGNORECASE)
                for match_obj in (m, mc):
                    if match_obj:
                        matched = normalize_role_str(match_obj.group(1).strip())
                        if matched:
                            return matched
    except Exception:
        pass

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
        if isinstance(v, str) and v.strip():
            snippets.append(v.strip())
    steps = payload.get("steps")
    if isinstance(steps, list):
        for s in steps[:2]:
            if isinstance(s, dict):
                for sk in ("lastUserInput", "prompt", "user_input", "userPrompt", "message", "text", "query", "input", "step_data"):
                    sv = s.get(sk)
                    if isinstance(sv, str) and sv.strip():
                        snippets.append(sv.strip())
            elif isinstance(s, str) and s.strip():
                snippets.append(s.strip())

    eff_cid, _ = resolve_conv_and_brain(payload, conversation_id)
    metrics = db_metrics
    if metrics is None and eff_cid and eff_cid != "default":
        metrics = read_db_trajectory_state(eff_cid, db_dir=db_dir, timeout=timeout)
    if metrics is not None:
        if metrics.turn0_prompt:
            snippets.append(metrics.turn0_prompt)
        if metrics.latest_user_prompt and not snippets:
            snippets.append(metrics.latest_user_prompt)

    if not snippets and eff_cid and eff_cid != "default":
        t_path, _ = find_transcript_path(eff_cid)
        if t_path is not None:
            t_steps, _, _ = load_transcript_steps(t_path)
            for ts in t_steps[:2]:
                if isinstance(ts, dict):
                    content = ts.get("content") or ts.get("userInput") or ""
                    if isinstance(content, str) and content.strip():
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
        payload_tok = 0
        for k in ("tokens", "token_count", "tokenCount", "num_tokens", "numTokens"):
            v = payload.get(k)
            if isinstance(v, (int, float)) and int(v) > 0:
                payload_tok = int(v)
                break
        eff_cid, _ = resolve_conv_and_brain(payload, conversation_id)
        m = db_metrics
        if m is None and eff_cid and eff_cid != "default":
            m = read_db_trajectory_state(eff_cid, db_dir=db_dir, timeout=timeout)
        cur_tokens = max(tokens, payload_tok, m.tokens if m else 0)
        step_val = payload.get("step_count") or payload.get("stepCount") or payload.get("initialNumSteps") or 0
        total_steps = max(int(step_val) if isinstance(step_val, (int, float)) else 0, m.total_steps if m else 0)
        if cur_tokens < 200_000 and total_steps < 100 and not payload.get("force_pillar_2"):
            return None

        pairs = _collect_tool_pairs(payload, eff_cid, db_dir, timeout, m)
        if not pairs:
            return None

        is_child = has_parent_conversation(payload, eff_cid)
        subagent_spawns = edit_test = explicit_audit = read_grep = 0
        is_swarm = False
        for tool_name, args in pairs:
            tn, al = tool_name.lower().strip(), args.lower()
            if not is_child and (tn in ("invoke_subagent", "manage_task", "schedule") or "subagent" in tn):
                subagent_spawns += 1
                if any(k in al or k in tn for k in ("swarm", "mesh", "strand")):
                    is_swarm = True
            elif tn in ("edit_file", "write_file", "replace_file_content", "write_to_file", "apply_diff"):
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
    except Exception:
        pass
    return None


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
    """Sticky role classification across explicit metadata, Pillar 3, sticky pin, Pillar 1, and initial behavior."""
    try:
        for key in ("subagent_role", "subagentRole", "subagentType", "agent_type", "agentType",
                    "role", "archetype", "typeName", "agentName", "agent_name"):
            if isinstance(payload.get(key), str):
                matched = normalize_role_str(payload[key])
                if matched:
                    return matched
        for pk in ("agent", "subagent", "metadata", "context"):
            pd = payload.get(pk)
            if isinstance(pd, dict):
                for key in ("subagent_role", "subagentRole", "role", "archetype", "typeName", "agentName", "agent_name"):
                    if isinstance(pd.get(key), str):
                        matched = normalize_role_str(pd[key])
                        if matched:
                            return matched

        p3 = check_pillar_3_explicit_role(payload, workspace_dir=workspace_dir, conversation_id=conversation_id)
        if p3:
            return p3

        eff_cid, _ = resolve_conv_and_brain(payload, conversation_id)
        if not is_post_compaction and eff_cid not in _EPHEMERAL_CIDS:
            state_dir = resolve_cid_state_dir(eff_cid, workspace_dir, payload)
            sticky = load_sticky_role_state(state_dir, eff_cid)
            epoch_idx = db_metrics.epoch_index if db_metrics is not None else 0
            if sticky and int(sticky.get("epoch", 0)) == epoch_idx:
                pinned = normalize_role_str(sticky.get("role"))
                if pinned:
                    return pinned

        p1 = check_pillar_1_intent(payload, conversation_id=eff_cid, db_dir=db_dir, timeout=timeout, db_metrics=db_metrics)
        if p1:
            return p1

        p2 = check_pillar_2_behavior(payload, conversation_id=eff_cid, tokens=tokens, db_dir=db_dir, timeout=timeout, db_metrics=db_metrics)
        if p2:
            return p2

        for root in _collect_search_paths(payload, workspace_dir)[:-1]:  # Exclude generic Path.cwd() tail
            matched = normalize_role_str(str(root))
            if matched:
                return matched
    except Exception:
        pass
    return ROLE_FLIGHT_DIRECTOR


def build_role_persona_prompt(role: str) -> str:
    """Returns static role-only persona prompt for systemMessage injection."""
    return ROLE_PERSONA_PROMPTS.get(
        role,
        (
            f"[AGYIS ROLE PINNING: {role.upper()}]\nYou are operating with role '{role}'.\n\n"
            "1. WORK PRESERVATION: Strictly prohibit 'git checkout -- .', 'git reset --hard', 'git clean -fd'.\n"
            "2. PLAN ADHERENCE: Implement only tasks specified in the approved plan.\n"
            "3. HERMETIC VERIFICATION: Execute native test commands and verify exit code 0.\n"
            "4. NON-POLLING: Stop calling tools after launching async tasks."
        ),
    )


def build_post_compaction_persona_prompt(role: str, checkpoint_path: Optional[str] = None) -> str:
    """Returns post-compaction re-anchor prompt referencing per-conversation checkpoint artifact."""
    cp_hint = checkpoint_path or ".agents/artifacts/checkpoints/<session_id>.md"
    return (
        f"{build_role_persona_prompt(role)}\n\n"
        "[AGYIS POST-COMPACTION SUCCESSION DIRECTIVE]\n"
        "You have resumed execution following a context window compaction event.\n\n"
        "1. GROUND TRUTH CHECKPOINT RESTORATION:\n"
        f"   - Read your session-scoped pre-compaction ground truth checkpoint immediately: `{cp_hint}`\n"
        "   - Restore situational awareness: active phase progress, pending tasks, active subagents, and git diff status.\n\n"
        "2. WORK PRESERVATION CONTRACT:\n"
        "   - Strictly prohibit destructive git resets: NEVER execute 'git reset --hard', 'git checkout -- .', or 'git clean -fd'.\n\n"
        "3. AUTONOMOUS CONTINUATION:\n"
        "   - Proceed directly with the next actionable task without asking the operator re-orientation questions."
    )


def build_role_reanchor_advisory(role: str, step_count: int, cadence: int) -> str:
    """Returns intra-epoch periodic re-anchor ephemeralMessage directive."""
    return (
        f"[AGYIS ROLE RE-ANCHOR: {role.upper()} (STEP {step_count} | CADENCE {cadence})]\n"
        f"PERIODIC COGNITIVE ATTENTION AUDIT — Reinforcing active invariants for '{role}':\n"
        "1. Work Preservation: Preserve in-flight edits; destructive git commands are banned.\n"
        "2. Role Fidelity: Adhere strictly to active stage boundaries; zero unauthorized remediation.\n"
        "3. Empirical Verification: Validate modifications with native test commands before concluding."
    )


def build_compaction_advisory(
    role: str,
    tokens: int,
    threshold: int = 230_000,
    max_context_tokens: Optional[int] = None,
    checkpoint_path: Optional[str] = None,
) -> str:
    """Generates role-tailored advisory directive alerting to imminent compaction."""
    win = max_context_tokens if (max_context_tokens and max_context_tokens > 0) else 256_000
    runway_cap = int(round(win * 246_000 / 256_000))
    est_turns = max(1, (runway_cap - tokens) // 3500) if tokens < runway_cap else 1
    cp_hint = checkpoint_path or ".agents/artifacts/checkpoints/<session_id>.md"
    header = f"[AGYIS SYSTEM DIRECTIVE: COMPACTION IMMINENT (~{tokens:,} / {threshold:,} TOKENS | ~{est_turns} TURNS REMAINING)]\n"
    preserve = "STRICTLY PROHIBIT 'git checkout -- .', 'git reset --hard', and 'git clean -fd'. Keep all in-flight work intact on disk."

    if role == ROLE_DEEP_EXECUTION:
        return (
            f"{header}ROLE: Deep Execution (Monolithic SWE Pairing / Executioner)\n\n"
            f"1. WORK PRESERVATION CONTRACT (MANDATORY): {preserve}\n"
            f"2. ZERO REPO DOCUMENT POLLUTION: Save session checkpoint state strictly to `{cp_hint}` or brain directory. Zero git commits for WIP markers.\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION: Post-compaction wake-up directive: inspect 'git status' and 'git diff' first, re-run tests, and resume without reverting and without asking the operator what happened."
        )
    if role == ROLE_SWARM_ORCHESTRATOR:
        return (
            f"{header}ROLE: Swarm Orchestrator (Workstream Coordinator)\n\n"
            f"1. SWARM STATE SURVIVAL & ZERO REPO POLLUTION: Persist subagent task rosters, worktree / stage status, and milestone gates strictly to `{cp_hint}`.\n"
            f"2. WORK PRESERVATION CONTRACT: {preserve}\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION: Inspect worker branches via 'git status'/'git diff' and resume gates without manual intervention."
        )
    if role == ROLE_FORENSIC_AUDITOR:
        return (
            f"{header}ROLE: Forensic Auditor (Auditor / Hammer)\n\n"
            f"1. EVIDENCE PRESERVATION & ZERO REPO POLLUTION: Preserve defect reports in `{cp_hint}`. Zero git commits for ephemeral audit markers.\n"
            f"2. WORK PRESERVATION CONTRACT: {preserve}\n"
            "3. AUTONOMOUS POST-COMPACTION CONTINUATION: Post-compaction wake-up: re-execute verification suites on HEAD, verify exit codes, and issue formal certification."
        )
    if role == ROLE_FLIGHT_DIRECTOR:
        return (
            f"{header}ROLE: Flight Director (Cockpit Coordinator)\n\n"
            "1. COGNITIVE STATE PRESERVATION INVARIANT & ZERO REPO DOCUMENT POLLUTION:\n"
            f"   - Materialize working memory, active task decomposition, pending subagent assignments, and operator steering decisions into session-scoped checkpoint `{cp_hint}` before compaction strikes (Zero repository pollution).\n"
            f"2. WORK PRESERVATION CONTRACT: {preserve}\n"
            f"3. AUTONOMOUS POST-COMPACTION CONTINUATION: Immediately inspect `{cp_hint}` and 'git status', then resume orchestration autonomously without human re-explanation."
        )
    return f"{header}ROLE: General Agent\n\n1. WORK PRESERVATION: {preserve}\n2. ZERO REPO POLLUTION: Store state in `{cp_hint}`. Zero git commits for temporary markers.\n3. CONTINUATION: Inspect 'git status' and 'git diff' post-compaction and resume without asking operator what happened."
