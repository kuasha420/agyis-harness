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
import os
from pathlib import Path
import sys
from typing import List, Optional

from harness.delivery import (
    enforce_single_source_rules,
    enforce_single_source_skills,
    get_plugin_provided_skills,
    install_workspace,
    resolve_skills_for_workspace,
)
from harness.skills import (
    ARCHITECTURAL_ROLE_PRESETS,
    LANGUAGE_RUNTIME_PRESETS,
    detect_monorepo_stack,
    detect_workspace_role,
    detect_workspace_stack,
    is_monorepo,
)
from harness.utils import theme


def cmd_init(args: argparse.Namespace) -> int:
    """Initializes workspace with stack-tailored skills, architectural roles, and tagged rules."""
    raw_path = Path(args.path) if getattr(args, "path", None) else Path.cwd()
    subproject = getattr(args, "subproject", None)
    target_ws = (raw_path / subproject).resolve() if subproject else raw_path.resolve()

    role = getattr(args, "role", None)
    stack = getattr(args, "stack", None)
    skills_arg = getattr(args, "skills", None)

    # Determine skills via language+role resolver (supports all/audit/auto parity with onboard)
    skills_list: Optional[List[str]] = None
    if skills_arg:
        skills_list = [s.strip() for s in skills_arg.split(",") if s.strip()]
    else:
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
            skills_list = resolve_skills_for_workspace(
                workspace_dir=target_ws,
                stack=stack or "auto",
                role=role,
            )

    include_agents = bool(getattr(args, "agents", False))
    agents_list = None
    if isinstance(getattr(args, "agents", None), str):
        agents_list = [a.strip() for a in getattr(args, "agents").split(",") if a.strip()]
        include_agents = True

    dedup = not getattr(args, "no_dedup", False)
    override = bool(getattr(args, "override", False))
    dry_run = bool(getattr(args, "dry_run", False))

    config_dir_arg = getattr(args, "config_dir", None)
    raw_cfg_dir = (
        config_dir_arg
        if config_dir_arg is not None and str(config_dir_arg).strip()
        else (
            os.environ.get("AGYIS_CONFIG_DIR")
            or os.environ.get("PSL_CONFIG_DIR")
            or (Path.home() / ".gemini" / "config")
        )
    )
    config_dir_path = Path(raw_cfg_dir).expanduser().resolve()

    # Avoid installing skills already provided by global plugins (PSL-INV-004)
    plugin_shadowed = {
        s.strip().lower().replace("_", "-")
        for s in get_plugin_provided_skills(config_dir_path)
    }
    filtered_skills: Optional[List[str]] = skills_list
    skipped_shadowed: List[str] = []
    if skills_list is not None and plugin_shadowed and not override:
        filtered_skills = []
        for s in skills_list:
            if s.strip().lower().replace("_", "-") in plugin_shadowed:
                skipped_shadowed.append(s)
            else:
                filtered_skills.append(s)

    effective_stack = stack or detect_workspace_stack(target_ws) or "generic"
    effective_role = role or detect_workspace_role(target_ws)

    res = install_workspace(
        workspace_dir=target_ws,
        stack=effective_stack,
        role=role,
        skills=filtered_skills,
        agents=agents_list,
        include_agents=include_agents,
        dedup=dedup,
        override=override,
        dry_run=dry_run,
    )

    if skipped_shadowed:
        for sk in skipped_shadowed:
            if sk not in res.skills_skipped:
                res.skills_skipped.append(sk)

    pruned_skills = enforce_single_source_skills(
        config_dir=config_dir_path,
        workspace_dir=target_ws,
        dry_run=dry_run,
    )
    enforce_single_source_rules(
        workspace_dir=target_ws,
        config_dir=config_dir_path,
        dry_run=dry_run,
    )

    rea_enabled = bool(getattr(args, "rea", False) or getattr(args, "experimental_rea", False))
    if rea_enabled and res.success:
        from harness.runtime.healing import provision_workspace_rea

        provision_workspace_rea(target_ws, dry_run=dry_run, config_dir=config_dir_path)

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
            "rea": rea_enabled,
            "experimental_rea": rea_enabled,
        }
        print(json.dumps(data, indent=2))
        return 0 if res.success else 1

    if res.success:
        print(theme.badge("PASS", res.message))
        print(f"  • Stack: {res.stack}")
        if rea_enabled:
            label = "Would scaffold" if res.dry_run else "Enabled"
            print(f"  • REA: {label} Reverse Engineer Anything support (.agents/ledger/)")
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
            print(f"\n{theme.badge('WARN', f'Notice: {res.legacy_notice}')}")
        return 0
    else:
        sys.stderr.write(theme.badge("FAIL", f"Error: {res.message}", stream=sys.stderr) + "\n")
        return 1
