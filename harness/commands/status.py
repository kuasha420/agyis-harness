# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
High-level system and harness status CLI command (ADR-014).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List

import harness
from harness.commands.subagents import format_subagents_table
from harness.runtime import doctor as psl_doctor

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "telemetry.db"
_logger = logging.getLogger(__name__)

_HOOK_DESCRIPTIONS: Dict[str, str] = {
    "command-safety": "CPython 3.12, pager, grep/diff sanitization",
    "anti-loop": "repetitive tool call & polling breaker",
    "compactor": "deterministic 2KB command / 32KB file compaction",
    "verification-fence": "unverified code/spec edit completion guard",
    "post-verification-fence": "verification command pass/fail state updater",
    "anti-drift": "plan boundary, flight-director & auditor write guard",
    "token-proximity": "proactive token horizon urgency monitor",
    "pre-invocation": "PreInvocation compaction & role-pinning advisory",
}


def _load_live_hooks_summary() -> tuple[List[str], List[Dict[str, Any]]]:
    """Reads live lifecycle hooks dynamically from harness/hooks/hooks.json (PSL-INV-007)."""
    candidates = [
        Path(__file__).resolve().parent.parent / "hooks" / "hooks.json",
        REPO_ROOT / "hooks.json",
    ]
    hooks_file = next((p for p in candidates if p.is_file()), None)
    if hooks_file is None:
        return [], []

    try:
        raw = json.loads(hooks_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("Failed to parse hooks.json at %s: %s", hooks_file, exc)
        return [], []

    if not isinstance(raw, dict):
        return [], []

    checks: List[str] = []
    blocks: List[Dict[str, Any]] = []
    seen_checks: set[str] = set()

    for block_name, events_map in raw.items():
        if not isinstance(events_map, dict):
            continue
        block_events: List[str] = []
        block_checks: List[str] = []
        for event_name, entries in events_map.items():
            if not isinstance(entries, list):
                continue
            block_events.append(str(event_name))
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for hook_def in entry.get("hooks", []) or []:
                    if not isinstance(hook_def, dict):
                        continue
                    cmd = str(hook_def.get("command", "")).strip()
                    if not cmd:
                        continue
                    check_name = cmd.split()[-1]
                    if check_name not in block_checks:
                        block_checks.append(check_name)
                    if check_name not in seen_checks:
                        seen_checks.add(check_name)
                        checks.append(check_name)
        blocks.append({
            "name": str(block_name),
            "events": block_events,
            "checks": block_checks,
        })
    return checks, blocks


def cmd_status(args: argparse.Namespace) -> int:
    """Prints a high-level status summary of the Agyis Harness."""
    if getattr(args, "json", False):
        herm_py = psl_doctor.find_hermetic_uv_python()
        from harness.skills import list_skills
        from harness.subagents import list_active_subagent_statuses, list_agent_specs

        skills = list_skills()
        agents = list_agent_specs()
        active_subagents = list_active_subagent_statuses()

        from harness.telemetry.config import resolve_db_path
        from harness.telemetry.sync.daemon import compute_telemetry_lag, read_sync_status

        db_target = DEFAULT_DB if DEFAULT_DB.exists() else resolve_db_path(must_exist=False)
        sync_payload: Dict[str, Any] = {
            "status": "not_initialized",
            "db_present": db_target.exists(),
        }
        if db_target.exists():
            import sqlite3
            from harness.telemetry.db import get_db_connection

            sync_payload["db_path"] = str(db_target)
            try:
                conn = get_db_connection(db_target)
                c = conn.cursor()
                c.execute("SELECT COUNT(*), MAX(end_time) FROM sessions")
                sess_row = c.fetchone()
                sess_cnt, last_end = (sess_row[0], sess_row[1]) if sess_row else (0, None)
                c.execute("SELECT COUNT(*) FROM steps")
                step_cnt = c.fetchone()[0]
                try:
                    c.execute("SELECT COUNT(*) FROM tool_calls")
                    tc_cnt = c.fetchone()[0]
                except sqlite3.Error:
                    tc_cnt = 0
                conn.close()
                sync_payload["sessions_count"] = sess_cnt
                sync_payload["steps_count"] = step_cnt
                sync_payload["tool_calls_count"] = tc_cnt
                sync_payload["last_session_end"] = str(last_end) if last_end else None
            except (sqlite3.Error, OSError):
                pass

        try:
            sync_st = read_sync_status()
            lag = compute_telemetry_lag(db_path=db_target)
            sync_payload["status"] = sync_st.get("status", "idle")
            sync_payload["last_harvest_at"] = str(sync_st.get("last_harvest_at")) if sync_st.get("last_harvest_at") else None
            sync_payload["consecutive_failures"] = sync_st.get("consecutive_failures", 0)
            sync_payload["unsynced_local"] = lag.get("unsynced_local", 0)
            sync_payload["stale_local"] = lag.get("stale_local", 0)
            sync_payload["total_transcripts"] = lag.get("total_transcripts", 0)
            sync_payload["last_error"] = sync_st.get("last_error")
        except (OSError, ValueError, RuntimeError) as exc:
            _logger.debug("Telemetry sync lag status unavailable: %s", exc)

        import os
        from harness.hooks.token_proximity_guard import (
            AMBER_THRESHOLD,
            COMPACTION_THRESHOLD,
            CONTEXT_WINDOW_TOKENS,
            RED_THRESHOLD,
            get_active_conversation_context_window,
            get_active_conversation_token_velocity,
            get_active_conversation_tokens,
            get_conversations_dir,
        )
        from harness.utils.context import get_active_conversation_id

        conv_id = get_active_conversation_id(check_presence=True) or os.environ.get("CONVERSATION_ID")
        if not conv_id:
            conv_dir = get_conversations_dir()
            if conv_dir.is_dir():
                dbs = sorted([f for f in conv_dir.glob("*.db") if not f.name.endswith(".tmp")], key=lambda f: f.stat().st_mtime, reverse=True)
                if dbs:
                    conv_id = dbs[0].stem

        ctx_win = get_active_conversation_context_window(conv_id) if conv_id else {
            "tokens": 0,
            "max_context_tokens": CONTEXT_WINDOW_TOKENS,
            "amber_threshold": AMBER_THRESHOLD,
            "red_threshold": RED_THRESHOLD,
            "compaction_threshold": COMPACTION_THRESHOLD,
        }
        max_ctx = int(ctx_win.get("max_context_tokens") or CONTEXT_WINDOW_TOKENS)
        amber_t = int(ctx_win.get("amber_threshold") or AMBER_THRESHOLD)
        red_t = int(ctx_win.get("red_threshold") or RED_THRESHOLD)
        comp_t = int(ctx_win.get("compaction_threshold") or COMPACTION_THRESHOLD)

        vel = get_active_conversation_token_velocity(conv_id) if conv_id else {}
        tokens = vel.get("tokens", 0) or ctx_win.get("tokens", 0)
        if tokens <= 0 and conv_id:
            tokens = get_active_conversation_tokens(conv_id)
        burn_rate = vel.get("burn_rate_tokens_per_min", 0.0)
        mins_to_comp = vel.get("mins_to_compaction") or vel.get("mins_to_50k")
        vel_tier = vel.get("velocity_tier", "SAFE")

        token_metrics = {
            "active_tokens": tokens,
            "max_context_tokens": max_ctx,
            "amber_threshold": amber_t,
            "red_threshold": red_t,
            "compaction_threshold": comp_t,
            "burn_rate_tokens_per_min": burn_rate,
            "mins_to_compaction": mins_to_comp,
            "velocity_tier": vel_tier,
            "conversation_id": conv_id,
        }

        try:
            from harness.subagents.heartbeat import read_stage_heartbeat
            workspace_dir = getattr(args, "workspace_dir", None)
            heartbeat = read_stage_heartbeat(workspace_dir=workspace_dir)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _logger.debug("Stage heartbeat unavailable: %s", exc)
            heartbeat = None

        live_hook_checks, live_hook_blocks = _load_live_hooks_summary()

        report = {
            "version": harness.__version__,
            "repository_root": str(REPO_ROOT),
            "platform": f"{sys.platform} (Python {sys.version.split()[0]})",
            "hermetic_python": str(herm_py) if herm_py else None,
            "skills_count": len(skills),
            "subagents_count": len(agents),
            "telemetry_sync": sync_payload,
            "active_hooks": live_hook_checks,
            "hook_blocks": live_hook_blocks,
            "token_metrics": token_metrics,
            "tokens": tokens,
            "max_context_tokens": max_ctx,
            "active_subagents_count": len(active_subagents),
            "heartbeat": heartbeat,
        }
        print(json.dumps(report, indent=2))
        return 0

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

    # Quick count of telemetry + daemon sync health/lag
    from harness.telemetry.config import resolve_db_path
    from harness.telemetry.sync.daemon import compute_telemetry_lag, read_sync_status

    db_target = DEFAULT_DB if DEFAULT_DB.exists() else resolve_db_path(must_exist=False)
    if db_target.exists():
        from harness.telemetry.db import get_db_connection
        import sqlite3

        try:
            conn = get_db_connection(db_target)
            c = conn.cursor()
            c.execute("SELECT COUNT(*), MAX(end_time) FROM sessions")
            sess_row = c.fetchone()
            sess_cnt, last_end = (sess_row[0], sess_row[1]) if sess_row else (0, None)
            c.execute("SELECT COUNT(*) FROM steps")
            step_cnt = c.fetchone()[0]
            try:
                c.execute("SELECT COUNT(*) FROM tool_calls")
                tc_cnt = c.fetchone()[0]
            except sqlite3.Error:
                tc_cnt = 0
            conn.close()
            end_part = f", last={str(last_end)[:19]}" if last_end else ""
            print(f" Telemetry DB:    {db_target.name} ({sess_cnt:,} sessions, {step_cnt:,} steps, {tc_cnt:,} tools{end_part})")
        except (sqlite3.Error, OSError):
            print(f" Telemetry DB:    {db_target.name} (present)")
    else:
        print(" Telemetry DB:    Not initialized")

    try:
        sync_st = read_sync_status()
        lag = compute_telemetry_lag(db_path=db_target)
        lag_parts = []
        if sync_st.get("status"):
            lag_parts.append(f"state={sync_st['status']}")
        if sync_st.get("last_harvest_at"):
            lag_parts.append(f"last_harvest={str(sync_st['last_harvest_at'])[:19]}")
        if sync_st.get("consecutive_failures"):
            lag_parts.append(f"failures={sync_st['consecutive_failures']}")
        unsynced, stale = lag.get("unsynced_local", 0), lag.get("stale_local", 0)
        if unsynced or stale:
            lag_parts.append(f"lag={unsynced} unsynced / {stale} stale")
        elif lag.get("total_transcripts"):
            lag_parts.append("lag=0 (up-to-date)")
        if sync_st.get("last_error"):
            lag_parts.append(f"last_err={str(sync_st['last_error'])[:60]}")
        if lag_parts:
            print(f" Telemetry Sync:  {', '.join(lag_parts)}")
    except (OSError, ValueError, RuntimeError) as exc:
        _logger.debug("Telemetry sync lag unavailable: %s", exc)

    live_hook_checks, live_hook_blocks = _load_live_hooks_summary()
    print("-" * 70)
    print(f" Active Lifecycle Hooks ({len(live_hook_blocks)} blocks / {len(live_hook_checks)} checks from hooks.json):")
    if live_hook_blocks:
        for blk in live_hook_blocks:
            events_str = "/".join(blk["events"]) or "unknown"
            checks_str = ", ".join(blk["checks"])
            desc = "; ".join(
                _HOOK_DESCRIPTIONS[c] for c in blk["checks"] if c in _HOOK_DESCRIPTIONS
            )
            detail = f"{events_str}: {desc}" if desc else events_str
            print(f"   ✔ {checks_str:<24} ({detail})")
    else:
        print("   ⚠ No hooks loaded from hooks.json")
    print("-" * 70)
    try:
        import os
        from harness.hooks.token_proximity_guard import (
            AMBER_THRESHOLD,
            COMPACTION_THRESHOLD,
            CONTEXT_WINDOW_TOKENS,
            MAX_SAFE_BURN_RATE_PER_MIN,
            RED_THRESHOLD,
            format_terminal_gauge,
            get_active_conversation_context_window,
            get_active_conversation_token_velocity,
            get_active_conversation_tokens,
            get_conversations_dir,
        )
        from harness.utils.context import detect_presence_conversation_id, get_active_conversation_id

        conv_id = get_active_conversation_id() or os.environ.get("CONVERSATION_ID")
        conv_source = "env" if conv_id else ""
        conv_dir = get_conversations_dir()
        if not conv_id:
            presence_cid = detect_presence_conversation_id()
            if presence_cid and (conv_dir / f"{presence_cid}.db").is_file():
                conv_id = presence_cid
                conv_source = "presence"
        if not conv_id:
            if conv_dir.is_dir():
                dbs = sorted([f for f in conv_dir.glob("*.db") if not f.name.endswith(".tmp")], key=lambda f: f.stat().st_mtime, reverse=True)
                if dbs:
                    conv_id = dbs[0].stem
                    conv_source = "fallback: newest mtime"
        ctx_win = get_active_conversation_context_window(conv_id) if conv_id else {
            "tokens": 0,
            "max_context_tokens": CONTEXT_WINDOW_TOKENS,
            "amber_threshold": AMBER_THRESHOLD,
            "red_threshold": RED_THRESHOLD,
            "compaction_threshold": COMPACTION_THRESHOLD,
        }
        max_ctx = int(ctx_win.get("max_context_tokens") or CONTEXT_WINDOW_TOKENS)
        amber_t = int(ctx_win.get("amber_threshold") or AMBER_THRESHOLD)
        red_t = int(ctx_win.get("red_threshold") or RED_THRESHOLD)
        comp_t = int(ctx_win.get("compaction_threshold") or COMPACTION_THRESHOLD)
        win_label = f"{max_ctx // 1_000_000}M" if (max_ctx >= 1_000_000 and max_ctx % 1_000_000 == 0) else f"{int(round(max_ctx / 1000))}k"
        amber_k = int(round(amber_t / 1000))
        red_k = int(round(red_t / 1000))

        print(f" Cognitive Attention Horizon Gauge ({win_label} Model Context Window):")
        print(f"   🟢 Healthy Zone: <{amber_k}k tokens (Nominal / High Attention Aperture)")
        print(f"   🟡 Amber Zone:   {amber_k}k–{red_k}k tokens (Attention Compaction Advised)")
        print(f"   🔴 Red Alert:    >={red_k}k tokens (Compaction Imminent, {win_label} Context Window)")

        if conv_id:
            vel = get_active_conversation_token_velocity(conv_id)
            tokens = vel.get("tokens", 0) or ctx_win.get("tokens", 0)
            if tokens <= 0:
                tokens = get_active_conversation_tokens(conv_id)
            burn_rate = vel.get("burn_rate_tokens_per_min", 0.0)
            mins_to_comp = vel.get("mins_to_compaction") or vel.get("mins_to_50k")
            vel_tier = vel.get("velocity_tier", "SAFE")
            if tokens > 0 or burn_rate > 0:
                gauge = format_terminal_gauge(
                    tokens,
                    threshold=max_ctx,
                    burn_rate=burn_rate,
                    mins_to_compaction=mins_to_comp,
                    velocity_tier=vel_tier if burn_rate >= MAX_SAFE_BURN_RATE_PER_MIN else None,
                    amber_threshold=amber_t,
                    red_threshold=red_t,
                    compaction_threshold=comp_t,
                )
                conv_label = f"{conv_id} | {conv_source}" if conv_source == "fallback: newest mtime" else conv_id
                print(f"   📊 Active Session ({conv_label}): {gauge}")
    except Exception:
        from harness.trajectory.health import AMBER_THRESHOLD, CONTEXT_WINDOW_TOKENS, RED_THRESHOLD

        win_k = int(round(CONTEXT_WINDOW_TOKENS / 1000))
        amber_k = int(round(AMBER_THRESHOLD / 1000))
        red_k = int(round(RED_THRESHOLD / 1000))
        print(f" Cognitive Attention Horizon Gauge ({win_k}k Default / 512k-1M Model-Scaled Context Window):")
        print(f"   🟢 Healthy Zone: <{amber_k}k tokens (Nominal / High Attention Aperture)")
        print(f"   🟡 Amber Zone:   {amber_k}k–{red_k}k tokens (Attention Compaction Advised)")
        print(f"   🔴 Red Alert:    >={red_k}k tokens (Compaction Imminent, {win_k}k Default Window)")
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
