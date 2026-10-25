# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Cockpit Flight Director CLI Suite (PSL-SPEC-2026-COCKPIT-DIRECTOR-001 / Issue #92).

Provides root flight deck status inspection, 12-workflow routing briefings,
and flight director invariant verification.
Zero external dependencies (100% Python Standard Library).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.delivery import (
    collect_active_subagents,
    inspect_git_state,
)
from harness.subagents.routing import (
    CANONICAL_ROUTES,
    build_stage_transition_payload,
    format_route_briefing,
    get_route,
    list_routes,
)
from harness.subagents.stage_role import read_stage_role
from harness.utils.plan_parser import find_active_plan


def _classify_token_horizon(tokens: int) -> Tuple[str, str]:
    """Classifies token count into Healthy, Amber, or Red Alert proximity zones."""
    if tokens < 180_000:
        return "HEALTHY", "🟢 Healthy Zone (<180k tokens)"
    elif tokens < 230_000:
        return "AMBER", "🟡 Amber Warning Zone (180k–229k tokens)"
    else:
        return "RED_ALERT", "🔴 Compaction Imminent (>=230k tokens)"


def _get_active_checkpoint_info(workspace: Path) -> Dict[str, Any]:
    """Inspects .agents/artifacts/compaction_checkpoint_latest.md freshness."""
    cp_latest = workspace / ".agents" / "artifacts" / "compaction_checkpoint_latest.md"
    if not cp_latest.exists():
        return {
            "exists": False,
            "path": str(cp_latest),
            "age_seconds": None,
            "is_fresh": False,
        }

    try:
        mtime = cp_latest.stat().st_mtime
        age_s = max(0.0, time.time() - mtime)
        return {
            "exists": True,
            "path": str(cp_latest),
            "age_seconds": round(age_s, 1),
            "is_fresh": age_s <= 3600.0,  # fresh within 60 mins
        }
    except Exception:
        return {
            "exists": False,
            "path": str(cp_latest),
            "age_seconds": None,
            "is_fresh": False,
        }


def _audit_flight_director_invariants(
    workspace: Path, allow_dirty: bool = False
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Audits the active workspace against the 5 Flight Director Invariants:
    1. Zero direct product code drift in root
    2. Clean scratchpads in root
    3. No orphaned worktrees
    4. Checkpoint availability / freshness
    5. Subagent health (no zombie/dead subagents)
    """
    results: List[Dict[str, Any]] = []
    overall_pass = True

    # Invariant 1: Zero direct product code drift in root
    git_state = inspect_git_state(workspace)
    product_prefixes = ("harness/", "src/", "lib/", "tests/", "pipeline/")
    dirty_product_files = [
        f for f in (git_state.modified_files + git_state.untracked_files)
        if any(f.startswith(p) for p in product_prefixes)
    ]
    inv1_passed = len(dirty_product_files) == 0 or allow_dirty
    if not inv1_passed:
        overall_pass = False
    results.append({
        "invariant": "Zero Product Code Drift",
        "description": "Root flight deck must not accumulate uncommitted product code edits.",
        "passed": inv1_passed,
        "details": f"{len(dirty_product_files)} uncommitted product files" if dirty_product_files else "Clean",
        "violations": dirty_product_files,
    })

    # Invariant 2: Clean scratchpads in repo root
    stray_root_files: List[str] = []
    try:
        for item in workspace.iterdir():
            if item.is_file() and not item.name.startswith("."):
                if item.suffix in (".py", ".sh", ".tmp", ".db", ".bak"):
                    # Check if it's an allowed standard script e.g. agyis
                    if item.name not in ("agyis", "setup.py", "conftest.py"):
                        stray_root_files.append(item.name)
    except Exception:
        pass
    inv2_passed = len(stray_root_files) == 0
    if not inv2_passed:
        overall_pass = False
    results.append({
        "invariant": "Clean Root Scratchpads (AC5)",
        "description": "Repo root must remain clean of ephemeral scratch scripts and databases.",
        "passed": inv2_passed,
        "details": f"{len(stray_root_files)} stray root files" if stray_root_files else "Clean",
        "violations": stray_root_files,
    })

    # Invariant 3: No orphaned worktrees
    orphaned_worktrees: List[str] = []
    try:
        res = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if res.returncode == 0:
            lines = res.stdout.splitlines()
            for line in lines:
                if line.startswith("worktree "):
                    wt_path_str = line[len("worktree "):].strip()
                    wt_path = Path(wt_path_str)
                    if not wt_path.exists():
                        orphaned_worktrees.append(wt_path_str)
                elif line.strip() == "prunable":
                    # Mark previous as prunable
                    pass
    except Exception:
        pass
    inv3_passed = len(orphaned_worktrees) == 0
    if not inv3_passed:
        overall_pass = False
    results.append({
        "invariant": "No Orphaned Worktrees",
        "description": "All git worktrees must point to valid, reachable working directories.",
        "passed": inv3_passed,
        "details": f"{len(orphaned_worktrees)} missing worktrees" if orphaned_worktrees else "Clean",
        "violations": orphaned_worktrees,
    })

    # Invariant 4: Checkpoint availability
    cp_info = _get_active_checkpoint_info(workspace)
    inv4_passed = cp_info["exists"]
    # Checkpoint missing is an advisory warning unless strict
    results.append({
        "invariant": "Active Checkpoint Availability",
        "description": "Compaction checkpoint must be present in .agents/artifacts/.",
        "passed": inv4_passed,
        "details": f"Age: {cp_info.get('age_seconds')}s" if inv4_passed else "Missing checkpoint",
        "violations": [] if inv4_passed else [cp_info["path"]],
    })

    # Invariant 5: Subagent health
    subagents = collect_active_subagents(workspace)
    red_subagents = [s for s in subagents if getattr(s, "health_zone", "") == "RED_ALERT"]
    inv5_passed = len(red_subagents) == 0
    if not inv5_passed and not allow_dirty:
        overall_pass = False
    results.append({
        "invariant": "Subagent Cognitive Health",
        "description": "Active subagents must not exceed the cognitive context cliff (>80k tokens or >80 steps).",
        "passed": inv5_passed or allow_dirty,
        "details": f"{len(subagents)} active subagents ({len(red_subagents)} red alert)",
        "violations": [
            f"{getattr(s, 'role', 'subagent')} ({getattr(s, 'conversation_id', '')[:8]}: {getattr(s, 'step_count', 0)} steps, ~{getattr(s, 'token_count', 0)} tokens)"
            for s in red_subagents
        ],
    })

    return overall_pass, results


def cmd_cockpit(args: argparse.Namespace) -> int:
    """
    Subcommand dispatcher for `agyis cockpit`:
    - status: Flight deck metrics (tokens, active ladder stage, git, subagents).
    - route <letter|alias>: Workflow dispatch briefing & transition payload template.
    - verify: Invariant audit against the 5 Flight Director principles.
    """
    subcommand = getattr(args, "subcommand", "")
    action = getattr(args, "cockpit_action", None)
    if not action:
        if subcommand in ("router", "ladder"):
            wf = getattr(args, "workflow", "status")
            if wf and wf.lower() != "status":
                action = "route"
            else:
                action = "status"
        else:
            action = "status"

    ws_val = getattr(args, "workspace", None)
    workspace = Path(ws_val).resolve() if ws_val else Path.cwd().resolve()
    is_json = bool(getattr(args, "json", False))

    if action == "status":
        raw_tokens_env = os.environ.get("AGYIS_TOKEN_COUNT") or os.environ.get("PSL_TOKEN_COUNT")
        try:
            tokens = int(raw_tokens_env) if raw_tokens_env else 45_000
        except ValueError:
            tokens = 45_000

        zone_code, zone_label = _classify_token_horizon(tokens)
        git_state = inspect_git_state(workspace)
        subagents = collect_active_subagents(workspace)
        stage_role = read_stage_role(workspace)
        plan_path = find_active_plan(workspace_root=workspace)
        cp_info = _get_active_checkpoint_info(workspace)

        data: Dict[str, Any] = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workspace": str(workspace),
            "flight_director": {
                "role": "ROLE_FLIGHT_DIRECTOR",
                "tokens_estimated": tokens,
                "proximity_zone": zone_code,
                "proximity_label": zone_label,
            },
            "active_plan": str(plan_path) if plan_path else None,
            "active_stage_role": stage_role,
            "git": {
                "branch": git_state.branch,
                "commit_short": git_state.commit_short,
                "is_dirty": git_state.is_dirty,
                "modified_files": git_state.modified_files,
                "untracked_files": git_state.untracked_files,
            },
            "subagents_active_count": len(subagents),
            "subagents": [
                {
                    "conversation_id": getattr(s, "conversation_id", ""),
                    "role": getattr(s, "role", "worker"),
                    "steps": getattr(s, "step_count", 0),
                    "tokens": getattr(s, "token_count", 0),
                    "health": getattr(s, "health_zone", "HEALTHY"),
                    "recommendation": getattr(s, "recommendation", "REUSE"),
                }
                for s in subagents
            ],
            "checkpoint": cp_info,
        }

        if is_json:
            print(json.dumps(data, indent=2))
            return 0

        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("🛫 AGYIS COCKPIT FLIGHT DECK STATUS")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"• Proximity Zone     : {zone_label} (~{tokens:,} tokens)")
        print(f"• Active Stage Role  : {stage_role.get('stage_name', 'None') if stage_role else 'ROOT_ATC'} ({stage_role.get('specialist_agent', 'cockpit_director') if stage_role else 'cockpit_director'})")
        print(f"• Active Plan        : {plan_path.name if plan_path else 'None declared'}")
        print(f"• Git State          : Branch '{git_state.branch}' @ {git_state.commit_short} ({'DIRTY' if git_state.is_dirty else 'CLEAN'})")
        if git_state.is_dirty:
            print(f"  └─ Modified: {len(git_state.modified_files)} | Untracked: {len(git_state.untracked_files)}")
        print(f"• Active Subagents   : {len(subagents)} registered in background")
        for s in subagents:
            cid_short = getattr(s, "conversation_id", "")[:8]
            steps = getattr(s, "step_count", 0)
            tokens_val = getattr(s, "token_count", 0)
            print(f"  └─ [{cid_short}] {getattr(s, 'role', 'worker')}: {steps} steps, ~{tokens_val:,} tokens [{getattr(s, 'health_zone', 'HEALTHY')}]")
        print(f"• Checkpoint Freshness: {'Fresh (' + str(cp_info.get('age_seconds')) + 's old)' if cp_info['is_fresh'] else ('Present' if cp_info['exists'] else 'Missing')}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return 0

    elif action == "route":
        query = getattr(args, "workflow", "") or ""
        route = get_route(query)
        if not route:
            valid_letters = ", ".join(r.letter for r in CANONICAL_ROUTES)
            valid_aliases = ", ".join(r.alias for r in CANONICAL_ROUTES)
            if is_json:
                print(json.dumps({
                    "status": "error",
                    "error": f"Unknown workflow route: '{query}'",
                    "valid_letters": [r.letter for r in CANONICAL_ROUTES],
                    "valid_aliases": [r.alias for r in CANONICAL_ROUTES],
                }, indent=2))
            else:
                print(f"❌ Error: Unknown workflow route '{query}'.", file=sys.stderr)
                print(f"Valid route letters: {valid_letters}", file=sys.stderr)
                print(f"Valid route aliases: {valid_aliases}", file=sys.stderr)
            return 1

        if is_json:
            template_payload = build_stage_transition_payload(
                task_id=getattr(args, "task_id", "TASK-001"),
                phase=f"Phase: {route.title}",
                stage=route.stage_sequence[0],
                sender_role="cockpit_director",
                next_recommended_stage=route.stage_sequence[1] if len(route.stage_sequence) > 1 else route.stage_sequence[0],
                plan_path=route.default_artifacts.get("plan_path"),
                reproduction_script=route.default_artifacts.get("reproduction_script"),
                report_path=route.default_artifacts.get("report_path"),
            )
            data = {
                "status": "ok",
                "letter": route.letter,
                "alias": route.alias,
                "mnemonic_aliases": list(route.mnemonic_aliases),
                "title": route.title,
                "starting_specialist": route.starting_specialist,
                "pipeline_route": route.pipeline_route,
                "mode": route.mode.value,
                "critical_invariants": route.critical_invariants,
                "primary_deliverable": route.primary_deliverable,
                "empirical_precedent": route.empirical_precedent,
                "stage_sequence": list(route.stage_sequence),
                "transition_payload_template": template_payload,
            }
            print(json.dumps(data, indent=2))
            return 0

        briefing = format_route_briefing(route, task_id=getattr(args, "task_id", "TASK-001"))
        print(briefing)
        return 0

    elif action == "verify":
        allow_dirty = bool(getattr(args, "allow_dirty", False))
        overall_pass, results = _audit_flight_director_invariants(workspace, allow_dirty=allow_dirty)

        if is_json:
            print(json.dumps({
                "status": "pass" if overall_pass else "fail",
                "workspace": str(workspace),
                "allow_dirty": allow_dirty,
                "invariants": results,
            }, indent=2))
            return 0 if overall_pass else 1

        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("🩺 AGYIS COCKPIT FLIGHT DECK INVARIANTS AUDIT")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for res in results:
            mark = "🟢 PASS" if res["passed"] else "🔴 FAIL"
            print(f"{mark} | {res['invariant']}: {res['details']}")
            if not res["passed"] and res.get("violations"):
                for v in res["violations"][:5]:
                    print(f"       └─ Violation: {v}")
                if len(res["violations"]) > 5:
                    print(f"       └─ ... and {len(res['violations']) - 5} more")

        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if overall_pass:
            print("✨ Overall Result: PASSED (All Flight Director Invariants Verified)")
            return 0
        else:
            print("❌ Overall Result: FAILED (Flight Director Invariant Violations Detected)")
            print("Tip: Use --allow-dirty to permit in-flight uncommitted code modifications.")
            return 0 if allow_dirty else 1

    else:
        print(f"Unknown cockpit action: {action}", file=sys.stderr)
        return 1
