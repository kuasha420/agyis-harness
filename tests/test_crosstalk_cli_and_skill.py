# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for Track D: `agyis crosstalk` CLI, `crosstalk` skill,
`presets.py` integration, and `succession.py` `/crosstalk` alignment.

Zero writes to `~/.gemini/` or live conversations. Uses TemporaryDirectory +
isolated `AGYIS_CONFIG_DIR`, `ANTIGRAVITY_APP_DATA_DIR`, and `AGYIS_HARNESS_STATE_DIR`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from harness.cli import build_parser, main as cli_main
from harness.delivery.projects import ensure_project_registered
from harness.skills import GROUP_PRESETS, get_skill
from harness.subagents.succession import build_succession_prompt, resolve_self_alias

REPO_ROOT = Path(__file__).resolve().parent.parent


def _seed_summaries_db(db_path: Path, rows: list[dict], fts_rows: list[tuple[str, str, str, str, str, str]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                preview TEXT NOT NULL DEFAULT '',
                step_count INTEGER NOT NULL DEFAULT 0,
                last_modified_time TEXT NOT NULL DEFAULT '',
                workspace_uris TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                project_id TEXT NOT NULL DEFAULT '',
                agent_name TEXT NOT NULL DEFAULT '',
                parent_conversation_id TEXT NOT NULL DEFAULT '',
                nesting_depth INTEGER NOT NULL DEFAULT 0,
                not_fully_idle INTEGER NOT NULL DEFAULT 0,
                killed INTEGER NOT NULL DEFAULT 0,
                last_user_input_time TEXT NOT NULL DEFAULT '',
                last_user_input_step_index INTEGER NOT NULL DEFAULT -1,
                app_data_dir TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE TABLE conversation_parents (conversation_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE conversations_fts USING fts5("
            "conversation_id UNINDEXED, title, workspace, project, user_body, agent_body)"
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO conversation_summaries (
                    conversation_id, title, preview, step_count, last_modified_time,
                    workspace_uris, status, project_id, app_data_dir
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["conversation_id"],
                    row.get("title", ""),
                    row.get("preview", ""),
                    row.get("step_count", 1),
                    row.get("last_modified_time", "2026-11-28T01:00:00Z"),
                    row.get("workspace_uris", ""),
                    row.get("status", "IDLE"),
                    row.get("project_id", ""),
                    str(db_path.parent),
                ),
            )
        for fts in fts_rows:
            conn.execute(
                "INSERT INTO conversations_fts (conversation_id, title, workspace, project, user_body, agent_body) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                fts,
            )
        conn.commit()
    finally:
        conn.close()


def _run_cli(argv: list[str], *, env_overrides: dict[str, str], stdin_text: str = "") -> tuple[int, str, str]:
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with (
        patch.dict(os.environ, env_overrides, clear=False),
        patch("sys.stdin", io.StringIO(stdin_text)),
        contextlib.redirect_stdout(out_buf),
        contextlib.redirect_stderr(err_buf),
    ):
        rc = cli_main(argv)
    return rc, out_buf.getvalue(), err_buf.getvalue()


class TestCrosstalkCliAndSkill(unittest.TestCase):
    """Hermetic tests for `agyis crosstalk` CLI, skill contracts, and succession updates."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg_dir = self.root / "gemini_home" / "config"
        self.app_dir = self.root / "gemini_home" / "antigravity"
        self.cli_app_dir = self.root / "gemini_home" / "antigravity-cli"
        self.state_dir = self.root / "state"
        self.src_ws = self.root / "repo-private"
        self.tgt_ws = self.root / "repo-oss"
        for d in (self.cfg_dir, self.app_dir, self.cli_app_dir, self.state_dir, self.src_ws, self.tgt_ws):
            d.mkdir(parents=True, exist_ok=True)

        self.src_proj = ensure_project_registered(self.src_ws, config_dir=self.cfg_dir, name="repo-private")
        self.tgt_proj = ensure_project_registered(self.tgt_ws, config_dir=self.cfg_dir, name="repo-oss")

        _seed_summaries_db(
            self.app_dir / "conversation_summaries.db",
            [
                {
                    "conversation_id": "conv-desktop-001",
                    "title": "Auth Contract Sync",
                    "preview": "Finalize OAuth token contract",
                    "last_modified_time": "2026-11-28T02:00:00Z",
                    "workspace_uris": json.dumps([self.tgt_proj["folder_uri"]]),
                    "project_id": self.tgt_proj["project_id"],
                },
            ],
            [("conv-desktop-001", "Auth Contract Sync", "repo-oss", "repo-oss", "auth token", "synced")],
        )
        _seed_summaries_db(
            self.cli_app_dir / "conversation_summaries.db",
            [
                {
                    "conversation_id": "conv-cli-002",
                    "title": "CLI Smoke Session",
                    "preview": "Run hermetic test suite",
                    "last_modified_time": "2026-11-28T01:30:00Z",
                    "workspace_uris": json.dumps([self.src_proj["folder_uri"]]),
                    "project_id": self.src_proj["project_id"],
                },
            ],
            [("conv-cli-002", "CLI Smoke Session", "repo-private", "repo-private", "hermetic test", "passed")],
        )

        # Seed compact + full transcripts for inspect hydration test
        logs_dir = self.app_dir / "brain" / "conv-desktop-001" / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "transcript.jsonl").write_text(
            json.dumps({
                "step_index": 0,
                "type": "USER_INPUT",
                "status": "DONE",
                "content": "Sync auth token=ghp_1234567890abcdefghijklmnop in /home/devuser/secret",
                "truncated_fields": ["content"],
            }) + "\n",
            encoding="utf-8",
        )
        (logs_dir / "transcript_full.jsonl").write_text(
            json.dumps({
                "step_index": 0,
                "type": "USER_INPUT",
                "status": "DONE",
                "content": "Full auth token=ghp_1234567890abcdefghijklmnop from /home/devuser/repo-oss",
            }) + "\n",
            encoding="utf-8",
        )

        # Seed inbound baton for status test
        xt_dir = self.src_ws / ".agents" / "artifacts" / "crosstalk"
        xt_dir.mkdir(parents=True, exist_ok=True)
        (xt_dir / "inbound_sess-active-99.json").write_text(
            json.dumps({
                "schema_version": "crosstalk.baton.v1",
                "conversation_id": "sess-active-99",
                "from_cid": "conv-cli-002",
                "from_project": "repo-private",
                "to_project": "repo-private",
                "hop": 1,
                "max_hops": 2,
                "title": "Prior Baton",
                "consumed": False,
            }),
            encoding="utf-8",
        )

        self.env = {
            "AGYIS_CONFIG_DIR": str(self.cfg_dir),
            "PSL_CONFIG_DIR": str(self.cfg_dir),
            "ANTIGRAVITY_APP_DATA_DIR": str(self.app_dir),
            "AGYIS_HARNESS_STATE_DIR": str(self.state_dir),
            "PSL_HARNESS_STATE_DIR": str(self.state_dir),
            "ANTIGRAVITY_LS_ADDRESS": "",
            "ANTIGRAVITY_CSRF_TOKEN": "",
            "ANTIGRAVITY_CONVERSATION_ID": "",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_list_search_status_and_inspect_json(self) -> None:
        rc, out, _ = _run_cli(["crosstalk", "list", "--surface", "all", "--json"], env_overrides=self.env)
        self.assertEqual(rc, 0)
        listed = json.loads(out)
        self.assertTrue(listed["success"])
        cids = {c["conversation_id"] for c in listed["conversations"]}
        self.assertEqual(cids, {"conv-desktop-001", "conv-cli-002"})

        rc_s, out_s, _ = _run_cli(["crosstalk", "search", "Auth", "--project", "repo-oss", "--json"], env_overrides=self.env)
        self.assertEqual(rc_s, 0)
        searched = json.loads(out_s)
        self.assertEqual([c["conversation_id"] for c in searched["conversations"]], ["conv-desktop-001"])

        rc_st, out_st, _ = _run_cli(
            ["crosstalk", "status", "--session", "sess-active-99", "--workspace", str(self.src_ws), "--surface", "desktop", "--json"],
            env_overrides=self.env,
        )
        self.assertEqual(rc_st, 0)
        st = json.loads(out_st)
        self.assertEqual(st["detected_surface"], "desktop")
        self.assertEqual(st["active_hop"], 1)
        self.assertEqual(st["max_hops"], 2)
        self.assertIsNotNone(st["inbound_baton"])
        self.assertEqual(st["recent_count"], 2)

        rc_in, out_in, _ = _run_cli(["crosstalk", "inspect", "conv-desktop-001", "--steps", "5", "--json"], env_overrides=self.env)
        self.assertEqual(rc_in, 0)
        insp = json.loads(out_in)
        self.assertTrue(insp["success"])
        step0 = insp["steps"]["steps"][0]
        self.assertTrue(step0["hydrated_from_full"])
        self.assertNotIn("ghp_1234567890", step0["content"])
        self.assertNotIn("/home/devuser", step0["content"])

    def test_widget_desktop_html_and_cli_stdin_fallback(self) -> None:
        art_dir = self.root / "widgets"
        rc_d, out_d, _ = _run_cli(
            [
                "crosstalk", "widget", "--kind", "preflight", "--surface", "desktop",
                "--title", "Handoff OSS", "--from-project", "repo-private", "--to-project", "repo-oss",
                "--artifact-dir", str(art_dir), "--json",
            ],
            env_overrides=self.env,
        )
        self.assertEqual(rc_d, 0)
        w_d = json.loads(out_d)
        self.assertTrue(w_d["is_desktop"])
        self.assertIn("<agent-embed src=", w_d["embed_hint"])
        self.assertTrue((art_dir / "crosstalk_preflight.html").is_file())

        stdin_payload = json.dumps({
            "goal": {"title": "Constellation View", "line": "Active peer threads"},
            "entities": [{"id": "conv-desktop-001", "title": "Auth Contract Sync", "outcome": "active", "surface": "cli"}],
        })
        rc_c, out_c, _ = _run_cli(
            ["crosstalk", "widget", "--kind", "constellation", "--surface", "cli", "--payload", "-"],
            env_overrides=self.env,
            stdin_text=stdin_payload,
        )
        self.assertEqual(rc_c, 0)
        self.assertIn("Crosstalk Constellation", out_c)
        self.assertIn("agy --conversation conv-desktop-001", out_c)
        self.assertNotIn("<agent-embed", out_c)

    def test_handoff_send_archive_dry_run_and_d6_guards(self) -> None:
        # Private -> OSS strict redaction dry-run
        rc_h, out_h, _ = _run_cli(
            [
                "crosstalk", "handoff", "--to", "repo-oss", "--workspace", str(self.src_ws),
                "--title", "OSS Handoff", "--summary", "Token ghp_1234567890abcdefghijklmnop dev@example.com",
                "--task", f"Inspect {self.src_ws}/src/app.py",
                "--source-visibility", "private", "--target-visibility", "oss",
                "--dry-run", "--json",
            ],
            env_overrides=self.env,
        )
        self.assertEqual(rc_h, 0)
        h_data = json.loads(out_h)
        self.assertTrue(h_data["dry_run"])
        self.assertEqual(h_data["visibility_crossing"], "Private -> OSS")
        self.assertGreaterEqual(h_data["redaction"]["secrets_redacted"], 2)
        self.assertNotIn("ghp_1234567890", h_data["prompt_preview"])
        self.assertNotIn("dev@example.com", h_data["prompt_preview"])

        # D6: .dirtyroom/ leakage and MAX_CROSSTALK_HOPS enforcement
        rc_dr, out_dr, _ = _run_cli(
            [
                "crosstalk", "handoff", "--new", "--workspace", str(self.src_ws),
                "--summary", "See .dirtyroom/secret.c", "--dry-run", "--json",
            ],
            env_overrides=self.env,
        )
        self.assertEqual(rc_dr, 1)
        self.assertEqual(json.loads(out_dr)["reason"], "dirtyroom_leakage")

        rc_hop, out_hop, _ = _run_cli(
            [
                "crosstalk", "handoff", "--to", "repo-oss", "--workspace", str(self.src_ws),
                "--summary", "Too many hops", "--hops", "3", "--dry-run", "--json",
            ],
            env_overrides=self.env,
        )
        self.assertEqual(rc_hop, 1)
        self.assertEqual(json.loads(out_hop)["reason"], "hop_limit_exceeded")

        # Steer send --dry-run
        rc_snd, out_snd, _ = _run_cli(
            [
                "crosstalk", "send", "conv-desktop-001", "Check ANTIGRAVITY_CSRF_TOKEN=secret12345678",
                "--workspace", str(self.src_ws), "--dry-run", "--json",
            ],
            env_overrides=self.env,
        )
        self.assertEqual(rc_snd, 0)
        s_data = json.loads(out_snd)
        self.assertTrue(s_data["dry_run"])
        self.assertNotIn("secret12345678", s_data["message_preview"])

        # Archive --dry-run (and D6 absence of delete subcommand)
        rc_ar, out_ar, _ = _run_cli(["crosstalk", "archive", "conv-desktop-001", "--dry-run", "--json"], env_overrides=self.env)
        self.assertEqual(rc_ar, 0)
        ar_data = json.loads(out_ar)
        self.assertEqual(ar_data["rpc_method"], "UpdateConversation")
        self.assertTrue(ar_data["rpc_payload"]["annotations"]["archived"])

        parser = build_parser("agyis")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["crosstalk", "delete", "conv-desktop-001"])
        self.assertNotEqual(ctx.exception.code, 0)
        cmd_src = (REPO_ROOT / "harness" / "commands" / "crosstalk.py").read_text(encoding="utf-8")
        self.assertNotIn("DeleteConversation", cmd_src)

    def test_crosstalk_skill_symlink_presets_and_succession_guidance(self) -> None:
        skill = get_skill("crosstalk")
        self.assertIsNotNone(skill)
        self.assertLess(skill.path.stat().st_size, 24576)
        self.assertIn("## Table of Contents", skill.body)
        self.assertIn("invoke_subagent", skill.body)
        self.assertIn("/swarm", skill.body)
        self.assertIn("conversations", skill.body)
        self.assertIn("/crosstalk", skill.body)
        self.assertTrue((REPO_ROOT / "harness" / "skills" / "crosstalk" / "references" / "protocol-and-transports.md").is_file())

        sym = REPO_ROOT / ".agents" / "skills" / "crosstalk"
        self.assertTrue(sym.is_symlink())
        self.assertEqual(os.readlink(sym), "../../harness/skills/crosstalk")

        self.assertIn("crosstalk", GROUP_PRESETS["workflow"])
        self.assertIn("crosstalk", GROUP_PRESETS["continuity"])

        self.assertEqual(resolve_self_alias("coordinator"), "agyis_coordinator")
        prompt = build_succession_prompt(1, 2, "sess-x", 460_000)
        self.assertNotIn('TypeName="self"', prompt)
        self.assertNotIn("TypeName='self'", prompt)
        self.assertIn("agyis crosstalk handoff --new", prompt)


if __name__ == "__main__":
    unittest.main()
