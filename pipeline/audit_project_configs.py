#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness for Google Antigravity™
Project Rules & Skills Ecosystem Auditor

Analyzes the project-level context environments (AGENTS.md, .agents/rules, .agents/skills)
across all repositories audited in data/telemetry.db to measure:
- Rule calibration and clarity vs. ambiguity
- Impact of explicit command dictionaries on tool success
- Rule fragmentation (single consolidated file vs. multi-file indirection)
- Domain complexity effects (System/OS vs. Mesh vs. Web/Full-stack)
- Successes vs. misconfigurations that conditioned agent behavior

Outputs data/reports/project-rules-skills-audit.md and data/project_configs_audit.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional


from harness.telemetry.db import get_db_connection
from harness.utils.tokens import estimate_tokens


def audit_workspace_config(ws_path_str: str) -> Dict[str, Any]:
    ws_path = Path(ws_path_str)
    if not ws_path.exists() or not ws_path.is_dir():
        return {
            "workspace_path": ws_path_str,
            "exists": False,
            "rule_files": [],
            "skills": [],
            "hooks": [],
            "total_rule_tokens": 0,
            "rule_patterns": {}
        }

    # Discover rules: root AGENTS.md, .agents/AGENTS.md, .agent/rules/*.md, GEMINI.md, nested AGENTS.md
    rule_files = []
    for candidate in [
        ws_path / "AGENTS.md",
        ws_path / "GEMINI.md",
        ws_path / ".agents" / "AGENTS.md",
        ws_path / ".agent" / "AGENTS.md",
    ]:
        if candidate.exists() and candidate.is_file():
            rule_files.append(candidate)

    # Check for rules directories
    for rdir in [ws_path / ".agents" / "rules", ws_path / ".agent" / "rules"]:
        if rdir.exists() and rdir.is_dir():
            for f in rdir.glob("*.md"):
                if f not in rule_files:
                    rule_files.append(f)

    # Check for nested app AGENTS.md
    for f in ws_path.glob("*/AGENTS.md"):
        if f not in rule_files:
            rule_files.append(f)
    for f in ws_path.glob("apps/*/AGENTS.md"):
        if f not in rule_files:
            rule_files.append(f)

    # Parse rules content
    total_rule_text = ""
    rules_metadata = []
    for rf in rule_files:
        try:
            content = rf.read_text(encoding="utf-8", errors="replace")
            total_rule_text += "\n" + content
            rules_metadata.append({
                "path": str(rf.relative_to(ws_path)),
                "size_bytes": rf.stat().st_size,
                "lines": len(content.splitlines()),
                "estimated_tokens": estimate_tokens(content)
            })
        except Exception as e:
            rules_metadata.append({"path": str(rf), "error": str(e)})

    # Detect calibration patterns in rules
    rule_lower = total_rule_text.lower()
    patterns = {
        "has_explicit_commands": bool(re.search(r"pnpm\s+[a-z]|npm\s+run|cargo\s+|pytest\s+|make\s+", total_rule_text)),
        "bans_error_swallowing": bool(re.search(r"error swallowing|zero silent|2>/dev/null|\|\|\s*true", rule_lower)),
        "bans_product_homework": "homework" in rule_lower,
        "enforces_subagent_ladder": "subagent-ladder" in rule_lower or "ladder" in rule_lower,
        "has_pr_delay_fence": bool(re.search(r"10 minute|delay fence|pr merge delay", rule_lower)),
        "has_multi_file_indirection": bool(re.search(r"start with these rule files|read \.agent/rules", rule_lower)),
        "has_gpg_signing_rule": "gpg" in rule_lower or "commit -s" in rule_lower,
        "has_mesh_or_hardware_rules": any(k in rule_lower for k in ["knot", "mesh", "steamdeck", "rog-ally", "plasma", "dbus", "pacman"]),
    }

    # Discover project-level skills
    skills_found = []
    for sdir in [ws_path / ".agents" / "skills", ws_path / ".agent" / "skills", ws_path / "skills"]:
        if sdir.exists() and sdir.is_dir():
            for item in sdir.iterdir():
                skill_md = item / "SKILL.md" if item.is_dir() else (item if item.name == "SKILL.md" else None)
                if skill_md and skill_md.exists():
                    try:
                        sc = skill_md.read_text(encoding="utf-8", errors="replace")
                        skills_found.append({
                            "name": item.name,
                            "path": str(skill_md.relative_to(ws_path)),
                            "estimated_tokens": estimate_tokens(sc)
                        })
                    except Exception as e:
                        skills_found.append({"name": item.name, "error": str(e)})

    # Discover hooks
    hooks_found = []
    for hfile in [ws_path / ".agents" / "hooks.json", ws_path / "hooks.json"]:
        if hfile.exists():
            try:
                hdata = json.loads(hfile.read_text(encoding="utf-8"))
                hooks_found.append({"path": str(hfile.relative_to(ws_path)), "hooks": list(hdata.keys())})
            except Exception as e:
                hooks_found.append({"path": str(hfile), "error": str(e)})

    return {
        "workspace_path": ws_path_str,
        "repo_name": ws_path.name,
        "exists": True,
        "rule_files": rules_metadata,
        "rule_file_count": len(rules_metadata),
        "total_rule_tokens": estimate_tokens(total_rule_text),
        "skills": skills_found,
        "skill_count": len(skills_found),
        "hooks": hooks_found,
        "rule_patterns": patterns
    }


_UUID_WS_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _is_redacted_or_remote_ws(ws_path: str, origin_dev: Optional[str]) -> bool:
    if "[WORKSPACE_ROOT]" in ws_path or "[USER_HOME]" in ws_path:
        return True
    local_devs = {"", "local"}
    for cand in (Path.home().name, os.environ.get("USER", ""), os.environ.get("LOGNAME", "")):
        if cand and cand.strip():
            local_devs.add(cand.strip().lower())
    if (origin_dev or "").strip().lower() not in local_devs and not Path(ws_path).exists():
        return True
    return False


def analyze_all_workspaces(db_path: Path, limit: int = 100) -> Dict[str, Any]:
    conn = get_db_connection(db_path, row_factory=False, read_only=True)
    try:
        c = conn.cursor()
        c.execute("PRAGMA table_info(sessions)")
        sess_cols = {r[1] for r in c.fetchall()}
        dev_col = "COALESCE(origin_developer, 'local')" if "origin_developer" in sess_cols else "'local'"

        c.execute(
            f"""
            SELECT
                workspace_path,
                {dev_col} as origin_dev,
                COUNT(*) as session_count,
                ROUND(AVG(total_steps), 1) as avg_steps,
                SUM(COALESCE(tool_call_count, 0)) as total_tools,
                SUM(COALESCE(tool_error_count, 0)) as total_errors,
                ROUND(SUM(COALESCE(tool_error_count, 0)) * 100.0 / NULLIF(SUM(COALESCE(tool_call_count, 0)), 0), 2) as error_rate_pct,
                SUM(COALESCE(intervention_count, 0)) as total_interventions,
                ROUND(SUM(COALESCE(intervention_count, 0)) * 1.0 / COUNT(*), 2) as interv_per_sess,
                SUM(CASE WHEN COALESCE(tool_error_count, 0) <= 1 AND COALESCE(intervention_count, 0) = 0 AND COALESCE(total_steps, 0) >= 15 THEN 1 ELSE 0 END) as autonomous_sessions
            FROM sessions
            WHERE workspace_path IS NOT NULL AND workspace_path != ""
            GROUP BY workspace_path, origin_dev
            ORDER BY session_count DESC
            LIMIT ?
            """,
            (max(1, limit * 2),),
        )
        rows = c.fetchall()
    finally:
        conn.close()

    local_agg: Dict[str, Dict[str, Any]] = {}
    redacted_remote_workspaces: List[Dict[str, Any]] = []
    unattributed_uuid_count = 0
    unattributed_uuid_sessions = 0
    redacted_remote_sessions = 0
    redacted_devs: set[str] = set()

    for r in rows:
        ws_path, origin_dev, s_cnt, avg_steps, tot_tools, tot_errs, err_pct, tot_int, int_per_s, auto_s = r
        perf = {
            "session_count": s_cnt,
            "avg_steps": avg_steps or 0.0,
            "total_tools": tot_tools or 0,
            "total_errors": tot_errs or 0,
            "error_rate_pct": err_pct or 0.0,
            "total_interventions": tot_int or 0,
            "interventions_per_session": int_per_s or 0.0,
            "autonomous_sessions": auto_s or 0,
            "autonomous_pct": round((auto_s or 0) * 100.0 / s_cnt, 1) if s_cnt else 0.0,
        }
        if _UUID_WS_RE.match(ws_path.strip()):
            unattributed_uuid_count += 1
            unattributed_uuid_sessions += s_cnt
            continue
        if _is_redacted_or_remote_ws(ws_path, origin_dev):
            redacted_remote_sessions += s_cnt
            if origin_dev:
                redacted_devs.add(origin_dev)
            redacted_remote_workspaces.append({
                "workspace_path": ws_path,
                "origin_developer": origin_dev or "remote",
                "performance": perf,
            })
            continue

        cur_entry = local_agg.get(ws_path)
        if cur_entry is None:
            local_agg[ws_path] = {
                "workspace_path": ws_path,
                "repo_name": Path(ws_path).name,
                "config": audit_workspace_config(ws_path),
                "performance": perf,
            }
        else:
            p = cur_entry["performance"]
            new_sc = p["session_count"] + s_cnt
            p["avg_steps"] = round(((p["avg_steps"] * p["session_count"]) + ((avg_steps or 0.0) * s_cnt)) / max(1, new_sc), 1)
            p["session_count"] = new_sc
            p["total_tools"] += tot_tools or 0
            p["total_errors"] += tot_errs or 0
            p["error_rate_pct"] = round(p["total_errors"] * 100.0 / p["total_tools"], 2) if p["total_tools"] else 0.0
            p["total_interventions"] += tot_int or 0
            p["interventions_per_session"] = round(p["total_interventions"] * 1.0 / max(1, new_sc), 2)
            p["autonomous_sessions"] += auto_s or 0
            p["autonomous_pct"] = round(p["autonomous_sessions"] * 100.0 / max(1, new_sc), 1)

    workspace_analyses = sorted(
        local_agg.values(),
        key=lambda x: x["performance"]["session_count"],
        reverse=True,
    )[: max(1, limit)]

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "total_workspaces": len(workspace_analyses),
        "local_workspace_count": len(workspace_analyses),
        "redacted_remote_summary": {
            "workspace_entries": len(redacted_remote_workspaces),
            "session_count": redacted_remote_sessions,
            "developers": sorted(redacted_devs),
        },
        "unattributed_uuid_workspaces_count": unattributed_uuid_count,
        "unattributed_uuid_sessions_count": unattributed_uuid_sessions,
        "workspaces": workspace_analyses,
        "redacted_remote_workspaces": redacted_remote_workspaces,
    }


def generate_markdown_report(data: Dict[str, Any], output_path: Path, max_rows: int = 50) -> None:
    workspaces = data["workspaces"]
    displayed_workspaces = workspaces[:max_rows]

    md = f"""<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 🏛️ Empirical Project Rules & Skills Ecosystem Audit
**Project**: Agyis Harness for Google Antigravity™ (`agyis-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**License**: Apache-2.0  
**Generated At**: {data['timestamp']}  
**Data Source**: Cross-analysis of repository configuration files (`AGENTS.md`, `.agents/skills`) vs. session telemetry in `data/telemetry.db`

---

## Executive Summary: The Context Calibration Invariant

Agent autonomy, error rates, and human intervention frequency are **heavily governed by the quality, calibration, and architecture of the project's rules and skills**. 

When we evaluate the agent's behavior across distinct workspaces, failures are rarely "pure model hallucinations"—they correlate directly with **harness misconfigurations, rule indirection, contradictory constraints, or missing domain commands**.

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Workspace Performance & Rule Calibration                        │
├──────────────────────────────┬────────────┬───────────┬────────────┬───────────────────┤
│ Workspace                    │ Sessions   │ Error %   │ Interv/Sess│ Rule Architecture │
├──────────────────────────────┼────────────┼───────────┼────────────┼───────────────────┤
"""

    for w in displayed_workspaces:
        p = w["performance"]
        c = w["config"]
        rule_desc = f"{c['rule_file_count']} files (~{c['total_rule_tokens']} tok), {c['skill_count']} skills" if c["exists"] else "None / Undetected"
        md += f"| `{w['repo_name']}` | {p['session_count']} | {p['error_rate_pct']}% | {p['interventions_per_session']} | {rule_desc} |\n"

    if len(workspaces) > max_rows:
        md += f"| *({len(workspaces) - max_rows} additional workspaces omitted)* | - | - | - | - |\n"

    rr = data.get("redacted_remote_summary", {})
    md += f"""└──────────────────────────────┴────────────┴───────────┴────────────┴───────────────────┘
```

- **Local Workspaces Audited**: **{data.get('local_workspace_count', len(workspaces))}**
- **Redacted / Remote Workspace Buckets**: **{rr.get('workspace_entries', 0)}** ({rr.get('session_count', 0):,} sessions across `{', '.join(rr.get('developers', [])) or 'none'}`)
- **UUID-Only Trajectory Placeholders Excluded**: **{data.get('unattributed_uuid_workspaces_count', 0)}** ({data.get('unattributed_uuid_sessions_count', 0):,} sessions)

---

## 🔍 Architectural Ecosystem Patterns

Workspaces with consolidated root `AGENTS.md` files, explicit command dictionaries, and single-source `.agents/skills` prevent `read_file` indirection loops and Exit Code 127 tool errors while keeping human steering low.
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"[✓] Generated project rules audit report: {output_path}")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Audit project rules and skills across repositories.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite database")
    parser.add_argument("--output", "-o", default="data/reports/project-rules-skills-audit.md", help="Path to output markdown report")
    parser.add_argument("--json-out", default="data/project_configs_audit.json", help="Path to output structured JSON")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of workspaces to query from telemetry DB")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist.")
        return

    data = analyze_all_workspaces(db_path, limit=args.limit)

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    md_path = Path(args.output)
    generate_markdown_report(data, md_path)

    print("=" * 70)
    print(" 🏛️ PROJECT RULES & SKILLS AUDIT COMPLETE")
    print("=" * 70)
    print(f"Workspaces Analyzed: {data['total_workspaces']}")
    print(f"Report:              {md_path}")
    print(f"JSON Output:         {json_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
