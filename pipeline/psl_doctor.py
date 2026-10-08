#!/usr/bin/env python3
"""
PSL Harness for Google Antigravity™
Workstation Diagnostic & Environment Health Engine (psl doctor)

Audits host workstation runtimes against harness/runtime/matrix.json across:
- Tier 1: Core Languages & Package Managers (Python >= 3.12, Node >= 20, uv, pnpm)
- Tier 2: Core SWE CLI (git, gh, ripgrep, fd)
- Tier 3: Mesh/Host (ssh, knot)

Detects pyenv/conda shim hijacking, audits hermetic uv toolchains, and provides
zero-sudo auto-healing via `--heal`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parse version string into integer tuple for comparison."""
    parts = re.findall(r"\d+", v_str)
    return tuple(int(p) for p in parts) if parts else (0,)


def detect_os_family() -> str:
    """Detect operating system family for package manager suggestions."""
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        return "darwin"
    
    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text().lower()
        if "arch" in content or "endeavouros" in content or "manjaro" in content:
            return "arch"
        if "debian" in content or "ubuntu" in content or "pop" in content:
            return "debian"
        if "fedora" in content or "rhel" in content or "centos" in content:
            return "fedora"
    return "linux"


def check_tool(
    name: str,
    spec: Dict[str, Any],
    hermetic_python_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Audit an individual tool against its matrix specification."""
    binary = spec.get("binary", name)
    fallback = spec.get("fallback_binary")
    min_version_str = spec.get("min_version")
    optional = spec.get("optional", False)
    
    # 1. Resolve binary in PATH
    resolved_path = shutil.which(binary)
    if not resolved_path and fallback:
        resolved_path = shutil.which(fallback)
        if resolved_path:
            binary = fallback

    # For "uv", probe candidate user paths (~/.local/bin/uv, ~/.cargo/bin/uv) if not found on PATH
    if not resolved_path and (name == "uv" or binary == "uv"):
        for cand in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv"):
            if cand.exists() and os.access(cand, os.X_OK):
                resolved_path = str(cand)
                break

    # Check for pyenv/conda shim hijacking
    is_shim = False
    shim_details = None
    if resolved_path:
        p_lower = resolved_path.lower()
        if ".pyenv/shims" in p_lower or ".pyenv/versions" in p_lower:
            is_shim = True
            shim_details = "pyenv shim active in PATH"
        elif "conda" in p_lower or "miniconda" in p_lower:
            is_shim = True
            shim_details = "conda environment active in PATH"

    # Check for libpsl / non-harness collision if auditing psl
    is_collision = False
    collision_details = None
    if (name == "psl" or binary == "psl") and resolved_path:
        is_harness = False
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
                if "harness" in f.read(2048):
                    is_harness = True
        except OSError:
            pass
        if resolved_path in ("/usr/bin/psl", "/bin/psl") or not is_harness:
            is_collision = True
            collision_details = f"Collision detected: 'psl' resolves to non-harness binary ({resolved_path})"

    if not resolved_path:
        return {
            "name": name,
            "binary": binary,
            "status": "OPTIONAL_MISSING" if optional else "MISSING",
            "path": None,
            "version": None,
            "min_version": min_version_str,
            "is_shim": False,
            "shim_details": None,
            "is_collision": False,
            "collision_details": None,
            "spec": spec,
        }

    # 2. Extract version
    version_str = None
    cmd = spec.get("version_command", f"{binary} --version")
    if resolved_path:
        if cmd.startswith(f"{binary} "):
            cmd = f'"{resolved_path}" ' + cmd[len(binary) + 1:]
        elif cmd == binary:
            cmd = f'"{resolved_path}"'
    regex = spec.get("version_regex", r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        combined_out = (proc.stdout + " " + proc.stderr).strip()
        m = re.search(regex, combined_out)
        if m:
            version_str = m.group(1)
    except Exception as e:
        version_str = None

    # 3. Version comparison
    status = "OK"
    if not version_str:
        status = "UNKNOWN_VERSION"
    elif min_version_str:
        current_v = parse_version(version_str)
        required_v = parse_version(min_version_str)
        if current_v < required_v:
            status = "OUTDATED"
        elif is_shim or is_collision:
            status = "WARNING"
        else:
            status = "OK"
    elif is_shim or is_collision:
        status = "WARNING"

    return {
        "name": name,
        "binary": binary,
        "status": status,
        "path": resolved_path,
        "version": version_str,
        "min_version": min_version_str,
        "is_shim": is_shim,
        "shim_details": shim_details,
        "is_collision": is_collision,
        "collision_details": collision_details,
        "spec": spec,
    }


def find_hermetic_uv_python() -> Optional[Path]:
    """Find installed CPython 3.12+ in uv's toolchain directory."""
    uv_python_dir = Path.home() / ".local/share/uv/python"
    if not uv_python_dir.exists():
        return None
    
    for candidate in sorted(uv_python_dir.glob("cpython-3.1[2-9]*/bin/python3"), reverse=True):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def check_psl_collision() -> Dict[str, Any]:
    """Audit host 'psl' binary to detect collisions with system libpsl or non-harness binaries."""
    psl_path = shutil.which("psl")
    if not psl_path:
        return {
            "status": "NOT_FOUND",
            "path": None,
            "collision": False,
            "details": "psl binary not found on PATH.",
            "remediation": "Deploy the PSL launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH.",
        }

    is_harness = False
    try:
        with open(psl_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048)
            if "harness" in content:
                is_harness = True
    except OSError:
        pass

    if psl_path in ("/usr/bin/psl", "/bin/psl"):
        return {
            "status": "WARNING",
            "path": psl_path,
            "collision": True,
            "details": f"Collision detected: 'psl' resolves to system libpsl ({psl_path}).",
            "remediation": (
                "Prepend user bin directory (~/.local/bin) to PATH before /usr/bin:\n"
                "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "And ensure the launcher is installed via: python3 -m harness.cli install"
            ),
        }

    if not is_harness:
        return {
            "status": "WARNING",
            "path": psl_path,
            "collision": True,
            "details": f"Collision detected: 'psl' resolves to non-harness binary ({psl_path}).",
            "remediation": (
                "Ensure PSL harness bin directory is prioritized in PATH:\n"
                "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "And ensure the launcher is installed via: python3 -m harness.cli install"
            ),
        }

    return {
        "status": "OK",
        "path": psl_path,
        "collision": False,
        "details": f"psl binary correctly resolves to PSL Harness launcher ({psl_path}).",
        "remediation": None,
    }


def check_duplicate_agents(config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Audit ~/.gemini/config/agents/*.md and ~/.gemini/config/plugins/*/agents/*.md for duplicates (Issue #30)."""
    cfg = Path(config_dir).resolve() if config_dir is not None else Path.home() / ".gemini" / "config"
    agents_dir = cfg / "agents"
    plugins_dir = cfg / "plugins"

    standalone_agents: Dict[str, Path] = {}
    if agents_dir.is_dir():
        for f in sorted(agents_dir.glob("*.md")):
            if f.is_file() or f.is_symlink():
                standalone_agents[f.name] = f

    plugin_agents: Dict[str, List[Path]] = {}
    if plugins_dir.is_dir():
        for f in sorted(plugins_dir.glob("*/agents/*.md")):
            if f.is_file() or f.is_symlink():
                plugin_agents.setdefault(f.name, []).append(f)

    duplicate_names = sorted(set(standalone_agents.keys()) & set(plugin_agents.keys()))

    if duplicate_names:
        dups_info = []
        for name in duplicate_names:
            plugin_paths = [str(p) for p in plugin_agents[name]]
            dups_info.append({
                "agent": name,
                "standalone": str(standalone_agents[name]),
                "plugin_sources": plugin_paths,
            })
        return {
            "status": "WARNING",
            "duplicates": duplicate_names,
            "details": f"Duplicate agent definitions detected across standalone config and plugins: {', '.join(duplicate_names)}",
            "duplicate_items": dups_info,
            "remediation": (
                "Remove duplicate standalone agent files in ~/.gemini/config/agents/ "
                "or run 'python3 -m harness.cli install' to enforce single-source plugin delivery."
            ),
        }

    return {
        "status": "OK",
        "duplicates": [],
        "details": "No duplicate agent definitions detected between standalone config and plugins.",
        "duplicate_items": [],
        "remediation": None,
    }


def check_node_script_hygiene(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    In packages with 'type': 'module', check .js files for CommonJS syntax (Issue #17).

    Audits .js files for require(, module.exports, or exports., recommending .cjs or ESM syntax.
    """
    ws = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    pkg_json = ws / "package.json"

    if not pkg_json.is_file():
        return {
            "status": "OK",
            "is_esm": False,
            "violations": [],
            "details": "No package.json found at workspace root.",
            "remediation": None,
        }

    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {
            "status": "OK",
            "is_esm": False,
            "violations": [],
            "details": "Malformed or unreadable package.json.",
            "remediation": None,
        }

    if not isinstance(data, dict) or data.get("type") != "module":
        return {
            "status": "OK",
            "is_esm": False,
            "violations": [],
            "details": "Package does not specify 'type': 'module' (CommonJS default).",
            "remediation": None,
        }

    ignored_dir_names = {
        "node_modules", ".git", ".venv", "venv", "dist", "build",
        ".cache", ".next", "__pycache__", ".agents", ".psl", "scratch",
    }

    cjs_patterns = [
        (re.compile(r"\brequire\s*\("), "require("),
        (re.compile(r"\bmodule\.exports\b"), "module.exports"),
        (re.compile(r"\bexports\.[a-zA-Z0-9_$]+"), "exports."),
    ]

    violations: List[Dict[str, Any]] = []

    for root_dir, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in ignored_dir_names]

        for fname in files:
            if fname.endswith(".js"):
                fpath = Path(root_dir) / fname
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                matched_patterns = []
                for regex, pat_label in cjs_patterns:
                    if regex.search(content):
                        matched_patterns.append(pat_label)

                if matched_patterns:
                    try:
                        rel = str(fpath.relative_to(ws))
                    except ValueError:
                        rel = str(fpath)
                    violations.append({
                        "file": rel,
                        "patterns": matched_patterns,
                    })

    if violations:
        violation_files = [v["file"] for v in violations]
        return {
            "status": "WARNING",
            "is_esm": True,
            "violations": violations,
            "details": (
                f"CommonJS syntax detected in {len(violations)} .js file(s) under 'type': 'module' package: "
                f"{', '.join(violation_files[:5])}{'...' if len(violation_files) > 5 else ''}"
            ),
            "remediation": (
                "Rename CommonJS scripts from '.js' to '.cjs' or convert to ES module "
                "syntax ('import' / 'export'). Under 'type': 'module', Node rejects CommonJS in '.js' files."
            ),
        }

    return {
        "status": "OK",
        "is_esm": True,
        "violations": [],
        "details": "Node script module hygiene verified: all .js files adhere to ESM syntax.",
        "remediation": None,
    }


def check_hooks_health(hooks_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Audits hooks.json (canonical in repo or workspace), verifies every registered
    hook module can be dynamically loaded and provides a callable main().
    (Issue #31 / ADR-016)
    """
    target_path: Optional[Path] = None
    if hooks_path is not None:
        target_path = Path(hooks_path)
    else:
        for cand in (
            Path.cwd() / "hooks.json",
            REPO_ROOT / "hooks.json",
            REPO_ROOT / "harness/hooks/hooks.json",
        ):
            if cand.is_file():
                target_path = cand
                break

    if target_path is None or not target_path.exists():
        missing_path = str(target_path) if target_path else str(REPO_ROOT / "hooks.json")
        return {
            "status": "WARNING",
            "hooks_path": missing_path,
            "checked_hooks": [],
            "failures": [f"hooks.json not found at {missing_path}."],
            "remediation": "Create hooks.json at workspace root or restore harness/hooks/hooks.json.",
        }

    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "status": "WARNING",
            "hooks_path": str(target_path),
            "checked_hooks": [],
            "failures": [f"Malformed hooks.json: {e}"],
            "remediation": f"Ensure {target_path} contains valid JSON syntax.",
        }

    hook_commands: List[str] = []

    def _extract_commands(node: Any) -> None:
        if isinstance(node, dict):
            if "command" in node and isinstance(node["command"], str):
                hook_commands.append(node["command"])
            for val in node.values():
                _extract_commands(val)
        elif isinstance(node, list):
            for elem in node:
                _extract_commands(elem)

    _extract_commands(data)

    if not hook_commands:
        return {
            "status": "WARNING",
            "hooks_path": str(target_path),
            "checked_hooks": [],
            "failures": ["No hook commands found in hooks.json."],
            "remediation": "Configure at least one lifecycle hook in hooks.json.",
        }

    try:
        from harness.hooks.runner import resolve_hook_module, HOOK_MODULES
    except ImportError:
        HOOK_MODULES = {
            "anti-drift": "harness.hooks.anti_drift_hook",
            "anti-loop": "harness.hooks.anti_loop_hook",
            "command-safety": "harness.hooks.command_safety_hook",
            "compactor": "harness.hooks.output_compactor_hook",
            "verification-fence": "harness.hooks.completion_fence_hook",
        }

        def resolve_hook_module(name: str) -> str:
            clean = (name or "").strip().lower().replace("_", "-")
            if clean in HOOK_MODULES:
                return HOOK_MODULES[clean]
            raise ValueError(f"Unknown hook '{name}'. Supported hooks: {', '.join(sorted(HOOK_MODULES.keys()))}")

    failures: List[str] = []
    hooks_to_verify: Dict[str, str] = {}

    for cmd in hook_commands:
        tokens = shlex.split(cmd.strip())
        if not tokens:
            continue

        hook_name: Optional[str] = None
        module_to_load: Optional[str] = None

        # Format A: python3 -m harness.hooks.runner <hook_name>
        for i, tok in enumerate(tokens):
            if tok in ("harness.hooks.runner", "runner") and i + 1 < len(tokens):
                hook_name = tokens[i + 1]
                break
            if tok == "hook" and i > 0 and "cli" in tokens[i - 1] and i + 1 < len(tokens):
                hook_name = tokens[i + 1]
                break

        if hook_name:
            try:
                module_to_load = resolve_hook_module(hook_name)
            except ValueError as ve:
                failures.append(str(ve))
                continue
        else:
            # Format B: python3 -m <direct_module>
            for i, tok in enumerate(tokens):
                if tok == "-m" and i + 1 < len(tokens):
                    module_to_load = tokens[i + 1]
                    hook_name = module_to_load
                    break

        if not module_to_load or not hook_name:
            failures.append(f"Could not resolve hook module from command: '{cmd}'")
            continue

        hooks_to_verify[hook_name] = module_to_load

    checked_hooks: List[str] = []
    for hook_name, module_path in sorted(hooks_to_verify.items()):
        try:
            mod = importlib.import_module(module_path)
            if not hasattr(mod, "main") or not callable(getattr(mod, "main")):
                failures.append(f"Hook module '{module_path}' for '{hook_name}' does not expose callable main()")
            else:
                checked_hooks.append(hook_name)
        except Exception as exc:
            failures.append(f"Failed to load hook module '{module_path}' for '{hook_name}': {exc}")
        except SystemExit as se:
            failures.append(f"Hook module '{module_path}' exited on load with status: {se}")

    status = "OK" if not failures else "WARNING"
    remediation = None
    if failures:
        remediation = "Fix hook module entrypoints or definitions in hooks.json:\n  - " + "\n  - ".join(failures)

    return {
        "status": status,
        "hooks_path": str(target_path),
        "checked_hooks": sorted(list(set(checked_hooks))),
        "failures": failures,
        "remediation": remediation,
    }


def run_doctor(
    matrix_path: Path,
    workspace_root: Optional[Path] = None,
    config_dir: Optional[Path] = None,
    hooks_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Perform complete workstation runtime audit."""
    if not matrix_path.exists():
        raise FileNotFoundError(f"Matrix file not found: {matrix_path}")

    with open(matrix_path, "r", encoding="utf-8") as f:
        matrix = json.load(f)

    os_family = detect_os_family()
    hermetic_python = find_hermetic_uv_python()
    psl_collision = check_psl_collision()
    duplicate_agents = check_duplicate_agents(config_dir=config_dir)
    node_script_hygiene = check_node_script_hygiene(workspace_root=workspace_root)
    hooks_health = check_hooks_health(hooks_path=hooks_path)

    results: Dict[str, Any] = {
        "os_family": os_family,
        "hermetic_python_available": str(hermetic_python) if hermetic_python else None,
        "path_environment": os.environ.get("PATH", ""),
        "psl_collision": psl_collision,
        "duplicate_agents": duplicate_agents,
        "node_script_hygiene": node_script_hygiene,
        "hooks_health": hooks_health,
        "tiers": {},
        "summary": {
            "total_tools": 0,
            "ok": 0,
            "warning": 0,
            "outdated": 0,
            "missing": 0,
            "optional_missing": 0,
        }
    }

    if psl_collision.get("collision") or psl_collision.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if duplicate_agents.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if node_script_hygiene.get("status") == "WARNING":
        results["summary"]["warning"] += 1
    if hooks_health.get("status") != "OK":
        results["summary"]["warning"] += 1

    for tier_key, tier_data in matrix.get("tiers", {}).items():
        tier_results = []
        for tool_name, tool_spec in tier_data.get("tools", {}).items():
            check = check_tool(tool_name, tool_spec, hermetic_python)
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


def heal_environment(audit: Dict[str, Any], matrix_path: Path) -> List[str]:
    """Execute non-destructive user-space repairs and return manual instructions."""
    actions_taken = []
    os_family = audit["os_family"]
    missing_distro_pkgs = []

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


def print_cli_report(audit: Dict[str, Any]) -> None:
    """Print beautifully styled terminal report."""
    print("\n" + "=" * 70)
    print(" 🩺  PSL WORKSTATION DOCTOR & RUNTIME GUARANTEE AUDIT")
    print("=" * 70)
    print(f" OS Family: {audit['os_family'].upper()}")
    herm_py = audit.get("hermetic_python_available")
    if herm_py:
        print(f" Hermetic uv Python: {herm_py} (CPython >= 3.12 Ready)")
    else:
        print(" Hermetic uv Python: Not found in ~/.local/share/uv/python")

    psl_col = audit.get("psl_collision")
    if psl_col:
        if psl_col.get("collision"):
            print(f" PSL Launcher: [\033[33mWARN\033[0m] -> {psl_col.get('details')}")
            if psl_col.get("remediation"):
                print(f"    Remediation:\n      {psl_col.get('remediation')}")
        elif psl_col.get("status") == "OK":
            print(f" PSL Launcher: [\033[32mPASS\033[0m] -> {psl_col.get('path')}")
        else:
            print(f" PSL Launcher: [\033[34mINFO\033[0m] -> {psl_col.get('details')}")

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
    print("-" * 70)

    symbols = {
        "OK": "[\033[32mPASS\033[0m]",
        "WARNING": "[\033[33mWARN\033[0m]",
        "OUTDATED": "[\033[31mFAIL\033[0m]",
        "MISSING": "[\033[31mMISS\033[0m]",
        "OPTIONAL_MISSING": "[\033[34mINFO\033[0m]",
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

    summ = audit["summary"]
    print("\n" + "-" * 70)
    print(f" Summary: {summ['ok']} OK | {summ['warning']} Warnings | {summ['outdated']} Outdated | {summ['missing']} Missing")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="PSL Workstation Diagnostic & Runtime Guarantee")
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path(__file__).parent.parent / "harness/runtime/matrix.json",
        help="Path to matrix.json",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON results")
    parser.add_argument("--heal", action="store_true", help="Execute safe user-space auto-healing")
    args = parser.parse_args()

    audit = run_doctor(args.matrix)

    if args.json:
        print(json.dumps(audit, indent=2))
        return 0

    print_cli_report(audit)

    if args.heal:
        print("\n🔧 Executing Auto-Healing...")
        actions = heal_environment(audit, args.matrix)
        for act in actions:
            print(f"  ✔ {act}")
        print()

    # Non-zero exit if required tools are missing or outdated
    if audit["summary"]["missing"] > 0 or audit["summary"]["outdated"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
