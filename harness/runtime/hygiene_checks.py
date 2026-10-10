# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Workspace and configuration hygiene audits for PSL Harness (ADR-014 / ADR-016).
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import shlex
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
