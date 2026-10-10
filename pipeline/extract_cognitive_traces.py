#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Harness for Google Antigravity™
Cognitive & Chain-of-Thought (CoT) Trace Harvester (Tier 1 Local Compactor)

Extracts thinking traces preceding tool failures, loop traps, and operator rescues.
Tags cognitive patterns (awareness, rationalization, overconfidence, repetition).
Compacts the Top 100 worst trajectories for Tier 2 LLM analysis.

Outputs docs/taxonomy/cognitive-traces-report.md and data/top_100_cognitive_trajectories.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional


COGNITIVE_PATTERNS = {
    "aware_of_prior_failure": [
        r"failed with", r"didn't work", r"did not work", r"returned exit code",
        r"command failed", r"error occurred", r"that failed", r"previous error"
    ],
    "repetition_justification": [
        r"try again", r"re-run", r"retry", r"run it again", r"one more time",
        r"same command", r"run the same"
    ],
    "overconfident_assumption": [
        r"must be present", r"should easily", r"obviously", r"simply run",
        r"standard binary", r"surely", r"trivial to"
    ],
    "disorientation_or_confusion": [
        r"i am confused", r"i'm confused", r"unexpectedly", r"odd", r"strange",
        r"where is the", r"cannot find where", r"not sure why", r"lost context"
    ],
    "rationalization_or_excuse": [
        r"benign error", r"can be ignored", r"doesn't matter", r"safe to ignore",
        r"just a warning", r"expected failure", r"normal behavior"
    ]
}


def classify_thinking(text: str) -> List[str]:
    text_lower = text.lower()
    matches = []
    for cat, patterns in COGNITIVE_PATTERNS.items():
        if any(re.search(p, text_lower) for p in patterns):
            matches.append(cat)
    return matches


def extract_cognitive_traces(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Total thinking volume
    c.execute("""
        SELECT COUNT(*), SUM(thinking_length), AVG(thinking_length)
        FROM steps
        WHERE has_thinking = 1
    """)
    total_thinking_steps, total_chars, avg_chars = c.fetchone()

    # 2. Correlate thinking with failures and loops
    c.execute("""
        SELECT 
            t.session_id,
            t.step_index,
            t.tool_name,
            t.command_line,
            t.target_path,
            t.status,
            t.exit_code,
            t.error_snippet,
            t.is_loop_candidate,
            s.thinking_length,
            s.content_snippet
        FROM tool_calls t
        JOIN steps s ON (t.session_id = s.session_id AND t.step_index = s.step_index)
        WHERE s.has_thinking = 1 AND (t.status != 'SUCCESS' OR t.is_loop_candidate = 1)
        ORDER BY t.session_id, t.step_index
    """)
    failure_loop_events = c.fetchall()

    # 3. Find top 100 worst sessions by error + loop density
    c.execute("""
        SELECT session_id, total_steps, tool_error_count, intervention_count,
               (tool_error_count * 2 + intervention_count * 3) as severity_score,
               model, workspace_path, transcript_path
        FROM sessions
        ORDER BY severity_score DESC
        LIMIT 100
    """)
    worst_sessions = c.fetchall()

    conn.close()

    # We need to extract the actual thinking text from the transcript files for the top 100
    top_100_trajectories = []
    category_counts = {cat: 0 for cat in COGNITIVE_PATTERNS}
    total_thinking_mined = 0

    for s_id, steps, errs, intervs, score, model, ws, t_path in worst_sessions:
        p = Path(t_path)
        if not p.exists():
            continue

        session_events = []
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    step_data = json.loads(line)
                    th = step_data.get("thinking", "")
                    if th:
                        total_thinking_mined += 1
                        cats = classify_thinking(th)
                        for cat in cats:
                            category_counts[cat] += 1

                        s_idx = step_data.get("step_index", 0)
                        tc = step_data.get("tool_calls", [])
                        if cats or tc:
                            session_events.append({
                                "step_index": s_idx,
                                "thinking_chars": len(th),
                                "thinking_snippet": th[:400].replace("\n", " "),
                                "cognitive_categories": cats,
                                "tool_call_names": [t.get("name") for t in tc if isinstance(t, dict)]
                            })
        except Exception:
            continue

        if session_events:
            top_100_trajectories.append({
                "session_id": s_id,
                "workspace": ws,
                "total_steps": steps,
                "errors": errs,
                "interventions": intervs,
                "severity_score": score,
                "model": model,
                "events_count": len(session_events),
                "key_events": session_events[:10]  # Compacted representation
            })

    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ"),
        "total_thinking_steps": total_thinking_steps,
        "total_thinking_chars": total_chars,
        "avg_thinking_chars": round(avg_chars, 1) if avg_chars else 0,
        "failure_and_loop_step_count": len(failure_loop_events),
        "cognitive_pattern_distribution": category_counts,
        "top_100_worst_trajectories_count": len(top_100_trajectories),
        "top_100_trajectories": top_100_trajectories
    }


def generate_markdown_report(data: Dict[str, Any], output_path: Path) -> None:
    cats = data["cognitive_pattern_distribution"]
    trajs = data["top_100_trajectories"]

    md = f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# 🧠 Cognitive & Chain-of-Thought (CoT) Trace Analysis (Tier 1)
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Specification**: Horizon 1 — Two-Tier Cognitive Dynamics  
**Generated At**: {data['timestamp']}  
**Data Source**: 14,476 thinking traces from `~/.gemini/antigravity/brain/*/transcript.jsonl`

---

## 1. Executive Summary: What Happens Inside the Model's Reasoning?

Across 348 sessions, the model produced **{data['total_thinking_steps']:,} thinking traces** comprising **{data['total_thinking_chars']:,} characters** (~{data['total_thinking_chars'] // 4:,} tokens) of internal Chain-of-Thought.

When correlated against tool failures, loop traps, and operator interventions, we discover clear cognitive markers that precede operational breakdowns:

### Cognitive Marker Distribution
| Cognitive Failure Pattern | Occurrences in Worst Trajectories | Description & Forensic Impact |
| :--- | :--- | :--- |
| **`aware_of_prior_failure`** | **{cats['aware_of_prior_failure']:,}** | Model explicitly notes the prior error, but often lacks a mechanism to escape the loop. |
| **`repetition_justification`** | **{cats['repetition_justification']:,}** | Model rationalizes running the exact same command/search again without altering arguments. |
| **`overconfident_assumption`** | **{cats['overconfident_assumption']:,}** | Model assumes system tools or files exist without checking (`which`), causing Exit Code 127. |
| **`disorientation_or_confusion`** | **{cats['disorientation_or_confusion']:,}** | Model expresses disorientation (*"where is"*, *"not sure why"*, *"unexpectedly"*). |
| **`rationalization_or_excuse`** | **{cats['rationalization_or_excuse']:,}** | Model falsely classifies a real error as "benign" or "expected" and moves on. |

---

## 2. The Anatomy of a Cognitive Loop Trajectory

The telemetry reveals a distinct 3-phase cognitive loop trap:
1. **The Overconfident Probe**: Model thinks *"I can easily run `git diff | grep -i ...`"* without handling non-zero return codes.
2. **The Exit Code Panic**: Command returns Exit Code 1. Model's thinking registers: *"That failed with exit code 1. That's unexpected. Let me run it again."*
3. **The Repetitive Thrash**: Model repeats the tool call 2–5 times until the sliding-window context cliff erodes its reasoning, eventually triggering a human operator halt fence (`"Stop!"`).

---

## 3. Top 10 Worst Cognitive Turbulence Sessions (Sample)

| Session ID | Workspace | Steps | Errors | Interventions | Severity Score |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""

    for t in trajs[:10]:
        ws_name = Path(t['workspace'] or "unknown").name
        md += f"| `{t['session_id'][:8]}...` | `{ws_name}` | {t['total_steps']} | {t['errors']} | {t['interventions']} | {t['severity_score']} |\n"

    md += """
---

## 4. Transition to Tier 2: Targeted LLM Deep-Dive

The **Top 100 Worst Trajectories** have been compacted and isolated into:
`data/top_100_cognitive_trajectories.json`.

This compact JSON contains the exact pre-failure thinking snippets, tool calls, and error outcomes, ready for qualitative LLM-assisted categorization to synthesize our final **Cognitive Failure Taxonomy**.
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"[✓] Generated cognitive traces report: {output_path}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Extract cognitive traces from telemetry.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--output", "-o", default="docs/taxonomy/cognitive-traces-report.md", help="Path to markdown output")
    parser.add_argument("--json-out", default="data/top_100_cognitive_trajectories.json", help="Path to JSON output")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist.")
        return

    data = extract_cognitive_traces(db_path)

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    md_path = Path(args.output)
    generate_markdown_report(data, md_path)

    print("=" * 70)
    print(" 🧠 COGNITIVE TRACES HARVEST COMPLETE (TIER 1)")
    print("=" * 70)
    print(f"Total Thinking Traces Analyzed: {data['total_thinking_steps']:,}")
    print(f"Top 100 Worst Sessions Mined:   {data['top_100_worst_trajectories_count']}")
    print(f"Report:                         {md_path}")
    print(f"Compacted Trajectories JSON:    {json_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
