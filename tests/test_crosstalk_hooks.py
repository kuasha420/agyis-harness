#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for Track C: SessionStart, user_markdown, PLUGIN_DATA, D6 advisories, and fence_dispatch."""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from harness.hooks import (
    anti_drift_hook,
    anti_loop_hook,
    command_safety_hook,
    drift_guards,
    fence_dispatch,
    fence_gates,
    pre_invocation_hook,
    role_lineage,
    role_pinning,
    role_prompts,
    runner,
    wire_compat,
)
from harness.runtime.hygiene_checks import check_hooks_health
from harness.utils import state as state_utils


def _isolated_env(state_dir: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(state_dir.parent),
        "AGYIS_HARNESS_STATE_DIR": str(state_dir),
    }
    env.update(extra)
    return env


class TestPluginDataStatePrecedence(unittest.TestCase):
    def test_state_dir_env_precedence_and_uid_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agyis_dir = root / "agyis_state"
            psl_dir = root / "psl_state"
            plugin_dir = root / "plugin_data"

            with mock.patch.dict(os.environ, {
                "AGYIS_HARNESS_STATE_DIR": str(agyis_dir),
                "PSL_HARNESS_STATE_DIR": str(psl_dir),
                "PLUGIN_DATA": str(plugin_dir),
            }, clear=True):
                self.assertEqual(state_utils.get_state_dir(), agyis_dir)

            with mock.patch.dict(os.environ, {
                "PSL_HARNESS_STATE_DIR": str(psl_dir),
                "PLUGIN_DATA": str(plugin_dir),
            }, clear=True):
                self.assertEqual(state_utils.get_state_dir(), psl_dir)

            with mock.patch.dict(os.environ, {"PLUGIN_DATA": str(plugin_dir)}, clear=True):
                resolved = state_utils.get_state_dir()
                self.assertEqual(resolved, plugin_dir / "state")
                self.assertTrue(resolved.is_dir())
                self.assertEqual(state_utils.get_state_dir("custom"), plugin_dir / "custom")

            with mock.patch.dict(os.environ, {}, clear=True):
                uid = os.getuid() if hasattr(os, "getuid") else 0
                self.assertEqual(state_utils.get_state_dir(), Path(f"/tmp/agyis_harness_state_{uid}"))


class TestSessionStartAndUserMarkdown(unittest.TestCase):
    def test_hooks_json_and_runner_support_session_start(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        hooks_path = repo_root / "harness" / "hooks" / "hooks.json"
        hooks_map = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(len(hooks_map), 7)
        self.assertIn("SessionStart", hooks_map["psl-compaction-advisory"])
        self.assertEqual(
            hooks_map["psl-compaction-advisory"]["SessionStart"][0]["command"],
            "python3 -m harness.hooks.runner pre-invocation",
        )
        self.assertTrue(runner.is_pre_invocation_context("session-start"))
        self.assertTrue(runner.is_pre_invocation_context("SessionStart"))
        self.assertTrue(runner.is_pre_invocation_context("unknown", json.dumps({"hookEventName": "SessionStart"})))

        health = check_hooks_health(hooks_path)
        self.assertEqual(health["status"], "OK")
        self.assertEqual(health["failures"], [])
        self.assertIn("pre-invocation", health["checked_hooks"])

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf), mock.patch.dict(os.environ, {}, clear=True):
            rc = runner.run_hook("session-start", "{bad json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue()), {"injectSteps": []})

    def test_session_start_consumes_inbound_cid_baton_once_with_user_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "repo"
            ws.mkdir()
            state_dir = root / "state"
            state_dir.mkdir()
            xt_dir = ws / ".agents" / "artifacts" / "crosstalk"
            xt_dir.mkdir(parents=True)

            cid = "cid-target-001"
            baton_path = xt_dir / f"inbound_{cid}.json"
            baton_path.write_text(json.dumps({
                "baton_id": "baton-1",
                "from_cid": "cid-origin-999",
                "from_title": "Root Director",
                "from_project": "alpha-core",
                "to_project": "agyis-harness",
                "hop": 1,
                "max_hops": 2,
                "role_hint": "reviewer",
                "redacted": True,
                "checkpoint_path": ".agents/artifacts/checkpoints/cid-origin-999.md",
                "intent": "Verify Track C hook schema compliance.",
            }), encoding="utf-8")

            payload = {
                "hookEventName": "SessionStart",
                "conversationId": cid,
                "workspacePaths": [str(ws)],
            }
            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                out1 = pre_invocation_hook.evaluate_pre_invocation(json.dumps(payload), workspace_dir=ws)
                out2 = pre_invocation_hook.evaluate_pre_invocation(json.dumps(payload), workspace_dir=ws)

            self.assertEqual(len(out1["injectSteps"]), 1)
            step = out1["injectSteps"][0]
            sys_obj = step["systemMessage"]
            user_md = sys_obj["metadata"]["user_markdown"]
            self.assertIn("[Root Director](conversation://cid-origin-999)", user_md)
            self.assertIn("Hop `1/2`", user_md)
            self.assertIn("Redacted OK", user_md)
            self.assertIn("[Checkpoint](file://", user_md)
            self.assertIn("[AGYIS CROSSTALK SESSION BOOT]", sys_obj["systemMessage"])
            self.assertIn("Role Hint: reviewer", sys_obj["systemMessage"])

            stored = json.loads(baton_path.read_text(encoding="utf-8"))
            self.assertTrue(stored.get("consumed"))
            self.assertEqual(stored.get("consumed_by"), cid)
            self.assertEqual(out2, {"injectSteps": []})

    def test_inbound_latest_matches_fresh_workspace_and_skips_stale_or_foreign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws_a = root / "ws_a"
            ws_b = root / "ws_b"
            ws_c = root / "ws_c"
            state_dir = root / "state"
            (ws_a / ".agents" / "artifacts" / "crosstalk").mkdir(parents=True)
            (ws_b / ".agents" / "artifacts" / "crosstalk").mkdir(parents=True)
            (ws_c / ".agents" / "artifacts" / "crosstalk").mkdir(parents=True)
            state_dir.mkdir()

            latest_a = ws_a / ".agents" / "artifacts" / "crosstalk" / "inbound_latest.json"
            latest_a.write_text(json.dumps({
                "baton_id": "latest-1",
                "from_cid": "cid-origin-a",
                "target_workspace": str(ws_a),
                "created_at": time.time(),
                "role_hint": "auditor",
                "hop": 1,
                "max_hops": 2,
            }), encoding="utf-8")

            stale_b = ws_b / ".agents" / "artifacts" / "crosstalk" / "inbound_latest.json"
            stale_b.write_text(json.dumps({
                "baton_id": "stale-1",
                "from_cid": "cid-origin-b",
                "target_workspace": str(ws_b),
                "created_at": time.time() - 7200,
                "hop": 1,
                "max_hops": 2,
            }), encoding="utf-8")

            mismatch_c = ws_c / ".agents" / "artifacts" / "crosstalk" / "inbound_latest.json"
            mismatch_c.write_text(json.dumps({
                "baton_id": "mismatch-1",
                "from_cid": "cid-origin-c",
                "target_workspace": str(root / "other_project"),
                "created_at": time.time(),
                "hop": 1,
                "max_hops": 2,
            }), encoding="utf-8")

            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                stale_res = pre_invocation_hook.evaluate_session_start(
                    {"hookEventName": "SessionStart", "conversationId": "cid-2"},
                    workspace_dir=ws_b,
                )
                self.assertEqual(stale_res, {"injectSteps": []})

                mismatch_res = pre_invocation_hook.evaluate_session_start(
                    {"hookEventName": "SessionStart", "conversationId": "cid-2", "workspacePaths": [str(ws_c)]},
                )
                self.assertEqual(mismatch_res, {"injectSteps": []})

                matched = pre_invocation_hook.evaluate_session_start(
                    {"hookEventName": "SessionStart", "conversationId": "cid-2", "workspacePaths": [str(ws_a)]},
                    workspace_dir=ws_a,
                )
                self.assertEqual(len(matched["injectSteps"]), 1)
                self.assertIn("user_markdown", matched["injectSteps"][0]["systemMessage"]["metadata"])

    def test_pending_advisory_user_markdown_drain_and_plain_compat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir()
            cid = "cid-adv-1"
            wire_compat.enqueue_pending_advisory(
                cid,
                "[AGYIS CROSSTALK] Model note",
                user_markdown="> **Banner**",
                state_dir=state_dir,
            )
            steps = wire_compat.drain_pending_advisory_steps(cid, state_dir=state_dir)
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0]["systemMessage"]["systemMessage"], "[AGYIS CROSSTALK] Model note")
            self.assertEqual(steps[0]["systemMessage"]["metadata"]["user_markdown"], "> **Banner**")
            self.assertEqual(wire_compat.drain_pending_advisory_steps(cid, state_dir=state_dir), [])

            wire_compat.enqueue_pending_advisory(cid, "Plain msg", user_markdown="> Plain md", state_dir=state_dir)
            plain_list = wire_compat.drain_pending_advisories(cid, state_dir=state_dir)
            self.assertEqual(plain_list, ["Plain msg"])


class TestCrosstalkRolePinningAndPrompts(unittest.TestCase):
    def test_turn0_crosstalk_role_markers_and_slash_command_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "plan.md").write_text("# Plan", encoding="utf-8")
            state_dir = ws / "state"
            state_dir.mkdir()

            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                for raw_role, expected_macro in (
                    ("reviewer", "forensic_auditor"),
                    ("auditor", "forensic_auditor"),
                    ("investigator", "forensic_auditor"),
                    ("builder", "deep_execution"),
                    ("coordinator", "flight_director"),
                    ("planner", "flight_director"),
                ):
                    role, meta = role_pinning.classify_agent_role_details(
                        {"conversationId": f"cid-{raw_role}", "prompt": f"[CROSSTALK-ROLE: {raw_role}] fix bug /plan"},
                        workspace_dir=ws,
                    )
                    self.assertEqual(role, expected_macro)
                    self.assertEqual(meta["agent_name"], raw_role)

                resolved_role, exact_agent = role_lineage.resolve_hook_role_and_agent(
                    {"conversationId": "cid-lin-1", "prompt": "[CROSSTALK-ROLE: auditor] Check tests"},
                    conv_id="cid-lin-1",
                    state_dir=state_dir,
                )
                self.assertEqual(resolved_role, "forensic_auditor")
                self.assertEqual(exact_agent, "auditor")

        self.assertNotIn("crosstalk", role_pinning.NATIVE_SYSTEM_SLASH_COMMANDS)
        self.assertFalse(role_pinning.is_native_slash_command("/crosstalk handoff"))
        advisory = role_prompts.build_compaction_advisory("flight_director", is_subagent=False, tokens=350_000, max_context_tokens=512_000)
        self.assertIn("/crosstalk", advisory)


class TestDecisionD6AdvisoryOnlyHooks(unittest.TestCase):
    def test_command_safety_crosstalk_advisories_allow_and_preserve_pause_deny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "ws"
            ws.mkdir()
            state_dir = root / "state"
            state_dir.mkdir()

            cmds = [
                "curl -X POST http://127.0.0.1:42/exa.language_server_pb.ConversationService/DeleteConversation -d '{\"id\":\"x\"}'",
                "curl -X POST http://127.0.0.1:42/exa.language_server_pb.ConversationService/CreateConversation -d '{}'",
                "agyis crosstalk handoff --hop 3/2 --from cid-same --to cid-same --note 'read .dirtyroom/.env'",
            ]
            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                for idx, cmd in enumerate(cmds):
                    cid = f"cid-cs-{idx}"
                    out_buf = io.StringIO()
                    err_buf = io.StringIO()
                    stdin_payload = json.dumps({
                        "conversationId": cid,
                        "workspacePaths": [str(ws)],
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    })
                    with mock.patch("sys.stdin", io.StringIO(stdin_payload)), mock.patch("sys.stdout", out_buf), mock.patch("sys.stderr", err_buf):
                        command_safety_hook.main()
                    resp = json.loads(out_buf.getvalue())
                    self.assertEqual(resp["decision"], "allow", f"Expected D6 allow for {cmd}, got {resp}")
                    self.assertIn("AGYIS CROSSTALK ADVISORY", resp.get("reason", ""))
                    self.assertIn("AGYIS CROSSTALK ADVISORY", err_buf.getvalue())

                    steps = pre_invocation_hook.evaluate_pre_invocation(
                        json.dumps({"hookEventName": "PreInvocation", "conversationId": cid, "workspacePaths": [str(ws)], "step": 1, "prompt": "hi"}),
                        workspace_dir=ws,
                    )["injectSteps"]
                    self.assertTrue(any("user_markdown" in s.get("systemMessage", {}).get("metadata", {}) for s in steps))

                # Zero-Kill pause_gate protection must remain a strict deny
                art_dir = ws / ".agents" / "artifacts"
                art_dir.mkdir(parents=True, exist_ok=True)
                (art_dir / "pause_gate.json").write_text(json.dumps({"status": "paused"}), encoding="utf-8")
                dec, _ = command_safety_hook.check_pause_safety("run_command", {"CommandLine": "kill -9 12345"}, workspace_dir=ws)
                self.assertEqual(dec, "deny")

    def test_anti_loop_crosstalk_polling_is_advisory_only_while_task_logs_deny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir()
            cid = "cid-poll-1"
            poll_args = {"CommandLine": "curl -s http://127.0.0.1:42/exa.language_server_pb.ConversationService/GetConversation -d '{}'"}
            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                res1 = anti_loop_hook.check_anti_loop("run_command", poll_args, conv_id=cid, state_dir=state_dir)
                self.assertEqual(res1["decision"], "allow")
                for attempt in range(4):
                    err_buf = io.StringIO()
                    with mock.patch("sys.stderr", err_buf):
                        res_n = anti_loop_hook.check_anti_loop("run_command", poll_args, conv_id=cid, state_dir=state_dir)
                    self.assertEqual(res_n["decision"], "allow", f"Attempt {attempt + 2} should never deny GetConversation polling")
                    self.assertIn("GetConversation/ListConversations", res_n.get("reason", ""))
                    self.assertIn("AGYIS ANTI-LOOP", err_buf.getvalue())
                drained = wire_compat.drain_pending_advisory_steps(cid, state_dir=state_dir)
                self.assertTrue(any("user_markdown" in s.get("systemMessage", {}).get("metadata", {}) for s in drained))

                list_sig = {"name": "run_command", "args": {"CommandLine": "curl -s http://127.0.0.1:42/exa.language_server_pb.ConversationService/ListConversations -d '{}'"}}
                self.assertTrue(anti_loop_hook._is_background_poll(list_sig))
                for _ in range(4):
                    self.assertEqual(
                        anti_loop_hook.check_anti_loop("run_command", list_sig["args"], conv_id="cid-poll-list", state_dir=state_dir)["decision"],
                        "allow",
                    )

                # Existing background task log inspection still hard-denies on >=3 consecutive calls
                task_args = {"CommandLine": "tail -n 20 .system_generated/tasks/worker1.log"}
                for _ in range(2):
                    self.assertEqual(
                        anti_loop_hook.check_anti_loop("run_command", task_args, conv_id="cid-task-1", state_dir=state_dir)["decision"],
                        "allow",
                    )
                self.assertEqual(
                    anti_loop_hook.check_anti_loop("run_command", task_args, conv_id="cid-task-1", state_dir=state_dir)["decision"],
                    "deny",
                )

    def test_drift_guards_subagents_false_and_auditor_crosstalk_are_advisory_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            state_dir.mkdir()
            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                auditor_xt = {
                    "conversationId": "cid-drift-1",
                    "role": "agyis_auditor",
                    "toolCall": {
                        "name": "run_command",
                        "args": {"CommandLine": "curl -s http://127.0.0.1:42/exa.language_server_pb.ConversationService/CreateConversation -d '{}'"},
                    },
                }
                err_buf = io.StringIO()
                out_buf = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(json.dumps(auditor_xt))), mock.patch("sys.stdout", out_buf), mock.patch("sys.stderr", err_buf):
                    anti_drift_hook.main()
                resp = json.loads(out_buf.getvalue())
                self.assertEqual(resp["decision"], "allow")
                self.assertIn("AGYIS CROSSTALK ROLE ADVISORY", resp.get("reason", ""))
                self.assertIn("AGYIS CROSSTALK ROLE ADVISORY", err_buf.getvalue())

                subagents_false_payload = {
                    "conversationId": "cid-drift-2",
                    "subagents": False,
                    "role": "custom_worker",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "agyis crosstalk handoff --to cid-2"}},
                }
                res_sf = drift_guards.check_auditor_write_block(subagents_false_payload)
                self.assertIsNotNone(res_sf)
                self.assertEqual(res_sf["decision"], "allow")

                coord_xt = {
                    "conversationId": "cid-coord-1",
                    "role": "agyis_coordinator",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "agyis crosstalk handoff --to cid-2"}},
                }
                self.assertIsNone(drift_guards.check_crosstalk_role_guard(coord_xt))

                auditor_write = {
                    "conversationId": "cid-drift-3",
                    "role": "agyis_auditor",
                    "toolCall": {"name": "write_to_file", "args": {"TargetFile": "src/app.py"}},
                }
                self.assertEqual(drift_guards.check_auditor_write_block(auditor_write)["decision"], "deny")


class TestFenceDispatchSplit(unittest.TestCase):
    def test_fence_gates_size_reexports_and_crosstalk_orchestrator_stop(self) -> None:
        gates_path = Path(fence_gates.__file__)
        self.assertLess(len(gates_path.read_text(encoding="utf-8").splitlines()), 650)
        for name in (
            "_resolve_isolated_native_dirs",
            "_classify_dispatched_subagents",
            "_has_dispatched_subagents",
            "_evaluate_orchestrator_stop",
            "_emit_stop_deadlock_diagnostic",
        ):
            self.assertIs(getattr(fence_gates, name), getattr(fence_dispatch, name))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "ws"
            state_dir = root / "state"
            xt_dir = ws / ".agents" / "artifacts" / "crosstalk"
            xt_dir.mkdir(parents=True)
            state_dir.mkdir()

            conv_id = "cid-orch-1"
            (xt_dir / "inbound_peer.json").write_text(
                json.dumps({"from_cid": conv_id, "to_cid": "cid-peer-2", "consumed": False}),
                encoding="utf-8",
            )
            self.assertEqual(fence_dispatch._classify_dispatched_subagents(ws, {"conversationId": conv_id}, conv_id=conv_id), "none")
            self.assertTrue(fence_dispatch._has_crosstalk_handoff(ws, conv_id=conv_id))

            # Even if legacy teamwork dir exists, an active outbound crosstalk baton from this CID permits orchestrator stop
            (ws / ".agents" / "teamwork" / "worker_old").mkdir(parents=True)
            self.assertEqual(fence_dispatch._classify_dispatched_subagents(ws, {"conversationId": conv_id}, conv_id=conv_id), "legacy")
            stop_res = fence_dispatch._evaluate_orchestrator_stop(
                {"code_dirty": False, "spec_dirty": False},
                ws,
                conv_id,
                state_dir,
                None,
                {"conversationId": conv_id},
            )
            self.assertEqual(stop_res, {"decision": "allow"})

            handoff_res = fence_gates._evaluate_handoff_gate(
                {"last_modified_files": [str(xt_dir / "handoff_baton.md")], "turn_modified_files": [], "session_modified_files": []},
                ws,
                verified_tier=None,
                session_has_code=True,
                conv_id=conv_id,
                state_dir=state_dir,
                payload=None,
            )
            self.assertIsNone(handoff_res)

    def test_session_start_sanitizes_origin_title_brackets_and_invalid_cid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "repo"
            state_dir = root / "state"
            xt_dir = ws / ".agents" / "artifacts" / "crosstalk"
            xt_dir.mkdir(parents=True)
            state_dir.mkdir()

            # Valid CID with nested [v1] brackets & newline inside origin title
            cid_ok = "cid-target-ok"
            (xt_dir / f"inbound_{cid_ok}.json").write_text(json.dumps({
                "baton_id": "b-ok",
                "from_cid": "cid-origin-ok",
                "from_title": "Release [v1]\nVerify",
                "to_project": "agyis-harness",
            }), encoding="utf-8")

            # Invalid CID must fall back cleanly without malformed conversation:// link
            cid_bad = "cid-target-bad"
            (xt_dir / f"inbound_{cid_bad}.json").write_text(json.dumps({
                "baton_id": "b-bad",
                "from_cid": "../bad cid?x=1",
                "from_title": "Unsafe [v2]\nOrigin",
                "to_project": "agyis-harness",
            }), encoding="utf-8")

            with mock.patch.dict(os.environ, _isolated_env(state_dir), clear=True):
                res_ok = pre_invocation_hook.evaluate_session_start(
                    {"hookEventName": "SessionStart", "conversationId": cid_ok, "workspacePaths": [str(ws)]},
                    workspace_dir=ws,
                )
                res_bad = pre_invocation_hook.evaluate_session_start(
                    {"hookEventName": "SessionStart", "conversationId": cid_bad, "workspacePaths": [str(ws)]},
                    workspace_dir=ws,
                )

            umd_ok = res_ok["injectSteps"][0]["systemMessage"]["metadata"]["user_markdown"]
            self.assertIn("[Release (v1) Verify](conversation://cid-origin-ok)", umd_ok)
            self.assertNotIn("[Release [v1]", umd_ok)

            umd_bad = res_bad["injectSteps"][0]["systemMessage"]["metadata"]["user_markdown"]
            self.assertIn("Unsafe (v2) Origin", umd_bad)
            self.assertNotIn("conversation://", umd_bad)


if __name__ == "__main__":
    unittest.main()
