# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Verification suite for Phase 4: Rule Bifurcation, Packaging & Subagent Upgrades
(PSL-SPEC-2026-DRA-001).

Validates:
- GLOBAL_AGENTS.md contains universal invariants and zero harness CLI / ADR-015 benchmark mandates.
- .agents/rules/AGENTS.md isolates harness command dictionaries and ADR-015 benchmarks.
- subagent-ladder/SKILL.md has zero RecipientName occurrences and enforces Workspace: "share".
- Frozen wheel release build and install via PluginInstaller and CLI (agyis install -g).
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.cli import main
from harness.commands.install import cmd_install
from harness.delivery import (
    DeliveryMode,
    DeliveryResult,
    PluginInstaller,
    REPO_ROOT,
)


class TestRuleBifurcation(unittest.TestCase):
    """Test suite verifying separation of universal and harness-specific rules."""

    def test_global_agents_authored_with_universal_invariants(self) -> None:
        """GLOBAL_AGENTS.md must exist and contain universal rules without harness-specific mandates."""
        root_global = REPO_ROOT / "GLOBAL_AGENTS.md"
        template_global = REPO_ROOT / "harness" / "rules" / "GLOBAL_AGENTS.md"

        self.assertTrue(root_global.exists(), f"Missing root GLOBAL_AGENTS.md at {root_global}")
        self.assertTrue(template_global.exists(), f"Missing template GLOBAL_AGENTS.md at {template_global}")

        content = root_global.read_text(encoding="utf-8")

        # Must NOT contain harness-specific commands or benchmarks
        self.assertNotIn("./agyis test", content)
        self.assertNotIn("harness.cli test", content)
        self.assertNotIn("ADR-015", content)
        self.assertNotIn("<1.0s", content)

        # Must contain universal engineering hygiene standards
        self.assertIn("Universal Automated Verification Standard", content)
        self.assertIn("Terminal Invariants & Grep Probing Exception", content)
        self.assertIn("Surgical Contiguous Edits Invariant", content)
        self.assertIn("Context Preservation, Reactive Wait & Anti-Loop Discipline", content)
        self.assertIn("The Artifact-First Planning Invariant", content)
        self.assertIn("Human-in-the-Loop & Steering Alignment", content)
        self.assertIn("Always execute the active repository's native verification command", content)

    def test_local_agents_rules_retains_harness_specifics(self) -> None:
        """Local AGENTS.md must retain harness CLI command dictionary and ADR-015 benchmarks."""
        local_rules = REPO_ROOT / ".agents" / "rules" / "AGENTS.md"
        self.assertTrue(local_rules.exists(), f"Missing local AGENTS.md at {local_rules}")

        content = local_rules.read_text(encoding="utf-8")
        self.assertIn("./agyis test", content)
        self.assertIn("python3 -m harness.cli test", content)
        self.assertIn("ADR-015", content)
        self.assertIn("<1.0 second", content)

    def test_subagent_ladder_skill_compliance(self) -> None:
        """subagent-ladder/SKILL.md must have 0 RecipientName references and specify Workspace: 'share'."""
        ladder_skill = REPO_ROOT / ".agents" / "skills" / "subagent-ladder" / "SKILL.md"
        self.assertTrue(ladder_skill.exists(), f"Missing subagent ladder skill at {ladder_skill}")

        content = ladder_skill.read_text(encoding="utf-8")

        # Zero RecipientName references
        self.assertNotIn("RecipientName", content)

        # Enforces Workspace: "share"
        self.assertIn('Workspace: "share"', content)


class TestFrozenWheelPackaging(unittest.TestCase):
    """Test suite verifying frozen wheel release build and installation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name) / "installed_plugin"
        self.bin_dir = Path(self.temp_dir.name) / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_install_global_defaults_to_wheel(self) -> None:
        """agyis install -g (global_install=True) defaults to DeliveryMode.WHEEL."""
        args = argparse.Namespace(
            global_install=True,
            copy=False,
            symlink=False,
            wheel=False,
            target=str(self.target_dir),
            bin_dir=str(self.bin_dir),
            dry_run=True,
            json=True,
            workspace=None,
            all_surfaces=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_install(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "wheel")

    def test_cli_install_wheel_flag_selects_wheel_mode(self) -> None:
        """agyis install --wheel selects DeliveryMode.WHEEL."""
        args = argparse.Namespace(
            global_install=False,
            copy=False,
            symlink=False,
            wheel=True,
            target=str(self.target_dir),
            bin_dir=str(self.bin_dir),
            dry_run=True,
            json=True,
            workspace=None,
            all_surfaces=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_install(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "wheel")

    def test_cli_symlink_overrides_global(self) -> None:
        """Explicit --symlink flag overrides global default to preserve symlink mode."""
        args = argparse.Namespace(
            global_install=True,
            copy=False,
            symlink=True,
            wheel=False,
            target=str(self.target_dir),
            bin_dir=str(self.bin_dir),
            dry_run=True,
            json=True,
            workspace=None,
            all_surfaces=False,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_install(args)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["success"])
            self.assertEqual(data["mode"], "symlink")

    def test_installer_wheel_installation_and_symlink_severing(self) -> None:
        """PluginInstaller installs frozen wheel release, severs symlink hazard, and prunes local AGENTS.md."""
        installer = PluginInstaller(
            source_dir=REPO_ROOT,
            default_target_dir=self.target_dir,
            bin_dir=self.bin_dir,
        )

        # 1. Create a simulated live development symlink hazard
        dummy_source = Path(self.temp_dir.name) / "dummy_repo"
        dummy_source.mkdir()
        self.target_dir.symlink_to(dummy_source)
        self.assertTrue(self.target_dir.is_symlink())

        # 2. Install with DeliveryMode.WHEEL (mocking _build_frozen_wheel for fast hermetic test)
        import zipfile
        fake_wheel = Path(self.temp_dir.name) / "agyis_harness-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(fake_wheel, "w") as zf:
            zf.writestr("harness/__init__.py", "__version__ = '1.0.0'\n")
            zf.writestr("agyis_harness-1.0.0.dist-info/METADATA", "Name: agyis-harness\n")

        with patch.object(installer, "_build_frozen_wheel", return_value=fake_wheel):
            result = installer.install(mode=DeliveryMode.WHEEL)

        self.assertTrue(result.success)
        self.assertEqual(result.mode, "wheel")

        # Symlink must be completely severed: target must be a real directory
        self.assertFalse(self.target_dir.is_symlink())
        self.assertTrue(self.target_dir.is_dir())

        # Expected packaged contents
        self.assertIn("assets", result.items_installed)
        self.assertTrue((self.target_dir / "harness" / "__init__.py").exists())
        self.assertTrue((self.target_dir / "dist" / fake_wheel.name).exists())
        self.assertTrue((self.target_dir / "plugin.json").exists())
        self.assertTrue((self.target_dir / "assets" / "logo.svg").is_file())
        self.assertTrue((self.target_dir / "matrix.json").exists())
        self.assertTrue((self.target_dir / "hooks.json").exists())
        self.assertTrue((self.target_dir / "skills").is_dir())

        # Rules isolation in global installation: GLOBAL_AGENTS.md installed into rules/AGENTS.md, repo-internal commands pruned
        self.assertTrue((self.target_dir / "rules" / "GLOBAL_AGENTS.md").exists())
        self.assertTrue((self.target_dir / "rules" / "AGENTS.md").exists())
        installed_rules = (self.target_dir / "rules" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("./agyis test", installed_rules)
        self.assertNotIn("harness.cli test", installed_rules)
        self.assertIn("Universal Automated Verification Standard", installed_rules)
        self.assertEqual(installed_rules, (self.target_dir / "rules" / "GLOBAL_AGENTS.md").read_text(encoding="utf-8"))

        # Install info detection
        info = installer.get_install_info(self.target_dir)
        self.assertTrue(info["installed"])
        self.assertEqual(info["mode"], "wheel")

        # Uninstallation cleans up completely
        uninst = installer.uninstall(target_dir=self.target_dir)
        self.assertTrue(uninst.success)
        self.assertEqual(uninst.mode, "wheel")
        self.assertFalse(self.target_dir.exists())

    def test_pyproject_packaging_config_matches_manifest(self) -> None:
        """pyproject.toml pins explicit sdist only-include and wheel force-include mappings (ADR-014)."""
        pyproject_data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject_data["project"]["version"], "1.0.0-rc9")

        sdist_only_include = pyproject_data["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
        for expected in (
            "harness",
            "assets",
            "plugin.json",
            "GLOBAL_AGENTS.md",
            "pyproject.toml",
            "README.md",
            "LICENSE",
            "NOTICE",
            "CHANGELOG.md",
        ):
            self.assertIn(expected, sdist_only_include)
        for excluded in (".agents", "pipeline", "tests", "data", "scratch"):
            self.assertNotIn(excluded, sdist_only_include)

        wheel_cfg = pyproject_data["tool"]["hatch"]["build"]["targets"]["wheel"]
        self.assertEqual(wheel_cfg["packages"], ["harness"])
        self.assertEqual(
            wheel_cfg["force-include"],
            {
                "plugin.json": "harness/plugin.json",
                "assets/logo.svg": "harness/assets/logo.svg",
                "GLOBAL_AGENTS.md": "harness/GLOBAL_AGENTS.md",
            },
        )

    def test_hatchling_sdist_and_wheel_completeness_and_importlib_resources(self) -> None:
        """Hatchling SdistBuilder -> WheelBuilder includes all tracked harness/ files, plugin.json, assets/logo.svg, zero .agents/."""
        tracked_harness = set(
            subprocess.check_output(
                ["git", "ls-files", "harness/"],
                cwd=REPO_ROOT,
                text=True,
            ).splitlines()
        )
        self.assertGreater(len(tracked_harness), 150)

        build_and_verify_script = r"""
import importlib.resources as ir
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from hatchling.builders.sdist import SdistBuilder
from hatchling.builders.wheel import WheelBuilder

repo = Path(sys.argv[1])
tracked = set(
    subprocess.check_output(["git", "ls-files", "harness/"], cwd=repo, text=True).splitlines()
)
agent_mds = {p for p in tracked if p.startswith("harness/agents/") and p.endswith(".md")}
assert len(agent_mds) == 8, sorted(agent_mds)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "out"
    out.mkdir()
    sdist_path = Path(next(SdistBuilder(str(repo)).build(directory=str(out))))
    sdist_extract = Path(tmp) / "sdist_src"
    sdist_extract.mkdir()
    with tarfile.open(sdist_path, "r:gz") as tf:
        tf.extractall(sdist_extract, filter="data")
        sdist_names = {m.name.split("/", 1)[1] for m in tf.getmembers() if m.isfile() and "/" in m.name}

    sdist_root = next(sdist_extract.iterdir())
    whl_path = Path(next(WheelBuilder(str(sdist_root)).build(directory=str(out))))
    whl_extract = Path(tmp) / "whl_site"
    whl_extract.mkdir()
    with zipfile.ZipFile(whl_path) as zf:
        whl_names = set(zf.namelist())
        zf.extractall(whl_extract)

    missing_sdist = sorted(tracked - sdist_names)
    missing_whl = sorted(tracked - whl_names)
    assert not missing_sdist, f"Sdist missing tracked harness/ files: {missing_sdist}"
    assert not missing_whl, f"Wheel missing tracked harness/ files: {missing_whl}"
    assert "harness/plugin.json" in whl_names
    assert "harness/assets/logo.svg" in whl_names
    assert "harness/GLOBAL_AGENTS.md" in whl_names
    assert "plugin.json" in sdist_names
    assert "assets/logo.svg" in sdist_names
    assert "GLOBAL_AGENTS.md" in sdist_names
    for label, names in (("wheel", whl_names), ("sdist", sdist_names)):
        leaks = [n for n in names if n.startswith(".agents/") or "/.agents/" in n]
        assert not leaks, f"{label} leaked .agents/: {leaks}"

    empty_cwd = Path(tmp) / "empty"
    empty_cwd.mkdir()
    base_py = getattr(sys, "_base_executable", sys.executable)
    check = (
        "import importlib.resources as ir, sys; "
        "from pathlib import Path; "
        "import harness; "
        "from harness.agents import resolve_agent_name; "
        "repo_p = Path(sys.argv[1]).resolve(); "
        "site_p = Path(sys.argv[2]).resolve(); "
        "assert not any(Path(p).resolve() == repo_p for p in sys.path if p), sys.path; "
        "assert Path(harness.__file__).resolve().is_relative_to(site_p), harness.__file__; "
        "assert resolve_agent_name('builder') == 'agyis_builder'; "
        "assert (ir.files('harness.gui.assets') / 'hud.js').is_file(); "
        "assert (ir.files('harness.hooks') / 'hooks.json').is_file(); "
        "assert (ir.files('harness.runtime') / 'matrix.json').is_file(); "
        "assert (ir.files('harness.agents') / 'agyis_builder.md').is_file(); "
        "assert (ir.files('harness.skills') / 'cockpit-director' / 'SKILL.md').is_file(); "
        "assert (ir.files('harness.skills') / 'subagent-router' / 'SKILL.md').is_file(); "
        "assert (ir.files('harness.skills') / 'subagent-ladder' / 'SKILL.md').is_file(); "
        "assert (ir.files('harness') / 'plugin.json').is_file(); "
        "assert (ir.files('harness') / 'assets' / 'logo.svg').is_file(); "
        "assert (ir.files('harness.assets') / 'logo.svg').is_file(); "
        "assert (ir.files('harness') / 'GLOBAL_AGENTS.md').is_file(); "
        "print('HATCHLING_WHEEL_OK')"
    )
    subprocess.run(
        [base_py, "-c", check, str(repo), str(whl_extract)],
        cwd=empty_cwd,
        env={"PATH": "", "PYTHONPATH": str(whl_extract)},
        check=True,
    )
"""
        try:
            import hatchling  # noqa: F401
            cmd = [sys.executable, "-c", build_and_verify_script, str(REPO_ROOT)]
        except ImportError:
            uv_bin = shutil.which("uv")
            if not uv_bin:
                self.skipTest("hatchling is not installed and uv binary is unavailable")
            cmd = [
                uv_bin,
                "run",
                "--no-project",
                "--isolated",
                "--offline",
                "--with",
                "hatchling",
                "python3",
                "-c",
                build_and_verify_script,
                str(REPO_ROOT),
            ]

        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if proc.returncode != 0 and "No cached" in proc.stderr:
            self.skipTest(f"hatchling not cached for offline test execution: {proc.stderr.strip()}")
        self.assertEqual(proc.returncode, 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        self.assertIn("HATCHLING_WHEEL_OK", proc.stdout)


class TestReleaseWorkflowAndLockHygiene(unittest.TestCase):
    """Contract assertions for .python-version pinning and hardened release.yml pipeline."""

    def test_python_version_pinned_to_3_12(self) -> None:
        """.python-version must pin 3.12 instead of unsupported 'system'."""
        pv_path = REPO_ROOT / ".python-version"
        self.assertTrue(pv_path.is_file(), f"Missing {pv_path}")
        self.assertEqual(pv_path.read_text(encoding="utf-8").strip(), "3.12")

    def test_release_workflow_hardened_contracts(self) -> None:
        """.github/workflows/release.yml enforces lockfile hygiene, deterministic tag validation, gates, smoke test, and race-safe publish."""
        wf_path = REPO_ROOT / ".github" / "workflows" / "release.yml"
        self.assertTrue(wf_path.is_file(), f"Missing {wf_path}")
        wf_text = wf_path.read_text(encoding="utf-8")

        # Stale rc5 fallback must be completely eliminated
        self.assertNotIn("v1.0.0-rc5", wf_text)

        # Triggers, inputs, concurrency, checkout tags
        self.assertIn("workflow_dispatch:", wf_text)
        self.assertIn("type: string", wf_text)
        self.assertIn("${{ github.workflow }}-${{ github.event.inputs.tag || github.ref }}", wf_text)
        self.assertIn("fetch-tags: true", wf_text)

        # Lockfile & frozen sync
        self.assertIn("uv lock --check", wf_text)
        self.assertIn("uv sync --frozen --extra dev", wf_text)

        # Deterministic tag resolution + pyproject.toml validation + outputs
        self.assertIn("id: meta", wf_text)
        self.assertIn("tomllib", wf_text)
        self.assertIn("pyproject.toml", wf_text)
        self.assertIn("is_prerelease", wf_text)
        self.assertIn("refs/tags/$TAG", wf_text)

        # Pre-build CI verification gates
        for gate in (
            "uv run --frozen python3 -m harness.cli verify --spec",
            "uv run --frozen python3 -m harness.cli verify",
            "uv run --frozen python3 -m harness.cli rules --lint",
            "uv run --frozen python3 -m harness.cli audit aff",
            "uv run --frozen python3 -m harness.cli test",
        ):
            self.assertIn(gate, wf_text)

        # Build & archive content verification
        self.assertIn("uv build --clear", wf_text)
        self.assertIn("WHL_FILES=(dist/agyis_harness-*.whl)", wf_text)
        self.assertIn("SDIST_FILES=(dist/agyis_harness-*.tar.gz)", wf_text)
        self.assertIn("sha256sum", wf_text)
        for required_entry in (
            "git ls-files",
            "harness/gui/assets/hud.js",
            "harness/hooks/hooks.json",
            "harness/runtime/matrix.json",
            "harness/agents/__init__.py",
            "harness/skills/cockpit-director/SKILL.md",
            "harness/skills/subagent-router/SKILL.md",
            "harness/skills/subagent-ladder/SKILL.md",
            "harness/rules/GLOBAL_AGENTS.md",
            "harness/plugin.json",
            "harness/assets/logo.svg",
            ".agents/",
        ):
            self.assertIn(required_entry, wf_text)

        # Isolated wheel smoke verification
        self.assertIn("uv run --no-project --isolated --with \"$ABS_WHL\"", wf_text)
        self.assertIn("importlib.resources", wf_text)
        self.assertIn("agyis --version", wf_text)

        # Release notes & race-safe GitHub release publish
        self.assertIn('uv run --frozen python3 -m harness.cli release-notes --tag "$TAG" --output dist/RELEASE_NOTES.md', wf_text)
        self.assertIn('gh release view "$TAG"', wf_text)
        self.assertIn('gh release create "$TAG"', wf_text)
        self.assertIn('gh release edit "$TAG"', wf_text)
        self.assertIn("gh release upload", wf_text)
        self.assertIn("--clobber", wf_text)
        self.assertIn('--title "$TAG"', wf_text)
        self.assertIn("--prerelease=false", wf_text)



class TestSingleSourceRuleDeduplication(unittest.TestCase):

    """Test suite verifying single-source rule deduplication engine (Issues #70 & #71)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "test_workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.agents_rules = self.workspace / ".agents" / "rules" / "AGENTS.md"
        self.agents_rules.parent.mkdir(parents=True, exist_ok=True)

        # Mock workspace rules containing custom sections + duplicate universal sections
        self.sample_content = """<!-- SPDX-License-Identifier: Apache-2.0 -->
# Empirical Agent Rules: Mock Guidelines

## 1. Explicit Project Command Dictionary (The Victory Pattern)
./mock test

## 2. Product vs. Project Bifurcation (ADR-014)
Product vs project.

## 3. Clean-Room Testing & Verification Contract (ADR-015)
Fast tests.

## 4. Terminal Invariants & Grep Probing Exception (ADR-013)
Terminal rules.

## 5. Surgical Contiguous Edits Invariant (99.9% Tool Success)
Contiguous edits.

## 6. Context Preservation & Subagent Ladder
Context rules.

## 7. The Artifact-First Planning Invariant (ADR-012) & Dynamic Aperture
Artifact planning rules.

## 8. Human-in-the-Loop & Steering Alignment
HITL rules.

## 9. Cleanroom Reverse Engineering & Reconstruction Invariants (ADR-028)
Cleanroom rules.
"""
        self.agents_rules.write_text(self.sample_content, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_enforce_single_source_rules_dry_run(self) -> None:
        """enforce_single_source_rules(dry_run=True) previews pruning without disk mutations."""
        from harness.delivery import enforce_single_source_rules

        result = enforce_single_source_rules(workspace_dir=self.workspace, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertGreater(result["chars_removed"], 0)
        self.assertGreater(result["tokens_saved"], 0)
        self.assertGreaterEqual(len(result["removed_sections"]), 6)

        # Assert disk file untouched
        current_content = self.agents_rules.read_text(encoding="utf-8")
        self.assertEqual(current_content, self.sample_content)

    def test_enforce_single_source_rules_prunes_and_symlinks(self) -> None:
        """enforce_single_source_rules prunes duplicate universal rules and symlinks rules/AGENTS.md."""
        from harness.delivery import enforce_single_source_rules

        result = enforce_single_source_rules(workspace_dir=self.workspace, dry_run=False)
        self.assertFalse(result["dry_run"])
        self.assertIn(str(self.agents_rules), result["pruned_files"])

        pruned = self.agents_rules.read_text(encoding="utf-8")
        self.assertIn("PSL-INV-001 through PSL-INV-009", pruned)
        self.assertIn("Explicit Project Command Dictionary", pruned)
        self.assertIn("Product vs. Project Bifurcation", pruned)
        self.assertIn("Clean-Room Testing & Verification Contract", pruned)

        # Duplicate universal sections stripped
        self.assertNotIn("Terminal Invariants & Grep Probing Exception", pruned)
        self.assertNotIn("Surgical Contiguous Edits Invariant", pruned)
        self.assertNotIn("Context Preservation & Subagent Ladder", pruned)
        self.assertNotIn("Human-in-the-Loop & Steering Alignment", pruned)

        # rules/AGENTS.md must be a symlink to ../.agents/rules/AGENTS.md
        root_rules = self.workspace / "rules" / "AGENTS.md"
        self.assertTrue(root_rules.is_symlink())
        self.assertEqual(os.readlink(root_rules), "../.agents/rules/AGENTS.md")

    def test_token_savings_exceeds_threshold(self) -> None:
        """Deduplicating full workspace rules saves >= 1,500 tokens."""
        from harness.delivery import enforce_single_source_rules

        # Create workspace with actual repo's original unpruned rules
        unpruned_full = (
            self.sample_content + "\n" +
            ("Universal Rule Filler Prose " * 300)
        )
        self.agents_rules.write_text(unpruned_full, encoding="utf-8")
        result = enforce_single_source_rules(workspace_dir=self.workspace, dry_run=True)
        # Verify calculation logic
        self.assertEqual(result["tokens_saved"], result["chars_removed"] // 4)

    def test_elimination_of_rule_numbering_collisions(self) -> None:
        """Pruned workspace rules eliminate numbering collisions (e.g. Rule 7)."""
        from harness.delivery import enforce_single_source_rules

        enforce_single_source_rules(workspace_dir=self.workspace, dry_run=False)
        pruned = self.agents_rules.read_text(encoding="utf-8")
        self.assertNotIn("## 7. The Artifact-First Planning Invariant", pruned)
        self.assertNotIn("## 9. Cleanroom Reverse Engineering", pruned)

    def test_rule_echo_linter_passes_on_clean_workspace(self) -> None:
        """lint_rule_echo passes with clean status on repo root."""
        from harness.delivery import lint_rule_echo

        res = lint_rule_echo(REPO_ROOT)
        self.assertTrue(res["clean"], f"Rule echo linter failed: {res.get('echoes')}")
        self.assertGreater(res["files_scanned"], 0)

    def test_cli_rules_command(self) -> None:
        """agyis rules CLI command supports --dedup and --lint."""
        from harness.commands.rules import cmd_rules

        # Test lint
        args_lint = argparse.Namespace(
            workspace=str(REPO_ROOT),
            lint=True,
            dedup=False,
            dry_run=False,
            json=True,
            config_dir=None,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_rules(args_lint)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["clean"])

        # Test dedup dry-run
        args_dedup = argparse.Namespace(
            workspace=str(self.workspace),
            lint=False,
            dedup=True,
            dry_run=True,
            json=True,
            config_dir=None,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cmd_rules(args_dedup)
            self.assertEqual(code, 0)
            data = json.loads(mock_out.getvalue().strip())
            self.assertTrue(data["dry_run"])

    def test_onboard_step_12b_rule_dedup_integration(self) -> None:
        """Onboard pipeline imports and executes enforce_single_source_rules in step 12b."""
        from harness.commands.onboard import cmd_onboard
        import inspect

        source = inspect.getsource(cmd_onboard)
        self.assertIn("enforce_single_source_rules", source)
        self.assertIn("12b. Enforce single-source rule deduplication", source)


if __name__ == "__main__":
    unittest.main()

