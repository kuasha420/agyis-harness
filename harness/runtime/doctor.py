#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Harness for Google Antigravity™
Workstation Diagnostic & Environment Health Engine (agyis doctor)
Antigravity Immune System (Self-Healing Runtime Architecture)

Audits host workstation runtimes against harness/runtime/matrix.json across:
- Tier 1: Core Languages & Package Managers (Python >= 3.12, Node >= 20, uv, pnpm)
- Tier 2: Core SWE CLI (git, gh, ripgrep, fd)
- Tier 3: Mesh/Host (ssh, knot)

Detects pyenv/conda shim hijacking, audits hermetic uv toolchains, probes agyis/psl
CLI binaries, and provides zero-sudo auto-healing via `--heal`.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from harness.runtime.healing import heal_environment
from harness.runtime.hygiene_checks import (
    check_database_port_conflicts,
    check_duplicate_agents,
    check_duplicate_skills,
    check_hooks_health,
    check_node_script_hygiene,
)
from harness.runtime.re_checks import audit_forensic_toolchain, is_re_workspace
from harness.runtime.tool_checks import (
    REPO_ROOT,
    check_cli_binary,
    check_psl_collision,
    check_rea_tooling,
    check_tool,
    detect_os_family,
    find_hermetic_uv_python,
    find_rea_binary,
    parse_version,
)

DEFAULT_MATRIX = Path(__file__).resolve().parent / "matrix.json"

__all__ = [
    "DEFAULT_MATRIX",
    "REPO_ROOT",
    "audit_environment",
    "audit_forensic_toolchain",
    "check_architectural_fitness",
    "check_cli_binary",
    "check_database_port_conflicts",
    "check_duplicate_agents",
    "check_duplicate_skills",
    "check_hooks_health",
    "check_node_script_hygiene",
    "check_psl_collision",
    "check_rea_tooling",
    "check_telemetry_daemon",
    "check_tool",
    "deprecated_psl_doctor_main",
    "detect_os_family",
    "find_hermetic_uv_python",
    "find_rea_binary",
    "heal_environment",
    "is_re_workspace",
    "main",
    "parse_version",
    "print_cli_report",
    "run_doctor",
    "run_doctor_checks",
]


def check_architectural_fitness(workspace_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Audits workspace structural invariants and architectural fitness (ADR-014 / Phase 1)."""
    if not workspace_root:
        return None
    target_ws = Path(workspace_root).resolve()
    if not (target_ws / "harness").is_dir():
        return None
    try:
        from harness.runtime.aff import audit_architectural_fitness

        rep = audit_architectural_fitness(workspace_root=target_ws)
        return rep.to_dict()
    except Exception as exc:
        return {
            "status": "FAIL",
            "score": 0.0,
            "error": str(exc),
            "details": f"AFF evaluation crashed: {exc}",
            "scanned_files_count": 0,
            "benchmark_latency_s": 0.0,
        }


def check_telemetry_daemon() -> Optional[Dict[str, Any]]:
    """Checks the status and harvest/sync health of agyis-sync.service (Issue #55)."""
    if not shutil.which("systemctl"):
        return None

    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", "agyis-sync.service"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        output = (proc.stdout or proc.stderr or "").strip().lower()
    except Exception:
        output = "unknown"

    sync_health: Dict[str, Any] = {}
    telemetry_lag: Dict[str, Any] = {}
    try:
        from harness.telemetry.sync.daemon import compute_telemetry_lag, read_sync_status
        sync_health = read_sync_status()
        telemetry_lag = compute_telemetry_lag()
    except Exception:
        pass

    if output == "active":
        failures = int(sync_health.get("consecutive_failures") or 0)
        if failures > 0 or sync_health.get("status") == "error":
            last_err = sync_health.get("last_error") or "consecutive daemon failures"
            remediation = (
                f"agyis-sync.service is active but failing ({failures} consecutive failure(s): {last_err}). "
                "Run 'agyis sync' or check 'agyis sync --service status'."
            )
            return {
                "status": "WARNING",
                "service": "agyis-sync.service",
                "state": "active_failing",
                "message": remediation,
                "details": remediation,
                "remediation": remediation,
                "sync_health": sync_health,
                "telemetry_lag": telemetry_lag,
            }
        return {
            "status": "OK",
            "service": "agyis-sync.service",
            "state": "active",
            "message": "Telemetry Sync Service (agyis-sync.service is active)",
            "details": "Telemetry Sync Service (agyis-sync.service is active)",
            "sync_health": sync_health,
            "telemetry_lag": telemetry_lag,
        }
    elif output == "failed":
        remediation = "agyis-sync.service in failed state. Run 'agyis sync --service status' for logs."
        return {
            "status": "WARNING",
            "service": "agyis-sync.service",
            "state": "failed",
            "message": remediation,
            "details": remediation,
            "remediation": remediation,
            "sync_health": sync_health,
            "telemetry_lag": telemetry_lag,
        }
    elif output == "inactive":
        remediation = "agyis-sync.service is inactive. Run 'agyis sync --service install' / 'start' to enable background sync."
        return {
            "status": "WARNING",
            "service": "agyis-sync.service",
            "state": "inactive",
            "message": remediation,
            "details": remediation,
            "remediation": remediation,
            "sync_health": sync_health,
            "telemetry_lag": telemetry_lag,
        }
    else:
        remediation = f"agyis-sync.service is {output}. Run 'agyis sync --service install' / 'start' to enable background sync."
        return {
            "status": "WARNING",
            "service": "agyis-sync.service",
            "state": output,
            "message": remediation,
            "details": remediation,
            "remediation": remediation,
            "sync_health": sync_health,
            "telemetry_lag": telemetry_lag,
        }


def run_doctor_checks(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Runs all doctor checks and returns audit results dictionary."""
    return run_doctor(*args, **kwargs)


def audit_environment(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Alias for run_doctor for backward-compatible environment auditing."""
    return run_doctor(*args, **kwargs)


def run_doctor(
    matrix_path: Optional[Path] = None,
    workspace_root: Optional[Path] = None,
    config_dir: Optional[Path] = None,
    hooks_path: Optional[Path] = None,
    mcp_config_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    experimental_rea: bool = False,
    re_toolchain: bool = False,
) -> Dict[str, Any]:
    """Perform complete workstation runtime audit."""
    eff_matrix = matrix_path if matrix_path is not None else DEFAULT_MATRIX
    if not eff_matrix.exists():
        raise FileNotFoundError(f"Matrix file not found: {eff_matrix}")

    with open(eff_matrix, "r", encoding="utf-8") as f:
        matrix = json.load(f)

    effective_workspace = workspace_root or repo_root
    os_family = detect_os_family()
    hermetic_python = find_hermetic_uv_python()
    cli_binary = check_cli_binary()
    psl_collision = cli_binary.get("psl_details") or cli_binary.get("psl_collision") or check_psl_collision()
    duplicate_agents = check_duplicate_agents(config_dir=config_dir)
    duplicate_skills = check_duplicate_skills(workspace_root=effective_workspace, config_dir=config_dir)
    node_script_hygiene = check_node_script_hygiene(workspace_root=effective_workspace)
    hooks_health = check_hooks_health(hooks_path=hooks_path)
    architectural_fitness = check_architectural_fitness(effective_workspace)

    is_re = is_re_workspace(effective_workspace)
    re_active = re_toolchain or is_re

    # Execute independent subprocess probes concurrently to keep fast-path doctor <1.0s.
    with ThreadPoolExecutor(max_workers=12) as pool:
        fut_db = pool.submit(check_database_port_conflicts, workspace_root=effective_workspace)
        fut_daemon = pool.submit(check_telemetry_daemon)
        fut_rea = pool.submit(check_rea_tooling, mcp_config_path=mcp_config_path, experimental_rea=experimental_rea)
        fut_ft = pool.submit(audit_forensic_toolchain, workspace_dir=effective_workspace) if re_active else None
        tool_futures: Dict[Tuple[str, str], Any] = {}
        for tier_key, tier_data in matrix.get("tiers", {}).items():
            for tool_name, tool_spec in tier_data.get("tools", {}).items():
                tool_futures[(tier_key, tool_name)] = pool.submit(
                    check_tool, tool_name, tool_spec, hermetic_python
                )

        database_port_conflicts = fut_db.result()
        telemetry_daemon = fut_daemon.result()
        rea_tooling = fut_rea.result()
        forensic_toolchain = fut_ft.result() if fut_ft else None
        checked_tools = {k: fut.result() for k, fut in tool_futures.items()}

    results: Dict[str, Any] = {
        "os_family": os_family,
        "hermetic_python_available": str(hermetic_python) if hermetic_python else None,
        "path_environment": os.environ.get("PATH", ""),
        "cli_binary": cli_binary,
        "psl_collision": psl_collision,
        "duplicate_agents": duplicate_agents,
        "duplicate_skills": duplicate_skills,
        "node_script_hygiene": node_script_hygiene,
        "hooks_health": hooks_health,
        "database_port_conflicts": database_port_conflicts,
        "telemetry_daemon": telemetry_daemon,
        "rea_tooling": rea_tooling,
        "architectural_fitness": architectural_fitness,
        "experimental_rea": experimental_rea,
        "re_toolchain": re_active,
        "forensic_toolchain": forensic_toolchain,
        "tiers": {},
        "summary": {
            "total_tools": 0,
            "ok": 0,
            "warning": 0,
            "outdated": 0,
            "missing": 0,
            "optional_missing": 0,
        },
    }

    if cli_binary.get("collision") or cli_binary.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    elif psl_collision.get("collision") or psl_collision.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if duplicate_agents.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if duplicate_skills.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if node_script_hygiene.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if hooks_health.get("status") != "OK":
        results["summary"]["warning"] += 1
    if database_port_conflicts.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if telemetry_daemon and telemetry_daemon.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if architectural_fitness and architectural_fitness.get("status") in ("WARNING", "FAIL"):
        results["summary"]["warning"] += 1

    if experimental_rea:
        if rea_tooling.get("status") == "warning":
            results["summary"]["warning"] += 1
        elif rea_tooling.get("status") == "optional_missing":
            results["summary"]["optional_missing"] += 1
    else:
        # Fast path (experimental_rea=False): strictly 0 warnings added
        if rea_tooling.get("status") == "optional_missing":
            results["summary"]["optional_missing"] += 1

    if forensic_toolchain:
        ft_summ = forensic_toolchain.get("summary", {})
        results["summary"]["ok"] += ft_summ.get("pass", 0)
        results["summary"]["optional_missing"] += ft_summ.get("info", 0)
        if re_active:
            results["summary"]["warning"] += ft_summ.get("warn", 0)

    for tier_key, tier_data in matrix.get("tiers", {}).items():
        tier_results = []
        for tool_name, _ in tier_data.get("tools", {}).items():
            check = checked_tools[(tier_key, tool_name)]
            tier_results.append(check)

            st = check["status"]
            results["summary"]["total_tools"] += 1
            if st == "OK":
                results["summary"]["ok"] += 1
            elif st == "WARNING":
                results["summary"]["warning"] += 1
            elif st == "OUTDATED":
                results["summary"]["outdated"] += 1
            elif st == "MISSING":
                results["summary"]["missing"] += 1
            elif st == "OPTIONAL_MISSING":
                results["summary"]["optional_missing"] += 1

        results["tiers"][tier_key] = {
            "description": tier_data.get("description", ""),
            "tools": tier_results,
        }

    return results


def print_cli_report(audit: Dict[str, Any]) -> None:
    """Print beautifully styled terminal report."""
    print("\n" + "=" * 70)
    print(" 🩺  AGYIS WORKSTATION DOCTOR & RUNTIME GUARANTEE AUDIT")
    print("     Antigravity Immune System (Autonomous Agent Runtime)")
    print("=" * 70)
    print(f" OS Family: {audit['os_family'].upper()}")
    herm_py = audit.get("hermetic_python_available")
    if herm_py:
        print(f" Hermetic uv Python: {herm_py} (CPython >= 3.12 Ready)")
    else:
        print(" Hermetic uv Python: Not found in ~/.local/share/uv/python")

    cli_bin = audit.get("cli_binary")
    if cli_bin:
        if cli_bin.get("collision"):
            print(f" Agyis Launcher:     [\033[33mWARN\033[0m] -> {cli_bin.get('details')}")
            if cli_bin.get("remediation"):
                print(f"    Remediation:\n      {cli_bin.get('remediation')}")
        elif cli_bin.get("status") == "OK" or cli_bin.get("agyis_status") == "OK":
            print(f" Agyis Launcher:     [\033[32mPASS\033[0m] -> {cli_bin.get('agyis_path') or cli_bin.get('path')}")
        elif cli_bin.get("status") == "WARNING":
            print(f" Agyis Launcher:     [\033[33mWARN\033[0m] -> {cli_bin.get('details')}")
            if cli_bin.get("remediation"):
                print(f"    Remediation:\n      {cli_bin.get('remediation')}")
        else:
            print(f" Agyis Launcher:     [\033[34mINFO\033[0m] -> {cli_bin.get('details')}")

        psl_details = cli_bin.get("psl_details") or cli_bin.get("psl_collision") or audit.get("psl_collision")
        if psl_details:
            if psl_details.get("collision"):
                print(f" PSL Compatibility:  [\033[33mWARN\033[0m] -> {psl_details.get('details')}")
                if psl_details.get("remediation"):
                    print(f"    Remediation:\n      {psl_details.get('remediation')}")
            elif psl_details.get("status") == "OK":
                print(f" PSL Compatibility:  [\033[32mPASS\033[0m] -> {psl_details.get('path')} (Deprecated shim)")
            else:
                print(f" PSL Compatibility:  [\033[34mINFO\033[0m] -> {psl_details.get('details')}")
    else:
        psl_col = audit.get("psl_collision")
        if psl_col:
            if psl_col.get("collision"):
                print(f" PSL Launcher:       [\033[33mWARN\033[0m] -> {psl_col.get('details')}")
                if psl_col.get("remediation"):
                    print(f"    Remediation:\n      {psl_col.get('remediation')}")
            elif psl_col.get("status") == "OK":
                print(f" PSL Launcher:       [\033[32mPASS\033[0m] -> {psl_col.get('path')}")
            else:
                print(f" PSL Launcher:       [\033[34mINFO\033[0m] -> {psl_col.get('details')}")

    dup_agents = audit.get("duplicate_agents")
    if dup_agents:
        if dup_agents.get("status") == "WARNING":
            print(f" Duplicate Agents: [\033[33mWARN\033[0m] -> {dup_agents.get('details')}")
            if dup_agents.get("remediation"):
                print(f"    Remediation:\n      {dup_agents.get('remediation')}")
        elif dup_agents.get("status") == "OK":
            print(f" Duplicate Agents: [\033[32mPASS\033[0m] -> {dup_agents.get('details')}")
        else:
            print(f" Duplicate Agents: [\033[34mINFO\033[0m] -> {dup_agents.get('details')}")

    dup_skills = audit.get("duplicate_skills")
    if dup_skills:
        if dup_skills.get("status") == "WARNING":
            print(f" Duplicate Skills:    [\033[33mWARN\033[0m] -> {dup_skills.get('details')}")
            if dup_skills.get("remediation"):
                print(f"    Remediation:\n      {dup_skills.get('remediation')}")
        elif dup_skills.get("status") in ("OK", "PASS"):
            print(f" Duplicate Skills:    [\033[32mPASS\033[0m] -> {dup_skills.get('details')}")
        else:
            print(f" Duplicate Skills:    [\033[34mINFO\033[0m] -> {dup_skills.get('details')}")

    node_hyg = audit.get("node_script_hygiene")
    if node_hyg:
        if node_hyg.get("status") == "WARNING":
            print(f" Node Script Hygiene: [\033[33mWARN\033[0m] -> {node_hyg.get('details')}")
            if node_hyg.get("remediation"):
                print(f"    Remediation:\n      {node_hyg.get('remediation')}")
        elif node_hyg.get("status") == "OK":
            print(f" Node Script Hygiene: [\033[32mPASS\033[0m] -> {node_hyg.get('details')}")
        else:
            print(f" Node Script Hygiene: [\033[34mINFO\033[0m] -> {node_hyg.get('details')}")

    hooks_h = audit.get("hooks_health")
    if hooks_h:
        if hooks_h.get("status") == "WARNING":
            print(f" Lifecycle Hooks:     [\033[33mWARN\033[0m] -> {len(hooks_h.get('failures', []))} failure(s) in {hooks_h.get('hooks_path')}")
            for fail in hooks_h.get("failures", []):
                print(f"    ⚠️  {fail}")
            if hooks_h.get("remediation"):
                print(f"    Remediation:\n      {hooks_h['remediation']}")
        elif hooks_h.get("status") == "OK":
            hook_count = len(hooks_h.get("checked_hooks", []))
            print(f" Lifecycle Hooks:     [\033[32mPASS\033[0m] -> {hook_count} hooks verified ({hooks_h.get('hooks_path')})")
        else:
            print(f" Lifecycle Hooks:     [\033[34mINFO\033[0m] -> {hooks_h.get('status')}")

    db_conflict = audit.get("database_port_conflicts")
    if db_conflict:
        port = db_conflict.get("port", 5432)
        if db_conflict.get("status") == "WARNING":
            print(f" Database Port ({port}): [\033[33mWARN\033[0m] -> {db_conflict.get('details')}")
            if db_conflict.get("remediation"):
                print(f"    Remediation:\n      {db_conflict.get('remediation')}")
        elif db_conflict.get("status") in ("OK", "PASS"):
            print(f" Database Port ({port}): [\033[32mPASS\033[0m] -> {db_conflict.get('details')}")
        else:
            print(f" Database Port ({port}): [\033[34mINFO\033[0m] -> {db_conflict.get('details')}")

    telem_d = audit.get("telemetry_daemon")
    if telem_d:
        st = telem_d.get("status")
        msg = telem_d.get("message") or telem_d.get("details", "")
        if st in ("OK", "PASS"):
            print(f" Telemetry Daemon:    [\033[32mPASS\033[0m] -> {msg}")
        elif st == "WARNING":
            print(f" Telemetry Daemon:    [\033[33mWARN\033[0m] -> {msg}")
            if telem_d.get("remediation"):
                print(f"    Remediation:\n      {telem_d.get('remediation')}")
        else:
            print(f" Telemetry Daemon:    [\033[34mINFO\033[0m] -> {msg}")
        lag = telem_d.get("telemetry_lag") or {}
        sh = telem_d.get("sync_health") or {}
        if sh.get("last_harvest_at") or lag.get("unsynced_local") or lag.get("stale_local"):
            print(
                f"    Sync Health:      state={sh.get('status', 'unknown')}, "
                f"last_harvest={str(sh.get('last_harvest_at') or 'never')[:19]}, "
                f"lag={lag.get('unsynced_local', 0)} unsynced / {lag.get('stale_local', 0)} stale"
            )

    aff_data = audit.get("architectural_fitness")
    if aff_data:
        st = aff_data.get("status", "PASS")
        score = aff_data.get("score", 100.0)
        scanned = aff_data.get("scanned_files_count", 0)
        lat = aff_data.get("benchmark_latency_s", 0.0)
        if st in ("PASS", "OK"):
            print(f" Architectural Fitness (AFF): [\033[32mPASS\033[0m] -> Score: {score:.1f}/100 ({scanned} files in {lat:.3f}s)")
        elif st == "WARNING":
            print(f" Architectural Fitness (AFF): [\033[33mWARN\033[0m] -> Score: {score:.1f}/100 ({scanned} files in {lat:.3f}s)")
        else:
            print(f" Architectural Fitness (AFF): [\033[31mFAIL\033[0m] -> Score: {score:.1f}/100 ({scanned} files in {lat:.3f}s)")

    rea_t = audit.get("rea_tooling")
    if rea_t:
        st = rea_t.get("status")
        fast_path = rea_t.get("fast_path", False)
        if fast_path:
            if st == "ok":
                print(f" REA Tooling:         [\033[32mPASS\033[0m] -> {rea_t.get('details')}")
            else:
                print(" REA Tooling:         [\033[34mINFO\033[0m] -> REA not detected (optional reverse engineering toolchain)")
                if rea_t.get("remediation"):
                    print(f"    Remediation:\n      {rea_t.get('remediation')}")
        else:
            if st == "ok":
                v = rea_t.get("version") or "unknown"
                bin_path = rea_t.get("binary") or "rea"
                prov_active = len((rea_t.get("providers") or {}).get("active") or [])
                mcp_str = "Configured" if rea_t.get("mcp_configured") else "Not configured"
                print(f" REA Tooling:         [\033[32mPASS\033[0m] -> rea {v} ({bin_path}) | Providers: {prov_active} active | MCP: {mcp_str}")
            elif st == "optional_missing":
                print(" REA Tooling:         [\033[34mINFO\033[0m] -> REA not detected (optional reverse engineering toolchain)")
                if rea_t.get("remediation"):
                    print(f"    Remediation:\n      {rea_t.get('remediation')}")
            elif st == "warning":
                print(f" REA Tooling:         [\033[33mWARN\033[0m] -> {rea_t.get('details')}")
                if rea_t.get("remediation"):
                    print(f"    Remediation:\n      {rea_t.get('remediation')}")
            else:
                print(f" REA Tooling:         [\033[34mINFO\033[0m] -> {rea_t.get('details', '')}")

            # Dynamic render of native provider candidates from rea providers --json
            prov_data = rea_t.get("providers") or {}
            details = prov_data.get("details") or []
            for p in details:
                name = p.get("name") or "Unknown"
                is_avail = p.get("available")
                reason = p.get("reason")
                if is_avail:
                    print(f"   • {name:20}: [\033[32mPASS\033[0m] -> Active & verified")
                else:
                    reason_str = f" ({reason})" if reason else ""
                    print(f"   • {name:20}: [\033[34mINFO\033[0m] -> Unavailable{reason_str}")
    print("-" * 70)

    symbols = {
        "OK": "[\033[32mPASS\033[0m]",
        "PASS": "[\033[32mPASS\033[0m]",
        "WARNING": "[\033[33mWARN\033[0m]",
        "WARN": "[\033[33mWARN\033[0m]",
        "OUTDATED": "[\033[31mFAIL\033[0m]",
        "MISSING": "[\033[31mMISS\033[0m]",
        "OPTIONAL_MISSING": "[\033[34mINFO\033[0m]",
        "INFO": "[\033[34mINFO\033[0m]",
        "UNKNOWN_VERSION": "[\033[33mUNKN\033[0m]",
    }

    for tier_key, tier_data in audit["tiers"].items():
        tier_title = tier_key.replace("_", " ").upper()
        print(f"\n▶ {tier_title}: {tier_data['description']}")
        for tool in tier_data["tools"]:
            sym = symbols.get(tool["status"], "[????]")
            v_info = tool["version"] or "N/A"
            req_info = f"(min: {tool['min_version']})" if tool["min_version"] else ""
            shim_note = f" ⚠️  {tool['shim_details']}" if tool["is_shim"] else ""
            print(f"  {sym:16} {tool['name']:10} {v_info:12} {req_info:14} -> {tool['path'] or 'NOT FOUND'}{shim_note}")

    ft = audit.get("forensic_toolchain")
    if ft:
        prof = ft.get("profile", "static-cleanroom")
        print(f"\n▶ REVERSE ENGINEERING & DIRTYROOM TOOLCHAIN (Profile: {prof})")
        for tool in ft.get("tools", []):
            st = tool.get("status", "INFO")
            sym = symbols.get(st, f"[{st:^4}]")
            t_name = tool.get("name", "tool")
            v_info = tool.get("version") or "N/A"
            p_info = tool.get("path") or "NOT FOUND"
            cat = f"[{tool.get('category', 'core')}]"
            print(f"  {sym:16} {t_name:20} {cat:10} {v_info:14} -> {p_info}")
        if ft.get("remediation"):
            print("    Remediation:")
            for rem in ft.get("remediation"):
                print(f"      • {rem}")

    summ = audit["summary"]
    print("\n" + "-" * 70)
    print(f" Summary: {summ['ok']} OK | {summ['warning']} Warnings | {summ['outdated']} Outdated | {summ['missing']} Missing")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Agyis Workstation Diagnostic & Runtime Guarantee (Antigravity Immune System)"
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX,
        help="Path to matrix.json",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON results")
    parser.add_argument("--heal", action="store_true", help="Execute safe user-space auto-healing")
    parser.add_argument(
        "--experimental-rea",
        action="store_true",
        help="Enable experimental Reverse Engineer Anything (REA) diagnostics and provider audit",
    )
    parser.add_argument(
        "--re",
        dest="re_toolchain",
        action="store_true",
        help="Audit reverse engineering & dirtyroom forensic toolchain (Ghidra, objdump, tshark, ydotool)",
    )
    args = parser.parse_args()

    exp_rea = getattr(args, "experimental_rea", False)
    re_tool = getattr(args, "re_toolchain", False)
    audit = run_doctor(args.matrix, experimental_rea=exp_rea, re_toolchain=re_tool)

    if args.json:
        print(json.dumps(audit, indent=2))
        return 0

    print_cli_report(audit)

    if args.heal:
        print("\n🔧 Executing Auto-Healing...")
        actions = heal_environment(
            audit,
            args.matrix,
            experimental_rea=exp_rea,
            re_toolchain=re_tool,
        )
        for act in actions:
            print(f"  ✔ {act}")
        print()

    # Non-zero exit if required tools are missing or outdated
    if audit["summary"]["missing"] > 0 or audit["summary"]["outdated"] > 0:
        return 1
    return 0


def deprecated_psl_doctor_main() -> int:
    """Deprecated entrypoint for legacy 'psl-doctor'."""
    sys.stderr.write(
        "DeprecationWarning: 'psl-doctor' is deprecated and will be removed in 3 months. Use 'agyis doctor' instead.\n"
    )
    sys.stderr.flush()
    return main()


if __name__ == "__main__":
    sys.exit(main())
