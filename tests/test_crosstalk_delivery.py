# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit & Contract Tests for Crosstalk Core Engine, Target Resolution & Hygiene.

Uses TempDir, in-process `http.server.HTTPServer` mock Language Server, temp
Desktop (`antigravity`) and CLI (`antigravity-cli`) `conversation_summaries.db`
SQLite fixtures, and mock `transcript.jsonl`/`transcript_full.jsonl` files.
Zero host `~/.gemini/` or live LS access.
"""

from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import unittest
import uuid

import harness.delivery as delivery_pkg
from harness.delivery import (
    GIT_EXCLUDE_PATTERNS,
    HARD_MAX_CROSSTALK_HOPS,
    MAX_CROSSTALK_HOPS,
    archive_conversation,
    configure_git_exclude,
    discover_conversations,
    get_conversation,
    handoff_conversation,
    inspect_conversation_steps,
    parse_crosstalk_envelope,
    read_inbound_baton,
    resolve_project_target,
    serialize_crosstalk_envelope,
    steer_conversation,
    validate_crosstalk_guards,
)


class _MockLsState:
    """Thread-safe mock state for local Connect HTTP+JSON Language Server tests."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.sandbox_block: bool = False
        self.conversations: list[dict] = []
        self.created_seq: int = 0
        self.updated: list[dict] = []
        self.ls_messages: list[dict] = []


def _start_mock_ls(state: _MockLsState) -> tuple[http.server.ThreadingHTTPServer, threading.Thread, str]:
    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or "0")
            raw_body = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else "{}"
            try:
                body = json.loads(raw_body) if raw_body.strip() else {}
            except json.JSONDecodeError:
                body = {}
            state.calls.append({
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body,
            })

            if state.sandbox_block:
                self._send_json(403, {"error": "Port 43210 not allowed for HTTP"})
                return

            if self.path == "/product.v1.ConversationService/ListConversations":
                self._send_json(200, {"conversations": state.conversations, "nextPageToken": ""})
                return
            if self.path == "/product.v1.ConversationService/GetConversation":
                cid = body.get("conversationId")
                match = next((c for c in state.conversations if c.get("id") == cid), None)
                if match is None:
                    self._send_json(404, {"code": "not_found", "message": "not found"})
                else:
                    self._send_json(200, {"conversation": match})
                return
            if self.path == "/product.v1.ConversationService/CreateConversation":
                state.created_seq += 1
                new_id = f"created-conv-{state.created_seq:04d}"
                conv = {
                    "id": new_id,
                    "metadata": {"projectId": body.get("projectId", ""), "tags": body.get("tags", [])},
                    "annotations": {"title": body.get("title", ""), "tags": body.get("tags", [])},
                    "state": {"runState": "RUN_STATE_RUNNING", "summary": body.get("title", "")},
                }
                state.conversations.append(conv)
                self._send_json(200, {"conversation": conv})
                return
            if self.path == "/product.v1.ConversationService/UpdateConversation":
                cid = body.get("conversationId")
                ann = body.get("annotations") or {}
                state.updated.append(body)
                conv = next((c for c in state.conversations if c.get("id") == cid), {"id": cid, "annotations": {}, "metadata": {}, "state": {}})
                conv.setdefault("annotations", {}).update(ann)
                self._send_json(200, {"conversation": conv})
                return
            if self.path == "/exa.language_server_pb.LanguageServerService/SendUserCascadeMessage":
                state.ls_messages.append(body)
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"code": "not_found", "message": f"Unknown RPC {self.path}"})

        def _send_json(self, code: int, payload: dict) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    return server, thread, f"127.0.0.1:{port}"


def _create_summaries_db(
    db_path: Path,
    rows: list[dict],
    *,
    parents: list[tuple[str, str]] | None = None,
    fts_rows: list[tuple[str, str, str, str, str, str]] | None = None,
) -> None:
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
                    workspace_uris, status, source, project_id, agent_name,
                    parent_conversation_id, nesting_depth, not_fully_idle, killed,
                    app_data_dir, group_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["conversation_id"],
                    row.get("title", ""),
                    row.get("preview", ""),
                    row.get("step_count", 0),
                    row.get("last_modified_time", ""),
                    row.get("workspace_uris", ""),
                    row.get("status", ""),
                    row.get("source", ""),
                    row.get("project_id", ""),
                    row.get("agent_name", ""),
                    row.get("parent_conversation_id", ""),
                    row.get("nesting_depth", 0),
                    int(bool(row.get("not_fully_idle", False))),
                    int(bool(row.get("killed", False))),
                    row.get("app_data_dir", str(db_path.parent)),
                    row.get("group_id", ""),
                ),
            )
        for cid, pid in parents or ():
            conn.execute("INSERT INTO conversation_parents (conversation_id, parent_id) VALUES (?, ?)", (cid, pid))
        for item in fts_rows or ():
            conn.execute(
                "INSERT INTO conversations_fts (conversation_id, title, workspace, project, user_body, agent_body) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                item,
            )
        conn.commit()
    finally:
        conn.close()


def _write_project_json(config_dir: Path, project_id: str, name: str, workspace: Path, *, branch: str = "main") -> None:
    proj_dir = config_dir / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": project_id,
        "name": name,
        "projectResources": {
            "resources": [
                {
                    "gitFolder": {
                        "folderUri": f"{workspace.resolve().as_uri()}/",
                        "defaultBranch": branch,
                        "allowWrite": True,
                    }
                }
            ]
        },
        "settings": {},
        "isWorkspaceOnly": False,
    }
    (proj_dir / f"{project_id}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestCrosstalkDeliveryEngine(unittest.TestCase):
    """Hermetic verification suite for crosstalk discovery, guards, target resolution, and dispatchers."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gemini_root = self.root / ".gemini"
        self.config_dir = self.gemini_root / "config"
        self.desktop_dir = self.gemini_root / "antigravity"
        self.cli_dir = self.gemini_root / "antigravity-cli"
        for d in (self.config_dir, self.desktop_dir, self.cli_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.ws_a = self.root / "repo-alpha"
        self.ws_b = self.root / "repo-beta"
        self.ws_c = self.root / "repo-gamma"
        for ws in (self.ws_a, self.ws_b, self.ws_c):
            ws.mkdir(parents=True, exist_ok=True)

        self.proj_a_id = str(uuid.uuid4())
        self.proj_b_id = str(uuid.uuid4())
        self.proj_c_id = str(uuid.uuid4())
        _write_project_json(self.config_dir, self.proj_a_id, "repo-alpha", self.ws_a)
        _write_project_json(self.config_dir, self.proj_b_id, "repo-beta", self.ws_b)
        _write_project_json(self.config_dir, self.proj_c_id, "repo-gamma", self.ws_c)

        self._orig_env = {
            k: os.environ.get(k)
            for k in (
                "AGYIS_CONFIG_DIR",
                "PSL_CONFIG_DIR",
                "ANTIGRAVITY_LS_ADDRESS",
                "ANTIGRAVITY_CSRF_TOKEN",
                "ANTIGRAVITY_CONVERSATION_ID",
                "ANTIGRAVITY_AGENTAPI_EXE",
                "ANTIGRAVITY_APP_DATA_DIR",
            )
        }
        os.environ["AGYIS_CONFIG_DIR"] = str(self.config_dir)
        for k in ("PSL_CONFIG_DIR", "ANTIGRAVITY_LS_ADDRESS", "ANTIGRAVITY_CSRF_TOKEN", "ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_AGENTAPI_EXE", "ANTIGRAVITY_APP_DATA_DIR"):
            os.environ.pop(k, None)

        self.ls_state = _MockLsState()
        self.server, self.server_thread, self.ls_addr = _start_mock_ls(self.ls_state)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2.0)
        for k, prev in self._orig_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
        self.tmp.cleanup()

    def test_git_exclude_patterns_include_crosstalk(self) -> None:
        """Verifies .agents/artifacts/ and .agents/artifacts/crosstalk/ git exclude coverage."""
        self.assertIn(".agents/artifacts/", GIT_EXCLUDE_PATTERNS)
        self.assertIn(".agents/artifacts/crosstalk/", GIT_EXCLUDE_PATTERNS)
        git_repo = self.root / "git-repo"
        (git_repo / ".git").mkdir(parents=True)
        excl = configure_git_exclude(git_repo)
        txt = excl.read_text(encoding="utf-8")
        self.assertIn(".agents/artifacts/", txt)
        self.assertIn(".agents/artifacts/crosstalk/", txt)

    def test_resolve_project_target_uuid_path_slug_ambiguous_and_ensure(self) -> None:
        """Resolves projects by UUID, path, URI, slug, detects collisions, and supports ensure=True."""
        by_id = resolve_project_target(self.proj_a_id, config_dir=self.config_dir)
        self.assertTrue(by_id["success"])
        self.assertEqual(by_id["matched_by"], "project_id")
        self.assertEqual(Path(by_id["workspace_path"]), self.ws_a.resolve())

        by_path = resolve_project_target(self.ws_b, config_dir=self.config_dir)
        self.assertTrue(by_path["success"])
        self.assertEqual(by_path["matched_by"], "path")
        self.assertEqual(by_path["project_id"], self.proj_b_id)

        by_uri = resolve_project_target(self.ws_b.resolve().as_uri(), config_dir=self.config_dir)
        self.assertTrue(by_uri["success"])
        self.assertEqual(by_uri["project_id"], self.proj_b_id)

        by_slug = resolve_project_target("repo-alpha", config_dir=self.config_dir)
        self.assertTrue(by_slug["success"])
        self.assertEqual(by_slug["matched_by"], "slug")
        self.assertEqual(by_slug["project_id"], self.proj_a_id)

        # Ambiguous basename slug collision across two registered projects
        dup_ws = self.root / "nested" / "repo-alpha"
        dup_ws.mkdir(parents=True)
        _write_project_json(self.config_dir, str(uuid.uuid4()), "repo-alpha", dup_ws)
        ambig = resolve_project_target("repo-alpha", config_dir=self.config_dir)
        self.assertFalse(ambig["success"])
        self.assertEqual(ambig["status"], "ambiguous")
        self.assertEqual(len(ambig["candidates"]), 2)

        # Unregistered directory -> status=unregistered, then ensure=True (dry_run & real)
        unreg = self.root / "new-service"
        unreg.mkdir()
        unreg_res = resolve_project_target(unreg, config_dir=self.config_dir, ensure=False)
        self.assertFalse(unreg_res["success"])
        self.assertEqual(unreg_res["status"], "unregistered")
        self.assertTrue(unreg_res["can_ensure"])

        dry_ens = resolve_project_target(unreg, config_dir=self.config_dir, ensure=True, dry_run=True)
        self.assertTrue(dry_ens["success"])
        self.assertEqual(dry_ens["status"], "would_create")

        real_ens = resolve_project_target(unreg, config_dir=self.config_dir, ensure=True, dry_run=False)
        self.assertTrue(real_ens["success"])
        self.assertEqual(real_ens["status"], "created")
        self.assertEqual(resolve_project_target(unreg, config_dir=self.config_dir)["project_id"], real_ens["project_id"])

    def test_dual_surface_discovery_fts5_rpc_and_sandbox_refusal(self) -> None:
        """Merges Desktop + CLI SQLite DBs, FTS5, ConversationService RPC, and surfaces sandbox_blocked cleanly."""
        _create_summaries_db(
            self.desktop_dir / "conversation_summaries.db",
            [
                {
                    "conversation_id": "desk-1",
                    "title": "Desktop Main Thread",
                    "preview": "Working on auth",
                    "last_modified_time": "2026-11-27T10:00:00Z",
                    "workspace_uris": json.dumps([self.ws_a.resolve().as_uri()]),
                    "project_id": self.proj_a_id,
                },
                {
                    "conversation_id": "desk-child-1",
                    "title": "Subagent Worker",
                    "last_modified_time": "2026-11-27T10:05:00Z",
                    "project_id": self.proj_a_id,
                },
            ],
            parents=[("desk-child-1", "desk-1")],
            fts_rows=[("desk-1", "Desktop Main Thread", "repo-alpha", "repo-alpha", "oauth migration", "done")],
        )
        _create_summaries_db(
            self.cli_dir / "conversation_summaries.db",
            [
                {
                    "conversation_id": "cli-only-1",
                    "title": "CLI Headless Sweep",
                    "preview": "CLI audit",
                    "last_modified_time": "2026-11-27T11:00:00Z",
                    "workspace_uris": json.dumps([self.ws_b.resolve().as_uri()]),
                    "project_id": self.proj_b_id,
                    "not_fully_idle": 1,
                }
            ],
            fts_rows=[("cli-only-1", "CLI Headless Sweep", "repo-beta", "repo-beta", "oauth schema", "cli ready")],
        )

        self.ls_state.conversations = [
            {
                "id": "desk-1",
                "metadata": {"projectId": self.proj_a_id, "tags": ["crosstalk"]},
                "annotations": {"title": "Desktop Main Thread", "conversationGroupId": "grp-7", "pinned": True},
                "state": {"runState": "RUN_STATE_RUNNING", "updateTime": "2026-11-27T12:00:00Z"},
            },
            {
                "id": "rpc-fresh-1",
                "metadata": {"projectId": self.proj_b_id, "tags": ["crosstalk"]},
                "annotations": {"title": "Fresh RPC Thread"},
                "state": {"runState": "RUN_STATE_IDLE", "updateTime": "2026-11-27T12:30:00Z"},
            },
        ]

        res = discover_conversations(
            query="oauth",
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="test-csrf-token",
        )
        self.assertTrue(res["success"])
        cids = [c["conversation_id"] for c in res["conversations"]]
        self.assertIn("desk-1", cids)
        self.assertIn("cli-only-1", cids)
        self.assertNotIn("desk-child-1", cids)  # excluded via conversation_parents

        by_cid = {c["conversation_id"]: c for c in res["conversations"]}
        self.assertEqual(by_cid["desk-1"]["run_state"], "RUN_STATE_RUNNING")
        self.assertEqual(by_cid["desk-1"]["group_id"], "grp-7")
        self.assertTrue(by_cid["desk-1"]["fts_matched"])
        self.assertEqual(by_cid["desk-1"]["project_name"], "repo-alpha")
        self.assertEqual(by_cid["cli-only-1"]["surface"], "cli")
        self.assertFalse(by_cid["cli-only-1"]["live_rpc"])

        # Verify Connect HTTP+JSON headers
        rpc_call = self.ls_state.calls[-1]
        self.assertEqual(rpc_call["headers"].get("connect-protocol-version"), "1")
        self.assertEqual(rpc_call["headers"].get("x-antigravity-csrf-token"), "test-csrf-token")

        # GetConversation enrichment
        det = get_conversation("desk-1", config_dir=self.config_dir, ls_address=self.ls_addr, csrf_token="test-csrf-token")
        self.assertTrue(det["success"])
        self.assertEqual(det["conversation"]["group_id"], "grp-7")

        # Missing env diagnostics (SQLite still works, RPC marks missing_env cleanly)
        no_env = discover_conversations(config_dir=self.config_dir)
        self.assertTrue(no_env["success"])
        self.assertTrue(no_env["rpc"]["missing_env"])
        self.assertFalse(no_env["sandbox_blocked"])

        # Sandbox refusal diagnostic -> zero blind retry!
        self.ls_state.calls.clear()
        self.ls_state.sandbox_block = True
        sb = get_conversation("missing-rpc", config_dir=self.config_dir, ls_address=self.ls_addr, csrf_token="test-csrf-token")
        self.assertFalse(sb["success"])
        self.assertTrue(sb["sandbox_blocked"])
        self.assertEqual(len(self.ls_state.calls), 1)

    def test_selective_transcript_hydration_and_sanitization(self) -> None:
        """Hydrates transcript_full.jsonl ONLY for step_index rows with truncated_fields and sanitizes output."""
        logs_dir = self.cli_dir / "brain" / "cli-trans-1" / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        compact_steps = [
            {"step_index": 0, "type": "USER_INPUT", "content": "Start work in " + str(self.ws_a)},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "Normal compact step 1"},
            {"step_index": 2, "type": "PLANNER_RESPONSE", "content": "Truncated preview...", "truncated_fields": ["content"]},
        ]
        full_steps = [
            {"step_index": 0, "type": "USER_INPUT", "content": "SHOULD NOT OVERWRITE STEP 0"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "SHOULD NOT OVERWRITE STEP 1"},
            {
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "content": f"Full output at {self.ws_a}/app.py with ANTIGRAVITY_CSRF_TOKEN=secret_leak_99 and /home/alice/.ssh/id",
            },
        ]
        (logs_dir / "transcript.jsonl").write_text("\n".join(json.dumps(s) for s in compact_steps) + "\n", encoding="utf-8")
        (logs_dir / "transcript_full.jsonl").write_text("\n".join(json.dumps(s) for s in full_steps) + "\n", encoding="utf-8")

        res = inspect_conversation_steps(
            "cli-trans-1",
            tail=5,
            config_dir=self.config_dir,
            source_ws=self.ws_a,
            target_ws=self.ws_b,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["surface"], "cli")
        self.assertTrue(res["used_full_fallback"])
        self.assertEqual(res["hydrated_step_indices"], [2])
        self.assertEqual(res["steps"][1]["content"], "Normal compact step 1")
        self.assertFalse(res["steps"][1]["hydrated_from_full"])
        self.assertTrue(res["steps"][2]["hydrated_from_full"])
        self.assertIn("[WORKSPACE_ROOT]/app.py", res["steps"][2]["content"])
        self.assertIn("ANTIGRAVITY_CSRF_TOKEN=[REDACTED_SECRET]", res["steps"][2]["content"])
        self.assertIn("[USER_HOME]/.ssh/id", res["steps"][2]["content"])
        self.assertNotIn("secret_leak_99", res["steps"][2]["content"])
        self.assertGreaterEqual(res["redaction"]["secrets_redacted"], 1)

        # When NO step has truncated_fields, transcript_full.jsonl is NOT used
        no_trunc_dir = self.desktop_dir / "brain" / "desk-no-trunc" / ".system_generated" / "logs"
        no_trunc_dir.mkdir(parents=True)
        (no_trunc_dir / "transcript.jsonl").write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "ok"}) + "\n", encoding="utf-8")
        (no_trunc_dir / "transcript_full.jsonl").write_text("{corrupt should not matter", encoding="utf-8")
        res2 = inspect_conversation_steps("desk-no-trunc", config_dir=self.config_dir)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["used_full_fallback"])
        self.assertEqual(res2["hydrated_step_indices"], [])

    def test_envelope_roundtrip_hop_caps_cycles_and_dirtyroom_blocks(self) -> None:
        """Enforces [CROSSTALK-V1] roundtrip, hop limits, self-target/cycles, and .dirtyroom/ blocks."""
        env = {
            "from_cid": "cid-1",
            "from_project": "repo-alpha",
            "to_project": "repo-beta",
            "intent": "escalate",
            "hop": 1,
            "max_hops": MAX_CROSSTALK_HOPS,
            "role_hint": "deep_execution",
            "group_id": "grp-9",
            "lineage": ["cid-0", "cid-1"],
            "project_lineage": ["repo-alpha", "repo-beta"],
            "artifacts": [".agents/artifacts/checkpoints/cid-1.md"],
        }
        serialized = serialize_crosstalk_envelope(env)
        self.assertIn("[CROSSTALK-HOP: 1/2]", serialized)
        self.assertIn("[CROSSTALK-ROLE: deep_execution]", serialized)
        parsed = parse_crosstalk_envelope(serialized)
        self.assertEqual(parsed, env)

        # Hop limit rejection
        ok, reason, _ = validate_crosstalk_guards(hop=3, max_hops=MAX_CROSSTALK_HOPS)
        self.assertFalse(ok)
        self.assertEqual(reason, "hop_limit_exceeded")

        ok, reason, _ = validate_crosstalk_guards(hop=1, max_hops=HARD_MAX_CROSSTALK_HOPS + 1)
        self.assertFalse(ok)
        self.assertEqual(reason, "hop_limit_exceeded")

        # Self-target rejection
        ok, reason, _ = validate_crosstalk_guards(hop=1, caller_cid="cid-1", target_cid="cid-1")
        self.assertFalse(ok)
        self.assertEqual(reason, "self_target")

        # Cross-project A -> B -> A cycle rejection
        ok, reason, _ = validate_crosstalk_guards(
            hop=2,
            from_project="repo-beta",
            to_project="repo-alpha",
            project_lineage=["repo-alpha", "repo-beta"],
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "cycle_detected")

        # Same-project compaction succession A -> A IS allowed within hop budget
        ok, reason, _ = validate_crosstalk_guards(
            hop=1,
            caller_cid="cid-1",
            from_project="repo-alpha",
            to_project="repo-alpha",
            project_lineage=["repo-alpha"],
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

        # .dirtyroom/ artifact & body leakage rejection
        ok, reason, _ = validate_crosstalk_guards(hop=1, artifacts=[".dirtyroom/binary.c"])
        self.assertFalse(ok)
        self.assertEqual(reason, "dirtyroom_leakage")

        ok, reason, _ = validate_crosstalk_guards(hop=1, raw_text="Please inspect .dirtyroom/notes.md")
        self.assertFalse(ok)
        self.assertEqual(reason, "dirtyroom_leakage")

        ok, reason, _ = validate_crosstalk_guards(hop=1, artifacts=["config/.env.prod"])
        self.assertFalse(ok)
        self.assertEqual(reason, "sensitive_artifact_blocked")

    def test_handoff_dry_run_live_baton_lineage_and_archive(self) -> None:
        """Verifies handoff_conversation (dry-run + live + checkpoint + inbound baton + cycle/hop inheritance) & archive."""
        cp_file = self.ws_a / ".agents" / "artifacts" / "checkpoints" / "caller-1.md"
        cp_file.parent.mkdir(parents=True)
        cp_file.write_text("# Checkpoint\nToken ghp_1234567890abcdef1234567890abcdef", encoding="utf-8")

        dry = handoff_conversation(
            "repo-beta",
            f"Sync schema from {self.ws_a}/api.py with ANTIGRAVITY_CSRF_TOKEN=csrf_dry_secret",
            caller_cid="caller-1",
            source_ws=self.ws_a,
            role_hint="deep_execution",
            group_id="grp-sync",
            include_checkpoint=True,
            config_dir=self.config_dir,
            dry_run=True,
        )
        self.assertTrue(dry["success"])
        self.assertTrue(dry["dry_run"])
        self.assertIsNone(dry["conversation_id"])
        self.assertEqual(len(self.ls_state.calls), 0)
        self.assertFalse((self.ws_b / ".agents" / "artifacts" / "crosstalk").exists())
        self.assertNotIn("csrf_dry_secret", dry["prompt_preview"])
        self.assertNotIn("ghp_123456", dry["prompt_preview"])

        # Dirtyroom brief blocked cleanly
        blocked = handoff_conversation(
            "repo-beta",
            "Read .dirtyroom/dump.c before fixing",
            caller_cid="caller-1",
            source_ws=self.ws_a,
            config_dir=self.config_dir,
        )
        self.assertFalse(blocked["success"])
        self.assertTrue(blocked["blocked"])
        self.assertEqual(blocked["reason"], "dirtyroom_leakage")

        # Live handoff A -> B
        live = handoff_conversation(
            "repo-beta",
            f"Sync schema from {self.ws_a}/api.py with ANTIGRAVITY_CSRF_TOKEN=csrf_live_secret",
            intent="sync",
            title="Sync Beta Consumer",
            caller_cid="caller-1",
            source_ws=self.ws_a,
            role_hint="deep_execution",
            group_id="grp-sync",
            include_checkpoint=True,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertTrue(live["success"])
        new_cid = live["conversation_id"]
        self.assertEqual(live["hop"], 1)
        self.assertEqual(live["pill_markdown"], f"[Sync Beta Consumer](conversation://{new_cid})")
        self.assertEqual(live["cli_command"], f"agy --conversation {new_cid}")

        baton = read_inbound_baton(self.ws_b, new_cid)
        self.assertIsNotNone(baton)
        self.assertEqual(baton["from_cid"], "caller-1")
        self.assertEqual(baton["from_project"], "repo-alpha")
        self.assertEqual(baton["to_project"], "repo-beta")
        self.assertEqual(baton["hop"], 1)
        self.assertFalse(baton["consumed"])
        self.assertTrue(Path(live["outbound_ledger_path"]).is_file())
        self.assertEqual(self.ls_state.updated[-1]["annotations"]["conversationGroupId"], "grp-sync")

        # Returning from repo-beta back to repo-alpha is automatically rejected as cycle via inbound baton
        bounce = handoff_conversation(
            "repo-alpha",
            "Ping back to alpha",
            caller_cid=new_cid,
            source_ws=self.ws_b,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertFalse(bounce["success"])
        self.assertEqual(bounce["reason"], "cycle_detected")

        # Hop 2 -> repo-gamma succeeds, then Hop 3 is blocked via inherited baton hop count
        hop2 = handoff_conversation(
            "repo-gamma",
            "Forward contract",
            caller_cid=new_cid,
            source_ws=self.ws_b,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertTrue(hop2["success"])
        self.assertEqual(hop2["hop"], 2)

        hop3 = handoff_conversation(
            "repo-gamma",
            "Exceed hop cap",
            caller_cid=hop2["conversation_id"],
            source_ws=self.ws_c,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertFalse(hop3["success"])
        self.assertEqual(hop3["reason"], "hop_limit_exceeded")

        # Soft archive + DeleteConversation intentionally absent
        arch_dry = archive_conversation(new_cid, dry_run=True)
        self.assertTrue(arch_dry["success"])
        self.assertEqual(arch_dry["rpc_payload"]["annotations"], {"archived": True})
        arch = archive_conversation(new_cid, ls_address=self.ls_addr, csrf_token="ls-csrf")
        self.assertTrue(arch["success"])
        self.assertEqual(arch["status"], "archived")
        self.assertFalse(hasattr(delivery_pkg, "delete_conversation"))

    def test_steer_conversation_agentapi_hook_and_ls_fallback(self) -> None:
        """Verifies steer_conversation dry-run, fake agentapi subprocess, pluggable hook, and LS fallback."""
        log_file = self.root / "agentapi_args.json"
        fake_agentapi = self.root / "fake_agentapi.py"
        fake_agentapi.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"open({str(log_file)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
            "print('sent ok')\n",
            encoding="utf-8",
        )
        fake_agentapi.chmod(fake_agentapi.stat().st_mode | stat.S_IEXEC)

        # Self-steer blocked
        self_res = steer_conversation("cid-self", "hello", caller_cid="cid-self")
        self.assertFalse(self_res["success"])
        self.assertEqual(self_res["reason"], "self_target")

        # Dry run
        dry = steer_conversation(
            "cid-peer-1",
            "Update with ANTIGRAVITY_CSRF_TOKEN=steer_secret",
            title="Nudge",
            agentapi_exe=str(fake_agentapi),
            dry_run=True,
        )
        self.assertTrue(dry["success"])
        self.assertTrue(dry["dry_run"])
        self.assertFalse(log_file.exists())
        self.assertNotIn("steer_secret", dry["message_preview"])

        # Fake agentapi execution
        sent = steer_conversation(
            "cid-peer-1",
            "Nudge with ANTIGRAVITY_CSRF_TOKEN=steer_secret",
            title="Nudge",
            agentapi_exe=str(fake_agentapi),
        )
        self.assertTrue(sent["success"])
        self.assertEqual(sent["transport_used"], "agentapi")
        argv = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(argv[:3], ["send-message", "--title=Nudge", "cid-peer-1"])
        self.assertIn("ANTIGRAVITY_CSRF_TOKEN=[REDACTED_SECRET]", argv[3])

        # Pluggable LS fallback hook
        hook_calls = []

        def _hook(cid: str, msg: str, ctx: dict) -> dict:
            hook_calls.append((cid, msg, ctx))
            return {"success": True, "transport_used": "custom_smoke_hook", "data": {"ok": True}}

        hooked = steer_conversation(
            "cid-peer-2",
            "Via hook",
            transport="ls_rpc",
            ls_fallback_hook=_hook,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertTrue(hooked["success"])
        self.assertEqual(hooked["transport_used"], "custom_smoke_hook")
        self.assertEqual(len(hook_calls), 1)

        # Native LanguageServerService/SendUserCascadeMessage fallback
        ls_res = steer_conversation(
            "cid-peer-3",
            "Via LS RPC",
            transport="ls_rpc",
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertTrue(ls_res["success"])
        self.assertEqual(ls_res["transport_used"], "ls_rpc")
        self.assertEqual(self.ls_state.ls_messages[-1]["cascadeId"], "cid-peer-3")

    def test_steer_conversation_language_server_agentapi_wrapper(self) -> None:
        """Verifies `language_server` agentapi binaries invoke `[exe, 'agentapi', 'send-message', ...]`."""
        log_file = self.root / "ls_agentapi_args.json"
        ls_wrapper = self.root / "language_server"
        ls_wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"open({str(log_file)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
            "print('ls agentapi sent ok')\n",
            encoding="utf-8",
        )
        ls_wrapper.chmod(ls_wrapper.stat().st_mode | stat.S_IEXEC)

        dry = steer_conversation(
            "cid-peer-ls",
            "Dry run check",
            title="Sync Title",
            agentapi_exe=str(ls_wrapper),
            dry_run=True,
        )
        self.assertTrue(dry["success"])
        self.assertEqual(dry["command"], [str(ls_wrapper), "agentapi", "send-message", "--title=Sync Title", "cid-peer-ls", "Dry run check"])
        self.assertFalse(log_file.exists())

        sent = steer_conversation(
            "cid-peer-ls",
            "Steer with ANTIGRAVITY_CSRF_TOKEN=ls_secret",
            title="Sync Title",
            agentapi_exe=str(ls_wrapper),
        )
        self.assertTrue(sent["success"])
        self.assertEqual(sent["transport_used"], "agentapi")
        argv = json.loads(log_file.read_text(encoding="utf-8"))
        self.assertEqual(argv[:4], ["agentapi", "send-message", "--title=Sync Title", "cid-peer-ls"])
        self.assertIn("ANTIGRAVITY_CSRF_TOKEN=[REDACTED_SECRET]", argv[4])

    def test_discovery_where_pushdown_finds_older_matches_past_310_rows(self) -> None:
        """Verifies SQLite WHERE pushdown finds older matching rows beyond the 300-row newest window."""
        rows = []
        for idx in range(320):
            ts_min, ts_sec = divmod(idx, 60)
            is_old_target = idx == 0
            rows.append({
                "conversation_id": f"bulk-conv-{idx:04d}",
                "title": "Legacy Needle Match" if is_old_target else f"Recent Alpha Thread {idx}",
                "preview": "Old payload" if is_old_target else "Routine work",
                "last_modified_time": f"2026-11-28T00:{ts_min:02d}:{ts_sec:02d}Z",
                "project_id": self.proj_b_id if is_old_target else self.proj_a_id,
                "parent_conversation_id": "parent-legacy" if is_old_target else "",
            })
        _create_summaries_db(
            self.desktop_dir / "conversation_summaries.db",
            rows,
            fts_rows=[
                ("bulk-conv-0000", "Legacy Needle Match", "repo-beta", "repo-beta", "ancient-fts-token", "done"),
            ],
        )

        by_proj = discover_conversations(
            project_id=self.proj_b_id,
            include_children=True,
            limit=5,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertEqual([c["conversation_id"] for c in by_proj["conversations"]], ["bulk-conv-0000"])

        by_fts = discover_conversations(
            query="ancient-fts-token",
            include_children=True,
            limit=5,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertEqual([c["conversation_id"] for c in by_fts["conversations"]], ["bulk-conv-0000"])

        by_parent = discover_conversations(
            parent_conversation_id="parent-legacy",
            include_children=True,
            limit=5,
            config_dir=self.config_dir,
            ls_address=self.ls_addr,
            csrf_token="ls-csrf",
        )
        self.assertEqual([c["conversation_id"] for c in by_parent["conversations"]], ["bulk-conv-0000"])

    def test_resolve_project_target_dot_and_dotdot_cwd_paths(self) -> None:
        """Verifies resolve_project_target('.', ensure=False) and '..' match registered paths."""
        sub_dir = self.ws_a / "nested-pkg"
        sub_dir.mkdir(parents=True)
        orig_cwd = os.getcwd()
        try:
            os.chdir(str(self.ws_a))
            res_dot = resolve_project_target(".", config_dir=self.config_dir, ensure=False)
            self.assertTrue(res_dot["success"])
            self.assertEqual(res_dot["matched_by"], "path")
            self.assertEqual(res_dot["project_id"], self.proj_a_id)

            os.chdir(str(sub_dir))
            res_dotdot = resolve_project_target("..", config_dir=self.config_dir, ensure=False)
            self.assertTrue(res_dotdot["success"])
            self.assertEqual(res_dotdot["matched_by"], "path")
            self.assertEqual(res_dotdot["project_id"], self.proj_a_id)
        finally:
            os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main()
