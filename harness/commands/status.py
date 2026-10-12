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
    """Prints a high-level status summary of the PSL Harness."""
    print("=" * 70)
    print(f" 🐾 PSL Harness for Google Antigravity™ (v{harness.__version__})")
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
        import sqlite3

        try:
            conn = sqlite3.connect(DEFAULT_DB)
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
    print("-" * 70)
    print(" Cognitive Attention Horizon Gauge:")
    print("   🟢 Healthy Zone: <50k tokens / <50 steps (High Attention Aperture)")
    print("   🟡 Amber Zone:   50k–100k tokens / 50–100 steps (Attention Compaction Advised)")
    print("   🔴 Red Alert:    >100k tokens / >100 steps (Context Cliff Active)")
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
    if active_subagents:
        print("-" * 70)
        print(f" Live Active Subagents ({len(active_subagents)} active):")
        for line in format_subagents_table(active_subagents).splitlines():
            print(f"   {line}")
    print("=" * 70)
    return 0
