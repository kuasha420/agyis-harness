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
from harness.runtime.tool_checks_common import register_rea_flags
from harness.utils import theme

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
    except (ImportError, OSError, ValueError, RuntimeError):
        sync_health = {}
        telemetry_lag = {}

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


def _workspace_config_has_rea(workspace_root: Optional[Path] = None) -> bool:
    """Return True when workspace .agyis/config.json or .psl/config.json enables REA."""
    curr = (workspace_root or Path.cwd()).resolve()
    for rel in (".agyis/config.json", ".psl/config.json"):
        cfg_file = curr / rel
        if not cfg_file.is_file():
            continue
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and bool(data.get("rea") or data.get("experimental_rea")):
            return True
    return False


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
    rea: bool = False,
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
    ws_cfg_rea = _workspace_config_has_rea(effective_workspace)
    re_active = bool(re_toolchain or is_re)
    rea_active = bool(rea or experimental_rea or re_active or ws_cfg_rea)

    # Execute independent subprocess probes concurrently to keep fast-path doctor <1.0s.
    with ThreadPoolExecutor(max_workers=12) as pool:
        fut_db = pool.submit(check_database_port_conflicts, workspace_root=effective_workspace)
        fut_daemon = pool.submit(check_telemetry_daemon)
        fut_rea = pool.submit(
            check_rea_tooling,
            mcp_config_path=mcp_config_path,
            experimental_rea=rea_active,
            rea=rea_active,
        )
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

    antigravity_surfaces = {
        "desktop_bin": shutil.which("antigravity"),
        "cli_bin": shutil.which("agy"),
        "ide_bin": shutil.which("antigravity-ide"),
        "desktop_dir": (Path.home() / ".gemini" / "antigravity").is_dir(),
        "cli_dir": (Path.home() / ".gemini" / "antigravity-cli").is_dir(),
        "ide_dir": (Path.home() / ".gemini" / "antigravity-ide").is_dir(),
        "canonical_config": (Path.home() / ".gemini" / "config" / "config.json").is_file(),
        "cli_settings": (Path.home() / ".gemini" / "antigravity-cli" / "settings.json").is_file(),
    }

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
        "antigravity_surfaces": antigravity_surfaces,
        "rea": rea_active,
        "experimental_rea": rea_active,
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

    if rea_active:
        if rea_tooling.get("status") == "warning":
            results["summary"]["warning"] += 1
        elif rea_tooling.get("status") == "optional_missing":
            results["summary"]["optional_missing"] += 1
    else:
        # Fast path (rea_active=False): strictly 0 warnings added
        if rea_tooling.get("status") == "optional_missing":
            results["summary"]["optional_missing"] += 1

    if forensic_toolchain:
        ft_summ = forensic_toolchain.get("summary", {})
        results["summary"]["forensic_pass"] = ft_summ.get("pass", 0)
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


def _format_status_row(label: str, kind: str, detail: str, remediation: Optional[str] = None, label_width: int = 21) -> None:
    """Print an aligned status row with bracketed badge and optional remediation."""
    badge_txt = theme.badge(kind, kind, bracketed=True)
    print(f" {theme.pad_display(label, label_width)} {badge_txt} -> {detail}")
    if remediation:
        print(f"    Remediation:\n      {remediation}")


def print_cli_report(audit: Dict[str, Any]) -> None:
    """Print beautifully styled terminal report."""
    print(
        "\n"
        + theme.banner(
            "AGYIS WORKSTATION DOCTOR & RUNTIME GUARANTEE AUDIT",
            subtitle="Antigravity Immune System (Autonomous Agent Runtime)",
        )
    )
    print(f" OS Family: {audit['os_family'].upper()}")
    herm_py = audit.get("hermetic_python_available")
    if herm_py:
        print(f" Hermetic uv Python: {herm_py} (CPython >= 3.12 Ready)")
    else:
        print(" Hermetic uv Python: Not found in ~/.local/share/uv/python")

    cli_bin = audit.get("cli_binary")
    if cli_bin:
        if cli_bin.get("collision") or cli_bin.get("status") == "WARNING":
            _format_status_row("Agyis Launcher:", "WARN", str(cli_bin.get("details", "")), cli_bin.get("remediation"), 20)
        elif cli_bin.get("status") == "OK" or cli_bin.get("agyis_status") == "OK":
            _format_status_row("Agyis Launcher:", "PASS", str(cli_bin.get("agyis_path") or cli_bin.get("path") or ""), None, 20)
        else:
            _format_status_row("Agyis Launcher:", "INFO", str(cli_bin.get("details", "")), None, 20)

        psl_details = cli_bin.get("psl_details") or cli_bin.get("psl_collision") or audit.get("psl_collision")
        if psl_details:
            if psl_details.get("collision"):
                _format_status_row("Legacy 'psl' Alias:", "WARN", str(psl_details.get("details", "")), psl_details.get("remediation"), 20)
            elif psl_details.get("status") == "OK":
                _format_status_row("Legacy 'psl' Alias:", "PASS", f"{psl_details.get('path')} (Deprecated shim)", None, 20)
            else:
                _format_status_row("Legacy 'psl' Alias:", "INFO", str(psl_details.get("details", "")), None, 20)
    else:
        psl_col = audit.get("psl_collision")
        if psl_col:
            if psl_col.get("collision"):
                _format_status_row("Legacy 'psl' Alias:", "WARN", str(psl_col.get("details", "")), psl_col.get("remediation"), 20)
            elif psl_col.get("status") == "OK":
                _format_status_row("Legacy 'psl' Alias:", "PASS", str(psl_col.get("path", "")), None, 20)
            else:
                _format_status_row("Legacy 'psl' Alias:", "INFO", str(psl_col.get("details", "")), None, 20)

    for key, label, lw in (
        ("duplicate_agents", "Duplicate Agents:", 21),
        ("duplicate_skills", "Duplicate Skills:", 21),
        ("node_script_hygiene", "Node Script Hygiene:", 21),
    ):
        item = audit.get(key)
        if not item:
            continue
        st = item.get("status")
        if st == "WARNING":
            _format_status_row(label, "WARN", str(item.get("details", "")), item.get("remediation"), lw)
        elif st in ("OK", "PASS"):
            _format_status_row(label, "PASS", str(item.get("details", "")), None, lw)
        else:
            _format_status_row(label, "INFO", str(item.get("details", "")), None, lw)

    hooks_h = audit.get("hooks_health")
    if hooks_h:
        if hooks_h.get("status") == "WARNING":
            _format_status_row("Lifecycle Hooks:", "WARN", f"{len(hooks_h.get('failures', []))} failure(s) in {hooks_h.get('hooks_path')}")
            for fail in hooks_h.get("failures", []):
                print(f"    {theme.badge('WARN', str(fail))}")
            if hooks_h.get("remediation"):
                print(f"    Remediation:\n      {hooks_h['remediation']}")
        elif hooks_h.get("status") == "OK":
            hook_count = len(hooks_h.get("checked_hooks", []))
            _format_status_row("Lifecycle Hooks:", "PASS", f"{hook_count} hooks verified ({hooks_h.get('hooks_path')})")
        else:
            _format_status_row("Lifecycle Hooks:", "INFO", str(hooks_h.get("status", "")))

    db_conflict = audit.get("database_port_conflicts")
    if db_conflict:
        port = db_conflict.get("port", 5432)
        db_st = db_conflict.get("status")
        db_kind = "WARN" if db_st == "WARNING" else ("PASS" if db_st in ("OK", "PASS") else "INFO")
        _format_status_row(f"Database Port ({port}):", db_kind, str(db_conflict.get("details", "")), db_conflict.get("remediation") if db_kind == "WARN" else None)

    telem_d = audit.get("telemetry_daemon")
    if telem_d:
        st = telem_d.get("status")
        msg = str(telem_d.get("message") or telem_d.get("details", ""))
        td_kind = "PASS" if st in ("OK", "PASS") else ("WARN" if st == "WARNING" else "INFO")
        _format_status_row("Telemetry Daemon:", td_kind, msg, telem_d.get("remediation") if td_kind == "WARN" else None)
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
        aff_kind = "PASS" if st in ("PASS", "OK") else ("WARN" if st == "WARNING" else "FAIL")
        _format_status_row("Architectural Fitness (AFF):", aff_kind, f"Score: {score:.1f}/100 ({scanned} files in {lat:.3f}s)", label_width=28)

    rea_t = audit.get("rea_tooling")
    if rea_t:
        st = rea_t.get("status")
        fast_path = rea_t.get("fast_path", False)
        if fast_path:
            if st == "ok":
                _format_status_row("REA Tooling:", "PASS", str(rea_t.get("details", "")))
            else:
                _format_status_row("REA Tooling:", "INFO", "REA not detected (optional reverse engineering toolchain)", rea_t.get("remediation"))
        else:
            if st == "ok":
                v = rea_t.get("version") or "unknown"
                bin_path = rea_t.get("binary") or "rea"
                prov_active = len((rea_t.get("providers") or {}).get("active") or [])
                mcp_str = "Configured" if rea_t.get("mcp_configured") else "Not configured"
                _format_status_row("REA Tooling:", "PASS", f"rea {v} ({bin_path}) | Providers: {prov_active} active | MCP: {mcp_str}")
            elif st == "optional_missing":
                _format_status_row("REA Tooling:", "INFO", "REA not detected (optional reverse engineering toolchain)", rea_t.get("remediation"))
            elif st == "warning":
                _format_status_row("REA Tooling:", "WARN", str(rea_t.get("details", "")), rea_t.get("remediation"))
            else:
                _format_status_row("REA Tooling:", "INFO", str(rea_t.get("details", "")))

            prov_data = rea_t.get("providers") or {}
            for p in prov_data.get("details") or []:
                name = str(p.get("name") or "Unknown")
                if p.get("available"):
                    sym = theme.badge("PASS", "PASS", bracketed=True)
                    print(f"   • {theme.pad_display(name, 20)}: {sym} -> Active & verified")
                else:
                    sym = theme.badge("INFO", "INFO", bracketed=True)
                    reason_str = f" ({p.get('reason')})" if p.get("reason") else ""
                    print(f"   • {theme.pad_display(name, 20)}: {sym} -> Unavailable{reason_str}")
    print(theme.rule())

    symbols = {
        "OK": theme.badge("PASS", "PASS", bracketed=True),
        "PASS": theme.badge("PASS", "PASS", bracketed=True),
        "WARNING": theme.badge("WARN", "WARN", bracketed=True),
        "WARN": theme.badge("WARN", "WARN", bracketed=True),
        "OUTDATED": theme.badge("FAIL", "FAIL", bracketed=True),
        "MISSING": theme.badge("MISS", "MISS", bracketed=True),
        "OPTIONAL_MISSING": theme.badge("INFO", "INFO", bracketed=True),
        "INFO": theme.badge("INFO", "INFO", bracketed=True),
        "UNKNOWN_VERSION": theme.badge("UNKN", "UNKN", bracketed=True),
    }

    arrow = theme.style(theme.GLYPHS["ARROW"], "optical")
    for tier_key, tier_data in audit["tiers"].items():
        tier_title = tier_key.replace("_", " ").upper()
        print(f"\n{arrow} {theme.style(tier_title, 'ink', bold=True)}: {tier_data['description']}")
        for tool in tier_data["tools"]:
            sym = symbols.get(tool["status"], "[????]")
            v_info = tool["version"] or "N/A"
            req_info = f"(min: {tool['min_version']})" if tool["min_version"] else ""
            shim_note = f" {theme.badge('WARN', str(tool['shim_details']))}" if tool["is_shim"] else ""
            print(
                f"  {theme.pad_display(sym, 8)} {theme.pad_display(tool['name'], 10)} "
                f"{theme.pad_display(v_info, 12)} {theme.pad_display(req_info, 14)} "
                f"-> {tool['path'] or 'NOT FOUND'}{shim_note}"
            )

    ft = audit.get("forensic_toolchain")
    if ft:
        prof = ft.get("profile", "static-cleanroom")
        print(f"\n{arrow} {theme.style(f'REVERSE ENGINEERING & DIRTYROOM TOOLCHAIN (Profile: {prof})', 'ink', bold=True)}")
        for tool in ft.get("tools", []):
            st = tool.get("status", "INFO")
            sym = symbols.get(st, f"[{st:^4}]")
            t_name = tool.get("name", "tool")
            v_info = tool.get("version") or "N/A"
            p_info = tool.get("path") or "NOT FOUND"
            cat = f"[{tool.get('category', 'core')}]"
            print(
                f"  {theme.pad_display(sym, 8)} {theme.pad_display(t_name, 20)} "
                f"{theme.pad_display(cat, 10)} {theme.pad_display(v_info, 14)} -> {p_info}"
            )
        if ft.get("remediation"):
            print("    Remediation:")
            for rem in ft.get("remediation"):
                print(f"      • {rem}")

    summ = audit["summary"]
    print("\n" + theme.rule())
    print(f" Summary: {summ['ok']} OK | {summ['warning']} Warnings | {summ['outdated']} Outdated | {summ['missing']} Missing")
    print(theme.rule("━") + "\n")


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
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Target workspace path to inspect for config/RE activation",
    )
    register_rea_flags(
        parser,
        help_text="Enable Reverse Engineer Anything (REA) diagnostics and provider audit",
    )
    parser.add_argument(
        "--re",
        dest="re_toolchain",
        action="store_true",
        help="Audit reverse engineering & dirtyroom forensic toolchain (Ghidra, objdump, tshark, ydotool)",
    )
    parser.add_argument(
        "--anti-synthetic",
        action="store_true",
        help="Audit test files for synthetic, tautological, and fake test smells (Epic #51 R1)",
    )
    parser.add_argument(
        "--test-path",
        type=Path,
        default=None,
        metavar="PATH",
        help="Target directory or specific test file to audit (defaults to workspace test suites)",
    )
    args = parser.parse_args()

    if getattr(args, "anti_synthetic", False):
        from harness.doctor.test_smells import run_anti_synthetic_doctor
        return run_anti_synthetic_doctor(
            target_path=getattr(args, "test_path", None),
            as_json=bool(getattr(args, "json", False)),
        )

    rea_flag = bool(getattr(args, "rea", False) or getattr(args, "experimental_rea", False))
    re_tool = bool(getattr(args, "re_toolchain", False) or getattr(args, "re", False))
    ws_root = Path(args.workspace).resolve() if getattr(args, "workspace", None) else Path.cwd().resolve()
    audit = run_doctor(
        args.matrix,
        workspace_root=ws_root,
        rea=rea_flag,
        experimental_rea=rea_flag,
        re_toolchain=re_tool,
    )

    is_json = bool(getattr(args, "json", False))
    if args.heal:
        if not is_json:
            print_cli_report(audit)
            print(f"\n{theme.badge('BRAND')} {theme.style('Executing Auto-Healing...', 'ink', bold=True)}")
        actions = heal_environment(
            audit,
            args.matrix,
            rea=rea_flag,
            experimental_rea=rea_flag,
            re_toolchain=re_tool,
            workspace_dir=ws_root,
        )
        if not is_json:
            for act in actions:
                print(f"  {theme.badge('PASS')} {act}")
            print()
        audit = run_doctor(
            args.matrix,
            workspace_root=ws_root,
            rea=rea_flag,
            experimental_rea=rea_flag,
            re_toolchain=re_tool,
        )
        if is_json:
            audit = dict(audit)
            audit["heal_actions"] = actions
    elif not is_json:
        print_cli_report(audit)

    if is_json:
        print(json.dumps(audit, indent=2))

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
