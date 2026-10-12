#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness for Google Antigravity™
Live Session Telemetry & Topology Analyzer

Deeply analyzes an active or completed conversation trajectory:
- Discovers spawned child subagents and builds session lineage
- Computes character volumes and estimated token metrics (both truncated & full)
- Evaluates tool distributions, error rates, and failure patterns
- Calculates cognitive isolation efficiency and Subagent Ladder offload ratios
- Emits structured JSON and optional telemetry.db ingestion
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import glob
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from harness.utils.tokens import estimate_tokens


def find_latest_session_dir() -> Optional[Path]:
    brain_root = Path.home() / ".gemini" / "antigravity" / "brain"
    pattern = str(brain_root / "*" / ".system_generated" / "logs" / "transcript.jsonl")
    matches = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
    if not matches:
        return None
    # Return the session directory (e.g. brain/<session_id>)
    return Path(matches[0]).parents[2]


def find_session_dir(session_id: str) -> Optional[Path]:
    """Locates the directory for a specific session ID under ~/.gemini/antigravity/brain."""
    brain_root = Path.home() / ".gemini" / "antigravity" / "brain"
    target = brain_root / session_id
    if target.is_dir():
        return target
    return None


def parse_transcript_lines(transcript_path: Path) -> List[Dict[str, Any]]:
    if not transcript_path.exists():
        return []
    lines: List[Dict[str, Any]] = []
    with open(transcript_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                continue
    return lines


def discover_child_subagents(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    subagents: List[Dict[str, Any]] = []
    pending_prompt = ""
    pending_role = ""
    pending_type = ""

    for s in steps:
        # Check tool calls for invoke_subagent
        for tc in s.get("tool_calls", []):
            if tc.get("name") == "invoke_subagent":
                args = tc.get("args", {})
                subs = args.get("Subagents", [])
                if isinstance(subs, str):
                    try:
                        subs = json.loads(subs)
                    except Exception:
                        subs = []
                if isinstance(subs, list) and subs:
                    sub0 = subs[0]
                    if isinstance(sub0, str):
                        try:
                            sub0 = json.loads(sub0)
                        except Exception:
                            sub0 = {}
                    if isinstance(sub0, dict):
                        pending_role = sub0.get("Role", "")
                        pending_type = sub0.get("TypeName", "")
                        pending_prompt = sub0.get("Prompt", "")

        # Check tool responses for conversationId
        content = s.get("content", "")
        if s.get("type") == "GENERIC" and "Created the following subagents" in content:
            # Parse conversationId
            match = re.search(r'"conversationId":\s*"([a-f0-9\-]+)"', content)
            if match:
                conv_id = match.group(1)
                subagents.append({
                    "conversation_id": conv_id,
                    "role": pending_role or "Subagent",
                    "type": pending_type,
                    "prompt_snippet": pending_prompt[:120].strip() if pending_prompt else "",
                    "created_at": s.get("created_at")
                })
                pending_role = ""
                pending_type = ""
                pending_prompt = ""

    return subagents


def analyze_transcript(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    step_types = Counter()
    sources = Counter()
    tools = Counter()
    tool_errors = 0
    content_chars = 0
    thinking_chars = 0
    start_time = None
    end_time = None

    tool_details: List[Dict[str, Any]] = []

    for s in steps:
        t = s.get("type", "UNKNOWN")
        step_types[t] += 1
        src = s.get("source", "UNKNOWN")
        sources[src] += 1

        ts = s.get("created_at")
        if ts:
            if not start_time:
                start_time = ts
            end_time = ts

        content = s.get("content", "") or ""
        thinking = s.get("thinking", "") or ""
        content_chars += len(content)
        thinking_chars += len(thinking)

        if s.get("status") == "ERROR" or t == "ERROR_MESSAGE":
            tool_errors += 1

        for tc in s.get("tool_calls", []):
            name = tc.get("name", "UNKNOWN")
            tools[name] += 1
            args = tc.get("args", {})
            tool_details.append({
                "step_index": s.get("step_index"),
                "name": name,
                "summary": args.get("toolSummary", ""),
                "action": args.get("toolAction", ""),
            })

    duration_s = 0.0
    if start_time and end_time:
        try:
            t0 = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            duration_s = max(0.0, (t1 - t0).total_seconds())
        except Exception:
            pass

    total_chars = content_chars + thinking_chars

    return {
        "total_steps": len(steps),
        "duration_seconds": round(duration_s, 1),
        "start_time": start_time,
        "end_time": end_time,
        "step_types": dict(step_types),
        "sources": dict(sources),
        "tool_call_count": sum(tools.values()),
        "tool_distribution": dict(tools.most_common()),
        "tool_errors": tool_errors,
        "content_chars": content_chars,
        "thinking_chars": thinking_chars,
        "total_chars": total_chars,
        "estimated_tokens": estimate_tokens(total_chars),
        "estimated_thinking_tokens": estimate_tokens(thinking_chars),
        "estimated_content_tokens": estimate_tokens(content_chars),
    }


def analyze_session(session_dir: Path) -> Dict[str, Any]:
    session_id = session_dir.name
    logs_dir = session_dir / ".system_generated" / "logs"
    transcript_path = logs_dir / "transcript.jsonl"
    full_transcript_path = logs_dir / "transcript_full.jsonl"

    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcript not found at {transcript_path}")

    steps = parse_transcript_lines(transcript_path)
    full_steps = parse_transcript_lines(full_transcript_path) if full_transcript_path.exists() else []

    coord_summary = analyze_transcript(steps)
    full_summary = analyze_transcript(full_steps) if full_steps else coord_summary

    # Discover linked subagents
    child_refs = discover_child_subagents(steps)
    subagents_analysis: List[Dict[str, Any]] = []

    brain_root = session_dir.parent
    for ref in child_refs:
        cid = ref["conversation_id"]
        sub_dir = brain_root / cid
        sub_log = sub_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
        if not sub_log.exists():
            sub_log = sub_dir / ".system_generated" / "logs" / "transcript.jsonl"

        if sub_log.exists():
            sub_steps = parse_transcript_lines(sub_log)
            sub_metrics = analyze_transcript(sub_steps)
            subagents_analysis.append({
                "conversation_id": cid,
                "role": ref["role"],
                "type": ref["type"],
                "metrics": sub_metrics,
            })

    # Calculate collective / ladder offload metrics
    subagent_steps = sum(sa["metrics"]["total_steps"] for sa in subagents_analysis)
    subagent_tools = sum(sa["metrics"]["tool_call_count"] for sa in subagents_analysis)
    subagent_tokens = sum(sa["metrics"]["estimated_tokens"] for sa in subagents_analysis)

    total_pipeline_steps = coord_summary["total_steps"] + subagent_steps
    total_pipeline_tools = coord_summary["tool_call_count"] + subagent_tools
    total_pipeline_tokens = full_summary["estimated_tokens"] + subagent_tokens

    offload_step_pct = round((subagent_steps / max(1, total_pipeline_steps)) * 100, 1)
    offload_tool_pct = round((subagent_tools / max(1, total_pipeline_tools)) * 100, 1)
    offload_token_pct = round((subagent_tokens / max(1, total_pipeline_tokens)) * 100, 1)

    return {
        "session_id": session_id,
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "coordinator": {
            "compacted_transcript": coord_summary,
            "full_transcript": full_summary,
            "compaction_savings_chars": full_summary["total_chars"] - coord_summary["total_chars"],
            "compaction_savings_pct": round(
                ((full_summary["total_chars"] - coord_summary["total_chars"]) / max(1, full_summary["total_chars"])) * 100, 1
            ),
        },
        "subagents": subagents_analysis,
        "collective_pipeline": {
            "total_steps": total_pipeline_steps,
            "total_tools": total_pipeline_tools,
            "total_tokens": total_pipeline_tokens,
            "offload_step_pct": offload_step_pct,
            "offload_tool_pct": offload_tool_pct,
            "offload_token_pct": offload_token_pct,
        },
    }


def print_report(data: Dict[str, Any]) -> None:
    sid = data["session_id"]
    coord = data["coordinator"]["full_transcript"]
    compact = data["coordinator"]["compacted_transcript"]
    coll = data["collective_pipeline"]
    subagents = data["subagents"]

    print("=" * 78)
    print(f" 📊 LIVE SESSION TELEMETRY COCKPIT: {sid[:8]}...{sid[-4:]}")
    print("=" * 78)
    print(f" Session ID:     {sid}")
    print(f" Duration:       {coord['duration_seconds'] / 60.0:.1f} minutes ({coord['duration_seconds']:.0f}s)")
    print(f" Time Horizon:   {coord['start_time']}  ->  {coord['end_time']}")
    print("-" * 78)
    print(" 🧠 COORDINATOR CONTEXT & COGNITIVE TOPOLOGY")
    print(f"   • Total Trajectory Steps:     {coord['total_steps']}")
    print(f"   • User Interactions (Turns):  {coord['step_types'].get('USER_INPUT', 0)}")
    print(f"   • Model Planner Responses:    {coord['step_types'].get('PLANNER_RESPONSE', 0)}")
    print(f"   • Compaction Checkpoints:     {coord['step_types'].get('CHECKPOINT', 0)}")
    print(f"   • Cumulative Full Chars:      {coord['total_chars']:,} (~{coord['estimated_tokens']:,} tokens)")
    print(f"   • Thinking Chars (Reasoning): {coord['thinking_chars']:,} (~{coord['estimated_thinking_tokens']:,} tokens)")
    print(f"   • Output Compaction Savings:  {data['coordinator']['compaction_savings_chars']:,} chars ({data['coordinator']['compaction_savings_pct']}%)")
    print("-" * 78)
    print(" 🛠️ COORDINATOR TOOL DISPATCH MATRIX")
    print(f"   • Total Tool Calls:           {coord['tool_call_count']} (Errors: {coord['tool_errors']})")
    for tool_name, count in list(coord["tool_distribution"].items())[:8]:
        pct = (count / max(1, coord["tool_call_count"])) * 100
        print(f"     - {tool_name:<24}: {count:>3} ({pct:>4.1f}%)")
    if len(coord["tool_distribution"]) > 8:
        rem = sum(list(coord["tool_distribution"].values())[8:])
        print(f"     - Other Tools ({len(coord['tool_distribution']) - 8}):         {rem:>3}")
    print("-" * 78)
    print(f" 🪜 SUBAGENT LADDER DELEGATION & OFFLOADING ({len(subagents)} Subagents)")
    if subagents:
        for sa in subagents:
            m = sa["metrics"]
            cid = sa["conversation_id"][:8]
            print(f"   ✔ {sa['role']:<24} [{cid}] | Steps: {m['total_steps']:>3} | Tools: {m['tool_call_count']:>2} | Chars: {m['total_chars']:>7,} (~{m['estimated_tokens']:>5,} tok)")
        print("-" * 78)
        print(" 📈 COGNITIVE ISOLATION & OFFLOAD EFFICIENCY")
        print(f"   • Subagents Executed:         {coll['offload_step_pct']}% of all steps ({coll['total_steps'] - coord['total_steps']} / {coll['total_steps']})")
        print(f"   • Subagents Dispatched:       {coll['offload_tool_pct']}% of all tool calls ({coll['total_tools'] - coord['tool_call_count']} / {coll['total_tools']})")
        print(f"   • Context Volume Offloaded:   {coll['offload_token_pct']}% (~{coll['total_tokens'] - coord['estimated_tokens']:,} tokens preserved)")
    else:
        print("   (No child subagents spawned in this session)")
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Session Telemetry & Topology Analyzer")
    parser.add_argument("--session-id", "-s", type=str, default=None, help="Target session ID (UUID)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON data")
    parser.add_argument("--save-db", action="store_true", help="Sync session and subagents into data/telemetry.db")
    parser.add_argument("--out", type=Path, default=None, help="Optional output JSON path")
    args = parser.parse_args()

    if args.session_id:
        session_dir = Path.home() / ".gemini" / "antigravity" / "brain" / args.session_id
    else:
        session_dir = find_latest_session_dir()

    if not session_dir or not session_dir.exists():
        sys.stderr.write(f"Error: Session directory not found for {args.session_id or 'latest'}\n")
        return 1

    report_data = analyze_session(session_dir)

    if args.save_db:
        from pipeline import extract_transcripts
        db_path = Path(__file__).resolve().parent.parent / "data" / "telemetry.db"
        t_path = session_dir / ".system_generated" / "logs" / "transcript.jsonl"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.executescript(extract_transcripts.SCHEMA_SQL)
        conn.commit()

        # Ingest coordinator
        res = extract_transcripts.extract_session(t_path)
        if res:
            s_row, step_rows, tool_rows, interv_rows = res
            cur.execute("""
                INSERT OR REPLACE INTO sessions (
                    session_id, start_time, end_time, duration_seconds, total_steps,
                    model, workspace_path, transcript_path, file_size_bytes, has_errors,
                    tool_call_count, tool_error_count, intervention_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s_row["session_id"], s_row["start_time"], s_row["end_time"],
                s_row["duration_seconds"], s_row["total_steps"], s_row["model"],
                s_row["workspace_path"], s_row["transcript_path"], s_row["file_size_bytes"],
                s_row["has_errors"], s_row["tool_call_count"], s_row["tool_error_count"],
                s_row["intervention_count"]
            ))
            conn.commit()

        # Ingest subagents
        for sa in report_data["subagents"]:
            sub_p = session_dir.parent / sa["conversation_id"] / ".system_generated" / "logs" / "transcript.jsonl"
            sub_res = extract_transcripts.extract_session(sub_p)
            if sub_res:
                s_row, _, _, _ = sub_res
                cur.execute("""
                    INSERT OR REPLACE INTO sessions (
                        session_id, start_time, end_time, duration_seconds, total_steps,
                        model, workspace_path, transcript_path, file_size_bytes, has_errors,
                        tool_call_count, tool_error_count, intervention_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s_row["session_id"], s_row["start_time"], s_row["end_time"],
                    s_row["duration_seconds"], s_row["total_steps"], s_row["model"],
                    s_row["workspace_path"], s_row["transcript_path"], s_row["file_size_bytes"],
                    s_row["has_errors"], s_row["tool_call_count"], s_row["tool_error_count"],
                    s_row["intervention_count"]
                ))
                conn.commit()
        conn.close()
        print(f"✔ Synchronized session {report_data['session_id'][:8]} and {len(report_data['subagents'])} subagents into telemetry.db\n")

    if args.json:
        print(json.dumps(report_data, indent=2))
    else:
        print_report(report_data)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"✔ Exported structured analysis to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
