# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unified workspace onboarding CLI command (ADR-014, ADR-031).
Coordinates topology probing, harmonization, skill provisioning, and PR delivery.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Union

from harness.delivery import (
    GitTopology,
    GitTopologyProbe,
    RemoteInfo,
    configure_git_exclude,
    create_pull_request,
    harmonize_workspace,
    install_workspace,
    verify_zero_git_pollution,
)
from harness.skills import (
    ARCHITECTURAL_ROLE_PRESETS,
    LANGUAGE_RUNTIME_PRESETS,
    detect_monorepo_stack,
    detect_workspace_role,
    detect_workspace_stack,
    is_monorepo,
    resolve_skills_to_sync,
)


def cmd_onboard(
    workspace: Union[Path, str, argparse.Namespace] = Path.cwd(),
    lang: Optional[str] = None,
    role: Optional[str] = None,
    subproject: Optional[str] = None,
    prune_legacy: bool = False,
    dry_run: bool = False,
    json_output: bool = False,
    open_pr: bool = False,
    upstream_remote: Optional[str] = None,
    base_branch: Optional[str] = None,
) -> int:
    """
    Onboards a repository to the Agyis harness runtime.

    Probes git remote topology, runs legacy harmonization and pruning,
    provisions decoupled stack & role modular skills, configures exclusions,
    and optionally opens a GitHub Pull Request against the active base branch.
    """
    if isinstance(workspace, argparse.Namespace):
        args = workspace
        raw_path = getattr(args, "path", None) or getattr(args, "workspace", None) or Path.cwd()
        target_path = Path(raw_path)
        lang = getattr(args, "lang", None) or getattr(args, "stack", None)
        role = getattr(args, "role", None)
        subproject = getattr(args, "subproject", None)
        prune_legacy = bool(getattr(args, "prune_legacy", False) or getattr(args, "clean_agent_dir", False))
        dry_run = bool(getattr(args, "dry_run", False))
        json_output = bool(getattr(args, "json", False))
        open_pr = bool(getattr(args, "pr", False) or getattr(args, "open_pr", False) or getattr(args, "create_pr", False))
        upstream_remote = getattr(args, "upstream_remote", None)
        base_branch = getattr(args, "base_branch", None)
    else:
        target_path = Path(workspace)

    ws = target_path.resolve()
    if not ws.exists() or not ws.is_dir():
        err_msg = f"Workspace directory does not exist: {ws}"
        if json_output:
            print(json.dumps({"success": False, "error": err_msg, "workspace": str(ws)}, indent=2))
        else:
            sys.stderr.write(f"✘ Error: {err_msg}\n")
        return 1

    # 1. Probe git topology
    try:
        topology = GitTopologyProbe.probe(ws, upstream_remote=upstream_remote)
    except Exception as exc:
        if json_output:
            print(json.dumps({"success": False, "error": str(exc), "workspace": str(ws)}, indent=2))
        else:
            sys.stderr.write(f"✘ Error: {exc}\n")
        return 1

    if base_branch:
        topology.pr_base_branch = base_branch
        topology.active_base_branch = base_branch

    # 2. Self-referential harness host check
    if topology.is_harness_host:
        msg = "Notice: Workspace is the Agyis harness host repository. Skipping self-referential onboarding."
        if json_output:
            print(json.dumps({
                "success": True,
                "workspace": str(ws),
                "is_harness_host": True,
                "message": msg,
                "topology": topology.to_dict(),
            }, indent=2))
        else:
            print(f"💡 {msg}")
        return 0

    # 3. Auxiliary clone check
    if topology.is_auxiliary_clone:
        msg = "Notice: Workspace is an auxiliary clone. Skipping duplicate onboarding."
        if json_output:
            print(json.dumps({
                "success": True,
                "workspace": str(ws),
                "is_auxiliary_clone": True,
                "message": msg,
                "topology": topology.to_dict(),
            }, indent=2))
        else:
            print(f"💡 {msg}")
        return 0

    # 4. Monorepo subproject path resolution
    subproject_path = (ws / subproject).resolve() if subproject else ws
    if subproject and not subproject_path.is_dir():
        err_msg = f"Subproject directory '{subproject}' does not exist in {ws}"
        if json_output:
            print(json.dumps({"success": False, "error": err_msg, "workspace": str(ws)}, indent=2))
        else:
            sys.stderr.write(f"✘ Error: {err_msg}\n")
        return 1

    # 5. Configure git exclusions for runtime safety
    if not dry_run:
        try:
            configure_git_exclude(ws)
        except Exception:
            pass

    # 6. Harmonize workspace (legacy .agent/ migration, rules tags, archive/prune)
    harm_res = harmonize_workspace(
        workspace_dir=subproject_path,
        dry_run=dry_run,
        prune_legacy=prune_legacy,
        backup=True,
        stack=lang,
    )
    if not harm_res.success:
        if json_output:
            print(json.dumps({
                "success": False,
                "workspace": str(ws),
                "error": harm_res.message,
            }, indent=2))
        else:
            sys.stderr.write(f"✘ Error: {harm_res.message}\n")
        return 1

    # 7. Provision skills with decoupled presets
    skills_list: List[str] = []
    if is_monorepo(ws) and not subproject and not lang and not role:
        mono_langs, mono_roles = detect_monorepo_stack(ws)
        s_set: set[str] = set()
        for l in mono_langs:
            if l in LANGUAGE_RUNTIME_PRESETS:
                s_set.update(LANGUAGE_RUNTIME_PRESETS[l])
        for r in mono_roles:
            if r in ARCHITECTURAL_ROLE_PRESETS:
                s_set.update(ARCHITECTURAL_ROLE_PRESETS[r])
        if s_set:
            skills_list = sorted(s_set)

    if not skills_list:
        skills_list = resolve_skills_to_sync(
            stack=lang or "auto",
            role=role,
            workspace_root=subproject_path,
        )

    effective_stack = lang or detect_workspace_stack(subproject_path) or "generic"
    effective_role = role or detect_workspace_role(subproject_path)

    if skills_list:
        install_workspace(
            workspace_dir=subproject_path,
            stack=effective_stack,
            skills=skills_list,
            include_agents=False,
            dedup=True,
            dry_run=dry_run,
        )

    # 8. Pull Request creation if requested
    pr_created = False
    pr_url: Optional[str] = None
    pr_msg: Optional[str] = None

    if open_pr:
        if dry_run:
            pr_msg = f"[dry-run] Would push to '{topology.push_target_remote}' and create PR against '{topology.pr_target_repo}' ({topology.pr_base_branch})"
        else:
            push_cmd = ["git", "push", "-u", topology.push_target_remote or "origin", topology.current_branch]
            try:
                subprocess.run(
                    push_cmd,
                    cwd=ws,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except Exception:
                pass

            title = f"chore: onboard workspace to Agyis Harness"
            body = (
                f"Onboards `{ws.name}` to the Agyis Harness runtime.\n\n"
                f"- Harmonized `.agents/` structure\n"
                f"- Tagged AGYIS-HARNESS invariant rules injected\n"
                f"- Stack skills provisioned: {', '.join(skills_list) if skills_list else 'none'}\n"
            )
            ok, res_str = create_pull_request(
                topology=topology,
                title=title,
                body=body,
                draft=False,
                base=topology.pr_base_branch,
            )
            pr_created = ok
            pr_msg = res_str
            if ok:
                pr_url = res_str

    polluting_files = verify_zero_git_pollution(ws)

    # 9. Return JSON output or formatted terminal summary
    if json_output:
        out_data = {
            "success": True,
            "workspace": str(ws),
            "target_workspace": str(subproject_path),
            "subproject": subproject,
            "dry_run": dry_run,
            "stack": effective_stack,
            "role": effective_role,
            "topology": topology.to_dict(),
            "harmonize": harm_res.to_dict(),
            "skills_provisioned": skills_list,
            "polluting_files": polluting_files,
            "pr_opened": pr_created,
            "pr_url": pr_url,
            "pr_message": pr_msg,
            "message": "Workspace onboarded successfully",
        }
        print(json.dumps(out_data, indent=2))
        return 0

    prefix = "✔ [DRY-RUN] " if dry_run else "✔ "
    print(f"{prefix}Workspace onboarded: {ws}")
    print(f"  • Current branch: {topology.current_branch} (base: {topology.active_base_branch})")
    print(f"  • Remote target: {topology.push_target_remote} -> {topology.pr_target_repo or 'origin'}")
    if topology.requires_fork:
        print(f"  • Fork required: yes (viewer permission: {topology.viewer_permission or 'read-only'})")
    if subproject:
        print(f"  • Subproject: {subproject}")
    print(f"  • Stack: {effective_stack} (role: {effective_role or 'none'})")
    print(f"  • Skills: {', '.join(skills_list) if skills_list else 'none'}")
    if harm_res.legacy_agent_dir_found:
        print(f"  • Harmonized legacy .agent/: yes (pruned: {'yes' if prune_legacy else 'no'})")
    if open_pr:
        print(f"  • Pull Request: {pr_msg}")
    if polluting_files:
        print(f"  • Warning: {len(polluting_files)} polluting files detected: {', '.join(polluting_files[:3])}")

    return 0


__all__ = ["cmd_onboard"]
