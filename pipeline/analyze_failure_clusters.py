#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness for Google Antigravity™
Cross-Model Failure Cluster & Intervention Hotspot Analyzer.

Mines data/telemetry.db for:
1. Tool failures (exit_code != 0, status != 'SUCCESS') and loop candidates
   grouped by model and command_category.
2. Model-specific operational biases and error distributions.
3. User interventions following tool failures and recurrent operator rescues.
4. Concrete failure signatures justifying modular skills (db-ops, remote-ops, git-worktree-ops).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from harness.telemetry.models import CanonicalModelInfo, normalize_model

_NOISE_CHARS_RE = re.compile(r"[\"'\\[\]{}^$*?|]")


def _is_corrupt_model_noise(raw_model: Optional[str], info: CanonicalModelInfo) -> bool:
    if info.attribution_status in ("attributed", "unattributed_legacy"):
        return False
    if not raw_model or not isinstance(raw_model, str):
        return False
    trimmed = raw_model.strip()
    if trimmed.lower() in ("", "unknown", "none", "null", "n/a", "na"):
        return False
    if _NOISE_CHARS_RE.search(trimmed):
        return True
    if "(" in trimmed or ")" in trimmed:
        return True
    return info.canonical_model == "unknown"


def _classify_session_model(
    raw_model: Optional[str],
    model_slug: Optional[str] = None,
    model_display_name: Optional[str] = None,
) -> Tuple[Optional[str], CanonicalModelInfo]:
    info = normalize_model(raw_model, model_slug=model_slug, model_display_name=model_display_name)
    if _is_corrupt_model_noise(raw_model, info):
        return None, info
    if info.attribution_status == "unattributed_legacy":
        return "unattributed_legacy", info
    label = (raw_model or "").strip() or info.canonical_model
    return label, info


def analyze_model_failures_and_interventions(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("PRAGMA table_info(sessions)")
        sess_cols = {r[1] for r in c.fetchall()}
        slug_sel = "COALESCE(model_slug, '')" if "model_slug" in sess_cols else "''"
        disp_sel = "COALESCE(model_display_name, '')" if "model_display_name" in sess_cols else "''"
        slug_join = "COALESCE(s.model_slug, '')" if "model_slug" in sess_cols else "''"
        disp_join = "COALESCE(s.model_display_name, '')" if "model_display_name" in sess_cols else "''"

        # 1. Total sessions by validated model (and canonical model rollup)
        c.execute(
            f"""
            SELECT model, {slug_sel}, {disp_sel}, COUNT(*) as sess_count,
                   SUM(COALESCE(total_steps, 0)) as total_steps,
                   SUM(COALESCE(tool_call_count, 0)) as total_tools,
                   SUM(COALESCE(tool_error_count, 0)) as total_errors,
                   SUM(COALESCE(intervention_count, 0)) as total_interventions
            FROM sessions
            GROUP BY model, {slug_sel}, {disp_sel}
            ORDER BY sess_count DESC
            """
        )
        agg_raw: Dict[str, Dict[str, Any]] = {}
        agg_canon: Dict[str, Dict[str, Any]] = {}
        for raw_m, m_slug, m_disp, scnt, steps, tools, errs, intervs in c.fetchall():
            label, info = _classify_session_model(raw_m, m_slug or None, m_disp or None)
            if label is None:
                continue
            bucket = agg_raw.setdefault(label, {
                "model": label,
                "canonical_model": info.canonical_model,
                "model_family": info.family,
                "reasoning_effort": info.reasoning_effort,
                "attribution_status": info.attribution_status,
                "sessions": 0, "total_steps": 0, "total_tool_calls": 0,
                "total_errors": 0, "total_interventions": 0,
            })
            bucket["sessions"] += scnt
            bucket["total_steps"] += steps or 0
            bucket["total_tool_calls"] += tools or 0
            bucket["total_errors"] += errs or 0
            bucket["total_interventions"] += intervs or 0

            cb = agg_canon.setdefault(info.canonical_model, {
                "canonical_model": info.canonical_model,
                "model_family": info.family,
                "attribution_status": info.attribution_status,
                "sessions": 0, "total_steps": 0, "total_tool_calls": 0,
                "total_errors": 0, "total_interventions": 0,
            })
            cb["sessions"] += scnt
            cb["total_steps"] += steps or 0
            cb["total_tool_calls"] += tools or 0
            cb["total_errors"] += errs or 0
            cb["total_interventions"] += intervs or 0

        model_profiles: List[Dict[str, Any]] = []
        for item in sorted(agg_raw.values(), key=lambda x: x["sessions"], reverse=True):
            item["error_rate_pct"] = round((item["total_errors"] / (item["total_tool_calls"] or 1)) * 100.0, 2)
            item["intervention_rate_pct"] = round((item["total_interventions"] / (item["total_steps"] or 1)) * 100.0, 2)
            model_profiles.append(item)

        canonical_model_profiles: List[Dict[str, Any]] = []
        for item in sorted(agg_canon.values(), key=lambda x: x["sessions"], reverse=True):
            item["error_rate_pct"] = round((item["total_errors"] / (item["total_tool_calls"] or 1)) * 100.0, 2)
            item["intervention_rate_pct"] = round((item["total_interventions"] / (item["total_steps"] or 1)) * 100.0, 2)
            canonical_model_profiles.append(item)

        # 2. Tool failures and loops by validated model and command_category
        c.execute(
            f"""
            SELECT
                COALESCE(s.model, 'Unknown') as model_name,
                {slug_join},
                {disp_join},
                COALESCE(tc.command_category, 'non_command') as category,
                COUNT(*) as total_calls,
                SUM(CASE WHEN tc.status != 'SUCCESS' OR (tc.exit_code IS NOT NULL AND tc.exit_code != 0) THEN 1 ELSE 0 END) as failures,
                SUM(CASE WHEN tc.is_loop_candidate = 1 THEN 1 ELSE 0 END) as loops
            FROM tool_calls tc
            JOIN sessions s ON tc.session_id = s.session_id
            GROUP BY model_name, {slug_join}, {disp_join}, category
            HAVING failures > 0 OR loops > 0
            ORDER BY failures DESC, loops DESC
            """
        )
        cluster_agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for raw_m, m_slug, m_disp, cat, tot, fails, loops in c.fetchall():
            label, info = _classify_session_model(raw_m, m_slug or None, m_disp or None)
            if label is None:
                continue
            key = (label, cat)
            cl = cluster_agg.setdefault(key, {
                "model": label, "canonical_model": info.canonical_model,
                "category": cat, "total_calls": 0, "failures": 0, "loops": 0,
            })
            cl["total_calls"] += tot or 0
            cl["failures"] += fails or 0
            cl["loops"] += loops or 0
        model_category_clusters = []
        for cl in sorted(cluster_agg.values(), key=lambda x: (x["failures"], x["loops"]), reverse=True):
            cl["failure_rate_pct"] = round((cl["failures"] / max(cl["total_calls"], 1)) * 100.0, 2)
            model_category_clusters.append(cl)

        # 3. Top non-zero exit codes by validated model
        c.execute(
            f"""
            SELECT
                COALESCE(s.model, 'Unknown') as model_name,
                {slug_join},
                {disp_join},
                tc.exit_code,
                COUNT(*) as count
            FROM tool_calls tc
            JOIN sessions s ON tc.session_id = s.session_id
            WHERE tc.exit_code IS NOT NULL AND tc.exit_code != 0
            GROUP BY model_name, {slug_join}, {disp_join}, tc.exit_code
            ORDER BY count DESC
            """
        )
        ec_agg: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for raw_m, m_slug, m_disp, ec, cnt in c.fetchall():
            label, _ = _classify_session_model(raw_m, m_slug or None, m_disp or None)
            if label is None:
                continue
            ec_agg[label][ec] += cnt
        exit_codes_by_model = {
            m: [{"exit_code": ec, "count": cnt} for ec, cnt in sorted(ecs.items(), key=lambda x: x[1], reverse=True)]
            for m, ecs in ec_agg.items()
        }

        # 4. Detailed error signatures for specialized operational domains
        c.execute("""
            SELECT tc.command_line, tc.exit_code, tc.error_snippet, COUNT(*) as cnt
            FROM tool_calls tc
            WHERE tc.command_category = 'git' AND (tc.exit_code != 0 OR tc.status != 'SUCCESS')
            GROUP BY SUBSTR(tc.command_line, 1, 80), tc.exit_code
            ORDER BY cnt DESC
            LIMIT 15
        """)
        git_failures = [
            {"cmd": r[0] or "", "exit_code": r[1], "snippet": (r[2] or "")[:200], "count": r[3]}
            for r in c.fetchall()
        ]

        c.execute("""
            SELECT tc.command_line, tc.exit_code, tc.error_snippet, COUNT(*) as cnt
            FROM tool_calls tc
            WHERE (tc.exit_code = 255 OR tc.command_category = 'network' OR tc.command_line LIKE '%ssh %' OR tc.command_line LIKE '%tailscale%')
              AND (tc.exit_code != 0 OR tc.status != 'SUCCESS')
            GROUP BY SUBSTR(tc.command_line, 1, 80), tc.exit_code
            ORDER BY cnt DESC
            LIMIT 15
        """)
        mesh_network_failures = [
            {"cmd": r[0] or "", "exit_code": r[1], "snippet": (r[2] or "")[:200], "count": r[3]}
            for r in c.fetchall()
        ]

        c.execute("""
            SELECT tc.command_line, tc.exit_code, tc.error_snippet, COUNT(*) as cnt
            FROM tool_calls tc
            WHERE (tc.command_line LIKE '%psql%' OR tc.command_line LIKE '%sqlite%' OR tc.command_line LIKE '%postgres%' OR tc.command_line LIKE '%docker%' OR tc.command_line LIKE '%redis%')
              AND (tc.exit_code != 0 OR tc.status != 'SUCCESS')
            GROUP BY SUBSTR(tc.command_line, 1, 80), tc.exit_code
            ORDER BY cnt DESC
            LIMIT 15
        """)
        db_docker_failures = [
            {"cmd": r[0] or "", "exit_code": r[1], "snippet": (r[2] or "")[:200], "count": r[3]}
            for r in c.fetchall()
        ]

        # 5. User interventions following tool failures
        c.execute("""
            SELECT
                ui.session_id,
                ui.step_index,
                ui.intervention_type,
                ui.preceding_tool_name,
                ui.preceding_error_snippet,
                ui.prompt_text,
                s.model
            FROM user_interventions ui
            JOIN sessions s ON ui.session_id = s.session_id
            WHERE ui.preceding_tool_failed = 1
            ORDER BY ui.id DESC
        """)
        failed_tool_interventions = [
            {
                "session_id": r[0], "step_index": r[1], "intervention_type": r[2],
                "preceding_tool_name": r[3], "preceding_error_snippet": (r[4] or "")[:200],
                "prompt_text": (r[5] or "")[:200], "model": r[6],
            }
            for r in c.fetchall()
        ]

        # 6. User interventions with high steering signals
        c.execute("""
            SELECT
                ui.session_id,
                ui.step_index,
                ui.intervention_type,
                ui.prompt_text,
                s.model
            FROM user_interventions ui
            JOIN sessions s ON ui.session_id = s.session_id
            WHERE ui.intervention_type IN ('STEERING', 'ERROR_RECOVERY')
        """)
        steering_interventions = []
        correction_clusters: Dict[str, List[Dict[str, Any]]] = {
            "db_and_migration": [],
            "mesh_and_tailscale": [],
            "git_worktree_and_branches": [],
            "loop_stop_and_wait": [],
            "credentials_and_tokens": [],
            "test_and_verification": [],
        }

        for r in c.fetchall():
            prompt = r[3] or ""
            p_lower = prompt.lower()
            item = {
                "session_id": r[0], "step_index": r[1], "intervention_type": r[2],
                "prompt_snippet": prompt[:200].replace("\n", " "), "model": r[4],
            }
            steering_interventions.append(item)

            if any(k in p_lower for k in ["db", "database", "postgres", "sqlite", "migration", "query", "sql"]):
                correction_clusters["db_and_migration"].append(item)
            if any(k in p_lower for k in ["mesh", "knot", "tailscale", "node", "laptop", "deck", "remote", "ssh"]):
                correction_clusters["mesh_and_tailscale"].append(item)
            if any(k in p_lower for k in ["worktree", "branch", "commit", "stash", "pr ", "merge", "rebase"]):
                correction_clusters["git_worktree_and_branches"].append(item)
            if any(k in p_lower for k in ["stop", "pause", "wait", "hold", "loop", "don't do", "stuck"]):
                correction_clusters["loop_stop_and_wait"].append(item)
            if any(k in p_lower for k in ["token", "key", "password", "pat", "auth", "secret", "cred"]):
                correction_clusters["credentials_and_tokens"].append(item)
            if any(k in p_lower for k in ["test", "verify", "fail", "benchmark", "assert", "coverage"]):
                correction_clusters["test_and_verification"].append(item)
    finally:
        conn.close()

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "total_models": len(model_profiles),
            "total_canonical_models": len(canonical_model_profiles),
            "total_model_category_clusters": len(model_category_clusters),
            "total_failed_tool_interventions": len(failed_tool_interventions),
            "total_steering_interventions": len(steering_interventions),
        },
        "model_profiles": model_profiles,
        "canonical_model_profiles": canonical_model_profiles,
        "model_category_clusters": model_category_clusters,
        "exit_codes_by_model": exit_codes_by_model,
        "domain_failure_signatures": {
            "git_failures": git_failures,
            "mesh_network_failures": mesh_network_failures,
            "db_docker_failures": db_docker_failures,
        },
        "interventions_after_tool_failures": failed_tool_interventions,
        "steering_correction_clusters": {k: len(v) for k, v in correction_clusters.items()},
        "sample_steering_corrections": {k: v[:5] for k, v in correction_clusters.items()},
    }


def generate_markdown_report(data: Dict[str, Any]) -> str:
    total_sess = sum(m.get("sessions", 0) for m in data.get("model_profiles", []))
    total_steps = sum(m.get("total_steps", 0) for m in data.get("model_profiles", []))
    total_tools = sum(m.get("total_tool_calls", 0) for m in data.get("model_profiles", []))
    total_interv = sum(m.get("total_interventions", 0) for m in data.get("model_profiles", []))
    gen_at = data.get("generated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "<!-- SPDX-License-Identifier: Apache-2.0 -->",
        "<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->",
        "<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->",
        "<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->",
        "",
        "# Empirical Telemetry Analysis: Cross-Model Failure Clusters & Intervention Hotspots",
        "",
        f"**Dataset Source**: `data/telemetry.db` ({total_sess:,} Validated Sessions, {total_steps:,} Steps, {total_tools:,} Tool Calls, {total_interv:,} Interventions)",
        f"**Generated At**: {gen_at}",
        "",
        "---",
        "",
        "## 1. Cross-Model Profile & Operational Biases",
        "",
        "| Model | Canonical | Sessions | Steps | Tool Calls | Errors | Error % | Interventions | Interv % |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for m in data["model_profiles"]:
        canon = m.get("canonical_model", m["model"])
        lines.append(
            f"| `{m['model']}` | `{canon}` | {m['sessions']:,} | {m['total_steps']:,} | {m['total_tool_calls']:,} | "
            f"{m['total_errors']:,} | {m['error_rate_pct']}% | {m['total_interventions']:,} | {m['intervention_rate_pct']}% |"
        )

    top_attributed = [m for m in data.get("canonical_model_profiles", []) if m.get("attribution_status") == "attributed"][:4]
    lines.extend(["", "### Computed Model Highlights:"])
    if top_attributed:
        for tm in top_attributed:
            lines.append(
                f"- **`{tm['canonical_model']}`** ({tm['sessions']:,} sessions, {tm['total_steps']:,} steps): "
                f"{tm['error_rate_pct']}% tool error rate, {tm['intervention_rate_pct']}% intervention rate."
            )
    else:
        lines.append("- No attributed model sessions present in database.")

    lines.extend([
        "",
        "---",
        "",
        "## 2. Top Failure Clusters by Model & Command Category",
        "",
        "| Model | Category | Total Calls | Failures | Loops | Failure Rate |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for c in data["model_category_clusters"][:25]:
        lines.append(
            f"| `{c['model']}` | `{c['category']}` | {c['total_calls']:,} | {c['failures']:,} | {c['loops']:,} | {c['failure_rate_pct']}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Specialized Domain Failure Signatures",
        "",
        "### A. Database & Docker Operations (`db-ops` Justification)",
        "Frequent failures when probing PostgreSQL or Docker services without non-interactive flags, missing environment credentials, or handling active connection locks:",
        "",
    ])

    for f in data["domain_failure_signatures"]["db_docker_failures"][:6]:
        cmd_clean = f["cmd"].replace("`", "'")
        lines.append(f"- **`{cmd_clean}`** (Exit {f['exit_code']}, count={f['count']})")
        if f["snippet"]:
            snip_clean = f["snippet"].replace("`", "'").replace("\n", " ")
            lines.append(f"  *Snippet*: `{snip_clean}`")

    lines.extend([
        "",
        "### B. Mesh & Remote Operations (`remote-ops` Justification)",
        "SSH connection dropouts (Exit Code 255), unverified Tailscale hostnames, and unpinned socket paths:",
        "",
    ])

    for f in data["domain_failure_signatures"]["mesh_network_failures"][:6]:
        cmd_clean = f["cmd"].replace("`", "'")
        lines.append(f"- **`{cmd_clean}`** (Exit {f['exit_code']}, count={f['count']})")
        if f["snippet"]:
            snip_clean = f["snippet"].replace("`", "'").replace("\n", " ")
            lines.append(f"  *Snippet*: `{snip_clean}`")

    lines.extend([
        "",
        "### C. Git Worktree & Branching Operations (`git-worktree-ops` Justification)",
        "Stale worktrees, unmerged index collisions, checkout conflicts with dirty state, and orphan worktree directories:",
        "",
    ])

    for f in data["domain_failure_signatures"]["git_failures"][:6]:
        cmd_clean = f["cmd"].replace("`", "'")
        lines.append(f"- **`{cmd_clean}`** (Exit {f['exit_code']}, count={f['count']})")
        if f["snippet"]:
            snip_clean = f["snippet"].replace("`", "'").replace("\n", " ")
            lines.append(f"  *Snippet*: `{snip_clean}`")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Human-in-the-Loop Intervention Hotspots",
        "",
        "### Breakdown of Operator Steering Triggers:",
    ])

    for cluster, cnt in data["steering_correction_clusters"].items():
        lines.append(f"- **`{cluster}`**: {cnt} operator steering prompts")

    lines.extend([
        "",
        "### Preceding Tool Failures Leading to Operator Rescues:",
        "Direct interventions immediately triggered after tool failures:",
    ])

    for item in data["interventions_after_tool_failures"][:10]:
        prompt = item["prompt_text"].replace("`", "'").replace("\n", " ")
        lines.append(
            f"- **Step {item['step_index']}** (`{item['preceding_tool_name']}`, model `{item['model']}`): Operator prompt: *\"{prompt}\"*"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Architectural Synthesis: Three New Modular Skills",
        "",
        "Based on the empirical failure clusters and operator intervention hotspots identified in this audit, we codify three new operational runbooks:",
        "",
        "1. **`db-ops`**: Standardized database diagnostic and inspection runbook for PostgreSQL / SQLite / Docker instances (connection pooling, active locks, vacuuming, non-interactive CLI invocations). Eliminates interactive prompts and hanging client queries.",
        "2. **`remote-ops`**: Standardized remote SSH execution runbook (ControlMaster multiplexing, stdin script streaming, login-shell PATH promotion, and compact health triage). Resolves SSH exit code 255 dropouts and unverified remote targets.",
        "3. **`git-worktree-ops`**: Safe multi-branch worktree management, branch cleanup, orphan prune, and stashes without index corruption. Resolves dirty tree checkout errors and orphaned worktree index locks.",
        "",
    ])

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze model failure clusters and intervention hotspots.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--output-json", default="data/model_failure_clusters.json", help="Path to output JSON")
    parser.add_argument("--output-report", default="data/reports/model-failure-clusters-report.md", help="Path to output markdown")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist.")
        return 1

    results = analyze_model_failures_and_interventions(db_path)

    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    report_path = Path(args.output_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_content = generate_markdown_report(results)
    report_path.write_text(report_content, encoding="utf-8")

    print("=" * 70)
    print(" 🔬 MODEL FAILURE CLUSTERS & INTERVENTION HOTSPOTS AUDIT COMPLETE")
    print("=" * 70)
    print(f"Total Models Analyzed:             {results['summary']['total_models']}")
    print(f"Failure & Loop Clusters:           {results['summary']['total_model_category_clusters']}")
    print(f"Direct Rescue Interventions:       {results['summary']['total_failed_tool_interventions']}")
    print(f"Steering Interventions Analyzed:   {results['summary']['total_steering_interventions']}")
    print(f"JSON Report:                       {json_path}")
    print(f"Markdown Report:                   {report_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
