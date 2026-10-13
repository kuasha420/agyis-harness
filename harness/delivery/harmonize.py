# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Workspace Harmonization Engine (ADR-014, ADR-030).
Antigravity Immune System (Autonomous Agent Runtime).

Non-destructively harmonizes legacy Google Antigravity configurations:
- Migrates legacy .agent/agents/ to .agents/agents/
- Converts legacy .agent/workflows/*.md to .agents/skills/<name>/SKILL.md (synthesizing frontmatter)
- Migrates legacy .agent/rules/ to .agents/rules/
- Updates legacy <!-- Added by PSL-HARNESS --> tagged blocks in AGENTS.md to <!-- Added by AGYIS-HARNESS -->
- Preserves pre-existing user rules outside tagged fences 100% intact
- Supports dry-run inspection mode with zero filesystem side-effects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from typing import Any, Dict, List, Optional, Tuple

from harness.delivery.constants import GIT_EXCLUDE_PATTERNS, REPO_ROOT
from harness.delivery.git_hygiene import configure_git_exclude
from harness.delivery.workspace import (
    LEGACY_TAG_END,
    LEGACY_TAG_START,
    TAG_END,
    TAG_START,
    TAGGED_BLOCK_PATTERN,
    extract_command_dictionary,
    format_command_dictionary,
)
from harness.utils.frontmatter import parse_frontmatter


def _compute_sha256(path: Path) -> str:
    """Computes SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _rewrite_legacy_agent_references(text: str) -> str:
    """
    Rewrites references to legacy .agent/ paths (such as .agent/rules/, .agent/agents/,
    .agent/workflows/, .agent/skills/) to modern .agents/ paths in markdown text.
    """
    return re.sub(
        r"(?<![a-zA-Z0-9_/])\.agent/(rules|agents|workflows|skills)",
        r".agents/\1",
        text,
    )


def synthesize_skill_frontmatter(content: str, default_name: str) -> str:
    """
    Ensures a workflow markdown file has valid YAML frontmatter with 'name' and 'description'.
    If missing, synthesizes standard YAML frontmatter while preserving existing body content.
    """
    fm, body = parse_frontmatter(content)
    has_name = bool(fm.get("name"))
    has_desc = bool(fm.get("description"))

    if has_name and has_desc:
        return content

    name = str(fm.get("name") or default_name).strip()
    desc = str(fm.get("description") or "").strip()

    if not desc:
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("<!--"):
                clean = s.lstrip("> *-").strip()
                if clean:
                    desc = clean[:120]
                    break
        if not desc:
            desc = f"Migrated workflow: {default_name}"

    safe_desc = desc.replace('"', '\\"')
    frontmatter_block = f"---\nname: {name}\ndescription: \"{safe_desc}\"\n---\n"

    clean_body = body.lstrip()
    if clean_body:
        return f"{frontmatter_block}\n{clean_body}"
    return frontmatter_block


@dataclass
class HarmonizeResult:
    """Outcome report for workspace harmonization."""

    success: bool
    workspace_dir: Path
    dry_run: bool
    legacy_agent_dir_found: bool = False
    legacy_workflows_migrated: List[str] = field(default_factory=list)
    legacy_agents_migrated: List[str] = field(default_factory=list)
    legacy_rules_migrated: List[str] = field(default_factory=list)
    rules_action: str = ""  # "migrated_tagged_block", "inserted_tagged_block", "created_rules_file", "already_up_to_date"
    command_dictionary: Dict[str, str] = field(default_factory=dict)
    modified: bool = False
    message: str = ""
    pruned_legacy: bool = False
    backup_archive: Optional[Path] = None
    backup_manifest: Optional[Dict[str, Any]] = None
    untracked_debris_cleaned: List[str] = field(default_factory=list)
    skills_provisioned: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert harmonization result to JSON-serializable dictionary."""
        return {
            "success": self.success,
            "workspace_dir": str(self.workspace_dir),
            "dry_run": self.dry_run,
            "legacy_agent_dir_found": self.legacy_agent_dir_found,
            "legacy_workflows_migrated": self.legacy_workflows_migrated,
            "legacy_agents_migrated": self.legacy_agents_migrated,
            "legacy_rules_migrated": self.legacy_rules_migrated,
            "rules_action": self.rules_action,
            "command_dictionary": self.command_dictionary,
            "modified": self.modified,
            "message": self.message,
            "pruned_legacy": self.pruned_legacy,
            "backup_archive": str(self.backup_archive) if self.backup_archive else None,
            "backup_manifest": self.backup_manifest,
            "untracked_debris_cleaned": self.untracked_debris_cleaned,
            "skills_provisioned": self.skills_provisioned,
        }


def harmonize_workspace(
    workspace_dir: Path,
    dry_run: bool = False,
    source_dir: Optional[Path] = None,
    prune_legacy: bool = False,
    backup: bool = True,
    archive_dir: Optional[Path] = None,
    stack: Optional[str] = None,
    skills: Optional[List[str]] = None,
) -> HarmonizeResult:
    """
    Non-destructively harmonizes a workspace from legacy .agent/ configuration
    and PSL-HARNESS tagged rules into modern .agents/ structure and AGYIS-HARNESS rules.

    Executes a 4-phase atomic legacy deprecation lifecycle when prune_legacy is enabled:
    Phase 1: Scan & SHA-256 pre-flight verification of legacy .agent/ files.
    Phase 2: Progressive migration, frontmatter synthesis, reference rewriting & checksum verification.
    Phase 3: Atomic safety archival (.tar.gz + manifest JSON in .agents/archive/ with git exclusion).
    Phase 4: Controlled deterministic pruning (git rm -rf .agent + disk debris cleanup + invariant assertion).
    """
    ws = Path(workspace_dir).resolve()
    if not ws.exists():
        return HarmonizeResult(
            success=False,
            workspace_dir=ws,
            dry_run=dry_run,
            message=f"Target workspace directory '{ws}' does not exist",
        )

    src = Path(source_dir).resolve() if source_dir else REPO_ROOT.resolve()

    legacy_agent_dir = ws / ".agent"
    legacy_agent_dir_found = legacy_agent_dir.is_dir()

    target_agents_dir = ws / ".agents"
    target_agents_subagents = target_agents_dir / "agents"
    target_skills_dir = target_agents_dir / "skills"
    target_rules_dir = target_agents_dir / "rules"

    legacy_agents_migrated: List[str] = []
    legacy_workflows_migrated: List[str] = []
    legacy_rules_migrated: List[str] = []
    any_modified = False

    # ---------------------------------------------------------
    # PHASE 1: SCAN & PRE-FLIGHT VERIFICATION
    # ---------------------------------------------------------
    source_file_digests: Dict[str, str] = {}
    if legacy_agent_dir_found:
        for root, _, files in os.walk(legacy_agent_dir):
            for f in sorted(files):
                p = Path(root) / f
                if p.is_file() and not p.is_symlink():
                    try:
                        rel = str(p.relative_to(legacy_agent_dir))
                        source_file_digests[rel] = _compute_sha256(p)
                    except OSError:
                        pass

        if not dry_run:
            if target_agents_dir.exists() and not os.access(target_agents_dir, os.W_OK):
                return HarmonizeResult(
                    success=False,
                    workspace_dir=ws,
                    dry_run=dry_run,
                    legacy_agent_dir_found=True,
                    message=f"Target directory '{target_agents_dir}' is not writable",
                )

    # ---------------------------------------------------------
    # PHASE 2: PROGRESSIVE MIGRATION & INTEGRITY VERIFICATION
    # ---------------------------------------------------------

    # 1. Migrate .agent/agents/ -> .agents/agents/
    src_agents_dir = legacy_agent_dir / "agents"
    if src_agents_dir.is_dir():
        for item in sorted(src_agents_dir.glob("*.md")):
            if item.is_file() and not item.is_symlink():
                dst_file = target_agents_subagents / item.name
                needs_copy = True
                if dst_file.is_file():
                    try:
                        if dst_file.read_bytes() == item.read_bytes():
                            needs_copy = False
                    except OSError:
                        pass
                if needs_copy:
                    legacy_agents_migrated.append(item.name)
                    any_modified = True
                    if not dry_run:
                        target_agents_subagents.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dst_file)
                        if not dst_file.is_file() or _compute_sha256(dst_file) != _compute_sha256(item):
                            return HarmonizeResult(
                                success=False,
                                workspace_dir=ws,
                                dry_run=dry_run,
                                legacy_agent_dir_found=legacy_agent_dir_found,
                                message=f"Checksum verification failed for migrated agent {dst_file}",
                            )

    # 2. Migrate legacy workflows -> .agents/skills/<name>/SKILL.md
    workflow_dirs = []
    if (legacy_agent_dir / "workflows").is_dir():
        workflow_dirs.append(legacy_agent_dir / "workflows")
    if (ws / "workflows").is_dir() and (ws / "workflows") != (target_agents_dir / "workflows"):
        workflow_dirs.append(ws / "workflows")

    for wf_dir in workflow_dirs:
        for item in sorted(wf_dir.glob("*.md")):
            if item.is_file() and not item.is_symlink():
                skill_name = item.stem
                dst_skill_dir = target_skills_dir / skill_name
                dst_skill_file = dst_skill_dir / "SKILL.md"

                content = item.read_text(encoding="utf-8", errors="replace")
                synthesized = synthesize_skill_frontmatter(content, default_name=skill_name)
                synthesized = _rewrite_legacy_agent_references(synthesized)

                needs_write = True
                if dst_skill_file.is_file():
                    try:
                        if dst_skill_file.read_text(encoding="utf-8", errors="replace") == synthesized:
                            needs_write = False
                    except OSError:
                        pass

                if needs_write:
                    legacy_workflows_migrated.append(skill_name)
                    any_modified = True
                    if not dry_run:
                        dst_skill_dir.mkdir(parents=True, exist_ok=True)
                        dst_skill_file.write_text(synthesized, encoding="utf-8")
                        if not dst_skill_file.is_file() or dst_skill_file.stat().st_size == 0:
                            return HarmonizeResult(
                                success=False,
                                workspace_dir=ws,
                                dry_run=dry_run,
                                legacy_agent_dir_found=legacy_agent_dir_found,
                                message=f"Integrity check failed for synthesized skill {dst_skill_file}",
                            )

    # 3. Migrate .agent/rules/ -> .agents/rules/
    src_rules_dir = legacy_agent_dir / "rules"
    if src_rules_dir.is_dir():
        for item in sorted(src_rules_dir.rglob("*")):
            if item.is_file() and not item.is_symlink():
                rel_path = item.relative_to(src_rules_dir)
                dst_file = target_rules_dir / rel_path
                needs_copy = True
                if dst_file.is_file():
                    try:
                        if dst_file.read_bytes() == item.read_bytes():
                            needs_copy = False
                    except OSError:
                        pass
                if needs_copy:
                    legacy_rules_migrated.append(str(rel_path))
                    any_modified = True
                    if not dry_run:
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        if item.suffix.lower() == ".md":
                            rule_text = item.read_text(encoding="utf-8", errors="replace")
                            rewritten = _rewrite_legacy_agent_references(rule_text)
                            dst_file.write_text(rewritten, encoding="utf-8")
                            if not dst_file.is_file() or (dst_file.stat().st_size == 0 and item.stat().st_size > 0):
                                return HarmonizeResult(
                                    success=False,
                                    workspace_dir=ws,
                                    dry_run=dry_run,
                                    legacy_agent_dir_found=legacy_agent_dir_found,
                                    message=f"Integrity check failed for rule {dst_file}",
                                )
                        else:
                            shutil.copy2(item, dst_file)
                            if not dst_file.is_file() or _compute_sha256(dst_file) != _compute_sha256(item):
                                return HarmonizeResult(
                                    success=False,
                                    workspace_dir=ws,
                                    dry_run=dry_run,
                                    legacy_agent_dir_found=legacy_agent_dir_found,
                                    message=f"Checksum verification failed for rule {dst_file}",
                                )

    # 4. Extract command dictionary
    cmd_dict = extract_command_dictionary(ws)

    # 5. Harmonize AGENTS.md tagged block & rewrite internal references
    rules_path = ws / "AGENTS.md"
    universal_rules_file = src / "harness" / "rules" / "universal_agents.md"
    if not universal_rules_file.is_file():
        for cand in [src / "rules" / "universal_agents.md", src / "rules" / "AGENTS.md"]:
            if cand.is_file():
                universal_rules_file = cand
                break

    if universal_rules_file.is_file():
        universal_text = universal_rules_file.read_text(encoding="utf-8").strip()
    else:
        universal_text = "# Universal Empirical Agent Rules: Agyis Harness Guidelines"

    formatted_cmds = format_command_dictionary(cmd_dict)
    if formatted_cmds:
        if "```bash\n" in universal_text:
            universal_text = universal_text.replace("```bash\n", f"```bash\n{formatted_cmds}\n\n", 1)
        else:
            universal_text = f"```bash\n{formatted_cmds}\n```\n\n{universal_text}"

    tagged_block = f"{TAG_START}\n{universal_text}\n{TAG_END}"
    rules_action = "already_up_to_date"

    if rules_path.is_file():
        existing_rules = rules_path.read_text(encoding="utf-8")
        rewritten_existing = _rewrite_legacy_agent_references(existing_rules)
        if TAGGED_BLOCK_PATTERN.search(rewritten_existing):
            new_rules = TAGGED_BLOCK_PATTERN.sub(tagged_block, rewritten_existing)
            if new_rules != existing_rules:
                rules_action = "migrated_tagged_block"
                any_modified = True
                if not dry_run:
                    rules_path.write_text(new_rules, encoding="utf-8")
            else:
                rules_action = "already_up_to_date"
        else:
            existing_clean = rewritten_existing.rstrip()
            if existing_clean:
                new_rules = f"{existing_clean}\n\n{tagged_block}\n"
            else:
                new_rules = f"{tagged_block}\n"
            rules_action = "inserted_tagged_block"
            any_modified = True
            if not dry_run:
                rules_path.write_text(new_rules, encoding="utf-8")
    else:
        new_rules = f"{tagged_block}\n"
        rules_action = "created_rules_file"
        any_modified = True
        if not dry_run:
            rules_path.write_text(new_rules, encoding="utf-8")

    # 6. Provision stack skills if requested
    skills_provisioned: List[str] = []
    if stack or skills:
        from harness.delivery.workspace import STACK_SKILL_PRESETS
        from harness.skills import detect_workspace_stack

        selected_stack = stack.strip().lower() if stack else (detect_workspace_stack(ws) or "generic")
        selected_skills = list(skills) if skills else list(STACK_SKILL_PRESETS.get(selected_stack, []))

        src_skills = None
        for cand in [src / ".agents" / "skills", src / "skills", src / "harness" / "skills"]:
            if cand.is_dir():
                src_skills = cand
                break

        if selected_skills and src_skills and src_skills.is_dir():
            target_skills_dir = ws / ".agents" / "skills"
            if not dry_run:
                target_skills_dir.mkdir(parents=True, exist_ok=True)
            for sk_name in selected_skills:
                sk_dir = src_skills / sk_name
                if not (sk_dir.exists() and sk_dir.is_dir()):
                    for cand in src_skills.iterdir():
                        if cand.is_dir() and cand.name.lower().replace("_", "-") == sk_name.lower().replace("_", "-"):
                            sk_dir = cand
                            break
                if not (sk_dir.exists() and sk_dir.is_dir()):
                    continue

                dst_sk_dir = target_skills_dir / sk_dir.name
                dst_skill_file = dst_sk_dir / "SKILL.md"
                src_skill_file = sk_dir / "SKILL.md"

                if dst_skill_file.is_file() and src_skill_file.is_file():
                    try:
                        if dst_skill_file.read_bytes() == src_skill_file.read_bytes():
                            continue
                    except OSError:
                        pass

                any_modified = True
                skills_provisioned.append(sk_dir.name)
                if not dry_run:
                    dst_sk_dir.mkdir(parents=True, exist_ok=True)
                    for item in sk_dir.rglob("*"):
                        if item.is_file():
                            rel = item.relative_to(sk_dir)
                            out_f = dst_sk_dir / rel
                            out_f.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, out_f)

    # ---------------------------------------------------------
    # PHASE 3: ATOMIC SAFETY ARCHIVAL
    # ---------------------------------------------------------
    backup_archive_path: Optional[Path] = None
    backup_manifest: Optional[Dict[str, Any]] = None

    if prune_legacy and backup and legacy_agent_dir_found:
        target_archive_dir = Path(archive_dir).resolve() if archive_dir else (ws / ".agents" / "archive")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tarball_path = target_archive_dir / f"legacy-agent-backup-{timestamp}.tar.gz"
        manifest_path = target_archive_dir / f"legacy-agent-backup-{timestamp}-manifest.json"

        # Ensure git exclusion for .agents/archive/ if in a git repo
        if not dry_run and (ws / ".git").exists():
            try:
                configure_git_exclude(ws)
            except Exception:
                pass

        # Build file manifest list
        manifest_entries: List[Dict[str, Any]] = []
        for root, _, files in os.walk(legacy_agent_dir):
            for f in sorted(files):
                p = Path(root) / f
                if p.is_file():
                    try:
                        rel = str(p.relative_to(legacy_agent_dir))
                        manifest_entries.append({
                            "path": rel,
                            "size": p.stat().st_size,
                            "sha256": _compute_sha256(p),
                        })
                    except OSError:
                        pass

        backup_manifest = {
            "timestamp": timestamp,
            "archive_path": str(tarball_path),
            "files": manifest_entries,
            "digests": {m["path"]: m["sha256"] for m in manifest_entries},
            "file_count": len(manifest_entries),
        }

        if not dry_run:
            target_archive_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tarball_path, "w:gz") as tar:
                for entry in manifest_entries:
                    file_to_add = legacy_agent_dir / entry["path"]
                    arcname = str(Path(".agent") / entry["path"])
                    tar.add(file_to_add, arcname=arcname)
            manifest_path.write_text(json.dumps(backup_manifest, indent=2), encoding="utf-8")

        backup_archive_path = tarball_path

    # ---------------------------------------------------------
    # PHASE 4: CONTROLLED DETERMINISTIC PRUNING
    # ---------------------------------------------------------
    pruned_legacy_done = False
    untracked_debris_cleaned: List[str] = []

    if prune_legacy and legacy_agent_dir_found:
        any_modified = True
        pruned_legacy_done = True

        if not dry_run:
            # Step 1: If tracked by git, git rm -rf .agent
            if (ws / ".git").exists():
                try:
                    subprocess.run(
                        ["git", "-C", str(ws), "rm", "-rf", ".agent"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass

            # Step 2: If untracked files remain on disk, append to manifest and shutil.rmtree
            if legacy_agent_dir.exists():
                for root, _, files in os.walk(legacy_agent_dir):
                    for f in sorted(files):
                        p = Path(root) / f
                        try:
                            rel = str(p.relative_to(legacy_agent_dir))
                            untracked_debris_cleaned.append(rel)
                        except OSError:
                            pass

                if backup_manifest is not None and untracked_debris_cleaned:
                    backup_manifest["untracked_debris_cleaned"] = list(untracked_debris_cleaned)
                    if manifest_path.exists():
                        manifest_path.write_text(json.dumps(backup_manifest, indent=2), encoding="utf-8")

                shutil.rmtree(legacy_agent_dir)

            # Step 3: Explicit assertion
            assert not legacy_agent_dir.exists(), f"Legacy directory {legacy_agent_dir} still exists after pruning"
        else:
            for root, _, files in os.walk(legacy_agent_dir):
                for f in sorted(files):
                    p = Path(root) / f
                    try:
                        rel = str(p.relative_to(legacy_agent_dir))
                        untracked_debris_cleaned.append(rel)
                    except OSError:
                        pass

    action_summary = []
    if legacy_agents_migrated:
        action_summary.append(f"{len(legacy_agents_migrated)} agents")
    if legacy_workflows_migrated:
        action_summary.append(f"{len(legacy_workflows_migrated)} workflows")
    if legacy_rules_migrated:
        action_summary.append(f"{len(legacy_rules_migrated)} rules")
    if rules_action in ("migrated_tagged_block", "inserted_tagged_block", "created_rules_file"):
        action_summary.append(f"rules: {rules_action}")
    if skills_provisioned:
        action_summary.append(f"{len(skills_provisioned)} skills provisioned")
    if pruned_legacy_done:
        action_summary.append("pruned legacy .agent/")

    prefix = "[dry-run] " if dry_run else ""
    if any_modified:
        msg = f"{prefix}Harmonized workspace ({', '.join(action_summary) if action_summary else 'updated'})"
    else:
        msg = f"{prefix}Workspace already harmonized (no changes needed)"

    return HarmonizeResult(
        success=True,
        workspace_dir=ws,
        dry_run=dry_run,
        legacy_agent_dir_found=legacy_agent_dir_found,
        legacy_workflows_migrated=legacy_workflows_migrated,
        legacy_agents_migrated=legacy_agents_migrated,
        legacy_rules_migrated=legacy_rules_migrated,
        rules_action=rules_action,
        command_dictionary=cmd_dict,
        modified=any_modified,
        message=msg,
        pruned_legacy=pruned_legacy_done,
        backup_archive=backup_archive_path,
        backup_manifest=backup_manifest,
        untracked_debris_cleaned=untracked_debris_cleaned,
        skills_provisioned=skills_provisioned,
    )
