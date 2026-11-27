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

from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from harness.discovery_manifest import (
    resolve_node_package_manager,
)
from harness.harmonize.test_probes import (
    build_node_scripts_to_inject,
    build_secondary_runners_map,
    collect_secondary_polyglot_runners,
    detect_node_e2e_and_a11y,
    detect_node_framework,
    detect_python_runner_caps,
    format_json_with_style,
    inspect_nested_node_manifests,
    read_json_formatting,
    resolve_makefile_manifest_commands,
    resolve_node_manifest_commands,
)
from harness.skills import (
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
    has_dom_testing_library: bool = False
    vrt_status: str = "unsupported"  # "pixel_diff", "synthetic_existence_check", "missing", "unsupported"
    gaps: List[str] = field(default_factory=list)
    secondary_runners: List[Dict[str, Any]] = field(default_factory=list)
    vrt_pixel_diff: bool = False
    a11y_axe: bool = False
    all_scripts: Dict[str, str] = field(default_factory=dict)
    nested_manifests: List[str] = field(default_factory=list)

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
            "vrt_pixel_diff": self.vrt_pixel_diff,
            "a11y_axe": self.a11y_axe,
            "nested_manifests": self.nested_manifests,
            "gaps": self.gaps,
            "secondary_runners": self.secondary_runners,
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

        manifest_type: Optional[str] = None
        manifest_path: Optional[Path] = None
        framework = "unknown"
        pkg_manager = "npm"
        existing_scripts: Dict[str, str] = {}
        all_scripts: Dict[str, str] = {}
        missing_scripts: List[str] = []
        preserved_scripts: List[str] = []
        gaps: List[str] = []
        ui_mounting_status = "unsupported"
        has_dom_testing_library = False
        vrt_status = "unsupported"
        vrt_pixel_diff = False
        a11y_axe = False
        nested_manifests: List[str] = []
        secondary_runners: List[Dict[str, Any]] = []

        package_json = ws / "package.json"
        cargo_path: Optional[Path] = None
        cargo_type: Optional[str] = None
        for rel_cargo in ("Cargo.toml", "src-tauri/Cargo.toml", "native/Cargo.toml"):
            cand = ws / rel_cargo
            if cand.is_file():
                cargo_path = cand
                cargo_type = rel_cargo
                break

        pyproject_file = ws / "pyproject.toml"
        has_py = pyproject_file.is_file()
        make_file = ws / "Makefile" if (ws / "Makefile").is_file() else (ws / "makefile" if (ws / "makefile").is_file() else None)

        if package_json.is_file():
            manifest_type = "package.json"
            manifest_path = package_json
            try:
                data, _, _ = read_json_formatting(package_json)
                pkg_manager = resolve_node_package_manager(ws, data)
                raw_scripts = data.get("scripts", {})
                all_scripts = {str(k): str(v) for k, v in raw_scripts.items()} if isinstance(raw_scripts, dict) else {}
                raw_deps = data.get("dependencies") if isinstance(data.get("dependencies"), dict) else {}
                raw_dev = data.get("devDependencies") if isinstance(data.get("devDependencies"), dict) else {}
                deps = {**raw_deps, **raw_dev}

                framework = detect_node_framework(data, ws)
                nested_manifests, nested_runners, delegated_frm = inspect_nested_node_manifests(ws, all_scripts)
                if framework == "node--test" and delegated_frm:
                    framework = delegated_frm

                e2e_info = detect_node_e2e_and_a11y(ws, data)
                vrt_pixel_diff = bool(e2e_info["vrt_pixel_diff"])
                a11y_axe = bool(e2e_info["a11y_axe"])
                if vrt_pixel_diff:
                    vrt_status = "pixel_diff"
                if e2e_info["has_playwright"] and framework != "playwright":
                    secondary_runners.extend(e2e_info["secondary_runners"])
                secondary_runners.extend(nested_runners)

                standard_names = ["test:diff", "test:watch", "test:affected", "test:full"]
                if mono:
                    standard_names.insert(3, "test:pkg")
                for name in standard_names:
                    if name in all_scripts:
                        existing_scripts[name] = all_scripts[name]
                        preserved_scripts.append(name)
                    else:
                        missing_scripts.append(name)
                        gaps.append(f"Missing standardized tier script '{name}'")

                has_dom_testing_library = any(
                    k.startswith("@testing-library/") or k in ("@vue/test-utils", "@sveltejs/testing-library")
                    for k in deps
                )
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
            except Exception as exc:
                pkg_manager = resolve_node_package_manager(ws)
                gaps.append(f"Failed to parse package.json: {exc}")

            secondary_runners.extend(
                collect_secondary_polyglot_runners(
                    ws, cargo_path, cargo_type, pyproject_file, make_file, True, True
                )
            )
        elif cargo_path:
            manifest_type = cargo_type
            manifest_path = cargo_path
            framework = "cargo"
            pkg_manager = "cargo"
            missing_scripts = ["test:diff", "test:watch", "test:affected", "test:full"]
            if mono:
                missing_scripts.insert(3, "test:pkg")
            secondary_runners.extend(
                collect_secondary_polyglot_runners(
                    ws, cargo_path, cargo_type, pyproject_file, make_file, False, True
                )
            )
        elif has_py:
            manifest_type = "pyproject.toml"
            manifest_path = pyproject_file
            framework = "pytest"
            pkg_manager = "uv" if (ws / "uv.lock").exists() else "pip"
            missing_scripts = ["test:diff", "test:watch", "test:affected", "test:full"]
            secondary_runners.extend(
                collect_secondary_polyglot_runners(
                    ws, cargo_path, cargo_type, pyproject_file, make_file, False, False
                )
            )
        elif make_file:
            manifest_type = "Makefile"
            manifest_path = make_file
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
            has_dom_testing_library=has_dom_testing_library,
            vrt_status=vrt_status,
            gaps=gaps,
            secondary_runners=secondary_runners,
            vrt_pixel_diff=vrt_pixel_diff,
            a11y_axe=a11y_axe,
            all_scripts=all_scripts,
            nested_manifests=nested_manifests,
        )

    def plan_mutations(self, audit: TestAuditReport) -> List[FileMutation]:
        """Plans non-destructive file mutations with unified diff previews."""
        mutations: List[FileMutation] = []
        ws = self.workspace_root

        if audit.manifest_type == "package.json" and audit.manifest_path and audit.manifest_path.is_file():
            original_text = audit.manifest_path.read_text(encoding="utf-8")
            try:
                data, indent, trailing_newline = read_json_formatting(audit.manifest_path)
                raw_scripts = data.get("scripts", {})
                updated_scripts = dict(raw_scripts) if isinstance(raw_scripts, dict) else {}
                scripts_to_inject = build_node_scripts_to_inject(
                    audit.test_framework, audit.package_manager, audit.is_monorepo, updated_scripts
                )
                mutated = False
                for name, cmd in scripts_to_inject.items():
                    if name not in updated_scripts:
                        updated_scripts[name] = cmd
                        mutated = True

                if mutated:
                    data["scripts"] = updated_scripts
                    proposed_text = format_json_with_style(data, indent, trailing_newline)
                    diff = self._generate_unified_diff(audit.manifest_path, original_text, proposed_text)
                    mutations.append(
                        FileMutation(
                            target_path=audit.manifest_path,
                            original_content=original_text,
                            proposed_content=proposed_text,
                            unified_diff=diff,
                            description=f"Inject standardized diff-aware test scripts into {audit.manifest_path.name}",
                        )
                    )
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        elif audit.manifest_type in ("pyproject.toml", "Makefile"):
            make_file = ws / "Makefile"
            if make_file.is_file():
                orig_make = make_file.read_text(encoding="utf-8")
                py_caps = detect_python_runner_caps(ws)
                addition = (
                    "\n# Added by AGYIS-HARNESS (psl-test-harmonize)\n"
                    ".PHONY: test:diff test:watch test:affected test:full\n\n"
                    f"test:diff:\n\t{py_caps['diff_command']}\n\n"
                    f"test:watch:\n\t{py_caps['watch_command']}\n\n"
                    f"test:affected:\n\t{py_caps['affected_command']}\n\n"
                    f"test:full:\n\t{py_caps['full_command']}\n"
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
        patch_path.write_text("\n".join(m.unified_diff for m in mutations if m.unified_diff), encoding="utf-8")
        return patch_path

    def build_test_manifest(
        self,
        audit: TestAuditReport,
        backup_patch: Optional[Path] = None,
        assume_scripts_injected: bool = True,
    ) -> Dict[str, Any]:
        """Builds conforming .agyis/test_manifest.json structure."""
        now_iso = datetime.now(timezone.utc).isoformat()
        pm = audit.package_manager
        frm = audit.test_framework
        py_caps = detect_python_runner_caps(self.workspace_root)

        pkg_cmd: Optional[str] = None
        watch_cmd: Optional[str] = None
        if audit.manifest_type == "package.json":
            diff_cmd, affected_cmd, pkg_cmd, full_cmd, watch_cmd = resolve_node_manifest_commands(
                pm, frm, audit.is_monorepo, audit.all_scripts, assume_scripts_injected
            )
        elif audit.manifest_type and "Cargo.toml" in audit.manifest_type:
            manifest_flag = f" --manifest-path {audit.manifest_type}" if audit.manifest_type != "Cargo.toml" else ""
            diff_cmd = f"cargo test{manifest_flag}"
            affected_cmd = diff_cmd
            pkg_cmd = f"cargo test{manifest_flag} --package" if audit.is_monorepo else diff_cmd
            full_cmd = f"cargo test{manifest_flag} --workspace" if audit.is_monorepo else diff_cmd
            watch_cmd = f"cargo watch -x test{manifest_flag}"
        elif audit.manifest_type == "Makefile":
            make_target_path = audit.manifest_path or (
                self.workspace_root / "Makefile"
                if (self.workspace_root / "Makefile").is_file()
                else self.workspace_root / "makefile"
            )
            diff_cmd, affected_cmd, pkg_cmd, full_cmd, watch_cmd = resolve_makefile_manifest_commands(
                make_target_path,
                audit.is_monorepo,
                assume_scripts_injected,
            )
        else:
            diff_cmd = py_caps["diff_command"]
            affected_cmd = py_caps["affected_command"]
            pkg_cmd = py_caps["pkg_command"] if audit.is_monorepo else None
            full_cmd = py_caps["full_command"]
            watch_cmd = py_caps["watch_command"]

        backup_patch_str = None
        if backup_patch:
            try:
                backup_patch_str = str(backup_patch.relative_to(self.workspace_root))
            except ValueError:
                backup_patch_str = str(backup_patch)

        detected_frontend = audit.detected_role in ("frontend", "fullstack")
        anti_synthetic_score = (
            ("passing" if audit.ui_mounting_status == "optimal" else "warning")
            if detected_frontend
            else "not_applicable"
        )
        scripts_map: Dict[str, str] = {
            "test:diff": diff_cmd,
            "test:affected": affected_cmd,
            "test:full": full_cmd,
        }
        if watch_cmd:
            scripts_map["test:watch"] = watch_cmd
        if audit.is_monorepo and pkg_cmd:
            scripts_map["test:pkg"] = pkg_cmd

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
            "nested_manifests": audit.nested_manifests,
            "backup_patch": backup_patch_str,
            "tiers": {
                "tier_1a_diff": {
                    "name": "test:diff",
                    "command": diff_cmd,
                    "description": "Diff-targeted immediate test execution (<1.0s) for active turn",
                    "supported": True,
                    "native_support": frm in ("vitest", "jest", "turbo"),
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
                "detected_frontend": detected_frontend,
                "environment": "happy-dom" if audit.ui_mounting_status == "optimal" else None,
                "has_dom_testing_library": audit.has_dom_testing_library,
                "vrt_pixel_diff": audit.vrt_pixel_diff,
                "a11y_axe": audit.a11y_axe,
                "anti_synthetic_score": anti_synthetic_score,
            },
            "scripts": scripts_map,
        }

        runners: Dict[str, Any] = {}
        if audit.manifest_type:
            primary_key = (
                "node"
                if audit.manifest_type == "package.json"
                else ("cargo" if "Cargo" in audit.manifest_type else ("pytest" if "pyproject" in audit.manifest_type else "make"))
            )
            runners[primary_key] = {
                "manifest": str(audit.manifest_path.relative_to(self.workspace_root)) if audit.manifest_path else audit.manifest_type,
                "framework": frm,
                "package_manager": pm,
                "diff": diff_cmd,
                "affected": affected_cmd,
                "full": full_cmd,
                "watch": watch_cmd,
            }

        runners.update(
            build_secondary_runners_map(
                self.workspace_root,
                audit.secondary_runners,
                py_caps,
                assume_scripts_injected=assume_scripts_injected,
            )
        )
        manifest["runners"] = runners if runners else None
        manifest["secondary_runners"] = audit.secondary_runners
        return manifest

    def _generate_unified_diff(self, path: Path, original: str, updated: str) -> str:
        """Computes clean unified diff between original and updated file content."""
        try:
            rel = path.relative_to(self.workspace_root).as_posix()
        except ValueError:
            rel = path.name
        return "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )


def harmonize_test_runners(
    workspace_dir: Optional[Union[Path, str]] = None,
    dry_run: bool = True,
    apply: bool = False,
    backup: bool = True,
    backup_dir: Optional[Path] = None,
    mutate_package_json: bool = True,
    write_manifest: Optional[bool] = None,
) -> HarmonizeTestResult:
    """
    Main orchestration entrypoint for test runner harmonization.
    Defaults to non-destructive dry-run preview unless apply=True.
    """
    ws = Path(workspace_dir or Path.cwd()).resolve()
    harmonizer = TestHarmonizer(ws)
    audit = harmonizer.audit()
    all_mutations = harmonizer.plan_mutations(audit)
    mutations = [
        m for m in all_mutations
        if mutate_package_json or m.target_path.name.lower() not in ("package.json", "makefile")
    ]

    is_dry_run = not apply and dry_run
    should_write_manifest = (not is_dry_run) if write_manifest is None else bool(write_manifest and not is_dry_run)
    manifest_path = ws / ".agyis" / "test_manifest.json"
    assume_injected = mutate_package_json

    if is_dry_run:
        manifest_data = harmonizer.build_test_manifest(
            audit, backup_patch=None, assume_scripts_injected=assume_injected
        )
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

    backup_patch_path: Optional[Path] = None
    if backup and mutations:
        backup_patch_path = harmonizer.create_backup_patch(mutations, backup_dir=backup_dir)

    for mutation in mutations:
        mutation.target_path.parent.mkdir(parents=True, exist_ok=True)
        mutation.target_path.write_text(mutation.proposed_content, encoding="utf-8")

    manifest_data = harmonizer.build_test_manifest(
        audit, backup_patch=backup_patch_path, assume_scripts_injected=assume_injected
    )
    if should_write_manifest:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

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
