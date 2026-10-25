# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
High-level system and harness status CLI command (ADR-014).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import harness
from harness.commands.subagents import format_subagents_table
from harness.runtime import doctor as psl_doctor

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "telemetry.db"


def cmd_status(args: argparse.Namespace) -> int:
    """Prints a high-level status summary of the Agyis Harness."""
    print("=" * 70)
    print(f" 🛡️ Agyis Harness for Google Antigravity™ (v{harness.__version__})")
    print("=" * 70)
    print(f" Repository Root: {REPO_ROOT}")
    print(f" Platform:        {sys.platform} (Python {sys.version.split()[0]})")
    herm_py = psl_doctor.find_hermetic_uv_python()
    if herm_py:
        print(f" Hermetic Python: {herm_py} (Ready)")
    else:
        print(" Hermetic Python: Not found in uv cache")

    from harness.skills import list_skills
    from harness.subagents import list_active_subagent_statuses, list_agent_specs

    skills = list_skills()
    agents = list_agent_specs()
    active_subagents = list_active_subagent_statuses()
    print(f" Modular Skills:  {len(skills)} installed")
    print(
        f" Subagents:       {len(agents)} registered ({', '.join(a.archetype.value for a in agents)})"
    )

    # Quick count of telemetry
    if DEFAULT_DB.exists():
        from harness.telemetry.db import get_db_connection
        import sqlite3

        try:
            conn = get_db_connection(DEFAULT_DB)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM sessions")
            sess_cnt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM steps")
            step_cnt = c.fetchone()[0]
            conn.close()
            print(f" Telemetry DB:    {DEFAULT_DB.name} ({sess_cnt:,} sessions, {step_cnt:,} steps)")
        except (sqlite3.Error, OSError):
            print(f" Telemetry DB:    {DEFAULT_DB.name} (present)")
    else:
        print(" Telemetry DB:    Not initialized")

    print("-" * 70)
    print(" Active Lifecycle Hooks:")
    print("   ✔ command-safety   (PreToolUse: CPython 3.12, f-string, grep sanitization)")
    print("   ✔ anti-loop        (PreToolUse: repetitive tool call breaker)")
    print("   ✔ output-compactor (PostToolUse: deterministic 2KB output truncation)")
    print("   ✔ verification-fence (Stop: unverified code edit completion guard)")
    print("   ✔ anti-drift       (PreToolUse: plan boundary & cognitive anchor gate)")
    print("   ✔ token-proximity (PreToolUse: proactive token urgency monitor & alert)")
    print("-" * 70)
    print(" Cognitive Attention Horizon Gauge:")
    print("   🟢 Healthy Zone: <50k tokens / <50 steps (High Attention Aperture)")
    print("   🟡 Amber Zone:   50k–100k tokens / 50–100 steps (Attention Compaction Advised)")
    print("   🔴 Red Alert:    >100k tokens / >100 steps (Context Cliff Active)")
    try:
        import os
        from harness.hooks.token_proximity_guard import (
            format_terminal_gauge,
            get_active_conversation_tokens,
            get_conversations_dir,
        )
        conv_id = os.environ.get("ANTIGRAVITY_CONVERSATION_ID") or os.environ.get("CONVERSATION_ID")
        tokens = 0
        if conv_id:
            tokens = get_active_conversation_tokens(conv_id)
        else:
            conv_dir = get_conversations_dir()
            if conv_dir.is_dir():
                dbs = sorted([f for f in conv_dir.glob("*.db") if not f.name.endswith(".tmp")], key=lambda f: f.stat().st_mtime, reverse=True)
                if dbs:
                    tokens = get_active_conversation_tokens(dbs[0].stem)
        if tokens > 0:
            print(f"   📊 Active Session: {format_terminal_gauge(tokens)}")
    except Exception:
        pass
    print("-" * 70)
    print(" Specialist Subagents:")
    for ag in agents:
        caps = ["write" if ag.can_write else "read-only"]
        if ag.can_execute:
            caps.append("exec")
        print(f"   ✔ {ag.name:<18} ({ag.role}) [{' | '.join(caps)}]")
    print("-" * 70)
    print(" Modular Skills:")
    for sk in skills:
        print(f"   ✔ {sk.name:<22} - {sk.description[:42]}...")
    try:
        from harness.subagents.heartbeat import read_stage_heartbeat
        workspace_dir = getattr(args, "workspace_dir", None)
        heartbeat = read_stage_heartbeat(workspace_dir=workspace_dir)
    except Exception:
        heartbeat = None

    if active_subagents:
        print("-" * 70)
        print(f" Live Active Subagents ({len(active_subagents)} active):")
        for line in format_subagents_table(active_subagents, heartbeat=heartbeat).splitlines():
            print(f"   {line}")

    if heartbeat and not heartbeat.get("is_stale", False) and heartbeat.get("status") in {"dispatched", "in_progress", "verifying"}:
        print("-" * 70)
        print(" Active Subagent Ladder Stage:")
        stage_val = heartbeat.get("stage", "executioner")
        active_id = heartbeat.get("active_agent_id", "")
        subagent_role = heartbeat.get("subagent_role", "")

        STAGE_DISPLAY_MAP = {
            "coordinator": "Stage 0: Coordinator",
            "executioner": "Stage 1: Executioner",
            "hammer": "Stage 2: The Hammer",
            "custodian": "Stage 3: Workspace Custodian",
            "auditor": "Stage 4: Victory Auditor",
        }
        if subagent_role and "Stage " in subagent_role:
            if active_id and active_id not in subagent_role:
                stage_display = f"{subagent_role} ({active_id})"
            else:
                stage_display = subagent_role
        else:
            base_stage = STAGE_DISPLAY_MAP.get(stage_val.lower(), f"Stage: {stage_val.title()}")
            stage_display = f"{base_stage} ({active_id})" if active_id else base_stage

        task_id = heartbeat.get("task_id", "N/A")
        step_count = heartbeat.get("step_count", 0)
        elapsed_s = float(heartbeat.get("elapsed_s", 0.0))
        if elapsed_s >= 60:
            m = int(elapsed_s // 60)
            s = int(elapsed_s % 60)
            elapsed_str = f"{elapsed_s:.1f}s ({m}m {s}s)"
        else:
            elapsed_str = f"{elapsed_s:.1f}s"

        last_action = heartbeat.get("last_action", "N/A")
        status_name = heartbeat.get("status", "in_progress").upper()
        age_s = int(round(heartbeat.get("heartbeat_age_s", 0.0)))
        status_line = f"🟢 {status_name} (Heartbeat {age_s}s ago)"

        print(f"   Stage:         {stage_display}")
        print(f"   Task ID:       {task_id}")
        print(f"   Step Count:    {step_count} steps")
        print(f"   Elapsed Time:  {elapsed_str}")
        print(f"   Last Action:   {last_action}")
        print(f"   Status:        {status_line}")
        print("-" * 70)

    print("=" * 70)
    return 0
