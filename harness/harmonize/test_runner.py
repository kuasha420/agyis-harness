# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Test Runner Harmonization Engine (RFC-051 Phase 2).
Antigravity Immune System (Autonomous Agent Runtime).

Audits project test manifests, plans non-destructive script injections,
upgrades DOM mounting environments, creates pre-mutation backup patches,
and generates the standard .agyis/test_manifest.json manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import difflib
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.discovery import detect_project_test_runner
from harness.skills import (
    detect_monorepo_stack,
    detect_workspace_role,
    detect_workspace_stack,
    is_monorepo,
)


@dataclass(frozen=True)
class TestScriptSpec:
    """Standardized test script definition."""
    __test__ = False
    name: str
    command: str
    description: str
    tier: str  # "1a", "1b", "2a", "2b", "watch"
    clears_turn: bool = False
    required_for_handoff: bool = False
    required_for_commit: bool = False


@dataclass
class FileMutation:
    """Planned file modification with unified diff preview."""
    target_path: Path
    original_content: str
    proposed_content: str
    unified_diff: str
    description: str
    is_new_file: bool = False


@dataclass
class TestAuditReport:
    """Comprehensive test configuration audit of a workspace."""
    __test__ = False
    workspace_root: Path
    detected_stack: str
    detected_role: Optional[str]
    test_framework: str
    package_manager: str
    is_monorepo: bool
    manifest_type: Optional[str]
    manifest_path: Optional[Path]
    existing_scripts: Dict[str, str] = field(default_factory=dict)
    missing_scripts: List[str] = field(default_factory=list)
    preserved_custom_scripts: List[str] = field(default_factory=list)
    ui_mounting_status: str = "unsupported"  # "optimal", "missing_dom_env", "unsupported", "configured"
    vrt_status: str = "unsupported"  # "pixel_diff", "synthetic_existence_check", "missing", "unsupported"
    gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "detected_stack": self.detected_stack,
            "detected_role": self.detected_role,
            "test_framework": self.test_framework,
            "package_manager": self.package_manager,
            "is_monorepo": self.is_monorepo,
            "manifest_type": self.manifest_type,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "existing_scripts": self.existing_scripts,
            "missing_scripts": self.missing_scripts,
            "preserved_custom_scripts": self.preserved_custom_scripts,
            "ui_mounting_status": self.ui_mounting_status,
            "vrt_status": self.vrt_status,
            "gaps": self.gaps,
        }


@dataclass
class HarmonizeTestResult:
    """Outcome report for test runner harmonization."""
    success: bool
    workspace_root: Path
    dry_run: bool
    applied: bool
    audit: TestAuditReport
    mutations: List[FileMutation] = field(default_factory=list)
    backup_patch: Optional[Path] = None
    manifest_path: Optional[Path] = None
    manifest_data: Optional[Dict[str, Any]] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "workspace_root": str(self.workspace_root),
            "dry_run": self.dry_run,
            "applied": self.applied,
            "audit": self.audit.to_dict(),
            "mutations": [
                {
                    "target_path": str(m.target_path),
                    "description": m.description,
                    "is_new_file": m.is_new_file,
                    "unified_diff": m.unified_diff,
                }
                for m in self.mutations
            ],
            "backup_patch": str(self.backup_patch) if self.backup_patch else None,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "manifest_data": self.manifest_data,
            "message": self.message,
        }


class TestHarmonizer:
    """
    Core engine for auditing, diff-generating, patching, and applying
    standardized test configurations across polyglot repositories.
    """
    __test__ = False

    def __init__(self, workspace_root: Union[Path, str]) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def audit(self) -> TestAuditReport:
        """Audits the workspace for existing test manifests, runners, and gaps."""
        ws = self.workspace_root
        stack = detect_workspace_stack(ws) or "unknown"
        role = detect_workspace_role(ws)
        mono = is_monorepo(ws)

        manifest_type = None
        manifest_path = None
        framework = "unknown"
        pkg_manager = "npm"
        existing_scripts: Dict[str, str] = {}
        missing_scripts: List[str] = []
        preserved_scripts: List[str] = []
        gaps: List[str] = []
        ui_mounting_status = "unsupported"
        vrt_status = "unsupported"

        # 1. Node / TS
        package_json = ws / "package.json"
        if package_json.is_file():
            manifest_type = "package.json"
            manifest_path = package_json
            if (ws / "pnpm-lock.yaml").exists() or (ws / ".pnpm-lock.yaml").exists():
                pkg_manager = "pnpm"
            elif (ws / "bun.lockb").exists() or (ws / "bun.lock").exists() or (ws / "bunfig.toml").exists():
                pkg_manager = "bun"
            elif (ws / "yarn.lock").exists():
                pkg_manager = "yarn"
            else:
                pkg_manager = "npm"

            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                scripts = data.get("scripts", {})
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                if "vitest" in deps or "vitest" in str(scripts.get("test", "")):
                    framework = "vitest"
                elif "jest" in deps or "jest" in str(scripts.get("test", "")):
                    framework = "jest"
                elif "playwright" in deps or "@playwright/test" in deps:
                    framework = "playwright"
                else:
                    framework = "node--test"

                # Standard tier scripts to check
                standard_names = ["test:diff", "test:watch", "test:affected", "test:pkg", "test:full"]
                for name in standard_names:
                    if name in scripts:
                        existing_scripts[name] = scripts[name]
                        preserved_scripts.append(name)
                    else:
                        missing_scripts.append(name)
                        gaps.append(f"Missing standardized tier script '{name}'")

                # UI mounting checks
                is_frontend = role in ("frontend", "fullstack") or any(
                    f in deps for f in ("react", "vue", "svelte", "@testing-library/react")
                )
                if is_frontend:
                    vitest_configs = list(ws.glob("vitest.config.*")) + list(ws.glob("vite.config.*"))
                    if vitest_configs:
                        cfg_content = vitest_configs[0].read_text(encoding="utf-8", errors="replace")
                        if "happy-dom" in cfg_content or "jsdom" in cfg_content:
                            ui_mounting_status = "optimal"
                        else:
                            ui_mounting_status = "missing_dom_env"
                            gaps.append("Missing DOM mounting environment in vitest config (0% UI mounting risk). Recommend environment: 'happy-dom'")
                    else:
                        ui_mounting_status = "configured" if "@testing-library/react" in deps else "missing_dom_env"

            except Exception as e:
                gaps.append(f"Failed to parse package.json: {e}")

        # 2. Rust
        elif (ws / "Cargo.toml").is_file():
            manifest_type = "Cargo.toml"
            manifest_path = ws / "Cargo.toml"
            framework = "cargo"
            pkg_manager = "cargo"
            missing_scripts = ["test:diff", "test:watch", "test:affected", "test:pkg", "test:full"]

        # 3. Python
        elif (ws / "pyproject.toml").is_file():
            manifest_type = "pyproject.toml"
            manifest_path = ws / "pyproject.toml"
            framework = "pytest"
            pkg_manager = "uv" if (ws / "uv.lock").exists() else "pip"
            missing_scripts = ["test:diff", "test:watch", "test:affected", "test:full"]

        # 4. Makefile
        elif (ws / "Makefile").is_file() or (ws / "makefile").is_file():
            manifest_type = "Makefile"
            manifest_path = ws / "Makefile" if (ws / "Makefile").is_file() else ws / "makefile"
            framework = "make"
            pkg_manager = "make"
            missing_scripts = ["test:diff", "test:watch", "test:affected", "test:full"]

        return TestAuditReport(
            workspace_root=ws,
            detected_stack=stack,
            detected_role=role,
            test_framework=framework,
            package_manager=pkg_manager,
            is_monorepo=mono,
            manifest_type=manifest_type,
            manifest_path=manifest_path,
            existing_scripts=existing_scripts,
            missing_scripts=missing_scripts,
            preserved_custom_scripts=preserved_scripts,
            ui_mounting_status=ui_mounting_status,
            vrt_status=vrt_status,
            gaps=gaps,
        )

    def plan_mutations(self, audit: TestAuditReport) -> List[FileMutation]:
        """Plans non-destructive file mutations with unified diff previews."""
        mutations: List[FileMutation] = []
        ws = self.workspace_root

        # A. Node / TypeScript package.json mutations
        if audit.manifest_type == "package.json" and audit.manifest_path and audit.manifest_path.is_file():
            original_text = audit.manifest_path.read_text(encoding="utf-8")
            try:
                data = json.loads(original_text)
                scripts = data.get("scripts", {})
                updated_scripts = dict(scripts)

                framework = audit.test_framework
                pkg = audit.package_manager

                scripts_to_inject: Dict[str, str] = {}
                if framework == "vitest":
                    scripts_to_inject = {
                        "test:diff": "vitest related --run",
                        "test:watch": "vitest",
                        "test:affected": "vitest related --run",
                        "test:pkg": "vitest --project",
                        "test:full": "vitest run",
                    }
                elif framework == "jest":
                    scripts_to_inject = {
                        "test:diff": "jest --findRelatedTests --passWithNoTests",
                        "test:watch": "jest --watch",
                        "test:affected": "jest --findRelatedTests --passWithNoTests",
                        "test:pkg": f"{pkg} --filter",
                        "test:full": "jest --runInBand",
                    }
                else:
                    scripts_to_inject = {
                        "test:diff": f"{pkg} test -- --diff",
                        "test:watch": f"{pkg} test -- --watch",
                        "test:affected": f"{pkg} test -- --affected",
                        "test:pkg": f"{pkg} test",
                        "test:full": f"{pkg} test",
                    }

                mutated = False
                for name, cmd in scripts_to_inject.items():
                    if name not in updated_scripts:
                        updated_scripts[name] = cmd
                        mutated = True

                if mutated:
                    data["scripts"] = updated_scripts
                    proposed_text = json.dumps(data, indent=2) + "\n"
                    diff = self._generate_unified_diff(
                        audit.manifest_path, original_text, proposed_text
                    )
                    mutations.append(
                        FileMutation(
                            target_path=audit.manifest_path,
                            original_content=original_text,
                            proposed_content=proposed_text,
                            unified_diff=diff,
                            description=f"Inject standardized diff-aware test scripts into {audit.manifest_path.name}",
                        )
                    )
            except Exception:
                pass

        # B. Python / Makefile mutations
        elif audit.manifest_type in ("pyproject.toml", "Makefile"):
            make_file = ws / "Makefile"
            if make_file.is_file():
                orig_make = make_file.read_text(encoding="utf-8")
                addition = (
                    "\n# Added by AGYIS-HARNESS (psl-test-harmonize)\n"
                    ".PHONY: test:diff test:watch test:affected test:full\n\n"
                    "test:diff:\n\tpytest --picked -q\n\n"
                    "test:watch:\n\tptw\n\n"
                    "test:affected:\n\tpytest -q\n\n"
                    "test:full:\n\tpytest -v\n"
                )
                if "test:diff" not in orig_make:
                    proposed_make = orig_make.rstrip() + "\n" + addition
                    diff = self._generate_unified_diff(make_file, orig_make, proposed_make)
                    mutations.append(
                        FileMutation(
                            target_path=make_file,
                            original_content=orig_make,
                            proposed_content=proposed_make,
                            unified_diff=diff,
                            description="Inject standardized test targets into Makefile",
                        )
                    )

        return mutations

    def create_backup_patch(
        self,
        mutations: List[FileMutation],
        backup_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """Creates a pre-mutation unified diff backup patch before writing to disk."""
        if not mutations:
            return None

        target_backup_dir = backup_dir or (self.workspace_root / ".agyis" / "backups")
        target_backup_dir.mkdir(parents=True, exist_ok=True)

        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        patch_path = target_backup_dir / f"test_harmonize_{now_str}.patch"

        combined_diff = "\n".join(m.unified_diff for m in mutations if m.unified_diff)
        patch_path.write_text(combined_diff, encoding="utf-8")
        return patch_path

    def build_test_manifest(
        self,
        audit: TestAuditReport,
        backup_patch: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Builds conforming .agyis/test_manifest.json structure."""
        now_iso = datetime.now(timezone.utc).isoformat()
        pm = audit.package_manager
        frm = audit.test_framework

        if audit.manifest_type == "package.json":
            diff_cmd = f"{pm} test:diff"
            affected_cmd = f"{pm} test:affected"
            pkg_cmd = f"{pm} --filter" if audit.is_monorepo else f"{pm} test:pkg"
            full_cmd = f"{pm} test:full"
            watch_cmd = f"{pm} test:watch"
        elif audit.manifest_type == "Cargo.toml":
            diff_cmd = "cargo test"
            affected_cmd = "cargo test"
            pkg_cmd = "cargo test --package" if audit.is_monorepo else "cargo test"
            full_cmd = "cargo test --workspace" if audit.is_monorepo else "cargo test"
            watch_cmd = "cargo watch -x test"
        elif audit.manifest_type == "Makefile":
            diff_cmd = "make test:diff"
            affected_cmd = "make test:affected"
            pkg_cmd = "make test:pkg"
            full_cmd = "make test:full"
            watch_cmd = "make test:watch"
        else:
            diff_cmd = "pytest --picked"
            affected_cmd = "pytest"
            pkg_cmd = "pytest"
            full_cmd = "pytest"
            watch_cmd = "ptw"

        backup_patch_str = None
        if backup_patch:
            try:
                backup_patch_str = str(backup_patch.relative_to(self.workspace_root))
            except ValueError:
                backup_patch_str = str(backup_patch)

        manifest: Dict[str, Any] = {
            "$schema": "https://raw.githubusercontent.com/kuasha420/agyis-harness/main/docs/schemas/test_manifest.schema.json",
            "version": "1.0.0",
            "generated_at": now_iso,
            "workspace_root": str(self.workspace_root),
            "stack": audit.detected_stack,
            "role": audit.detected_role,
            "framework": frm,
            "package_manager": pm,
            "is_monorepo": audit.is_monorepo,
            "manifest_file": audit.manifest_type or "unknown",
            "backup_patch": backup_patch_str,
            "tiers": {
                "tier_1a_diff": {
                    "name": "test:diff",
                    "command": diff_cmd,
                    "description": "Diff-targeted immediate test execution (<1.0s) for active turn",
                    "supported": True,
                    "native_support": frm in ("vitest", "jest"),
                    "clears_turn_code_dirty": True,
                },
                "tier_1b_affected": {
                    "name": "test:affected",
                    "command": affected_cmd,
                    "description": "Blast-radius integration and component tests affected by diff",
                    "supported": True,
                    "required_for_handoff": True,
                },
                "tier_2a_pkg": {
                    "name": "test:pkg",
                    "command": pkg_cmd,
                    "description": "Filtered package execution in monorepos",
                    "supported": audit.is_monorepo,
                },
                "tier_2b_full": {
                    "name": "test:full",
                    "command": full_cmd,
                    "description": "Complete workspace test suite for final commit and PR gates",
                    "supported": True,
                    "required_for_commit": True,
                },
            },
            "human_loop": {
                "watch_command": watch_cmd,
                "non_interactive_guard": "--no-watch CI=true",
            },
            "ui_mounting": {
                "detected_frontend": audit.detected_role in ("frontend", "fullstack"),
                "environment": "happy-dom" if audit.ui_mounting_status == "optimal" else None,
                "has_dom_testing_library": True,
                "vrt_pixel_diff": False,
                "a11y_axe": False,
                "anti_synthetic_score": "passing" if audit.ui_mounting_status == "optimal" else "warning",
            },
            "scripts": {
                "test:diff": diff_cmd,
                "test:watch": watch_cmd,
                "test:affected": affected_cmd,
                "test:full": full_cmd,
            },
        }
        return manifest

    def _generate_unified_diff(self, path: Path, original: str, updated: str) -> str:
        """Computes clean unified diff between original and updated file content."""
        try:
            rel = path.relative_to(self.workspace_root).as_posix()
        except ValueError:
            rel = path.name
        from_lines = original.splitlines(keepends=True)
        to_lines = updated.splitlines(keepends=True)
        diff = difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        return "".join(diff)


def harmonize_test_runners(
    workspace_dir: Optional[Union[Path, str]] = None,
    dry_run: bool = True,
    apply: bool = False,
    backup: bool = True,
    backup_dir: Optional[Path] = None,
) -> HarmonizeTestResult:
    """
    Main orchestration entrypoint for test runner harmonization.
    Defaults to non-destructive dry-run preview unless apply=True.
    """
    ws = Path(workspace_dir or Path.cwd()).resolve()
    harmonizer = TestHarmonizer(ws)

    audit = harmonizer.audit()
    mutations = harmonizer.plan_mutations(audit)

    # Determine execution mode: apply overrides dry_run
    is_dry_run = not apply and dry_run

    backup_patch_path: Optional[Path] = None
    manifest_path = ws / ".agyis" / "test_manifest.json"
    manifest_data: Optional[Dict[str, Any]] = None

    if is_dry_run:
        manifest_data = harmonizer.build_test_manifest(audit, backup_patch=None)
        msg = f"Audited {audit.manifest_type or 'workspace'}: {len(mutations)} proposed mutation(s) previewed."
        return HarmonizeTestResult(
            success=True,
            workspace_root=ws,
            dry_run=True,
            applied=False,
            audit=audit,
            mutations=mutations,
            backup_patch=None,
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            message=msg,
        )

    # Apply mode: write backup patch first, then mutate files, then emit manifest
    if backup and mutations:
        backup_patch_path = harmonizer.create_backup_patch(mutations, backup_dir=backup_dir)

    for m in mutations:
        m.target_path.parent.mkdir(parents=True, exist_ok=True)
        m.target_path.write_text(m.proposed_content, encoding="utf-8")

    manifest_data = harmonizer.build_test_manifest(audit, backup_patch=backup_patch_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    msg = f"Harmonized {audit.manifest_type or 'workspace'}: Applied {len(mutations)} mutation(s) cleanly."
    return HarmonizeTestResult(
        success=True,
        workspace_root=ws,
        dry_run=False,
        applied=True,
        audit=audit,
        mutations=mutations,
        backup_patch=backup_patch_path,
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        message=msg,
    )
