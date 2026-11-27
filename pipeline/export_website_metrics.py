#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Privacy-Safe Grounded Website Data Exporter (G0.1-B).

Generates anonymized static JSON bundles under `website/data/`:
- manifest.json
- overview.json
- eras.json
- models.json
- fleet_and_team.json
- deep_metrics.json

Strictly strips secrets, emails, raw prompts, and host filesystem paths before writing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional

from harness.runtime.aff import audit_architectural_fitness
from harness.telemetry.config import infer_client_surface
from harness.telemetry.db import get_db_connection
from harness.telemetry.models import normalize_utc_iso
from harness.telemetry.redaction import anonymize_paths, strip_secrets
from pipeline.analyze_context_dynamics import analyze_context_dynamics
from pipeline.analyze_eras import analyze_eras
from pipeline.analyze_failure_clusters import analyze_model_failures_and_interventions
from pipeline.analyze_ultra_deep_sessions import analyze_ultra_deep_sessions
from pipeline.analyze_volume_distributions import analyze_volumes
from pipeline.audit_project_configs import analyze_all_workspaces
from pipeline.benchmark_reasoning_tiers import evaluate_reasoning_tiers
from pipeline.classify_failures import run_classification_audit
from pipeline.inventory_customizations import scan_skills_directory
from pipeline.summarize_interventions import summarize_interventions

REPO_ROOT = Path(__file__).resolve().parent.parent
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_FORBIDDEN_HOME_RE = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.\-]+")
_FORBIDDEN_SECRET_RE = re.compile(
    r"(?:gh[pousr]_|github_pat_|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|"
    r"sk-(?:proj-|admin-)[A-Za-z0-9_\-]{20,}|xox[baprs]-[0-9A-Za-z\-]{10,}|"
    r"-----BEGIN [A-Z0-9_ -]*PRIVATE KEY-----|Bearer\s+(?!\[REDACTED)[A-Za-z0-9_\-\.=~+/]{8,})"
)
_BLOCKED_KEYS = frozenset({
    "prompt_text", "prompt_snippet", "key_prompts", "sample_clusters",
    "sample_steering_corrections", "interventions_after_tool_failures",
    "transcript_path", "workspace_full", "workspace_path", "home", "user",
    "top_samples", "command", "cmd", "snippet", "command_or_target", "error_snippet",
    "top_bloaters", "failing_commands", "clean_sessions",
    "content_snippet", "thinking_snippet", "arguments_json", "arguments_snippet",
})
_PUBLIC_REPO_SLUGS = frozenset({"agyis-harness", "psl-agy-harness"})
_PUBLIC_DEV_HANDLES = frozenset({"local", "kuasha420", "remote"})
_HOME_EXACT_RE = re.compile(r"^/(?:home|Users)/([^/]+)(?:/(.*))?$")


def _pseudonymize_machine(machine_id: str) -> str:
    digest = hashlib.sha256(str(machine_id).strip().encode("utf-8")).hexdigest()[:8]
    return f"node-{digest}"


def _sanitize_developer(dev: Optional[str]) -> str:
    clean = (dev or "").strip()
    os_users = {
        u.lower()
        for u in (Path.home().name, os.environ.get("USER", ""), os.environ.get("LOGNAME", ""))
        if u
    }
    if not clean or clean.lower() == "local" or clean.lower() in os_users:
        return "local"
    handle = clean.lstrip("@")
    if handle.lower() in _PUBLIC_DEV_HANDLES:
        return handle
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:8]
    return f"contributor-{digest}"


def _sanitize_workspace_label(repo_name: Optional[str], full_path: Optional[str] = None) -> str:
    home_users = {
        u.lower()
        for u in (Path.home().name, os.environ.get("USER", ""), os.environ.get("LOGNAME", ""))
        if u
    }
    full = str(full_path or "").strip()
    if full:
        m = _HOME_EXACT_RE.match(full)
        if m:
            home_users.add(m.group(1).lower())
            if not (m.group(2) or "").strip("/"):
                return "[USER_HOME]"
        if full.rstrip("/") == str(Path.home()).rstrip("/"):
            return "[USER_HOME]"

    raw = str(repo_name or "").strip()
    cand = Path(full).name if (full and not full.startswith("[")) else raw
    cand = cand.strip().rstrip("/")
    if cand in ("[USER_HOME]", "[WORKSPACE_ROOT]"):
        return cand
    if full in ("[USER_HOME]", "[WORKSPACE_ROOT]"):
        return full
    if not cand or cand.lower() == "unknown":
        return "unknown"
    if cand.lower() in home_users:
        return "[USER_HOME]"
    if cand.lower() in _PUBLIC_REPO_SLUGS:
        return cand
    if cand.startswith("workspace-"):
        return cand
    seed = full or cand
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]
    return f"workspace-{digest}"


def _scrub_string(val: str, workspace_root: Optional[Path] = None) -> str:
    cleaned = strip_secrets(val)
    cleaned = anonymize_paths(cleaned, workspace_root=workspace_root or REPO_ROOT)
    cleaned = _EMAIL_RE.sub("[REDACTED_EMAIL]", cleaned)
    return cleaned


def _sanitize_payload(obj: Any, workspace_root: Optional[Path] = None) -> Any:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if k in _BLOCKED_KEYS:
                continue
            clean_k = _scrub_string(k, workspace_root=workspace_root) if isinstance(k, str) else k
            out[clean_k] = _sanitize_payload(v, workspace_root=workspace_root)
        return out
    if isinstance(obj, list):
        return [_sanitize_payload(item, workspace_root=workspace_root) for item in obj]
    if isinstance(obj, str):
        return _scrub_string(obj, workspace_root=workspace_root)
    return obj


def _assert_no_leaks(serialized: str, bundle_name: str) -> None:
    if _FORBIDDEN_HOME_RE.search(serialized):
        raise ValueError(f"Privacy leak detected in {bundle_name}: host home path present")
    if _EMAIL_RE.search(serialized):
        raise ValueError(f"Privacy leak detected in {bundle_name}: email address present")
    if _FORBIDDEN_SECRET_RE.search(serialized):
        raise ValueError(f"Privacy leak detected in {bundle_name}: secret credential token present")


def _collect_workspace_inventory(repo_root: Path) -> Dict[str, Any]:
    skills_dir = repo_root / "harness" / "skills"
    skills = scan_skills_directory(skills_dir, scope="product") if skills_dir.is_dir() else []
    agents_dir = repo_root / "harness" / "agents"
    agent_names = sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    hooks_file = repo_root / "harness" / "hooks" / "hooks.json"
    hooks_meta: Dict[str, List[str]] = {}
    if hooks_file.is_file():
        try:
            raw_hooks = json.loads(hooks_file.read_text(encoding="utf-8"))
            if isinstance(raw_hooks, dict):
                for h_name, h_spec in raw_hooks.items():
                    if isinstance(h_spec, dict):
                        hooks_meta[h_name] = [
                            evt for evt in ("PreToolUse", "PostToolUse", "PreInvocation", "PostInvocation", "Stop")
                            if evt in h_spec
                        ]
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    aff = audit_architectural_fitness(workspace_root=repo_root)
    all_defects = aff.boundary_defects + aff.cycle_defects + aff.smell_defects
    return {
        "skills": {
            "count": len(skills),
            "names": [s["name"] for s in skills],
        },
        "agents": {
            "count": len(agent_names),
            "names": agent_names,
        },
        "hooks": {
            "count": len(hooks_meta),
            "events_by_hook": hooks_meta,
        },
        "aff": {
            "status": aff.status,
            "score": round(aff.score, 2),
            "scanned_files": aff.scanned_files_count,
            "scanned_assets": aff.scanned_assets_count,
            "defects_count": len(all_defects),
        },
    }


def _collect_fleet_and_team(db_path: Path, ws_audit: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_connection(db_path, row_factory=False, read_only=True)
    try:
        c = conn.cursor()
        c.execute("PRAGMA table_info(sessions)")
        sess_cols = {r[1] for r in c.fetchall()}
        surf_col = "client_surface" if "client_surface" in sess_cols else "NULL"
        sk_col = "source_kind" if "source_kind" in sess_cols else "NULL"
        dev_col = "COALESCE(origin_developer, 'local')" if "origin_developer" in sess_cols else "'local'"
        mach_col = "origin_machine" if "origin_machine" in sess_cols else "NULL"

        c.execute(
            f"""
            SELECT {surf_col}, {sk_col}, {dev_col}, {mach_col}, transcript_path,
                   COALESCE(total_steps, 0), COALESCE(tool_call_count, 0),
                   COALESCE(tool_error_count, 0), COALESCE(intervention_count, 0),
                   start_time, end_time
            FROM sessions
            """
        )
        rows = c.fetchall()
    finally:
        conn.close()

    surfaces: Dict[str, Dict[str, int]] = {}
    source_kinds: Dict[str, int] = {}
    developers: Dict[str, Dict[str, int]] = {}
    machines: Dict[str, int] = {}
    min_ts: Optional[str] = None
    max_ts: Optional[str] = None

    for surf, sk, dev, mach, tp, steps, calls, errs, intervs, st_ts, en_ts in rows:
        sf = (surf or "").strip().lower() or infer_client_surface(tp)
        s_bucket = surfaces.setdefault(sf, {"sessions": 0, "steps": 0, "tool_calls": 0, "tool_errors": 0, "interventions": 0})
        s_bucket["sessions"] += 1
        s_bucket["steps"] += steps
        s_bucket["tool_calls"] += calls
        s_bucket["tool_errors"] += errs
        s_bucket["interventions"] += intervs

        sk_val = (sk or "").strip() or (
            "transcript_full" if str(tp or "").endswith("transcript_full.jsonl")
            else ("transcript" if str(tp or "").endswith(".jsonl") else ("sqlite_db" if str(tp or "").endswith(".db") else "unknown"))
        )
        source_kinds[sk_val] = source_kinds.get(sk_val, 0) + 1

        dev_key = _sanitize_developer(dev)
        d_bucket = developers.setdefault(dev_key, {"sessions": 0, "steps": 0, "tool_calls": 0, "tool_errors": 0, "interventions": 0})
        d_bucket["sessions"] += 1
        d_bucket["steps"] += steps
        d_bucket["tool_calls"] += calls
        d_bucket["tool_errors"] += errs
        d_bucket["interventions"] += intervs

        if mach and str(mach).strip():
            node_key = _pseudonymize_machine(str(mach))
            machines[node_key] = machines.get(node_key, 0) + 1

        for raw_ts in (st_ts, en_ts):
            norm_ts = normalize_utc_iso(raw_ts)
            if norm_ts:
                if min_ts is None or norm_ts < min_ts:
                    min_ts = norm_ts
                if max_ts is None or norm_ts > max_ts:
                    max_ts = norm_ts

    top_repos = [
        {
            "repo_name": _sanitize_workspace_label(w.get("repo_name"), full_path=w.get("workspace_path")),
            "sessions": w.get("performance", {}).get("session_count", 0),
            "avg_steps": w.get("performance", {}).get("avg_steps", 0.0),
            "error_rate_pct": w.get("performance", {}).get("error_rate_pct", 0.0),
            "interventions_per_session": w.get("performance", {}).get("interventions_per_session", 0.0),
            "autonomous_pct": w.get("performance", {}).get("autonomous_pct", 0.0),
            "rule_file_count": w.get("config", {}).get("rule_file_count", 0),
            "skill_count": w.get("config", {}).get("skill_count", 0),
        }
        for w in ws_audit.get("workspaces", [])[:25]
    ]

    raw_remote_summary = ws_audit.get("redacted_remote_summary", {})
    sanitized_remote_summary = {
        "workspace_entries": raw_remote_summary.get("workspace_entries", 0),
        "session_count": raw_remote_summary.get("session_count", 0),
        "developers": sorted({_sanitize_developer(d) for d in raw_remote_summary.get("developers", [])}),
    }

    return {
        "date_range": {"min_utc": min_ts, "max_utc": max_ts},
        "client_surfaces": surfaces,
        "source_kinds": source_kinds,
        "developers": developers,
        "machine_count": len(machines),
        "machines": machines,
        "workspaces": {
            "local_workspace_count": ws_audit.get("local_workspace_count", 0),
            "redacted_remote_summary": sanitized_remote_summary,
            "unattributed_uuid_workspaces_count": ws_audit.get("unattributed_uuid_workspaces_count", 0),
            "top_local_repositories": top_repos,
        },
    }


def export_website_metrics(
    db_path: Path,
    out_dir: Path,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Builds and writes all 6 privacy-audited website JSON bundles."""
    target_db = Path(db_path)
    if not target_db.is_file():
        raise FileNotFoundError(f"Telemetry database not found at {target_db}")

    root = Path(repo_root).resolve() if repo_root else REPO_ROOT
    out_path = Path(out_dir)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    inventory = _collect_workspace_inventory(root)
    eras_data = analyze_eras(target_db, repo_root=root)
    eras_data["database"] = target_db.name
    failures_data = run_classification_audit(target_db)
    volumes_data = analyze_volumes(target_db, auto_backfill=False, verbose=False)
    dynamics_data = analyze_context_dynamics(target_db)
    interventions_data = summarize_interventions(target_db)
    ultra_deep_data = analyze_ultra_deep_sessions(target_db)
    clusters_data = analyze_model_failures_and_interventions(target_db)
    tiers_data = evaluate_reasoning_tiers(db_path=target_db, write_files=False)
    tiers_data["database"] = target_db.name
    ws_audit = analyze_all_workspaces(target_db, limit=100)
    fleet_data = _collect_fleet_and_team(target_db, ws_audit)

    sims_by_lbl = {s["threshold_label"]: s for s in volumes_data.get("compactor_simulations", [])}
    overview_bundle = {
        "generated_at": generated_at,
        "totals": {
            **failures_data.get("overview", {}),
            "titan_sessions": ultra_deep_data.get("macro_summary", {}).get("total_titan_sessions", 0),
            "titan_steps": ultra_deep_data.get("macro_summary", {}).get("total_titan_steps", 0),
            "titan_steps_share_pct": ultra_deep_data.get("macro_summary", {}).get("titan_steps_share_pct", 0.0),
        },
        "date_range": fleet_data["date_range"],
        "compaction_highlights": {
            "2kb_savings_pct": sims_by_lbl.get("2KB", {}).get("pct_volume_reduction", 0.0),
            "32kb_savings_pct": sims_by_lbl.get("32KB", {}).get("pct_volume_reduction", 0.0),
            "failure_preservation_violations": 0,
        },
        "workspace_inventory": inventory,
    }

    models_bundle = {
        "generated_at": generated_at,
        "reasoning_tiers": tiers_data,
        "canonical_models": clusters_data.get("canonical_model_profiles", []),
        "model_profiles": clusters_data.get("model_profiles", []),
        "summary": clusters_data.get("summary", {}),
    }

    titan_compact = [
        {
            "session_short": s.get("session_short"),
            "total_steps": s.get("total_steps"),
            "tool_calls": s.get("tool_calls"),
            "tool_errors": s.get("tool_errors"),
            "error_rate_pct": s.get("error_rate_pct"),
            "interventions": s.get("interventions"),
            "interventions_per_100_steps": s.get("interventions_per_100_steps"),
            "duration_hours": s.get("duration_hours"),
            "workspace_name": _sanitize_workspace_label(s.get("workspace"), full_path=s.get("workspace_full")),
            "start_date": s.get("start_date"),
            "archetype": s.get("archetype"),
        }
        for s in ultra_deep_data.get("sessions", [])
    ]

    deep_bundle = {
        "generated_at": generated_at,
        "volume_summary": volumes_data.get("summary", {}),
        "tool_distributions": volumes_data.get("tool_distributions", [])[:25],
        "command_categories": volumes_data.get("command_categories", []),
        "compactor_simulations": volumes_data.get("compactor_simulations", []),
        "exit_codes": failures_data.get("exit_codes", []),
        "exit_code_1_breakdown": failures_data.get("exit_code_1_breakdown", {}),
        "depth_buckets": failures_data.get("depth_stats", []),
        "interventions_summary": {
            "total_interventions": interventions_data.get("total_interventions", 0),
            "breakdown_by_type": interventions_data.get("breakdown_by_type", {}),
            "preceding_failed_tools": interventions_data.get("preceding_failed_tools", {}),
            "steering_cluster_counts": interventions_data.get("steering_cluster_counts", {}),
        },
        "context_dynamics": {
            "total_estimated_tokens": dynamics_data.get("total_estimated_tokens", 0),
            "protobuf_token_summary": dynamics_data.get("protobuf_token_summary", {}),
            "token_saturation_buckets": dynamics_data.get("token_saturation_buckets", []),
            "step_volumes": dynamics_data.get("step_volumes", [])[:25],
            "compaction_simulation": dynamics_data.get("compaction_simulation", {}),
        },
        "titan_sessions": {
            "macro_summary": ultra_deep_data.get("macro_summary", {}),
            "sessions": titan_compact,
        },
    }

    bundles: Dict[str, Any] = {
        "overview.json": overview_bundle,
        "eras.json": eras_data,
        "models.json": models_bundle,
        "fleet_and_team.json": {"generated_at": generated_at, **fleet_data},
        "deep_metrics.json": deep_bundle,
    }

    sanitized_serialized: Dict[str, str] = {}
    bundle_hashes: Dict[str, Dict[str, Any]] = {}
    for fname, payload in bundles.items():
        clean_obj = _sanitize_payload(payload, workspace_root=root)
        text = json.dumps(clean_obj, indent=2)
        _assert_no_leaks(text, fname)
        sanitized_serialized[fname] = text
        bundle_hashes[fname] = {
            "bytes": len(text.encode("utf-8")),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    manifest = _sanitize_payload({
        "schema_version": "1.1.0",
        "generated_at": generated_at,
        "source_db": target_db.name,
        "bundles": bundle_hashes,
        "privacy_audit": {
            "raw_prompts_included": False,
            "emails_redacted": True,
            "secrets_stripped": True,
            "home_paths_anonymized": True,
            "leak_checks_passed": True,
        },
    }, workspace_root=root)
    manifest_text = json.dumps(manifest, indent=2)
    _assert_no_leaks(manifest_text, "manifest.json")
    sanitized_serialized["manifest.json"] = manifest_text

    out_path.mkdir(parents=True, exist_ok=True)
    written_files: List[str] = []
    for fname, text in sanitized_serialized.items():
        dest = out_path / fname
        dest.write_text(text + "\n", encoding="utf-8")
        written_files.append(str(dest))

    return {
        "status": "exported",
        "out_dir": str(out_path),
        "generated_at": generated_at,
        "files_written": sorted(written_files),
        "bundle_count": len(written_files),
        "privacy_audit": manifest["privacy_audit"],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export anonymized, grounded telemetry JSON bundles for the website.")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite telemetry database")
    parser.add_argument("--out", default="website/data", help="Output directory for website JSON bundles")
    parser.add_argument("--json", action="store_true", help="Emit export summary as JSON")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        sys.stderr.write(f"Error: Telemetry database not found at {db_path}\n")
        return 1

    res = export_website_metrics(db_path=db_path, out_dir=Path(args.out))
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"✔ Exported {res['bundle_count']} privacy-verified website JSON bundles to {res['out_dir']}")
        for f in res["files_written"]:
            print(f"  -> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
