# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for v1.1.2 Track 3 deliverables:
- cmd_onboard --dry-run preserves real current_branch while exposing created_branch/planned_branch
- cmd_onboard auto-writes .agyis/test_manifest.json without mutating package.json
- cmd_onboard surfaces engine_check warnings and fix hints on Node/pnpm mismatch
- cmd_onboard --ensure-project registers Antigravity projects in isolated config_dir
- cmd_onboard inherits experimental_rea: true from .agyis/config.json
- run_onboard_verification refuses npx network downloads via --no-install
- cmd_verify and is_manifest_verified support .agents/ledger/obligations.json
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from harness.cleanroom.obligation import ReviewedObligation
from harness.cli import main as cli_main
from harness.commands.onboard import cmd_onboard
from harness.commands.onboard_gates import run_onboard_verification
from harness.commands.verify import cmd_verify
from harness.delivery import verify_zero_git_pollution
from harness.delivery.projects import list_registered_projects
from harness.hooks.fence_classifiers import is_manifest_verified, resolve_cleanroom_ledger_path


def _build_typed_rea_ledger(disposition: str = "active") -> dict:
    """Build a valid REA 6.9.0 typed obligation ledger fixture."""
    bin_sha = hashlib.sha256(b"track3-sample-binary").hexdigest()
    ev_id = f"ev_{hashlib.sha256(b'track3-evidence-1').hexdigest()}"
    owner_sha = hashlib.sha256(b"track3-owner-module").hexdigest()
    ob_id = "OBL-01"
    ob = ReviewedObligation(
        obligation_id=ob_id,
        disposition=disposition,
        title="Cleanroom obligation OBL-01",
        target={
            "artifact_sha256": bin_sha,
            "application_node_id": None,
            "semantic_node_id": None,
            "location": "src/mod_1.py:fn_1",
        },
        review_evidence_ids=[ev_id],
    ).to_dict()

    return {
        "evidence_bundle": {
            "providers": [{"id": "rea", "name": "rea-agents", "version": "6.9.0"}],
            "records": [
                {
                    "evidence_id": ev_id,
                    "provider": {"id": "rea", "name": "rea-agents", "version": "6.9.0"},
                    "subject": {
                        "name": "sample.bin",
                        "digest": {"sha256": bin_sha},
                        "format": "elf",
                        "local_path": "sample.bin",
                        "architecture": "x86_64",
                    },
                    "predicate_type": "decompile",
                    "operation": "procedure_pseudo_code",
                    "confidence": "observed",
                    "authority": "shipped-artifact",
                }
            ],
            "artifacts": [{"digest": {"sha256": bin_sha}, "format": "elf"}],
            "captures": [],
            "environments": [],
            "scenarios": [],
            "unknowns": [],
        },
        "reviewed_obligations": [ob],
        "manifest": {
            "bindings": [
                {
                    "obligation_id": ob_id,
                    "owner": {
                        "module_path": "src/mod_1.py",
                        "symbol": "fn_1",
                        "owner_sha256": owner_sha,
                    },
                    "parser_type": None,
                    "original_cases": [
                        {"kind": "positive", "evidence_id": ev_id, "location": "0x1001"}
                    ],
                    "fixtures": [
                        {
                            "fixture_id": "FIX-01",
                            "case_kind": "positive",
                            "authority": "unit",
                            "evidence_ids": [ev_id],
                        }
                    ],
                    "verifier": {
                        "verifier_id": "VER-01",
                        "claim_id": "CLM-01",
                        "command": "python3 -m unittest",
                        "authority": "unit",
                        "status": "pass",
                        "result_evidence_id": ev_id,
                        "enumerated_obligation_ids": [ob_id],
                        "nondeterminism": {
                            "mode": "total-order",
                            "specification": "deterministic single-thread unit check",
                        },
                    },
                }
            ],
            "contradictions": [],
        },
    }


class TestV112OnboardAndVerify(unittest.TestCase):
    """Hermetic verification suite for v1.1.2 Track 3 onboard and verify behavior."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.ws = Path(self._td.name).resolve()
        self.cfg_dir = self.ws / "isolated_cfg"
        self.cfg_dir.mkdir(parents=True, exist_ok=True)
        self._orig_state = os.environ.get("PSL_HARNESS_STATE_DIR")
        self.state_dir = self.ws / ".state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PSL_HARNESS_STATE_DIR"] = str(self.state_dir)

    def tearDown(self) -> None:
        if self._orig_state is None:
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
        else:
            os.environ["PSL_HARNESS_STATE_DIR"] = self._orig_state
        self._td.cleanup()

    def _init_git_repo(self, repo_path: Path, branch: str = "main") -> None:
        repo_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", branch], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_path, check=True)
        (repo_path / "README.md").write_text("# Demo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_onboard_dry_run_preserves_real_current_branch(self) -> None:
        """cmd_onboard --dry-run must report true checked-out current_branch while reporting planned/created_branch."""
        repo = self.ws / "dry-branch-repo"
        self._init_git_repo(repo, branch="main")

        # JSON output check
        with patch("sys.stdout", new_callable=io.StringIO) as out_json:
            code = cmd_onboard(
                repo,
                create_branch="chore/onboard-preview",
                dry_run=True,
                json_output=True,
                config_dir=self.cfg_dir,
            )
        self.assertEqual(code, 0)
        payload = json.loads(out_json.getvalue())
        self.assertEqual(payload["topology"]["current_branch"], "main")
        self.assertEqual(payload["topology"]["pr_head_branch"], "main")
        self.assertEqual(payload["topology"]["planned_branch"], "chore/onboard-preview")
        self.assertEqual(payload["planned_branch"], "chore/onboard-preview")
        self.assertEqual(payload["created_branch"], "chore/onboard-preview")

        # Human output check
        with patch("sys.stdout", new_callable=io.StringIO) as out_txt:
            code_txt = cmd_onboard(
                repo,
                create_branch="chore/onboard-preview",
                dry_run=True,
                json_output=False,
                config_dir=self.cfg_dir,
            )
        self.assertEqual(code_txt, 0)
        txt = out_txt.getvalue()
        self.assertIn("Current branch: main", txt)
        self.assertIn("[dry-run] Would checkout onboarding branch: chore/onboard-preview", txt)

        # Repo HEAD must remain on main
        head_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
        self.assertEqual(head_branch, "main")

    def test_onboard_auto_writes_test_manifest_without_mutating_package_json(self) -> None:
        """cmd_onboard generates .agyis/test_manifest.json (git-excluded) and leaves package.json intact."""
        repo = self.ws / "node-manifest-repo"
        self._init_git_repo(repo, branch="main")
        pkg_original = (
            '{\n'
            '    "name": "app-demo",\n'
            '    "packageManager": "pnpm@10.0.0",\n'
            '    "scripts": {\n'
            '        "test": "vitest run"\n'
            '    },\n'
            '    "devDependencies": {\n'
            '        "vitest": "^2.0.0"\n'
            '    }\n'
            '}\n'
        )
        (repo / "package.json").write_text(pkg_original, encoding="utf-8")
        subprocess.run(["git", "add", "package.json"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "add package.json"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Dry-run must not write .agyis/test_manifest.json
        with patch("sys.stdout", new_callable=io.StringIO) as out_dry:
            code_dry = cmd_onboard(repo, dry_run=True, json_output=True, config_dir=self.cfg_dir)
        self.assertEqual(code_dry, 0)
        dry_data = json.loads(out_dry.getvalue())
        self.assertFalse((repo / ".agyis" / "test_manifest.json").exists())
        self.assertTrue(dry_data["test_manifest"]["planned"])
        self.assertFalse(dry_data["test_manifest"]["generated"])

        # Live run writes .agyis/test_manifest.json without modifying package.json
        with patch("sys.stdout", new_callable=io.StringIO) as out_live:
            code_live = cmd_onboard(repo, dry_run=False, json_output=True, config_dir=self.cfg_dir)
        self.assertEqual(code_live, 0)
        live_data = json.loads(out_live.getvalue())
        manifest_file = repo / ".agyis" / "test_manifest.json"
        self.assertTrue(manifest_file.is_file())
        self.assertEqual((repo / "package.json").read_text(encoding="utf-8"), pkg_original)
        self.assertTrue(live_data["test_manifest"]["generated"])
        self.assertEqual(live_data["test_manifest"]["package_manager"], "pnpm")
        self.assertEqual(live_data["test_manifest"]["framework"], "vitest")

        # .agyis/ must be excluded via .git/info/exclude and git status clean of .agyis/
        st = subprocess.check_output(["git", "status", "--short"], cwd=repo, text=True)
        self.assertNotIn(".agyis/", st)
        self.assertEqual(verify_zero_git_pollution(repo), [])

    def test_onboard_surfaces_engine_check_warning_without_crashing(self) -> None:
        """cmd_onboard surfaces engine_check warnings and fix hints on Node/pnpm mismatch."""
        repo = self.ws / "engine-mismatch-repo"
        self._init_git_repo(repo, branch="main")
        (repo / "package.json").write_text(
            json.dumps({
                "name": "engine-mismatch",
                "engines": {"node": ">=20.0.0", "pnpm": ">=10.0.0"},
                "packageManager": "pnpm@10.0.0",
                "scripts": {"test": "node --test"},
            }),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "package.json"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "add package.json"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        real_run = subprocess.run

        def _fake_run(cmd, *args, **kwargs):
            bin_name = Path(str(cmd[0])).name if cmd else ""
            if len(cmd) == 2 and cmd[1] == "--version":
                if bin_name == "node":
                    return subprocess.CompletedProcess(cmd, 0, stdout="v22.14.0\n", stderr="")
                if bin_name == "pnpm":
                    return subprocess.CompletedProcess(cmd, 0, stdout="9.15.9\n", stderr="")
            return real_run(cmd, *args, **kwargs)

        with patch("harness.runtime.engine_checks.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("harness.runtime.engine_checks.subprocess.run", side_effect=_fake_run), \
             patch("sys.stdout", new_callable=io.StringIO) as out_json:
            code = cmd_onboard(repo, dry_run=True, json_output=True, config_dir=self.cfg_dir)

        self.assertEqual(code, 0)
        data = json.loads(out_json.getvalue())
        self.assertEqual(data["engine_check"]["status"], "ERROR")
        self.assertTrue(any("9.15.9" in iss and ">=10.0.0" in iss for iss in data["engine_check"]["issues"]))
        self.assertIn("corepack enable", data["engine_check"]["fix_hints"])

        with patch("harness.runtime.engine_checks.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("harness.runtime.engine_checks.subprocess.run", side_effect=_fake_run), \
             patch("sys.stdout", new_callable=io.StringIO) as out_txt:
            code_txt = cmd_onboard(repo, dry_run=True, json_output=False, config_dir=self.cfg_dir)

        self.assertEqual(code_txt, 0)
        txt = out_txt.getvalue()
        self.assertIn("Engine Check (ERROR):", txt)
        self.assertIn("corepack enable", txt)

    def test_onboard_ensure_project_registers_in_isolated_config_dir(self) -> None:
        """cmd_onboard --ensure-project registers Antigravity project via CLI and direct call."""
        repo = self.ws / "proj-reg-repo"
        self._init_git_repo(repo, branch="main")

        # 1. Dry-run preview via CLI parser (--ensure-project) must not create project file
        with patch.dict(os.environ, {"AGYIS_CONFIG_DIR": str(self.cfg_dir), "PSL_CONFIG_DIR": str(self.cfg_dir)}), \
             patch("sys.stdout", new_callable=io.StringIO) as out_dry:
            code_dry = cli_main(
                ["onboard", str(repo), "--ensure-project", "--dry-run", "--json"],
                prog="agyis",
            )
        self.assertEqual(code_dry, 0)
        dry_data = json.loads(out_dry.getvalue())
        self.assertEqual(dry_data["project_registry"]["action"], "would_create")
        self.assertEqual(list_registered_projects(config_dir=self.cfg_dir), [])

        # 2. Live run registers canonical project file inside isolated temp config_dir
        with patch("sys.stdout", new_callable=io.StringIO) as out_live:
            code_live = cmd_onboard(
                repo,
                ensure_project=True,
                dry_run=False,
                json_output=True,
                config_dir=self.cfg_dir,
            )
        self.assertEqual(code_live, 0)
        live_data = json.loads(out_live.getvalue())
        self.assertEqual(live_data["project_registry"]["action"], "created")
        proj_file = Path(live_data["project_registry"]["project_file"])
        self.assertTrue(proj_file.is_file())
        self.assertTrue(proj_file.resolve().is_relative_to(self.cfg_dir.resolve()))
        projects = list_registered_projects(config_dir=self.cfg_dir)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], live_data["project_registry"]["project_id"])

        # 3. Re-running is idempotent (already_registered)
        with patch("sys.stdout", new_callable=io.StringIO) as out_again:
            code_again = cmd_onboard(
                repo,
                allow_dirty=True,
                ensure_project=True,
                dry_run=False,
                json_output=False,
                config_dir=self.cfg_dir,
            )
        self.assertEqual(code_again, 0)
        self.assertIn("Project Registry: already registered", out_again.getvalue())
        self.assertEqual(len(list_registered_projects(config_dir=self.cfg_dir)), 1)

    def test_onboard_inherits_experimental_rea_from_workspace_config(self) -> None:
        """cmd_onboard inherits experimental_rea: true from .agyis/config.json in dry-run and live."""
        repo = self.ws / "rea-inherit-repo"
        self._init_git_repo(repo, branch="main")
        (repo / ".agyis").mkdir()
        (repo / ".agyis" / "config.json").write_text(
            json.dumps({"experimental_rea": True}, indent=2) + "\n",
            encoding="utf-8",
        )
        # Keep working tree clean by excluding .agyis/ (as an already-configured repo) or testing both
        (repo / ".git" / "info" / "exclude").write_text(".agyis/\n", encoding="utf-8")

        # Dry-run reports rea=True without running provision_rea_skill or touching AGENTS.md
        with patch("harness.runtime.healing.provision_rea_skill") as mock_prov, \
             patch("sys.stdout", new_callable=io.StringIO) as out_dry:
            code_dry = cmd_onboard(repo, dry_run=True, json_output=True, config_dir=self.cfg_dir)
        self.assertEqual(code_dry, 0)
        dry_data = json.loads(out_dry.getvalue())
        self.assertTrue(dry_data["rea"])
        self.assertTrue(dry_data["experimental_rea"])
        mock_prov.assert_not_called()
        self.assertFalse((repo / "AGENTS.md").exists())

        # Live run passes rea_enabled=True to harmonize_workspace (AGENTS.md keeps agyis verify --spec)
        # and forwards config_dir into provision_workspace_rea
        with patch("harness.runtime.healing.provision_rea_skill") as mock_prov_live, \
             patch("sys.stdout", new_callable=io.StringIO) as out_live:
            code_live = cmd_onboard(repo, dry_run=False, json_output=True, config_dir=self.cfg_dir)
        self.assertEqual(code_live, 0)
        live_data = json.loads(out_live.getvalue())
        self.assertTrue(live_data["rea"])
        mock_prov_live.assert_called_once()
        agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("agyis verify --spec", agents_md)
        self.assertTrue((repo / ".agents" / "ledger").is_dir())

    def test_verify_and_is_manifest_verified_accept_obligations_json(self) -> None:
        """agyis verify and is_manifest_verified support .agents/ledger/obligations.json alongside obligation_ledger.json and manifest.json."""
        # 1. Typed REA ledger written to .agents/ledger/obligations.json
        ws_typed = self.ws / "verify-typed-obligations"
        ledger_dir = ws_typed / ".agents" / "ledger"
        ledger_dir.mkdir(parents=True)
        obligations_file = ledger_dir / "obligations.json"
        obligations_file.write_text(json.dumps(_build_typed_rea_ledger("active"), indent=2), encoding="utf-8")

        self.assertEqual(resolve_cleanroom_ledger_path(ws_typed), obligations_file.resolve())
        self.assertTrue(is_manifest_verified(ws_typed))

        args_typed = argparse.Namespace(workspace=ws_typed, spec=False, json=True, scaffold=False)
        out_typed = io.StringIO()
        with patch("shutil.which", return_value=None), patch("sys.stdout", out_typed):
            code_typed = cmd_verify(args_typed)
        self.assertEqual(code_typed, 0)
        res_typed = json.loads(out_typed.getvalue())
        self.assertEqual(res_typed["status"], "verified")
        self.assertEqual(res_typed["manifest_path"], str(obligations_file.resolve()))
        self.assertTrue(res_typed["manifest_verified"])

        # Blocked disposition inside obligations.json fails verification
        obligations_file.write_text(json.dumps(_build_typed_rea_ledger("blocked"), indent=2), encoding="utf-8")
        self.assertFalse(is_manifest_verified(ws_typed))

        # 2. Legacy manifest format written to .agents/ledger/obligations.json
        ws_legacy = self.ws / "verify-legacy-obligations"
        legacy_dir = ws_legacy / ".agents" / "ledger"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "obligations.json"
        legacy_file.write_text(
            json.dumps({
                "status": "verified",
                "evidence_hash": "b" * 64,
                "obligations": [{"id": "OBL-01", "status": "satisfied"}],
            }),
            encoding="utf-8",
        )
        self.assertTrue(is_manifest_verified(ws_legacy))

        args_legacy = argparse.Namespace(workspace=ws_legacy, spec=False, json=True, scaffold=False)
        out_legacy = io.StringIO()
        with patch("shutil.which", return_value="/usr/bin/rea"), patch("sys.stdout", out_legacy):
            code_legacy = cmd_verify(args_legacy)
        self.assertEqual(code_legacy, 0)
        res_legacy = json.loads(out_legacy.getvalue())
        self.assertEqual(res_legacy["status"], "verified")
        self.assertTrue(res_legacy["manifest_verified"])

        # 3. Priority order: obligation_ledger.json takes precedence over obligations.json & manifest.json
        (legacy_dir / "obligation_ledger.json").write_text("{}", encoding="utf-8")
        self.assertEqual(
            resolve_cleanroom_ledger_path(ws_legacy),
            (legacy_dir / "obligation_ledger.json").resolve(),
        )
        self.assertFalse(is_manifest_verified(ws_legacy))

    def test_onboard_verify_guards_npx_without_network_download(self) -> None:
        """run_onboard_verification injects --no-install on npx commands so --verify never triggers downloads."""
        repo = self.ws / "npx-guard-repo"
        repo.mkdir(parents=True)
        (repo / "package.json").write_text(
            json.dumps({"devDependencies": {"@playwright/test": "^1.50.0"}}),
            encoding="utf-8",
        )

        seen_cmds: list[list[str]] = []
        seen_envs: list[dict] = []

        def _mock_npx(cmd, *args, **kwargs):
            seen_cmds.append(list(cmd))
            seen_envs.append(dict(kwargs.get("env") or {}))
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="npx: could not determine executable to run")

        with patch("harness.commands.onboard_gates.subprocess.run", side_effect=_mock_npx):
            res = run_onboard_verification(repo, dry_run=False)

        self.assertFalse(res["passed"])
        self.assertEqual(res["exit_code"], 1)
        self.assertEqual(seen_cmds, [["npx", "--no-install", "playwright", "test"]])
        self.assertEqual(seen_envs[0].get("NPM_CONFIG_YES"), "false")


if __name__ == "__main__":
    unittest.main()
