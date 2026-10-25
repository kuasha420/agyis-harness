# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Compaction Checkpoint Engine & CLI Command Suite (ADR-031 / Issue #77).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional

from harness.delivery import (
    collect_active_subagents,
    generate_compaction_checkpoint,
    inspect_git_state,
)


def cmd_checkpoint(args: argparse.Namespace) -> int:
    """
    Handles `agyis checkpoint` subcommands:
    - generate (default): Assembles and writes pre-compaction checkpoint artifact.
    - verify: Asserts latest checkpoint presence and freshness within --max-age-mins.
    - status: Reports token proximity, active subagents, git dirty status, and latest checkpoint.
    """
    action = getattr(args, "checkpoint_action", None) or "generate"
    ws_val = getattr(args, "workspace", None)
    workspace = Path(ws_val).resolve() if ws_val else Path.cwd().resolve()
    is_json = bool(getattr(args, "json", False))

    if action == "generate":
        plan_path = getattr(args, "plan", None)
        out_path = getattr(args, "out", None)
        role = getattr(args, "role", None) or os.environ.get("AGYIS_ROLE", "agyis_coordinator")
        trigger_tokens = getattr(args, "trigger_tokens", 230_000)

        res = generate_compaction_checkpoint(
            workspace_dir=workspace,
            orchestrator_role=role,
            trigger_tokens=trigger_tokens,
            plan_path=plan_path,
            output_path=out_path,
        )

        if is_json:
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "output_path": str(res.output_path),
                        "latest_path": str(res.latest_path),
                        "elapsed_ms": round(res.elapsed_ms, 2),
                        "content_bytes": len(res.content),
                    }
                )
            )
        else:
            print("✔ Compaction Checkpoint Generated")
            print(f"  Artifact:   {res.output_path} ({len(res.content):,} bytes)")
            print(f"  Latest:     {res.latest_path}")
            print(f"  Latency:    {res.elapsed_ms:.2f} ms")
        return 0

    elif action == "verify":
        max_age_mins = getattr(args, "max_age_mins", 60)
        try:
            max_age_mins_val = float(max_age_mins)
        except (ValueError, TypeError):
            max_age_mins_val = 60.0

        max_age_seconds = max_age_mins_val * 60.0
        latest_file = workspace / ".agents" / "artifacts" / "compaction_checkpoint_latest.md"

        if not latest_file.is_file():
            if is_json:
                print(
                    json.dumps(
                        {
                            "status": "missing",
                            "checkpoint_path": None,
                            "age_seconds": None,
                            "max_age_seconds": max_age_seconds,
                            "valid": False,
                        }
                    )
                )
            else:
                print(f"❌ No latest checkpoint found at: {latest_file}")
            return 1

        try:
            mtime = latest_file.stat().st_mtime
            age_seconds = time.time() - mtime
        except OSError:
            age_seconds = 0.0

        valid = age_seconds <= max_age_seconds
        status_str = "ok" if valid else "stale"

        if is_json:
            print(
                json.dumps(
                    {
                        "status": status_str,
                        "checkpoint_path": str(latest_file),
                        "age_seconds": round(age_seconds, 2),
                        "max_age_seconds": max_age_seconds,
                        "valid": valid,
                    }
                )
            )
        else:
            if valid:
                print(
                    f"✔ Checkpoint verified: {latest_file} (age: {age_seconds / 60.0:.1f}m, max: {max_age_mins_val:.1f}m)"
                )
            else:
                print(
                    f"⚠️ Checkpoint is stale: {latest_file} (age: {age_seconds / 60.0:.1f}m > max: {max_age_mins_val:.1f}m)"
                )
        return 0 if valid else 1

    elif action == "status":
        latest_file = workspace / ".agents" / "artifacts" / "compaction_checkpoint_latest.md"
        checkpoint_present = latest_file.is_file()
        checkpoint_age_seconds: Optional[float] = None
        checkpoint_path: Optional[str] = None
        if checkpoint_present:
            checkpoint_path = str(latest_file)
            try:
                checkpoint_age_seconds = round(time.time() - latest_file.stat().st_mtime, 2)
            except OSError:
                checkpoint_age_seconds = 0.0

        git_state = inspect_git_state(workspace)
        subagents = collect_active_subagents(workspace)

        session_id = os.environ.get(
            "AGYIS_CONVERSATION_ID", os.environ.get("GEMINI_CONVERSATION_ID", "")
        )
        tokens = 0
        if os.environ.get("AGYIS_CURRENT_TOKENS"):
            try:
                tokens = int(os.environ["AGYIS_CURRENT_TOKENS"])
            except ValueError:
                tokens = 0
        elif session_id:
            try:
                from harness.hooks.token_proximity_guard import get_active_conversation_tokens

                tokens = get_active_conversation_tokens(session_id)
            except Exception:
                tokens = 0

        trigger_threshold = getattr(args, "trigger_tokens", 230_000)
        proximity_pct = (
            round((tokens / trigger_threshold * 100.0), 2) if trigger_threshold > 0 else 0.0
        )

        if is_json:
            data: Dict[str, Any] = {
                "tokens": {
                    "current": tokens,
                    "trigger_threshold": trigger_threshold,
                    "proximity_pct": proximity_pct,
                },
                "subagents": {
                    "active_count": len(subagents),
                    "entries": [
                        {
                            "conversation_id": s.conversation_id,
                            "role": s.role,
                            "step_count": s.step_count,
                            "token_count": s.token_count,
                            "health_zone": s.health_zone,
                            "recommendation": s.recommendation,
                        }
                        for s in subagents
                    ],
                },
                "git": {
                    "branch": git_state.branch,
                    "commit": git_state.commit_short,
                    "is_dirty": git_state.is_dirty,
                    "modified_files_count": len(git_state.modified_files),
                    "untracked_files_count": len(git_state.untracked_files),
                },
                "checkpoint": {
                    "present": checkpoint_present,
                    "path": checkpoint_path,
                    "age_seconds": checkpoint_age_seconds,
                },
            }
            print(json.dumps(data, indent=2))
        else:
            print("=" * 60)
            print(" 🧭 Agyis Compaction & Checkpoint Status")
            print("=" * 60)
            print(f" Token Level:       {tokens:,} / {trigger_threshold:,} ({proximity_pct}%)")
            git_badge = "🔴 DIRTY" if git_state.is_dirty else "🟢 CLEAN"
            print(f" Git Working Tree:  {git_state.branch} @ {git_state.commit_short} ({git_badge})")
            print(f" Active Subagents:  {len(subagents)}")
            if checkpoint_present and checkpoint_age_seconds is not None:
                age_min = checkpoint_age_seconds / 60.0
                print(f" Latest Checkpoint: {checkpoint_path} (age: {age_min:.1f}m)")
            else:
                print(
                    " Latest Checkpoint: None found (.agents/artifacts/compaction_checkpoint_latest.md)"
                )
            print("=" * 60)
        return 0

    return 0
