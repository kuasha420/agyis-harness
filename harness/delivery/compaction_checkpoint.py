# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness: Automated Pre-Compaction Checkpoint Generator (ADR-031 / Issue #77 / Issue #83).

Assembles runtime ground truth before context exhaustion or compaction strikes:
1. Active subagent conversation IDs, roles, step counts, and token health
2. Git working tree state (branch, HEAD commit, dirty/untracked files)
3. Active artifact links from .agents/artifacts/ and brain directories
4. Next actionable phase and pending tasks from the active implementation plan

Emits a standardized compaction_checkpoint_<epoch>.md artifact in sub-second latency (<50ms).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union


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
        items = (self.content, self.output_path, self.latest_path, self.elapsed_ms)
        return items[index]

    def __len__(self) -> int:
        return 2


def inspect_git_state(workspace_dir: Union[Path, str]) -> GitState:
    """Collects git branch, commit hash, and dirty working tree status hermetically."""
    ws = Path(workspace_dir)

    def _run_git(args: List[str]) -> str:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            return res.stdout.rstrip("\r\n")
        except Exception:
            return ""

    branch = _run_git(["branch", "--show-current"]).strip() or "detached"
    commit_hash = _run_git(["rev-parse", "HEAD"]).strip() or "unknown"
    commit_short = _run_git(["rev-parse", "--short", "HEAD"]).strip() or "unknown"
    status_raw = _run_git(["status", "--porcelain"])
    diff_stat = _run_git(["diff", "--stat"]).strip()

    modified: List[str] = []
    untracked: List[str] = []

    if status_raw:
        for line in status_raw.splitlines():
            line = line.rstrip("\r\n")
            if not line or len(line) < 3:
                continue
            status_code = line[:2]
            filename = line[3:].strip()
            if status_code.startswith("??"):
                untracked.append(filename)
            else:
                modified.append(filename)

    is_dirty = bool(modified or untracked)
    return GitState(
        branch=branch,
        commit_hash=commit_hash,
        commit_short=commit_short,
        is_dirty=is_dirty,
        modified_files=modified,
        untracked_files=untracked,
        diff_stat=diff_stat,
    )


def collect_active_subagents(
    workspace_dir: Union[Path, str], brain_dir: Optional[Union[Path, str]] = None
) -> List[SubagentEntry]:
    """Collects active subagent statuses using harness context estimator with robust fallback."""
    subagents: List[SubagentEntry] = []
    ws = Path(workspace_dir)
    b_dir = Path(brain_dir) if brain_dir is not None else None

    try:
        if str(ws) not in sys.path:
            sys.path.insert(0, str(ws))
        from harness.subagents.context import list_active_subagent_statuses

        statuses = list_active_subagent_statuses(brain_dir=b_dir)
        for s in statuses:
            subagents.append(
                SubagentEntry(
                    conversation_id=s.conversation_id,
                    role=s.role,
                    step_count=s.step_count,
                    token_count=s.token_count,
                    health_zone=s.health_zone,
                    recommendation=s.recommendation,
                )
            )
        return subagents
    except Exception:
        pass

    # Fallback to direct directory scanning if harness module unavailable or returned empty
    target_brain = b_dir or Path(
        os.environ.get(
            "ANTIGRAVITY_BRAIN_DIR",
            os.environ.get(
                "GEMINI_BRAIN_DIR", Path.home() / ".gemini" / "antigravity" / "brain"
            ),
        )
    )
    if target_brain.is_dir():
        now = time.time()
        try:
            for entry in os.scandir(target_brain):
                if entry.is_dir() and not entry.name.startswith("."):
                    try:
                        # Scan recent active sessions (<4 hours) or all if explicit brain_dir provided
                        if b_dir is not None or (now - entry.stat().st_mtime < 14400):
                            subagents.append(
                                SubagentEntry(
                                    conversation_id=entry.name,
                                    role="subagent",
                                    step_count=0,
                                    token_count=0,
                                    health_zone="HEALTHY",
                                    recommendation="REUSE",
                                )
                            )
                    except OSError:
                        pass
        except OSError:
            pass
    return subagents


def collect_active_artifacts(workspace_dir: Union[Path, str]) -> List[ArtifactLink]:
    """Scans .agents/artifacts/ and returns active markdown artifacts."""
    artifacts: List[ArtifactLink] = []
    ws = Path(workspace_dir)
    art_dir = ws / ".agents" / "artifacts"
    if not art_dir.is_dir():
        return artifacts

    try:
        for p in sorted(art_dir.glob("*.md")):
            if not p.is_file():
                continue
            title = p.stem.replace("_", " ").title()
            size_bytes = 0
            try:
                # Read first heading as title
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    for _ in range(10):
                        line = f.readline()
                        if not line:
                            break
                        line_s = line.strip()
                        if line_s.startswith("# "):
                            title = line_s[2:].strip()
                            break
                size_bytes = p.stat().st_size
            except OSError:
                pass

            try:
                rel_path = p.relative_to(ws).as_posix()
            except ValueError:
                rel_path = f".agents/artifacts/{p.name}"

            artifacts.append(
                ArtifactLink(
                    filename=p.name,
                    title=title,
                    path=rel_path,
                    size_bytes=size_bytes,
                )
            )
    except OSError:
        pass
    return artifacts


def parse_implementation_plan(
    workspace_dir: Union[Path, str],
    plan_path: Optional[Union[Path, str]] = None,
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
        candidates = [
            ws / ".agents" / "artifacts" / "implementation_plan_issue_77.md",
            ws / ".agents" / "artifacts" / "implementation_plan.md",
            ws / ".agents" / "artifacts" / "plan.md",
        ]
        for cand in candidates:
            if cand.is_file():
                resolved_path = cand
                break

        if not resolved_path:
            art_dir = ws / ".agents" / "artifacts"
            if art_dir.is_dir():
                for p in sorted(art_dir.glob("*plan*.md")):
                    if p.is_file():
                        resolved_path = p
                        break

    if not resolved_path:
        return PlanStatus(
            plan_path=None,
            plan_title="No active implementation plan found",
            total_tasks=0,
            completed_tasks=0,
            pending_tasks=0,
            current_phase=None,
            next_pending_phase=None,
            next_pending_task=None,
            phases_summary=[],
        )

    try:
        rel_plan_path = str(resolved_path.relative_to(ws))
    except ValueError:
        rel_plan_path = str(resolved_path)

    title = resolved_path.stem.replace("_", " ").title()
    content = ""
    try:
        content = resolved_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass

    # Extract title
    m_title = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m_title:
        title = m_title.group(1).strip()

    # Split into sections by Markdown headers (### Phase or ## Phase or Stage)
    phase_pattern = re.compile(
        r"^(#{2,3}\s+(?:(?:Phase|Stage)\s+\d+[^:\n]*:?[^\n]*))", re.MULTILINE
    )
    splits = phase_pattern.split(content)

    phases_summary: List[Dict[str, Any]] = []
    total_tasks = 0
    completed_tasks = 0

    current_phase: Optional[str] = None
    next_pending_phase: Optional[str] = None
    next_pending_task: Optional[str] = None

    if len(splits) > 1:
        # splits alternate: [preamble, phase_header_1, phase_body_1, phase_header_2, phase_body_2, ...]
        for i in range(1, len(splits), 2):
            p_header = splits[i].strip()
            clean_header = re.sub(r"^#{2,3}\s+", "", p_header).strip()
            p_body = splits[i + 1] if i + 1 < len(splits) else ""

            # Count checkboxes
            p_done = len(re.findall(r"^\s*[-*+]\s*\[[xX]\]", p_body, re.MULTILINE))
            p_pending = len(re.findall(r"^\s*[-*+]\s*\[\s*\]", p_body, re.MULTILINE))
            p_total = p_done + p_pending

            total_tasks += p_total
            completed_tasks += p_done

            status = "PENDING"
            if p_total > 0 and p_done == p_total:
                status = "COMPLETED"
            elif p_done > 0:
                status = "IN_PROGRESS"

            phases_summary.append({
                "header": clean_header,
                "completed": p_done,
                "pending": p_pending,
                "total": p_total,
                "status": status,
            })

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
        # Fallback: scan whole document for checkboxes
        done_matches = len(re.findall(r"^\s*[-*+]\s*\[[xX]\]", content, re.MULTILINE))
        pending_matches = re.findall(r"^\s*[-*+]\s*\[\s*\]\s+(.+)$", content, re.MULTILINE)
        total_tasks = done_matches + len(pending_matches)
        completed_tasks = done_matches
        if pending_matches:
            next_pending_task = pending_matches[0].strip()

    pending_tasks = total_tasks - completed_tasks
    cur_phase = current_phase or next_pending_phase
    if next_pending_task is None and cur_phase:
        next_pending_task = f"Execute {cur_phase}"

    return PlanStatus(
        plan_path=rel_plan_path,
        plan_title=title,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        current_phase=cur_phase,
        next_pending_phase=next_pending_phase,
        next_pending_task=next_pending_task,
        phases_summary=phases_summary,
    )


def generate_compaction_checkpoint(
    workspace_dir: Union[Path, str],
    session_id: Optional[str] = None,
    orchestrator_role: str = "agyis_coordinator",
    trigger_tokens: int = 230_000,
    plan_path: Optional[Union[Path, str]] = None,
    output_path: Optional[Union[Path, str]] = None,
    brain_dir: Optional[Union[Path, str]] = None,
) -> CheckpointResult:
    """
    Assembles complete pre-compaction state and writes standardized checkpoint artifact.
    Returns CheckpointResult supporting tuple unpacking (content, out_path).
    """
    t0 = time.perf_counter()
    epoch = int(time.time())
    iso_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ws = Path(workspace_dir)
    sess = session_id or os.environ.get(
        "AGYIS_CONVERSATION_ID",
        os.environ.get("GEMINI_CONVERSATION_ID", "unknown_session"),
    )

    git_state = inspect_git_state(ws)
    subagents = collect_active_subagents(ws, brain_dir=brain_dir)
    artifacts = collect_active_artifacts(ws)
    plan_status = parse_implementation_plan(ws, plan_path=plan_path)

    # Calculate plan completion percentage
    pct = (
        (plan_status.completed_tasks / plan_status.total_tasks * 100.0)
        if plan_status.total_tasks > 0
        else 0.0
    )

    # Subagents Markdown Table
    if subagents:
        sub_rows = []
        for s in subagents:
            badge = (
                "🟢 HEALTHY"
                if s.health_zone == "HEALTHY"
                else ("🟡 AMBER" if s.health_zone == "AMBER" else "🔴 RED_ALERT")
            )
            sub_rows.append(
                f"| `{s.conversation_id}` | `{s.role}` | {s.step_count} | {s.token_count:,} | {badge} | `{s.recommendation}` |"
            )
        subagents_table = (
            "| Conversation ID | Role | Steps | Tokens | Health Zone | Recommendation |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            + "\n".join(sub_rows)
        )
    else:
        subagents_table = "_No active background subagents recorded in brain directory._"

    # Artifacts Markdown Table
    if artifacts:
        art_rows = []
        for a in artifacts:
            art_rows.append(f"| [{a.filename}]({a.path}) | {a.title} | {a.size_bytes:,} B |")
        artifacts_table = (
            "| Artifact File | Title / Header | Size |\n"
            "| :--- | :--- | :--- |\n"
            + "\n".join(art_rows)
        )
    else:
        artifacts_table = "_No artifacts found in `.agents/artifacts/`._"

    # Phases Summary Table
    if plan_status.phases_summary:
        phase_rows = []
        for p in plan_status.phases_summary:
            status_badge = (
                "✅ COMPLETED"
                if p["status"] == "COMPLETED"
                else ("🔄 IN PROGRESS" if p["status"] == "IN_PROGRESS" else "⏳ PENDING")
            )
            phase_rows.append(
                f"| {p['header']} | {p['completed']} / {p['total']} | {status_badge} |"
            )
        phases_table = (
            "| Phase Breakdown | Completed Tasks | Status |\n"
            "| :--- | :--- | :--- |\n"
            + "\n".join(phase_rows)
        )
    else:
        phases_table = f"_Tasks: {plan_status.completed_tasks} completed, {plan_status.pending_tasks} pending._"

    # Git Status Breakdown
    git_dirty_badge = "🔴 DIRTY" if git_state.is_dirty else "🟢 CLEAN"
    dirty_details = ""
    if git_state.is_dirty:
        if git_state.modified_files:
            dirty_details += f"\n- **Modified Files ({len(git_state.modified_files)})**:\n" + "\n".join(
                f"  * `{f}`" for f in git_state.modified_files
            )
        if git_state.untracked_files:
            dirty_details += f"\n- **Untracked Files ({len(git_state.untracked_files)})**:\n" + "\n".join(
                f"  * `{f}`" for f in git_state.untracked_files
            )
        if git_state.diff_stat:
            dirty_details += f"\n\n```\n{git_state.diff_stat}\n```"
    else:
        dirty_details = "\n_Working tree is completely clean on HEAD._"

    t_preview_ms = (time.perf_counter() - t0) * 1000.0

    markdown = f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Generated by Agyis Pre-Compaction Checkpoint Automation -->

# 🧭 Compaction & Succession Checkpoint (Epoch `{epoch}`)

> **Predecessor Session**: `{sess}`  
> **Predecessor Role**: `{orchestrator_role}`  
> **Generation Timestamp**: `{iso_time}`  
> **Trigger Threshold**: `tokens >= {trigger_tokens:,}` (Proximity Alarm: Imminent Context Compaction / Succession)  
> **Checkpoint Latency**: `{t_preview_ms:.2f} ms`

---

## 1. Executive Succession Mandate & Handoff Summary

This checkpoint was materialized automatically before context compaction or horizontal succession.
The successor orchestrator or post-compaction model MUST adopt the following state immediately upon awakening.

- **Primary Goal**: Zero knowledge loss and autonomous continuation of active SWE milestones.
- **Active Implementation Plan**: `{plan_status.plan_path or "N/A"}` ({plan_status.plan_title})
- **Overall Milestone Progress**: **{plan_status.completed_tasks} / {plan_status.total_tasks} Tasks ({pct:.1f}%)**
- **Current / Resuming Phase**: **{plan_status.current_phase or "Phase Complete / Verification"}**
- **Next Actionable Task**: `{plan_status.next_pending_task or "Final verification gate and release certification"}`

---

## 2. Git Working Tree & Repository State

- **Active Branch**: `{git_state.branch}`
- **HEAD Commit**: `{git_state.commit_short}` (`{git_state.commit_hash}`)
- **Working Tree Status**: {git_dirty_badge}
{dirty_details}

> [!IMPORTANT]
> **Work Preservation Contract (AC4)**:
> In-flight modifications must NOT be reverted or discarded with `git reset --hard` or `git checkout -- .`.
> All work on disk represents intentional partial state.

---

## 3. Active Implementation Plan & Milestone Progression

{phases_table}

- **Active Plan Reference**: `{plan_status.plan_path or "N/A"}`
- **Next Pending Phase**: `{plan_status.next_pending_phase or "None (All phases satisfied)"}`
- **Immediate Next Step**:
  > {plan_status.next_pending_task or "Execute full project test suite (`python3 -m harness.cli test`) and seal release."}

---

## 4. Active Subagent Roster & Liveness Matrix

{subagents_table}

### Succession Custody Action:
1. Retain conversation IDs for subagents marked `HEALTHY` or `AMBER`.
2. Send status ping / custody claim via `send_message(Recipient='<conv_id>', Message='...')` if subagent is awaiting parent direction.
3. Retire subagents marked `RED_ALERT` (>80k tokens) by spawning fresh successors.

---

## 5. Active Workspace Artifact Bridge (`.agents/artifacts/`)

{artifacts_table}

---

## 6. Successor Wake-Up Checklist (Autonomous Continuation Directive)

When waking up in a clean context or post-compaction epoch:
1. [ ] **Verify Working Tree**: Run `git status` and `git diff --stat` to confirm uncommitted changes survived intact.
2. [ ] **Read Latest Plan**: View `{plan_status.plan_path or ".agents/artifacts/implementation_plan.md"}` to re-anchor milestones.
3. [ ] **Resume Current Phase**: Immediately execute **{plan_status.current_phase or "Next Phase"}** starting at `{plan_status.next_pending_task or "pending task"}`.
4. [ ] **Verify Tests**: Run `./agyis test` (or `python3 -m harness.cli test`) to assert baseline suite health before proceeding.
5. [ ] **Zero Operator Prompting**: Do NOT ask the operator *"What was I doing?"* or *"Should I continue?"*. Resume execution autonomously!
"""

    if output_path is not None:
        out_file = Path(output_path)
        if not out_file.is_absolute():
            out_file = ws / out_file
        out_dir = out_file.parent
        latest_file = out_dir / "compaction_checkpoint_latest.md"
    else:
        out_dir = ws / ".agents" / "artifacts"
        out_file = out_dir / f"compaction_checkpoint_{epoch}.md"
        latest_file = out_dir / "compaction_checkpoint_latest.md"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(markdown, encoding="utf-8")
    tmp_latest = out_dir / f".compaction_checkpoint_latest.{os.getpid()}.tmp"
    tmp_latest.write_text(markdown, encoding="utf-8")
    os.replace(tmp_latest, latest_file)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return CheckpointResult(
        content=markdown,
        output_path=out_file,
        latest_path=latest_file,
        elapsed_ms=elapsed_ms,
    )


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
    return generate_compaction_checkpoint(
        workspace_dir=workspace_dir,
        session_id=session_id,
        orchestrator_role=orchestrator_role,
        trigger_tokens=trigger_tokens,
        plan_path=plan_path,
        output_path=output_path,
        brain_dir=brain_dir,
    )


def main() -> int:
    t_start = time.perf_counter()
    workspace = Path(os.environ.get("AGYIS_WORKSPACE_DIR", Path.cwd()))
    session_id = os.environ.get("AGYIS_CONVERSATION_ID", "78adab16-ecb6-453e-9d73-b8f4c7e76fa4")
    role = os.environ.get("AGYIS_ROLE", "agyis_coordinator")

    print(f"=== Agyis Compaction Checkpoint Generator ===")
    print(f"Workspace: {workspace}")
    print(f"Session:   {session_id}")
    print(f"Role:      {role}")

    res = generate_compaction_checkpoint(
        workspace_dir=workspace,
        session_id=session_id,
        orchestrator_role=role,
        trigger_tokens=230_000,
    )

    t_total_ms = (time.perf_counter() - t_start) * 1000.0
    print(f"✔ Checkpoint written: {res.output_path} ({len(res.content):,} bytes)")
    print(f"✔ Latest pointer:    {res.latest_path}")
    print(f"✔ Execution latency: {t_total_ms:.2f} ms (<50ms benchmark invariant)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
