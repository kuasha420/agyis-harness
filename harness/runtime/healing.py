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


def provision_rea_skill(
    target_skills_dir: Path,
    link: bool = True,
    allow_download: bool = True,
) -> Optional[Path]:
    """Dynamically provisions the official reverse-engineer-anything skill without vendoring.

    1. Inspects local rea-agents package root via REA metadata or package managers.
    2. If found, symlinks or copies the official skill into target_skills_dir.
    3. If missing and allow_download is True, fetches on-demand from upstream repo.
    """
    dest_dir = target_skills_dir / "reverse-engineer-anything"
    if (dest_dir / "SKILL.md").is_file():
        return dest_dir

    # 1. Search candidate source skill paths
    source_skill_dir: Optional[Path] = None

    from harness.runtime.tool_checks import find_rea_binary

    rea_bin = find_rea_binary()
    if rea_bin:
        try:
            proc = subprocess.run(
                [str(rea_bin), "providers", "--json"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=2.0,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout)
                root_path = (
                    data.get("server_identity", {})
                    .get("package", {})
                    .get("root_path")
                )
                if root_path:
                    cand = Path(root_path) / "skills" / "reverse-engineer-anything"
                    if (cand / "SKILL.md").is_file():
                        source_skill_dir = cand
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            pass

    if not source_skill_dir:
        # Check standard pnpm / npm global locations
        home = Path.home()
        candidates = [
            home / ".gemini" / "config" / "plugins" / "psl-agy-harness" / "skills" / "reverse-engineer-anything",
            home / ".gemini" / "config" / "skills" / "reverse-engineer-anything",
            home / ".local" / "share" / "pnpm" / "global" / "5" / "node_modules" / "rea-agents" / "skills" / "reverse-engineer-anything",
            home / ".npm-global" / "lib" / "node_modules" / "rea-agents" / "skills" / "reverse-engineer-anything",
        ]
        # Check pnpm global store glob if present
        pnpm_global = home / ".local" / "share" / "pnpm" / "global"
        if pnpm_global.is_dir():
            for p in pnpm_global.glob("**/node_modules/rea-agents/skills/reverse-engineer-anything"):
                if (p / "SKILL.md").is_file():
                    candidates.append(p)
                    break

        for cand in candidates:
            if (cand / "SKILL.md").is_file() and cand.resolve() != dest_dir.resolve():
                source_skill_dir = cand
                break

    # 2. Link or copy if found locally
    if source_skill_dir:
        target_skills_dir.mkdir(parents=True, exist_ok=True)
        if dest_dir.is_symlink() or dest_dir.exists():
            if dest_dir.is_symlink() or dest_dir.is_file():
                dest_dir.unlink()
            elif dest_dir.is_dir():
                shutil.rmtree(dest_dir)

        if link:
            try:
                dest_dir.symlink_to(source_skill_dir, target_is_directory=True)
                return dest_dir
            except (OSError, NotImplementedError):
                pass
        try:
            shutil.copytree(source_skill_dir, dest_dir, dirs_exist_ok=True)
            return dest_dir
        except OSError:
            return None

    # 3. Fallback: on-demand fetch if allowed
    if allow_download:
        import urllib.request
        import urllib.error

        base_url = "https://raw.githubusercontent.com/morluto/rea/main/skills/reverse-engineer-anything"
        try:
            req = urllib.request.Request(f"{base_url}/SKILL.md", headers={"User-Agent": "agyis-harness"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    (dest_dir / "SKILL.md").write_bytes(resp.read())
                    return dest_dir
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            return None

    return None


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
    from harness.runtime.tool_checks import configure_rea_mcp_server

    jdk21_path = Path(os.environ["JAVA_HOME"]) if "JAVA_HOME" in os.environ else None
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

    # 3. Provision official skill dynamically into global skills directory
    global_skills_dir = Path.home() / ".gemini" / "config" / "skills"
    prov_path = provision_rea_skill(global_skills_dir, link=True, allow_download=False)
    if prov_path:
        actions.append(f"Provisioned 'reverse-engineer-anything' skill dynamically in {prov_path}.")

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
