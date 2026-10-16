# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Environment auto-healing implementation for Agyis Harness (ADR-014 / Antigravity Immune System).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List


def heal_rea_tooling(audit: Dict[str, Any]) -> List[str]:
    """Auto-heal REA tooling and Antigravity MCP configuration in user-space without sudo."""
    actions: List[str] = []
    rea_info = audit.get("rea_tooling", {})

    # 1. Install or update rea-agents in user space if missing or outdated
    bin_path = rea_info.get("binary")
    status = rea_info.get("status")
    if not bin_path or status in ("warning", "optional_missing"):
        pnpm = shutil.which("pnpm")
        npm = shutil.which("npm")
        installed = False
        if pnpm:
            print("[*] Installing/updating rea-agents via pnpm...")
            proc = subprocess.run([pnpm, "add", "-g", "rea-agents"], capture_output=True, text=True)
            if proc.returncode == 0:
                actions.append("Installed/updated 'rea-agents' globally via pnpm in user-space.")
                installed = True
            else:
                actions.append(f"Failed to install rea-agents via pnpm: {proc.stderr.strip()}")
        if not installed and npm:
            print("[*] Installing/updating rea-agents via npm...")
            proc = subprocess.run([npm, "install", "-g", "rea-agents"], capture_output=True, text=True)
            if proc.returncode == 0:
                actions.append("Installed/updated 'rea-agents' globally via npm in user-space.")
                installed = True
            else:
                actions.append(f"Failed to install rea-agents via npm: {proc.stderr.strip()}")
        if not pnpm and not npm:
            actions.append("Package manager (pnpm/npm) not found to install rea-agents in user-space.")

    # 2. Configure mcpServers.rea in ~/.gemini/config/mcp_config.json via shared helper
    from harness.runtime.tool_checks import configure_rea_mcp_server, find_jdk21_path

    jdk21_path = find_jdk21_path()
    ghidra_dir = os.environ.get("GHIDRA_INSTALL_DIR")
    if not ghidra_dir:
        for cand in [Path("/opt/ghidra"), Path("/usr/local/opt/ghidra"), Path.home() / "ghidra"]:
            if cand.is_dir():
                ghidra_dir = str(cand)
                break

    configured_paths, config_errors = configure_rea_mcp_server(
        jdk21_path=jdk21_path,
        ghidra_dir=ghidra_dir,
    )
    for cfg_p in configured_paths:
        actions.append(
            f"Wired 'rea' MCP server in {cfg_p} (JDK 21: {jdk21_path or 'unresolved'}, Ghidra: {ghidra_dir or '/opt/ghidra'})."
        )
    for err in config_errors:
        actions.append(err)

    return actions


def heal_environment(
    audit: Dict[str, Any], matrix_path: Path, experimental_rea: bool = False
) -> List[str]:
    """Execute non-destructive user-space repairs and return manual instructions."""
    actions_taken: List[str] = []
    os_family = audit["os_family"]
    missing_distro_pkgs: List[str] = []

    # Check for uv Python 3.12 provisioning
    uv_path = shutil.which("uv")
    if not uv_path:
        home_uv = Path.home() / ".local/bin/uv"
        if home_uv.exists():
            uv_path = str(home_uv)

    # 1. User space heals
    for tier_key, tier_info in audit["tiers"].items():
        for tool in tier_info["tools"]:
            st = tool["status"]
            name = tool["name"]
            spec = tool["spec"]
            heal_strat = spec.get("heal_strategy", {})
            strat_type = heal_strat.get("type")

            if st in ("MISSING", "OUTDATED", "WARNING"):
                if name == "python" and st in ("OUTDATED", "WARNING"):
                    # If host python is outdated or shimmed, ensure uv python 3.12 is ready
                    if uv_path:
                        print(f"[*] Provisioning hermetic Python 3.12 via {uv_path}...")
                        proc = subprocess.run(
                            [uv_path, "python", "install", "3.12"],
                            capture_output=True,
                            text=True,
                        )
                        if proc.returncode == 0:
                            actions_taken.append("Installed/verified CPython 3.12 in user-space uv toolchain.")
                        else:
                            actions_taken.append(f"Failed to install Python 3.12 via uv: {proc.stderr.strip()}")
                elif strat_type == "distro_package":
                    pkg_map = heal_strat.get("package_names", {})
                    pkg_name = pkg_map.get(os_family) or pkg_map.get("debian")
                    if pkg_name and st == "MISSING":
                        missing_distro_pkgs.append(pkg_name)

    if missing_distro_pkgs:
        if os_family == "arch":
            cmd = f"sudo pacman -S {' '.join(missing_distro_pkgs)}"
        elif os_family == "debian":
            cmd = f"sudo apt update && sudo apt install -y {' '.join(missing_distro_pkgs)}"
        elif os_family == "fedora":
            cmd = f"sudo dnf install -y {' '.join(missing_distro_pkgs)}"
        elif os_family == "darwin":
            cmd = f"brew install {' '.join(missing_distro_pkgs)}"
        else:
            cmd = f"# Install: {' '.join(missing_distro_pkgs)}"
        actions_taken.append(f"Distro package install required:\n    {cmd}")

    cli_binary = audit.get("cli_binary", {})
    if (cli_binary.get("collision") or cli_binary.get("status") == "WARNING") and cli_binary.get("remediation"):
        actions_taken.append(
            f"CLI Binary Remediation:\n    {cli_binary['remediation']}"
        )
    else:
        psl_collision = audit.get("psl_collision", {})
        if psl_collision.get("collision") and psl_collision.get("remediation"):
            actions_taken.append(
                f"PSL Collision Remediation:\n    {psl_collision['remediation']}"
            )

    dup_agents = audit.get("duplicate_agents", {})
    if dup_agents.get("status") == "WARNING" and dup_agents.get("remediation"):
        actions_taken.append(
            f"Duplicate Agents Remediation:\n    {dup_agents['remediation']}"
        )

    node_hyg = audit.get("node_script_hygiene", {})
    if node_hyg.get("status") == "WARNING" and node_hyg.get("remediation"):
        actions_taken.append(
            f"Node Script Hygiene Remediation:\n    {node_hyg['remediation']}"
        )

    hooks_h = audit.get("hooks_health", {})
    if hooks_h.get("status") == "WARNING" and hooks_h.get("remediation"):
        actions_taken.append(
            f"Hooks Health Remediation:\n    {hooks_h['remediation']}"
        )

    if experimental_rea or audit.get("experimental_rea"):
        rea_actions = heal_rea_tooling(audit)
        actions_taken.extend(rea_actions)

    return actions_taken
