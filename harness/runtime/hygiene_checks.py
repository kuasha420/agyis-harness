# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace and configuration hygiene audits for PSL Harness (ADR-014 / ADR-016).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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


def check_duplicate_skills(
    workspace_root: Optional[Path | str] = None,
    config_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Audit ~/.gemini/config/skills/, ~/.gemini/config/plugins/*/skills/, and <workspace>/.agents/skills/ for duplicate skills (Issue #52)."""
    cfg = Path(config_dir).resolve() if config_dir is not None else Path.home() / ".gemini" / "config"
    ws = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()

    standalone_skills: Dict[str, Path] = {}
    standalone_dir = cfg / "skills"
    if standalone_dir.is_dir():
        for item in sorted(standalone_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                if (item / "SKILL.md").is_file() or any(item.glob("*.md")):
                    standalone_skills[item.name] = item

    plugin_skills: Dict[str, List[Path]] = {}
    plugins_dir = cfg / "plugins"
    if plugins_dir.is_dir():
        from harness.utils.workspace import is_harness_workspace
        ws_is_harness = is_harness_workspace(ws)
        ws_plugin_names: Set[str] = set()
        if ws_is_harness:
            ws_plugin_names.update(["psl-agy-harness", "agyis-harness"])
        ws_plugin_json = ws / "plugin.json"
        if ws_plugin_json.is_file():
            try:
                with open(ws_plugin_json, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                    if pdata.get("name"):
                        ws_plugin_names.add(pdata["name"])
            except Exception:
                pass

        for plugin in sorted(plugins_dir.iterdir()):
            if plugin.is_dir() and not plugin.name.startswith("."):
                # Safety guard: ignore self-symlink or installed copy when workspace is the source repository
                try:
                    if plugin.resolve() == ws.resolve():
                        continue
                    if plugin.name in ws_plugin_names:
                        continue
                except OSError:
                    pass
                p_skills = plugin / "skills"
                if p_skills.is_dir():
                    for item in sorted(p_skills.iterdir()):
                        if item.is_dir() and not item.name.startswith("."):
                            if (item / "SKILL.md").is_file() or any(item.glob("*.md")):
                                plugin_skills.setdefault(item.name, []).append(item)

    workspace_skills: Dict[str, Path] = {}
    ws_skills_dir = ws / ".agents" / "skills"
    if ws_skills_dir.is_dir():
        for item in sorted(ws_skills_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                if (item / "SKILL.md").is_file() or any(item.glob("*.md")):
                    workspace_skills[item.name] = item

    all_skill_names = sorted(set(standalone_skills.keys()) | set(plugin_skills.keys()) | set(workspace_skills.keys()))
    duplicate_names: List[str] = []
    dups_info: List[Dict[str, Any]] = []

    for name in all_skill_names:
        sources: List[Dict[str, str]] = []
        if name in standalone_skills:
            sources.append({"type": "standalone", "path": str(standalone_skills[name])})
        if name in plugin_skills:
            for p in plugin_skills[name]:
                sources.append({"type": "plugin", "path": str(p)})
        if name in workspace_skills:
            sources.append({"type": "workspace", "path": str(workspace_skills[name])})

        if len(sources) > 1:
            duplicate_names.append(name)
            dups_info.append({
                "skill": name,
                "sources": sources,
            })

    if duplicate_names:
        return {
            "status": "WARNING",
            "duplicates": duplicate_names,
            "details": f"Duplicate skill definitions detected across workspace, plugin, or config: {', '.join(duplicate_names)}",
            "duplicate_items": dups_info,
            "remediation": (
                "Prune redundant workspace skills with 'agyis skills --prune-duplicates' "
                "or run 'python3 -m harness.cli install' to enforce single-source plugin delivery."
            ),
        }

    return {
        "status": "PASS",
        "duplicates": [],
        "details": "No duplicate skill registrations detected across workspace, plugin, or config.",
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
            "token-proximity": "harness.hooks.token_proximity_guard",
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


_PORT_DETECTOR_MOD = None


def _load_port_detector_module():
    global _PORT_DETECTOR_MOD
    if "detect_port_collision" in sys.modules and sys.modules["detect_port_collision"] is not None:
        return sys.modules["detect_port_collision"]
    if _PORT_DETECTOR_MOD is not None:
        return _PORT_DETECTOR_MOD

    candidates = [
        Path(__file__).resolve().parent.parent / "skills" / "db-ops" / "scripts" / "detect_port_collision.py",
        REPO_ROOT / "harness" / "skills" / "db-ops" / "scripts" / "detect_port_collision.py",
        REPO_ROOT / ".agents" / "skills" / "db-ops" / "scripts" / "detect_port_collision.py",
        Path.cwd() / "harness" / "skills" / "db-ops" / "scripts" / "detect_port_collision.py",
        Path.cwd() / ".agents" / "skills" / "db-ops" / "scripts" / "detect_port_collision.py",
    ]
    for cand in candidates:
        if cand.is_file():
            try:
                spec = importlib.util.spec_from_file_location("detect_port_collision", cand)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    _PORT_DETECTOR_MOD = mod
                    return mod
            except Exception:
                pass
    return None


def _fallback_check_database_port(
    workspace_root: Optional[Path | str] = None,
    port: int = 5432,
) -> Dict[str, Any]:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    in_use = False
    try:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            in_use = True
    except Exception:
        pass
    finally:
        s.close()

    if not in_use:
        return {
            "status": "PASS",
            "collision": False,
            "port": port,
            "owner": None,
            "free_port": port,
            "details": f"Port {port} is unbound and free for database binding.",
            "remediation": None,
        }

    return {
        "status": "WARNING",
        "collision": True,
        "port": port,
        "owner": None,
        "free_port": None,
        "details": f"Port {port} is active and occupied.",
        "remediation": f"Inspect active port {port} or rebind database configuration.",
    }


def check_database_port_conflicts(
    workspace_root: Optional[Path | str] = None,
    port: int = 5432,
) -> Dict[str, Any]:
    """
    Audits active database port (default 5432) for socket occupancy and foreign container collision (Issue #62).
    Returns dict with status ("PASS", "OK", "WARNING"), port, collision, owner, free_port, details, remediation.
    """
    mod = _load_port_detector_module()
    if mod is not None:
        try:
            res = mod.check_port_collision(port=port, workspace_root=workspace_root)
            script_status = res.get("status", "UNKNOWN")
            if script_status == "UNBOUND":
                status = "PASS"
            elif script_status == "SELF_OWNED":
                status = "OK"
            else:
                status = "WARNING"

            return {
                "status": status,
                "collision": bool(res.get("collision", script_status == "FOREIGN_COLLISION")),
                "port": port,
                "owner": res.get("owner"),
                "free_port": res.get("free_port"),
                "details": res.get("details", ""),
                "remediation": res.get("remediation"),
            }
        except Exception as exc:
            return {
                "status": "WARNING",
                "collision": False,
                "port": port,
                "owner": None,
                "free_port": None,
                "details": f"Error executing port collision check: {exc}",
                "remediation": None,
            }

    return _fallback_check_database_port(workspace_root=workspace_root, port=port)

