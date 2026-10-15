# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace initialization CLI command with decoupled stack & role presets (ADR-014, ADR-031).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

from harness.delivery import install_workspace
from harness.skills import (
    ARCHITECTURAL_ROLE_PRESETS,
    LANGUAGE_RUNTIME_PRESETS,
    detect_monorepo_stack,
    detect_workspace_role,
    detect_workspace_stack,
    is_monorepo,
    resolve_skills_to_sync,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Initializes workspace with stack-tailored skills, architectural roles, and tagged rules."""
    raw_path = Path(args.path) if getattr(args, "path", None) else Path.cwd()
    subproject = getattr(args, "subproject", None)
    target_ws = (raw_path / subproject).resolve() if subproject else raw_path.resolve()

    role = getattr(args, "role", None)
    stack = getattr(args, "stack", None)
    skills_arg = getattr(args, "skills", None)

    # Determine skills
    skills_list: Optional[List[str]] = None
    if skills_arg:
        skills_list = [s.strip() for s in skills_arg.split(",") if s.strip()]
    else:
        # Check if monorepo scanning applies
        if is_monorepo(raw_path) and not subproject and not stack and not role:
            mono_langs, mono_roles = detect_monorepo_stack(raw_path)
            skills_set: set[str] = set()
            for l in mono_langs:
                if l in LANGUAGE_RUNTIME_PRESETS:
                    skills_set.update(LANGUAGE_RUNTIME_PRESETS[l])
            for r in mono_roles:
                if r in ARCHITECTURAL_ROLE_PRESETS:
                    skills_set.update(ARCHITECTURAL_ROLE_PRESETS[r])
            if skills_set:
                skills_list = sorted(skills_set)

        if skills_list is None:
            # Resolve skills via decoupled presets
            skills_list = resolve_skills_to_sync(
                stack=stack or "auto",
                role=role,
                workspace_root=target_ws,
            )

    include_agents = bool(getattr(args, "agents", False))
    agents_list = None
    if isinstance(getattr(args, "agents", None), str):
        agents_list = [a.strip() for a in getattr(args, "agents").split(",") if a.strip()]
        include_agents = True

    dedup = not getattr(args, "no_dedup", False)
    override = bool(getattr(args, "override", False))
    dry_run = bool(getattr(args, "dry_run", False))

    effective_stack = stack or detect_workspace_stack(target_ws) or "generic"
    effective_role = role or detect_workspace_role(target_ws)

    res = install_workspace(
        workspace_dir=target_ws,
        stack=effective_stack,
        skills=skills_list,
        agents=agents_list,
        include_agents=include_agents,
        dedup=dedup,
        override=override,
        dry_run=dry_run,
    )

    exp_rea = bool(getattr(args, "experimental_rea", False))
    if exp_rea and res.success:
        if not dry_run:
            cfg_file = (
                (target_ws / ".psl" / "config.json")
                if (target_ws / ".psl").is_dir() and not (target_ws / ".agyis").exists()
                else (target_ws / ".agyis" / "config.json")
            )
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            ws_cfg: dict = {}
            if cfg_file.is_file():
                try:
                    ws_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    if not isinstance(ws_cfg, dict):
                        ws_cfg = {}
                except (json.JSONDecodeError, OSError):
                    ws_cfg = {}
            ws_cfg["experimental_rea"] = True
            cfg_file.write_text(json.dumps(ws_cfg, indent=2) + "\n", encoding="utf-8")

            # Scaffold .agents/ledger/
            ledger_dir = target_ws / ".agents" / "ledger"
            ledger_dir.mkdir(parents=True, exist_ok=True)

    if getattr(args, "json", False):
        data = {
            "success": res.success,
            "workspace_dir": str(res.workspace_dir),
            "stack": res.stack,
            "role": effective_role,
            "subproject": subproject,
            "dry_run": res.dry_run,
            "skills_installed": res.skills_installed,
            "skills_skipped": res.skills_skipped,
            "agents_installed": res.agents_installed,
            "agents_skipped": res.agents_skipped,
            "rules_updated": res.rules_updated,
            "command_dictionary": res.command_dictionary,
            "legacy_notice": res.legacy_notice,
            "message": res.message,
            "experimental_rea": exp_rea,
        }
        print(json.dumps(data, indent=2))
        return 0 if res.success else 1

    if res.success:
        print(f"✔ {res.message}")
        print(f"  • Stack: {res.stack}")
        if exp_rea:
            label = "Would scaffold" if res.dry_run else "Enabled"
            print(f"  • REA: {label} Reverse Engineer Anything opt-in (.agents/ledger/)")
        if effective_role:
            print(f"  • Role: {effective_role}")
        if subproject:
            print(f"  • Subproject: {subproject}")
        if res.skills_installed:
            label = "Planned skills" if res.dry_run else "Installed skills"
            print(f"  • {label}: {', '.join(res.skills_installed)}")
        if res.skills_skipped:
            print(f"  • Skipped skills: {', '.join(res.skills_skipped)}")
        if res.agents_installed:
            label = "Planned agents" if res.dry_run else "Installed agents"
            print(f"  • {label}: {', '.join(res.agents_installed)}")
        if res.rules_updated:
            action = "Would update" if res.dry_run else "Updated"
            print(f"  • Rules: {action} AGENTS.md with tagged AGYIS invariants block")
        else:
            print("  • Rules: AGENTS.md tagged block is up-to-date")
        if res.command_dictionary:
            print("  • Command Dictionary:")
            for verb, cmd in res.command_dictionary.items():
                print(f"    - {verb}: {cmd}")
        if res.legacy_notice:
            print(f"\n💡 Notice: {res.legacy_notice}")
        return 0
    else:
        sys.stderr.write(f"✘ Error: {res.message}\n")
        return 1
