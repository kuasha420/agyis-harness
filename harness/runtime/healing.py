# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Environment auto-healing implementation for PSL Harness (ADR-014).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List


def heal_environment(audit: Dict[str, Any], matrix_path: Path) -> List[str]:
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

    return actions_taken
