# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for Wave 1.2 Track 2 hardening and 2.35.2 compatibility."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from harness.cli_parsers_core import register_core_parsers
from harness.delivery.sync_check import run_sync_check
from harness.hooks.anti_drift_hook import (
    _is_mutating_shell_command,
    check_auditor_write_block,
    check_flight_director_write_guard,
    main as anti_drift_main,
    reset_flight_director_edits,
)
from harness.hooks.anti_loop_hook import _compact_history_args, check_anti_loop, main as anti_loop_main
from harness.hooks.command_safety_hook import find_hermetic_uv_python_bin
from harness.hooks.completion_fence_hook import evaluate_stop, main as completion_fence_main
from harness.hooks.fence_state import clear_spec_dirty, load_state, record_edit
from harness.hooks.mcp_normalizer import _discover_known_mcp_servers, normalize_mcp_tool_call
from harness.hooks.output_compactor_hook import process_payload
from harness.hooks.pre_invocation_hook import evaluate_pre_invocation
from harness.hooks.role_lineage import resolve_hook_role_and_agent
from harness.hooks.runner import ALIASES, HOOK_MODULES
from harness.hooks.wire_compat import PRE_TOOL_WIRE_KEYS, STOP_WIRE_KEYS, drain_pending_advisories
from harness.remote.safety import SSH_TIMEOUT_OPTIONS, get_ssh_timeout_options
from harness.runtime.aff import MAX_AFF_DISK_CACHE, _collect_pkg_facts, audit_architectural_fitness
from harness.runtime.hygiene_checks import check_hooks_health
from harness.runtime.tool_checks_common import find_hermetic_uv_python
from harness.subagents.spec import (
    ANTIGRAVITY_PLATFORM_TOOLS,
    CANONICAL_PLATFORM_TOOLS,
    MAX_AGENT_TOOLS,
    ROOT_PLAN_MODE_TOOLS,
)
from harness.subagents.validator import validate_agent_spec


class TestWave12CompatAndGuards(unittest.TestCase):
    """Contract and regression tests for Track 2 deliverables."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mcp_longest_prefix_discovery_and_env_dirs(self) -> None:
        app_dir = self.root / "antigravity"
        schema_dir = app_dir / "mcp" / "google-workspace"
        schema_dir.mkdir(parents=True)
        (app_dir / "mcp_config.json").write_text(
            json.dumps({"mcpServers": {"google_workspace": {}, "google": {}}}),
            encoding="utf-8",
        )
        (schema_dir / "search_gmail_messages.json").write_text(
            json.dumps({"properties": {"query": {"type": "string"}, "maxResults": {"type": "integer"}}}),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": str(app_dir)}, clear=False):
            servers = _discover_known_mcp_servers()
            self.assertIn("google_workspace", servers)
            self.assertIn("google-workspace", servers)
            self.assertLess(
                servers.index("google_workspace"),
                servers.index("google"),
            )
            dec, ow, reason = normalize_mcp_tool_call(
                "mcp_google_workspace_search_gmail_messages",
                {"Query": "from:ops", "max_results": 5},
            )
        self.assertEqual(dec, "allow")
        self.assertIsNotNone(ow)
        self.assertEqual(ow.get("query"), "from:ops")
        self.assertEqual(ow.get("maxResults"), 5)
        self.assertIn("normalized argument", reason or "")

    def test_numeric_cpython_discovery_beats_lexical_order(self) -> None:
        uv_dir = self.root / ".local" / "share" / "uv" / "python"
        for ver in ("cpython-3.11.9-linux", "cpython-3.13.1-linux", "cpython-3.100.0-linux"):
            bin_p = uv_dir / ver / "bin" / "python3"
            bin_p.parent.mkdir(parents=True, exist_ok=True)
            bin_p.write_text("#!/bin/sh\n", encoding="utf-8")
            bin_p.chmod(0o755)
        with patch.object(Path, "home", return_value=self.root):
            found = find_hermetic_uv_python()
            found_bin = find_hermetic_uv_python_bin()
        self.assertIsNotNone(found)
        self.assertIn("cpython-3.100.0", str(found))
        self.assertEqual(found_bin, found.parent)

    def test_anti_loop_compacts_history_args_and_catches_oversized_loops(self) -> None:
        big_text = "A" * 800
        compacted = _compact_history_args({"Content": big_text, "ok": "short"})
        self.assertTrue(compacted["Content"].startswith("__sha256:"))
        self.assertIn(":800:", compacted["Content"])
        self.assertEqual(compacted["ok"], "short")

        state_dir = self.root / "loop_state"
        for _ in range(3):
            res = check_anti_loop(
                "write_file",
                {"TargetFile": "foo.py", "CodeContent": big_text},
                conv_id="conv-loop-big",
                state_dir=state_dir,
            )
            self.assertEqual(res["decision"], "allow")
        blocked = check_anti_loop(
            "write_file",
            {"TargetFile": "foo.py", "CodeContent": big_text},
            conv_id="conv-loop-big",
            state_dir=state_dir,
        )
        self.assertEqual(blocked["decision"], "deny")
        saved = json.loads((state_dir / "history_conv-loop-big.json").read_text(encoding="utf-8"))
        self.assertTrue(saved[-1]["args"]["CodeContent"].startswith("__sha256:"))

    def test_output_compactor_command_only_error_regex_gate(self) -> None:
        huge_log = ("line ok\n" * 5500) + "Command failed with exit code: 2"
        state_dir = self.root / "compactor"
        read_res = process_payload(
            {"toolCall": {"name": "read_file", "args": {"AbsolutePath": "/tmp/x.log"}}, "output": huge_log},
            state_dir=state_dir,
        )
        self.assertTrue(read_res["wasCompacted"])
        self.assertFalse(read_res["isError"])
        self.assertEqual(read_res["exitCode"], 0)

        cmd_res = process_payload(
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}}, "output": huge_log},
            state_dir=state_dir,
        )
        self.assertFalse(cmd_res["wasCompacted"])
        self.assertTrue(cmd_res["isError"])
        self.assertEqual(cmd_res["exitCode"], 2)

    def test_ssh_timeout_options_honor_state_dir_env(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGYIS_HARNESS_STATE_DIR", None)
            os.environ.pop("PSL_HARNESS_STATE_DIR", None)
            self.assertEqual(get_ssh_timeout_options(), SSH_TIMEOUT_OPTIONS)
        with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(self.root)}, clear=False):
            opts = get_ssh_timeout_options()
            self.assertIn(f"-o ControlPath={self.root}/ssh/cm_%C", opts)

    def test_recursive_mutating_shell_and_inline_patterns(self) -> None:
        self.assertTrue(_is_mutating_shell_command("bash -c 'rm -rf build/'"))
        self.assertTrue(_is_mutating_shell_command('sh -lc "echo hi > out.py"'))
        self.assertTrue(_is_mutating_shell_command('zsh -c "bash -c \'touch a.py\'"'))
        self.assertTrue(_is_mutating_shell_command('bash -c "sh -c \'zsh -c \\"mkdir d\\"\'"'))
        self.assertTrue(_is_mutating_shell_command('python3 -c "from pathlib import Path; Path(\'x.py\').write_text(\'a\')"'))
        self.assertTrue(_is_mutating_shell_command('python3 -c "import os; os.chmod(\'x.py\', 0o755)"'))
        self.assertTrue(_is_mutating_shell_command('node -e "fs.writeFileSync(\'x.py\', \'1\')"'))
        self.assertFalse(_is_mutating_shell_command("bash -c 'git status && pwd'"))
        self.assertFalse(_is_mutating_shell_command('zsh -c "cat README.md"'))

    def test_live_lineage_role_enforcement_and_manage_subagents_fd_reset(self) -> None:
        app_dir = self.root / "app"
        brain_root = app_dir / "brain"
        brain_root.mkdir(parents=True)
        state_dir = self.root / "state"
        db_path = app_dir / "conversation_summaries.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE conversation_summaries "
                "(conversation_id TEXT PRIMARY KEY, parent_conversation_id TEXT, agent_name TEXT, nesting_depth INTEGER)"
            )
            conn.executemany(
                "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)",
                [
                    ("cid-custodian", "cid-root", "agyis_custodian", 1),
                    ("cid-investigator", "cid-root", "agyis_investigator", 1),
                    ("cid-reviewer", "cid-root", "agyis_reviewer", 1),
                    ("cid-builder", "cid-root", "agyis_builder", 1),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        with patch.dict(
            os.environ,
            {
                "ANTIGRAVITY_APP_DATA_DIR": str(app_dir),
                "ANTIGRAVITY_BRAIN_DIR": str(brain_root),
                "AGYIS_HARNESS_STATE_DIR": str(state_dir),
            },
            clear=False,
        ):
            blk = check_auditor_write_block({
                "conversationId": "cid-custodian",
                "toolCall": {"name": "write_file", "args": {"TargetFile": "harness/a.py"}},
            })
            self.assertEqual((blk or {}).get("decision"), "deny")
            self.assertIn("Custodian", (blk or {}).get("reason", ""))
            allow_git = check_auditor_write_block({
                "conversationId": "cid-custodian",
                "toolCall": {"name": "run_command", "args": {"CommandLine": "git commit -m 'ok'"}},
            })
            self.assertIsNone(allow_git)

            inv_code = check_auditor_write_block({
                "conversationId": "cid-investigator",
                "toolCall": {"name": "edit_file", "args": {"TargetFile": "harness/a.py"}},
            })
            self.assertEqual((inv_code or {}).get("decision"), "deny")
            inv_scratch = check_auditor_write_block({
                "conversationId": "cid-investigator",
                "toolCall": {"name": "write_file", "args": {"TargetFile": "scratch/rca.py"}},
            })
            self.assertIsNone(inv_scratch)

            rev_cmd = check_auditor_write_block({
                "conversationId": "cid-reviewer",
                "toolCall": {"name": "run_command", "args": {"CommandLine": "rm -f a.py"}},
            })
            self.assertEqual((rev_cmd or {}).get("decision"), "deny")

            # Flight director counter reset on manage_subagents spawn
            fd_cid = "fd-reset-cid"
            reset_flight_director_edits(fd_cid)
            for idx in range(4):
                check_flight_director_write_guard({
                    "role": "flight_director",
                    "conversationId": fd_cid,
                    "toolCall": {"name": "write_file", "args": {"TargetFile": f"src/f{idx}.py"}},
                })
            edits_file = state_dir / f"cockpit_direct_edits_{fd_cid}.json"
            self.assertTrue(edits_file.is_file())
            with patch("sys.stdin", io.StringIO(json.dumps({
                "conversationId": fd_cid,
                "toolCall": {"name": "manage_subagents", "args": {"action": "spawn", "agent": "agyis_builder"}},
            }))), patch("sys.stdout", new_callable=io.StringIO):
                anti_drift_main()
            self.assertFalse(edits_file.exists())

            # Flight director counter reset via artifactDirectoryPath UUID when conversationId omitted
            art_uuid = "11112222-3333-4444-8555-666677778888"
            art_path = str(brain_root / art_uuid)
            reset_flight_director_edits(art_uuid)
            for idx in range(4):
                check_flight_director_write_guard({
                    "role": "flight_director",
                    "artifactDirectoryPath": art_path,
                    "toolCall": {"name": "write_file", "args": {"TargetFile": f"src/g{idx}.py"}},
                })
            art_edits_file = state_dir / f"cockpit_direct_edits_{art_uuid}.json"
            self.assertTrue(art_edits_file.is_file())
            with patch("sys.stdin", io.StringIO(json.dumps({
                "artifactDirectoryPath": art_path,
                "toolCall": {"name": "invoke_subagent", "args": {"TypeName": "agyis_builder"}},
            }))), patch("sys.stdout", new_callable=io.StringIO):
                anti_drift_main()
            self.assertFalse(art_edits_file.exists())

    def test_clear_spec_dirty_all_and_stop_termination_bypass(self) -> None:
        sdir = self.root / "fence_state"
        record_edit("docs/specs/spec_a.md", conv_id="c1", state_dir=sdir)
        record_edit("docs/specs/spec_b.md", conv_id="c2", state_dir=sdir)
        record_edit("src/code.py", conv_id="c3", state_dir=sdir)
        clear_spec_dirty(state_dir=sdir, clear_all=True)
        self.assertFalse(load_state("c1", state_dir=sdir)["spec_dirty"])
        self.assertFalse(load_state("c2", state_dir=sdir)["spec_dirty"])
        self.assertTrue(load_state("c3", state_dir=sdir)["code_dirty"])

        for term in ("USER_CANCELED", "ERROR", "MAX_TOKEN_BUDGET_EXCEEDED", "MAX_INVOCATIONS", "MAX_FORCED_INVOCATIONS", "TERMINAL_CUSTOM_HOOK"):
            res = evaluate_stop(conv_id="c3", state_dir=sdir, payload={"terminationReason": term})
            self.assertEqual(res, {"decision": "allow"})
        self.assertEqual(evaluate_stop(conv_id="c3", state_dir=sdir, payload={"error": "stream closed"}), {"decision": "allow"})

    def test_strict_wire_keys_and_pending_advisory_drain(self) -> None:
        sdir = self.root / "wire_state"
        err_buf = io.StringIO()
        with contextlib.redirect_stderr(err_buf), patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(sdir)}, clear=False):
            with patch("sys.stdin", io.StringIO(json.dumps({
                "conversationId": "wire-conv",
                "role": "deep_execution",
                "step_count": 82,
                "toolCall": {"name": "grep_search", "args": {"Query": "foo"}},
            }))), patch("sys.stdout", new_callable=io.StringIO) as out_loop:
                anti_loop_main()
            parsed_loop = json.loads(out_loop.getvalue().strip())
            self.assertTrue(set(parsed_loop).issubset(PRE_TOOL_WIRE_KEYS))
            self.assertNotIn("advisory", parsed_loop)

            record_edit("src/app.py", conv_id="wire-stop", state_dir=sdir)
            for _ in range(3):
                with patch("sys.stdin", io.StringIO(json.dumps({"conversationId": "wire-stop", "stateDir": str(sdir)}))), \
                     patch("sys.stdout", new_callable=io.StringIO) as out_stop:
                    completion_fence_main()
                parsed_stop = json.loads(out_stop.getvalue().strip())
                self.assertTrue(set(parsed_stop).issubset(STOP_WIRE_KEYS))
                self.assertNotIn("warning", parsed_stop)

            pre_res = evaluate_pre_invocation({"conversationId": "wire-stop", "stepIdx": 5}, workspace_dir=self.root)
            steps = [s.get("systemMessage", {}).get("systemMessage", "") for s in pre_res.get("injectSteps", [])]
            self.assertTrue(any("Anti-deadlock valve tripped" in m for m in steps))
            self.assertEqual(drain_pending_advisories("wire-stop", state_dir=sdir), [])

    def test_cli_choices_v235_tools_hooks_health_aff_and_sync_check(self) -> None:
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_core_parsers(sub)
        hook_choices = sub._name_parser_map["hook"]._actions[1].choices
        self.assertEqual(set(hook_choices), set(HOOK_MODULES) | set(ALIASES))
        audit_choices = sub._name_parser_map["audit"]._actions[1].choices
        self.assertIn("sync-check", audit_choices)

        self.assertEqual(len(CANONICAL_PLATFORM_TOOLS), 19)
        self.assertLessEqual(len(CANONICAL_PLATFORM_TOOLS), MAX_AGENT_TOOLS)
        self.assertTrue({"update_focus", "update_steps", "manage_subagents"}.issubset(CANONICAL_PLATFORM_TOOLS))
        self.assertEqual(ROOT_PLAN_MODE_TOOLS, frozenset({"enter_plan_mode", "exit_plan_mode"}))
        self.assertTrue(ROOT_PLAN_MODE_TOOLS.issubset(ANTIGRAVITY_PLATFORM_TOOLS))

        bad_agent = self.root / "bad_agent.md"
        bad_agent.write_text(
            "---\nname: x\narchetype: executioner\ntools: [read_file, enter_plan_mode]\n---\nZero-Exploration Invariant\n",
            encoding="utf-8",
        )
        errs = validate_agent_spec(bad_agent)
        self.assertTrue(any("root-session-only" in e for e in errs))

        script_hook = self.root / "my_custom_hook.py"
        script_hook.write_text("import json\nprint(json.dumps({'decision': 'allow'}))\n", encoding="utf-8")
        hooks_json = self.root / "hooks.json"
        hooks_json.write_text(
            json.dumps({"custom": {"PreToolUse": [{"matcher": "read_file", "hooks": [{"type": "command", "command": f"python3 {script_hook}"}]}]}}),
            encoding="utf-8",
        )
        hh = check_hooks_health(hooks_path=hooks_json)
        self.assertEqual(hh["status"], "OK")
        self.assertIn("audited_paths", hh)
        self.assertIn(str(hooks_json), hh["audited_paths"])

        # JS unbounded cache smell + bounded AFF disk cache + sync-check parity
        pkg = self.root / "pkg"
        (pkg / "assets").mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "assets" / "leaky.js").write_text("const resultCache = new Map();\nfunction add(k, v) { resultCache.set(k, v); }\n", encoding="utf-8")
        aff_rep = audit_architectural_fitness(workspace_root=self.root, target_pkg="pkg")
        self.assertTrue(any(d.smell_type == "UNBOUNDED_CACHE" and "leaky.js" in d.file for d in aff_rep.smell_defects))

        oversized_cache = {f"k{i}": {"total_lines": 1, "top_level_defs": 0, "class_methods": [], "imports": [], "smells": []} for i in range(MAX_AFF_DISK_CACHE + 25)}
        with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": str(self.root / "aff_state")}, clear=False):
            cfile = self.root / "aff_state" / "aff_facts_v1.json"
            cfile.parent.mkdir(parents=True, exist_ok=True)
            cfile.write_text(json.dumps(oversized_cache), encoding="utf-8")
            py_files = [self.root / "pkg" / f"m{i}.py" for i in range(16)]
            for pf in py_files:
                pf.write_text("x = 1\n", encoding="utf-8")
            _collect_pkg_facts(py_files)
            reloaded = json.loads(cfile.read_text(encoding="utf-8"))
            self.assertLessEqual(len(reloaded), MAX_AFF_DISK_CACHE)

        (self.root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8")
        (self.root / "plugin.json").write_text('{"name": "x", "version": "1.0.0"}', encoding="utf-8")
        (self.root / "website").mkdir()
        (self.root / "website" / "index.html").write_text("<p>2,000 tests</p>", encoding="utf-8")
        tdir = self.root / "tests"
        tdir.mkdir()
        (tdir / "test_sample.py").write_text(
            "import unittest\nclass S(unittest.TestCase):\n    def test_ok(self):\n        self.assertEqual(1, 1)\n",
            encoding="utf-8",
        )
        t0 = time.perf_counter()
        sc_default = run_sync_check(workspace_root=self.root, include_site=False)
        sc_site = run_sync_check(workspace_root=self.root, include_site=True)
        self.assertEqual(sc_default["status"], "PASS")
        self.assertEqual(sc_site["status"], "FAIL")
        self.assertLess(time.perf_counter() - t0, 0.5)

    def test_anti_loop_live_brain_sticky_lookup_and_fd_guard_cid_parity(self) -> None:
        app_dir = self.root / "app"
        brain_dir = app_dir / "brain"
        state_dir = self.root / "state"
        ws_dir = self.root / "ws"
        state_dir.mkdir(parents=True)

        cid_exec = "exec-sticky-001"
        cid_fd = "fd-sticky-002"
        cid_ws = "ws-sticky-003"
        cid_legacy = "legacy-sticky-005"
        for cid, role in ((cid_exec, "deep_execution"),):
            agyis_dir = brain_dir / cid / ".agyis"
            agyis_dir.mkdir(parents=True)
            (agyis_dir / f"role_state_{cid}.json").write_text(
                json.dumps({"conversation_id": cid, "checkpoint": 0, "role": role, "source": "pillar_1"}),
                encoding="utf-8",
            )
        # Legacy persisted sticky role_state_<cid>.json with "epoch" key (backwards-compat fallback)
        for cid, role in ((cid_fd, "flight_director"), (cid_legacy, "deep_execution")):
            agyis_dir = brain_dir / cid / ".agyis"
            agyis_dir.mkdir(parents=True)
            (agyis_dir / f"role_state_{cid}.json").write_text(
                json.dumps({"conversation_id": cid, "epoch": 0, "role": role, "source": "pillar_1"}),
                encoding="utf-8",
            )
        ws_cp = ws_dir / ".agents" / "artifacts" / "checkpoints" / cid_ws
        ws_cp.mkdir(parents=True)
        (ws_cp / f"role_state_{cid_ws}.json").write_text(
            json.dumps({"conversation_id": cid_ws, "checkpoint": 0, "role": "deep_execution"}),
            encoding="utf-8",
        )

        env = {
            "AGYIS_APP_DATA_DIR": str(app_dir),
            "AGYIS_HARNESS_STATE_DIR": str(state_dir),
        }
        with contextlib.redirect_stderr(io.StringIO()), patch.dict(os.environ, env, clear=True):
            res_exec = check_anti_loop(
                "grep_search",
                {"Query": "foo"},
                conv_id=cid_exec,
                step_count=85,
                state_dir=None,
            )
            self.assertEqual(res_exec["decision"], "allow")
            exec_advisories = drain_pending_advisories(cid_exec, state_dir=state_dir)
            self.assertTrue(any("CHECKPOINT HORIZON: 85/80" in m for m in exec_advisories))

            # Verify legacy "epoch" sticky state is honored in pre_invocation_hook & role_pinning
            res_legacy_pre = evaluate_pre_invocation(
                {"conversationId": cid_legacy, "step_count": 80},
                workspace_dir=ws_dir,
            )
            legacy_msgs = [
                s.get("systemMessage", {}).get("systemMessage", "")
                for s in res_legacy_pre.get("injectSteps", [])
                if isinstance(s.get("systemMessage"), dict)
            ]
            self.assertTrue(any("[AGYIS CHECKPOINT HORIZON ADVISORY: Checkpoint step 80/80" in m for m in legacy_msgs))
            self.assertTrue(any("DEEP_EXECUTION" in m for m in legacy_msgs))
            self.assertFalse(any("POST-COMPACTION" in m for m in legacy_msgs))

            res_fd = check_anti_loop(
                "grep_search",
                {"Query": "foo"},
                conv_id=cid_fd,
                step_count=85,
                state_dir=None,
            )
            self.assertEqual(res_fd["decision"], "allow")
            self.assertEqual(drain_pending_advisories(cid_fd, state_dir=state_dir), [])

            self.assertEqual(
                resolve_hook_role_and_agent({"conversationId": cid_ws, "workspacePaths": [str(ws_dir)]}),
                ("deep_execution", None),
            )

            live_fd_cid = "fd-live-parity-004"
            with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATION_ID": live_fd_cid}, clear=False):
                for idx in range(4):
                    check_flight_director_write_guard({
                        "role": "flight_director",
                        "toolCall": {"name": "write_file", "args": {"TargetFile": f"src/m{idx}.py"}},
                    })
                self.assertTrue((state_dir / f"cockpit_direct_edits_{live_fd_cid}.json").is_file())
                fd_advisories = drain_pending_advisories(live_fd_cid, state_dir=state_dir)
                self.assertTrue(any("[AGYIS FLIGHT DIRECTOR] Advisory" in m for m in fd_advisories))
