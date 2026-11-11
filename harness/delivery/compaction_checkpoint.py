# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: Automated Pre-Compaction Checkpoint Generator (ADR-031, Issue #112).

Writes isolated per-conversation checkpoints (`.agents/artifacts/checkpoints/<cid>.md`)
without clobbering shared workspace checkpoints or active plans across concurrent sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.subagents.context import list_active_subagent_statuses
from harness.utils.context import get_active_brain_dir, get_active_conversation_id
from harness.utils.plan_parser import find_active_plan


@dataclass
class GitState:
    branch: str
    commit_hash: str
    commit_short: str
    is_dirty: bool
    modified_files: List[str]
    untracked_files: List[str]
    diff_stat: str


@dataclass
class SubagentEntry:
    conversation_id: str
    role: str
    step_count: int
    token_count: int
    health_zone: str
    recommendation: str
    parent_conversation_id: Optional[str] = None


SubagentState = SubagentEntry


@dataclass
class ArtifactLink:
    filename: str
    title: str
    path: str
    size_bytes: int


@dataclass
class PlanStatus:
    plan_path: Optional[str]
    plan_title: str
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    current_phase: Optional[str]
    next_pending_phase: Optional[str]
    next_pending_task: Optional[str]
    phases_summary: List[Dict[str, Any]] = field(default_factory=list)


PlanState = PlanStatus


@dataclass
class CheckpointResult:
    content: str
    output_path: Path
    latest_path: Path
    elapsed_ms: float = 0.0

    def __iter__(self):
        return iter((self.content, self.output_path))

    def __getitem__(self, index: int) -> Any:
        return (self.content, self.output_path, self.latest_path, self.elapsed_ms)[index]

    def __len__(self) -> int:
        return 2


def inspect_git_state(workspace_dir: Union[Path, str]) -> GitState:
    """Collects git branch, commit hash, and dirty working tree status hermetically."""
    ws = Path(workspace_dir)

    def _run_git(args: List[str]) -> str:
        try:
            res = subprocess.run(["git"] + args, cwd=str(ws), capture_output=True, text=True, timeout=1.5, check=False)
            return res.stdout.rstrip("\r\n")
        except Exception:
            return ""

    modified: List[str] = []
    untracked: List[str] = []
    for line in (_run_git(["status", "--porcelain"]) or "").splitlines():
        line = line.rstrip("\r\n")
        if len(line) < 3:
            continue
        target_list = untracked if line[:2].startswith("??") else modified
        target_list.append(line[3:].strip())

    return GitState(
        branch=_run_git(["branch", "--show-current"]).strip() or "detached",
        commit_hash=_run_git(["rev-parse", "HEAD"]).strip() or "unknown",
        commit_short=_run_git(["rev-parse", "--short", "HEAD"]).strip() or "unknown",
        is_dirty=bool(modified or untracked),
        modified_files=modified,
        untracked_files=untracked,
        diff_stat=_run_git(["diff", "--stat"]).strip(),
    )


def resolve_checkpoint_retention(retention_limit: Optional[int] = None) -> int:
    """Resolves checkpoint retention limit from arg or AGYIS_CHECKPOINT_RETENTION (default 5)."""
    raw: Any = os.environ.get("AGYIS_CHECKPOINT_RETENTION", "5") if retention_limit is None else retention_limit
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 5


def prune_stale_checkpoints(
    artifacts_dir: Union[Path, str],
    retention_limit: Optional[int] = None,
    dry_run: bool = False,
) -> List[Path]:
    """Prunes older compaction_checkpoint_<ts>.md snapshots while preserving active CID checkpoints."""
    art_dir = Path(artifacts_dir)
    if not art_dir.is_dir():
        return []
    limit = resolve_checkpoint_retention(retention_limit)
    pattern = re.compile(r"^compaction_checkpoint_(\d+)\.md$")
    candidates: List[Tuple[float, Path]] = []

    try:
        for entry in art_dir.glob("compaction_checkpoint_*.md"):
            if not entry.is_file() or entry.name == "compaction_checkpoint_latest.md":
                continue
            m = pattern.match(entry.name)
            sort_key = float(m.group(1)) if m else (entry.stat().st_mtime if entry.exists() else 0.0)
            candidates.append((sort_key, entry))
    except OSError:
        return []

    candidates.sort(key=lambda x: x[0], reverse=True)
    pruned: List[Path] = []
    for file_path in (item[1] for item in candidates[limit:]):
        if dry_run:
            pruned.append(file_path)
            continue
        try:
            file_path.unlink()
            pruned.append(file_path)
        except OSError:
            pass
    return pruned


def collect_active_subagents(
    workspace_dir: Union[Path, str],
    brain_dir: Optional[Union[Path, str]] = None,
    session_id: Optional[str] = None,
) -> List[SubagentEntry]:
    """Collects active subagent statuses strictly via SSOT trajectory discovery."""
    ws = Path(workspace_dir)
    b_dir = Path(brain_dir) if brain_dir is not None else None
    eff_parent = session_id if b_dir is not None else get_active_conversation_id(session_id)

    heartbeat_meta: Optional[Dict[str, Any]] = None
    try:
        from harness.subagents.heartbeat import read_stage_heartbeat
        heartbeat_meta = read_stage_heartbeat(workspace_dir=ws)
    except Exception:
        pass

    try:
        statuses = list_active_subagent_statuses(brain_dir=b_dir, root_conv_id=eff_parent)
    except Exception:
        statuses = []

    entries: List[SubagentEntry] = []
    for s in statuses:
        role_display = s.role
        if heartbeat_meta:
            hb_stage = str(heartbeat_meta.get("stage") or "").strip()
            hb_agent = str(heartbeat_meta.get("active_agent_id") or "").strip()
            if hb_stage and (s.conversation_id == hb_agent or hb_stage.lower() in role_display.lower()):
                badge = f"[{hb_stage.upper()}]"
                if badge not in role_display.upper():
                    role_display = f"{role_display} {badge}"
        entries.append(
            SubagentEntry(
                conversation_id=s.conversation_id,
                role=role_display,
                step_count=s.step_count,
                token_count=s.token_count,
                health_zone=s.health_zone,
                recommendation=s.recommendation,
                parent_conversation_id=getattr(s, "parent_conversation_id", None),
            )
        )
    return entries


def collect_active_artifacts(
    workspace_dir: Union[Path, str],
    brain_dir: Optional[Union[Path, str]] = None,
) -> List[ArtifactLink]:
    """Scans .agents/artifacts/ and active session brain_dir returning deduplicated markdown links."""
    ws = Path(workspace_dir)
    scan_dirs = [d for d in (ws / ".agents" / "artifacts", Path(brain_dir) if brain_dir else None) if d and d.is_dir()]
    file_map: Dict[str, Tuple[Path, float]] = {}

    for d in scan_dirs:
        try:
            for p in d.iterdir():
                if not p.is_file() or p.name.startswith(".") or not p.name.endswith(".md"):
                    continue
                mtime = p.stat().st_mtime if p.exists() else 0.0
                if p.name not in file_map or mtime > file_map[p.name][1]:
                    file_map[p.name] = (p, mtime)
        except OSError:
            pass

    artifacts: List[ArtifactLink] = []
    for p, _ in sorted(file_map.values(), key=lambda item: item[1], reverse=True):
        title = p.stem.replace("_", " ").title()
        size_bytes = 0
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for _ in range(10):
                    line = f.readline()
                    if not line:
                        break
                    if line.strip().startswith("# "):
                        title = line.strip()[2:].strip()
                        break
            size_bytes = p.stat().st_size
        except OSError:
            pass
        try:
            rel_path = p.relative_to(ws).as_posix()
        except ValueError:
            rel_path = str(p)
        artifacts.append(ArtifactLink(filename=p.name, title=title, path=rel_path, size_bytes=size_bytes))
    return artifacts


def parse_implementation_plan(
    workspace_dir: Union[Path, str],
    plan_path: Optional[Union[Path, str]] = None,
    brain_dir: Optional[Union[Path, str]] = None,
    conv_id: Optional[str] = None,
) -> PlanStatus:
    """Parses implementation plan to extract phase progress and next actions."""
    ws = Path(workspace_dir)
    resolved_path: Optional[Path] = None
    if plan_path is not None:
        p = Path(plan_path)
        if not p.is_absolute():
            p = ws / p
        if p.is_file():
            resolved_path = p
    else:
        resolved_path = find_active_plan(conv_id=conv_id, workspace_root=ws, brain_dir=brain_dir, ignore_completed=True)

    if not resolved_path:
        return PlanStatus(None, "No active implementation plan found", 0, 0, 0, None, None, None, [])

    try:
        rel_plan_path = str(resolved_path.relative_to(ws))
    except ValueError:
        rel_plan_path = str(resolved_path)

    content = ""
    try:
        content = resolved_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    m_title = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = m_title.group(1).strip() if m_title else resolved_path.stem.replace("_", " ").title()

    splits = re.compile(r"^(#{2,3}\s+(?:(?:Phase|Stage)\s+\d+[^:\n]*:?[^\n]*))", re.MULTILINE).split(content)
    phases_summary: List[Dict[str, Any]] = []
    total_tasks = completed_tasks = 0
    current_phase: Optional[str] = None
    next_pending_phase: Optional[str] = None
    next_pending_task: Optional[str] = None

    if len(splits) > 1:
        for i in range(1, len(splits), 2):
            clean_header = re.sub(r"^#{2,3}\s+", "", splits[i].strip()).strip()
            p_body = splits[i + 1] if i + 1 < len(splits) else ""
            p_done = len(re.findall(r"^\s*[-*+]\s*\[[xX]\]", p_body, re.MULTILINE))
            p_pending = len(re.findall(r"^\s*[-*+]\s*\[\s*\]", p_body, re.MULTILINE))
            p_total = p_done + p_pending
            total_tasks += p_total
            completed_tasks += p_done
            status = "COMPLETED" if (p_total > 0 and p_done == p_total) else ("IN_PROGRESS" if p_done > 0 else "PENDING")
            phases_summary.append({"header": clean_header, "completed": p_done, "pending": p_pending, "total": p_total, "status": status})

            if status == "IN_PROGRESS" and current_phase is None:
                current_phase = clean_header
                m_task = re.search(r"^\s*[-*+]\s*\[\s*\]\s+(.+)$", p_body, re.MULTILINE)
                if m_task and next_pending_task is None:
                    next_pending_task = m_task.group(1).strip()
            if status in ("IN_PROGRESS", "PENDING") and next_pending_phase is None:
                next_pending_phase = clean_header
                if next_pending_task is None:
                    m_task = re.search(r"^\s*[-*+]\s*\[\s*\]\s+(.+)$", p_body, re.MULTILINE)
                    if m_task:
                        next_pending_task = m_task.group(1).strip()
    else:
        done_matches = len(re.findall(r"^\s*[-*+]\s*\[[xX]\]", content, re.MULTILINE))
        pending_matches = re.findall(r"^\s*[-*+]\s*\[\s*\]\s+(.+)$", content, re.MULTILINE)
        total_tasks = done_matches + len(pending_matches)
        completed_tasks = done_matches
        if pending_matches:
            next_pending_task = pending_matches[0].strip()

    cur_phase = current_phase or next_pending_phase
    if next_pending_task is None and cur_phase:
        next_pending_task = f"Execute {cur_phase}"
    return PlanStatus(rel_plan_path, title, total_tasks, completed_tasks, total_tasks - completed_tasks, cur_phase, next_pending_phase, next_pending_task, phases_summary)


def generate_compaction_checkpoint(
    workspace_dir: Union[Path, str],
    session_id: Optional[str] = None,
    orchestrator_role: str = "agyis_coordinator",
    trigger_tokens: int = 230_000,
    plan_path: Optional[Union[Path, str]] = None,
    output_path: Optional[Union[Path, str]] = None,
    brain_dir: Optional[Union[Path, str]] = None,
) -> CheckpointResult:
    """Assembles pre-compaction state and writes isolated per-conversation checkpoint."""
    t0 = time.perf_counter()
    epoch = int(time.time())
    iso_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ws = Path(workspace_dir)
    raw_sess = get_active_conversation_id(session_id)
    sess = raw_sess or "unknown_session"
    effective_brain = get_active_brain_dir(brain_dir)
    cand_session_brain = effective_brain / sess if raw_sess else None
    active_artifact_brain = brain_dir or (cand_session_brain if cand_session_brain and cand_session_brain.is_dir() else None)

    git_state = inspect_git_state(ws)
    subagents = collect_active_subagents(
        ws,
        brain_dir=brain_dir,
        session_id=session_id if brain_dir is not None else raw_sess,
    )
    artifacts = collect_active_artifacts(ws, brain_dir=active_artifact_brain)
    plan_status = parse_implementation_plan(ws, plan_path=plan_path, brain_dir=active_artifact_brain, conv_id=sess)
    pct = (plan_status.completed_tasks / plan_status.total_tasks * 100.0) if plan_status.total_tasks > 0 else 0.0

    if subagents:
        sub_rows = [
            f"| `{s.conversation_id}` | `{s.role}` | {s.step_count} | {s.token_count:,} | "
            f"{'🟢 HEALTHY' if s.health_zone == 'HEALTHY' else ('🟡 AMBER' if s.health_zone == 'AMBER' else '🔴 RED_ALERT')} | `{s.recommendation}` |"
            for s in subagents
        ]
        subagents_table = "| Conversation ID | Role | Steps | Tokens | Health Zone | Recommendation |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(sub_rows)
    else:
        subagents_table = "_No active background subagents recorded for this session._"

    if artifacts:
        artifacts_table = "| Artifact File | Title / Header | Size |\n| :--- | :--- | :--- |\n" + "\n".join(
            f"| [{a.filename}]({a.path}) | {a.title} | {a.size_bytes:,} B |" for a in artifacts
        )
    else:
        artifacts_table = "_No artifacts found in `.agents/artifacts/`._"

    if plan_status.phases_summary:
        phases_table = "| Phase Breakdown | Completed Tasks | Status |\n| :--- | :--- | :--- |\n" + "\n".join(
            f"| {p['header']} | {p['completed']} / {p['total']} | {'✅ COMPLETED' if p['status'] == 'COMPLETED' else ('🔄 IN PROGRESS' if p['status'] == 'IN_PROGRESS' else '⏳ PENDING')} |"
            for p in plan_status.phases_summary
        )
    else:
        phases_table = f"_Tasks: {plan_status.completed_tasks} completed, {plan_status.pending_tasks} pending._"

    dirty_parts: List[str] = []
    if git_state.is_dirty:
        if git_state.modified_files:
            dirty_parts.append(f"\n- **Modified Files ({len(git_state.modified_files)})**:\n" + "\n".join(f"  * `{f}`" for f in git_state.modified_files))
        if git_state.untracked_files:
            dirty_parts.append(f"\n- **Untracked Files ({len(git_state.untracked_files)})**:\n" + "\n".join(f"  * `{f}`" for f in git_state.untracked_files))
        if git_state.diff_stat:
            dirty_parts.append(f"\n\n```\n{git_state.diff_stat}\n```")
    dirty_details = "".join(dirty_parts) or "\n_Working tree is completely clean on HEAD._"

    t_preview_ms = (time.perf_counter() - t0) * 1000.0
    markdown = f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
# 🧭 Compaction & Succession Checkpoint (Epoch `{epoch}`)

> **Predecessor Session**: `{sess}`  
> **Predecessor Role**: `{orchestrator_role}`  
> **Generation Timestamp**: `{iso_time}`  
> **Trigger Threshold**: `tokens >= {trigger_tokens:,}`  
> **Checkpoint Latency**: `{t_preview_ms:.2f} ms`

## 1. Executive Succession Mandate & Handoff Summary
- **Active Implementation Plan**: `{plan_status.plan_path or "N/A"}` ({plan_status.plan_title})
- **Overall Milestone Progress**: **{plan_status.completed_tasks} / {plan_status.total_tasks} Tasks ({pct:.1f}%)**
- **Current / Resuming Phase**: **{plan_status.current_phase or "Phase Complete / Verification"}**
- **Next Actionable Task**: `{plan_status.next_pending_task or "Final verification gate and release certification"}`

## 2. Git Working Tree & Repository State
- **Active Branch**: `{git_state.branch}` | **HEAD**: `{git_state.commit_short}` (`{git_state.commit_hash}`) | **Status**: {'🔴 DIRTY' if git_state.is_dirty else '🟢 CLEAN'}
{dirty_details}
> [!IMPORTANT] Work Preservation Contract (AC4): NEVER run `git reset --hard` or `git checkout -- .`.

## 3. Active Implementation Plan & Milestone Progression
{phases_table}
- **Active Plan Reference**: `{plan_status.plan_path or "N/A"}` | **Next Phase**: `{plan_status.next_pending_phase or "None"}`

## 4. Active Subagent Roster & Liveness Matrix
{subagents_table}
1. Retain conversation IDs for subagents marked `HEALTHY` or `AMBER`.
2. Compact or hand off subagents marked `RED_ALERT` (>=80% context window) before spawning replacements.

## 5. Active Workspace Artifact Bridge (`.agents/artifacts/`)
{artifacts_table}

## 6. Successor Wake-Up Checklist (Autonomous Continuation Directive)
1. [ ] Verify tree via `git status` and inspect `{plan_status.plan_path or ".agents/artifacts/implementation_plan.md"}`.
2. [ ] Resume **{plan_status.current_phase or "Next Phase"}** starting at `{plan_status.next_pending_task or "pending task"}` without re-prompting.
"""

    if output_path is not None:
        out_file = Path(output_path)
        if not out_file.is_absolute():
            out_file = ws / out_file
        out_dir = out_file.parent
    else:
        out_dir = ws / ".agents" / "artifacts" / "checkpoints"
        cid_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_sess) if raw_sess else "session"
        out_file = out_dir / f"{cid_slug}.md"

    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = out_dir / f".{out_file.name}.{os.getpid()}.tmp"
    tmp_file.write_text(markdown, encoding="utf-8")
    os.replace(tmp_file, out_file)

    try:
        prune_stale_checkpoints(out_dir)
        if output_path is None:
            prune_stale_checkpoints(ws / ".agents" / "artifacts")
    except Exception:
        pass

    return CheckpointResult(content=markdown, output_path=out_file, latest_path=out_file, elapsed_ms=(time.perf_counter() - t0) * 1000.0)


def assemble_compaction_checkpoint(
    workspace_dir: Union[Path, str],
    session_id: Optional[str] = None,
    orchestrator_role: str = "agyis_coordinator",
    trigger_tokens: int = 230_000,
    brain_dir: Optional[Union[Path, str]] = None,
    plan_path: Optional[Union[Path, str]] = None,
    output_path: Optional[Union[Path, str]] = None,
) -> CheckpointResult:
    """Backwards-compatible alias for generate_compaction_checkpoint."""
    return generate_compaction_checkpoint(workspace_dir=workspace_dir, session_id=session_id, orchestrator_role=orchestrator_role, trigger_tokens=trigger_tokens, plan_path=plan_path, output_path=output_path, brain_dir=brain_dir)


def main() -> int:
    workspace = Path(os.environ.get("AGYIS_WORKSPACE_DIR", Path.cwd()))
    session_id = get_active_conversation_id()
    role = os.environ.get("AGYIS_ROLE", "agyis_coordinator")
    res = generate_compaction_checkpoint(workspace_dir=workspace, session_id=session_id, orchestrator_role=role, trigger_tokens=230_000)
    print(f"✔ Checkpoint written: {res.output_path} ({len(res.content):,} bytes, {res.elapsed_ms:.2f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
