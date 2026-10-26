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
    enforce_single_source_rules,
    enforce_single_source_skills,
    harmonize_workspace,
    install_workspace,
    purge_build_caches,
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
    skills: Optional[Union[str, List[str]]] = None,
    prune_legacy: bool = True,
    no_prune: bool = False,
    allow_dirty: bool = False,
    create_branch: Optional[Union[str, bool]] = None,
    purge_caches: bool = True,
    no_cache_purge: bool = False,
    dry_run: bool = False,
    json_output: bool = False,
    open_pr: bool = False,
    upstream_remote: Optional[str] = None,
    base_branch: Optional[str] = None,
    config_dir: Optional[Union[Path, str]] = None,
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
        skills_arg = getattr(args, "skills", None)
        if isinstance(skills_arg, str):
            skills = [s.strip() for s in skills_arg.split(",") if s.strip()]
        elif isinstance(skills_arg, (list, tuple, set)):
            skills = list(skills_arg)
        else:
            skills = None
        no_prune = bool(getattr(args, "no_prune", False))
        prune_legacy = bool(getattr(args, "prune_legacy", True) or getattr(args, "clean_agent_dir", False))
        effective_prune = False if no_prune else prune_legacy
        allow_dirty = bool(getattr(args, "allow_dirty", False))
        create_branch = getattr(args, "create_branch", None)
        no_cache_purge = bool(getattr(args, "no_cache_purge", False))
        purge_caches = bool(getattr(args, "purge_caches", True))
        effective_purge_caches = False if no_cache_purge else purge_caches
        dry_run = bool(getattr(args, "dry_run", False))
        json_output = bool(getattr(args, "json", False))
        open_pr = bool(getattr(args, "pr", False) or getattr(args, "open_pr", False) or getattr(args, "create_pr", False))
        upstream_remote = getattr(args, "upstream_remote", None)
        base_branch = getattr(args, "base_branch", None)
        config_dir = getattr(args, "config_dir", None)
    else:
        target_path = Path(workspace)
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]
        elif isinstance(skills, (list, tuple, set)):
            skills = list(skills)
        effective_prune = False if no_prune else prune_legacy
        allow_dirty = bool(allow_dirty)
        effective_purge_caches = False if no_cache_purge else purge_caches

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

    # 4. Working tree dirty safety check
    safety_patch_path: Optional[str] = None
    if topology.is_dirty:
        if not allow_dirty:
            err_msg = "Working tree has uncommitted changes. Stash/commit your changes or use --allow-dirty."
            if json_output:
                print(json.dumps({
                    "success": False,
                    "error": err_msg,
                    "workspace": str(ws),
                    "is_dirty": True,
                }, indent=2))
            else:
                sys.stderr.write(f"✘ Error: {err_msg}\n")
            return 1

        patch_file = ws / ".agents" / "artifacts" / "wip-safety-pre-onboard.patch"
        safety_patch_path = str(patch_file)
        if not dry_run:
            patch_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                configure_git_exclude(ws)
            except Exception:
                pass
            diff_proc = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                check=False,
            )
            diff_content = diff_proc.stdout
            if diff_proc.returncode != 0 or not diff_content:
                diff_proc2 = subprocess.run(
                    ["git", "diff"],
                    cwd=ws,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                    check=False,
                )
                diff_content = diff_proc2.stdout
            patch_file.write_text(diff_content, encoding="utf-8")

    # 5. Dedicated branch isolation
    created_branch_name: Optional[str] = None
    if create_branch:
        branch_name = (
            create_branch
            if isinstance(create_branch, str) and create_branch.strip()
            else "chore/agyis-harness-onboarding"
        )
        created_branch_name = branch_name
        if topology.current_branch != branch_name:
            if dry_run:
                topology.current_branch = branch_name
            else:
                base_b = topology.active_base_branch or topology.default_branch or "main"
                checkout_proc = subprocess.run(
                    ["git", "checkout", "-b", branch_name, base_b],
                    cwd=ws,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if checkout_proc.returncode != 0:
                    checkout_proc = subprocess.run(
                        ["git", "checkout", "-b", branch_name],
                        cwd=ws,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                if checkout_proc.returncode != 0:
                    checkout_proc = subprocess.run(
                        ["git", "checkout", branch_name],
                        cwd=ws,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                if checkout_proc.returncode != 0:
                    err_msg = f"Failed to checkout branch '{branch_name}': {checkout_proc.stderr.strip()}"
                    if json_output:
                        print(json.dumps({"success": False, "error": err_msg, "workspace": str(ws)}, indent=2))
                    else:
                        sys.stderr.write(f"✘ Error: {err_msg}\n")
                    return 1
                topology.current_branch = branch_name

    # 6. Monorepo subproject path resolution
    subproject_path = (ws / subproject).resolve() if subproject else ws
    if subproject and not subproject_path.is_dir():
        err_msg = f"Subproject directory '{subproject}' does not exist in {ws}"
        if json_output:
            print(json.dumps({"success": False, "error": err_msg, "workspace": str(ws)}, indent=2))
        else:
            sys.stderr.write(f"✘ Error: {err_msg}\n")
        return 1

    # 7. Purge stale build caches (.next/, .turbo/) before verification gates
    purged_caches: List[str] = []
    if effective_purge_caches:
        purged_caches = purge_build_caches(ws, subproject=subproject, dry_run=dry_run)

    # 8. Configure git exclusions for runtime safety
    if not dry_run:
        try:
            configure_git_exclude(ws)
        except Exception:
            pass

    # 9. Harmonize workspace (legacy .agent/ migration, rules tags, archive/prune)
    harm_res = harmonize_workspace(
        workspace_dir=subproject_path,
        dry_run=dry_run,
        prune_legacy=effective_prune,
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

    # 10. Provision skills with decoupled presets or explicit list
    skills_list: List[str] = []
    if skills is not None:
        skills_list = list(skills)
    elif is_monorepo(ws) and not subproject and not lang and not role:
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

    if not skills_list and skills is None:
        skills_list = resolve_skills_to_sync(
            stack=lang or "auto",
            role=role,
            workspace_root=subproject_path,
        )

    effective_stack = lang or detect_workspace_stack(subproject_path) or "generic"
    effective_role = role or detect_workspace_role(subproject_path)

    # 11. Database port collision audit for backend/fullstack roles
    db_check: Optional[Dict[str, Any]] = None
    if effective_role in ("backend", "fullstack"):
        from harness.runtime.hygiene_checks import check_database_port_conflicts

        db_check = check_database_port_conflicts(workspace_root=subproject_path)

    if skills_list:
        install_workspace(
            workspace_dir=subproject_path,
            stack=effective_stack,
            skills=skills_list,
            include_agents=False,
            dedup=True,
            dry_run=dry_run,
        )

    # 12. Enforce single-source skill deduplication by default (Issue #52, rc4 learnings)
    config_dir_path = (
        Path(config_dir).resolve()
        if config_dir is not None
        else Path(os.environ.get("AGYIS_CONFIG_DIR") or os.environ.get("PSL_CONFIG_DIR") or (Path.home() / ".gemini" / "config")).resolve()
    )
    pruned_skills = enforce_single_source_skills(
        config_dir=config_dir_path,
        workspace_dir=subproject_path,
        dry_run=dry_run,
    )

    # 12b. Enforce single-source rule deduplication by default (Issue #70, v1.0.0-rc7)
    rule_dedup_res = enforce_single_source_rules(
        workspace_dir=subproject_path,
        config_dir=config_dir_path,
        dry_run=dry_run,
    )

    # 13. Pull Request creation if requested
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

    # 14. Return JSON output or formatted terminal summary
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
            "skills_deduplicated": pruned_skills,
            "caches_purged": purged_caches,
            "purged_caches": purged_caches,
            "safety_patch": safety_patch_path,
            "created_branch": created_branch_name,
            "database_port_check": db_check,
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
    if created_branch_name:
        prefix_branch = "[dry-run] Would checkout" if dry_run else "Switched to"
        print(f"  • {prefix_branch} onboarding branch: {created_branch_name}")
    print(f"  • Remote target: {topology.push_target_remote} -> {topology.pr_target_repo or 'origin'}")
    if topology.requires_fork:
        print(f"  • Fork required: yes (viewer permission: {topology.viewer_permission or 'read-only'})")
    if subproject:
        print(f"  • Subproject: {subproject}")
    print(f"  • Stack: {effective_stack} (role: {effective_role or 'none'})")
    print(f"  • Skills: {', '.join(skills_list) if skills_list else 'none'}")
    if pruned_skills:
        prefix_dedup = "[dry-run] Would prune" if dry_run else "Pruned"
        print(f"  • {prefix_dedup} {len(pruned_skills)} duplicate skill(s) shadowing global plugin: {', '.join(Path(p).name for p in pruned_skills)}")
    if safety_patch_path:
        prefix_patch = "[dry-run] Would record" if dry_run else "Recorded"
        print(f"  • {prefix_patch} pre-onboard safety patch: .agents/artifacts/wip-safety-pre-onboard.patch")
    if purged_caches:
        prefix_cache = "[dry-run] Would purge" if dry_run else "Purged"
        print(f"  • {prefix_cache} {len(purged_caches)} build cache directory(ies): {', '.join(Path(p).name for p in purged_caches)}")
    if harm_res.legacy_agent_dir_found:
        print(f"  • Harmonized legacy .agent/: yes (pruned: {'yes' if effective_prune else 'no'})")
    if db_check and db_check.get("status") == "WARNING":
        print(f"  • Warning: Database port conflict detected on port {db_check.get('port')}: {db_check.get('details')}")
    if open_pr:
        print(f"  • Pull Request: {pr_msg}")
    if polluting_files:
        print(f"  • Warning: {len(polluting_files)} polluting files detected: {', '.join(polluting_files[:3])}")

    return 0


__all__ = ["cmd_onboard"]
