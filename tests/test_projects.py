# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for Antigravity project registry (`agyis project`, WS4)."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

from harness.cli import build_parser, main as cli_main
from harness.delivery import (
    ensure_project_registered,
    extract_project_folder_uris,
    list_registered_projects,
    normalize_folder_uri,
)
from harness.delivery.projects import resolve_projects_config_dir


class TestAntigravityProjectRegistry(unittest.TestCase):
    """Contract and CLI tests for `harness.delivery.projects` and `agyis project`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_dir = self.root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._orig_env = {
            key: os.environ.get(key)
            for key in ("AGYIS_CONFIG_DIR", "PSL_CONFIG_DIR", "AGYIS_PLUGINS_DIR", "PSL_PLUGINS_DIR")
        }
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        os.environ.pop("PSL_CONFIG_DIR", None)

    def tearDown(self) -> None:
        for key, prev in self._orig_env.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev
        self.tmp.cleanup()

    def test_config_dir_resolution_precedence(self) -> None:
        explicit = self.root / "explicit_cfg"
        self.assertEqual(resolve_projects_config_dir(explicit), explicit.resolve())
        self.assertEqual(resolve_projects_config_dir(None), self.config_dir.resolve())

        os.environ.pop("AGYIS_CONFIG_DIR", None)
        psl_cfg = self.root / "psl_cfg"
        os.environ["PSL_CONFIG_DIR"] = str(psl_cfg)
        self.assertEqual(resolve_projects_config_dir(None), psl_cfg.resolve())

    def test_normalize_folder_uri_equivalence_and_percent_decoding(self) -> None:
        space_dir = self.root / "My Workspace"
        space_dir.mkdir()

        expected = space_dir.resolve().as_uri() + "/"
        self.assertEqual(normalize_folder_uri(space_dir), expected)
        self.assertEqual(normalize_folder_uri(f"{space_dir}/"), expected)
        self.assertEqual(normalize_folder_uri(space_dir.as_uri()), expected)
        self.assertEqual(normalize_folder_uri(space_dir.as_uri() + "/"), expected)
        self.assertEqual(normalize_folder_uri(f"file://{space_dir.resolve()}"), expected)

        link_dir = self.root / "alias_link"
        link_dir.symlink_to(space_dir)
        self.assertEqual(normalize_folder_uri(link_dir), expected)

        self.assertEqual(
            normalize_folder_uri("vscode-remote://ssh-remote+box/srv/app"),
            "vscode-remote://ssh-remote+box/srv/app/",
        )
        with self.assertRaises(ValueError):
            normalize_folder_uri("   ")

    def test_extract_and_list_projects_handles_legacy_git_multi_and_malformed(self) -> None:
        projects_dir = self.config_dir / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)

        # Bare folderUri shape (0a7e0526 pattern, without trailing slash)
        bare_dir = self.root / "constitution-2026"
        bare_dir.mkdir()
        (projects_dir / "0a7e0526-5229-4bad-8f1d-74ac878e0fb0.json").write_text(
            json.dumps({
                "id": "0a7e0526-5229-4bad-8f1d-74ac878e0fb0",
                "name": "constitution-2026",
                "projectResources": {
                    "resources": [{"folderUri": f"file://{bare_dir.resolve()}"}]
                },
                "settings": {},
                "isWorkspaceOnly": False,
            }),
            encoding="utf-8",
        )

        # Canonical gitFolder + multi-resource shape (8c97fb13 / 23eb585f pattern)
        repo_a = self.root / "repo-a"
        repo_b = self.root / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        multi_payload = {
            "id": "8c97fb13-205e-425f-9570-25c59edba1cd",
            "name": "multi-repo",
            "projectResources": {
                "resources": [
                    {
                        "gitFolder": {
                            "folderUri": f"file://{repo_a.resolve()}/",
                            "defaultBranch": "develop",
                            "allowWrite": True,
                        }
                    },
                    {
                        "gitFolder": {
                            "folderUri": f"file://{repo_b.resolve()}",
                            "defaultBranch": "main",
                        }
                    },
                ]
            },
            "permissionGrants": {"v2Migrated": True},
            "settings": {},
            "isWorkspaceOnly": False,
        }
        (projects_dir / "8c97fb13-205e-425f-9570-25c59edba1cd.json").write_text(
            json.dumps(multi_payload),
            encoding="utf-8",
        )

        # Non-JSON, malformed JSON, and non-object JSON must be skipped gracefully
        (projects_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
        (projects_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
        (projects_dir / "array.json").write_text("[1, 2, 3]", encoding="utf-8")

        extracted = extract_project_folder_uris(multi_payload)
        self.assertEqual(len(extracted), 2)
        self.assertEqual(extract_project_folder_uris({}), [])

        listed = list_registered_projects()
        self.assertEqual(len(listed), 2)
        by_id = {item["id"]: item for item in listed}

        bare_rec = by_id["0a7e0526-5229-4bad-8f1d-74ac878e0fb0"]
        self.assertFalse(bare_rec["is_git_folder"])
        self.assertIsNone(bare_rec["default_branch"])
        self.assertEqual(bare_rec["folder_uris"], [normalize_folder_uri(bare_dir)])

        multi_rec = by_id["8c97fb13-205e-425f-9570-25c59edba1cd"]
        self.assertTrue(multi_rec["is_git_folder"])
        self.assertEqual(multi_rec["default_branch"], "develop")
        self.assertEqual(
            multi_rec["folder_uris"],
            [normalize_folder_uri(repo_a), normalize_folder_uri(repo_b)],
        )

    def test_ensure_project_registered_dedup_dry_run_and_canonical_schema(self) -> None:
        projects_dir = self.config_dir / "projects"

        # 1. Pre-register a bare folderUri without trailing slash
        existing_ws = self.root / "already-bare"
        existing_ws.mkdir()
        projects_dir.mkdir(parents=True, exist_ok=True)
        existing_file = projects_dir / "0a7e0526-1111-2222-3333-444455556666.json"
        existing_file.write_text(
            json.dumps({
                "id": "0a7e0526-1111-2222-3333-444455556666",
                "name": "already-bare",
                "projectResources": {"resources": [{"folderUri": f"file://{existing_ws.resolve()}"}]},
                "settings": {},
                "isWorkspaceOnly": False,
            }),
            encoding="utf-8",
        )
        dedup_res = ensure_project_registered(existing_ws)
        self.assertTrue(dedup_res["success"])
        self.assertEqual(dedup_res["action"], "already_registered")
        self.assertEqual(dedup_res["project_id"], "0a7e0526-1111-2222-3333-444455556666")
        self.assertEqual(len(list(projects_dir.glob("*.json"))), 1)

        # 2. Initialize a real git repo on branch 'develop' and test dry-run + create + idempotency
        new_repo = self.root / "purrfect-app"
        new_repo.mkdir()
        subprocess.run(["git", "init", "-b", "develop"], cwd=new_repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        dry_res = ensure_project_registered(new_repo, dry_run=True)
        self.assertTrue(dry_res["success"])
        self.assertEqual(dry_res["action"], "would_create")
        self.assertTrue(dry_res["dry_run"])
        self.assertEqual(dry_res["default_branch"], "develop")
        self.assertEqual(len(list(projects_dir.glob("*.json"))), 1)

        created_res = ensure_project_registered(new_repo)
        self.assertTrue(created_res["success"])
        self.assertEqual(created_res["action"], "created")
        self.assertFalse(created_res["dry_run"])
        self.assertEqual(created_res["name"], "purrfect-app")
        self.assertEqual(created_res["default_branch"], "develop")
        self.assertEqual(created_res["folder_uri"], normalize_folder_uri(new_repo))
        uuid.UUID(created_res["project_id"])  # valid UUID

        created_file = Path(created_res["project_file"])
        self.assertTrue(created_file.is_file())
        raw_text = created_file.read_text(encoding="utf-8")
        self.assertTrue(raw_text.endswith("\n"))
        payload = json.loads(raw_text)
        self.assertEqual(
            payload,
            {
                "id": created_res["project_id"],
                "name": "purrfect-app",
                "projectResources": {
                    "resources": [
                        {
                            "gitFolder": {
                                "folderUri": normalize_folder_uri(new_repo),
                                "defaultBranch": "develop",
                                "allowWrite": True,
                            }
                        }
                    ]
                },
                "permissionGrants": {"v2Migrated": True},
                "settings": {},
                "isWorkspaceOnly": False,
            },
        )

        # Second call returns already_registered without creating duplicates
        second_res = ensure_project_registered(f"{new_repo}/")
        self.assertEqual(second_res["action"], "already_registered")
        self.assertEqual(second_res["project_id"], created_res["project_id"])
        self.assertEqual(len(list(projects_dir.glob("*.json"))), 2)

        # Non-existent workspace directory returns success=False
        err_res = ensure_project_registered(self.root / "missing-ws")
        self.assertFalse(err_res["success"])
        self.assertEqual(err_res["action"], "error")

    def test_cli_project_list_ensure_and_onboard_flag(self) -> None:
        custom_cfg = self.root / "cli_cfg"
        ws = self.root / "cli-repo"
        ws.mkdir()

        # Empty list
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main(["project", "list", "--config-dir", str(custom_cfg), "--json"])
        self.assertEqual(rc, 0)
        list_empty = json.loads(buf.getvalue())
        self.assertTrue(list_empty["success"])
        self.assertEqual(list_empty["count"], 0)
        self.assertEqual(list_empty["projects"], [])

        # Ensure dry-run
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main([
                "project", "ensure", str(ws),
                "--config-dir", str(custom_cfg),
                "--name", "custom-cli-repo",
                "--branch", "trunk",
                "--dry-run", "--json",
            ])
        self.assertEqual(rc, 0)
        dry_data = json.loads(buf.getvalue())
        self.assertEqual(dry_data["action"], "would_create")
        self.assertEqual(dry_data["name"], "custom-cli-repo")
        self.assertEqual(dry_data["default_branch"], "trunk")
        self.assertFalse((custom_cfg / "projects").exists())

        # Ensure real write + human list + default action
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main([
                "project", "ensure", str(ws),
                "--config-dir", str(custom_cfg),
                "--name", "custom-cli-repo",
                "--branch", "trunk",
                "--json",
            ])
        self.assertEqual(rc, 0)
        created_data = json.loads(buf.getvalue())
        self.assertEqual(created_data["action"], "created")
        self.assertTrue(Path(created_data["project_file"]).is_file())

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main(["project", "--config-dir", str(custom_cfg)])
        self.assertEqual(rc, 0)
        self.assertIn("custom-cli-repo", buf.getvalue())
        self.assertIn("trunk", buf.getvalue())

        # Ensure failure exit code on missing workspace
        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf):
            rc = cli_main(["project", "ensure", str(self.root / "nope"), "--config-dir", str(custom_cfg)])
        self.assertEqual(rc, 1)
        self.assertIn("does not exist", err_buf.getvalue())

        # Onboard --ensure-project parser plumbing
        parser = build_parser()
        self.assertFalse(parser.parse_args(["onboard"]).ensure_project)
        self.assertTrue(parser.parse_args(["onboard", "--ensure-project"]).ensure_project)


if __name__ == "__main__":
    unittest.main()
