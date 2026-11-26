# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic verification suite for Wave 1.3 Track 2:
1. ASCII BEL (\\a) elimination & Orbital Aegis NO_COLOR-safe terminal token gauge.
2. Unified [AGYIS ...] branding across all hook banners and stderr prefixes.
3. Single-width geometric glyphs & clean Markdown report formatting.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.delivery.compaction_checkpoint import (
    GitState,
    SubagentEntry,
    generate_compaction_checkpoint,
    main as checkpoint_main,
)
from harness.delivery.workspace_probe import format_command_dictionary
from harness.hooks.anti_drift_hook import (
    check_auditor_write_block,
    check_drift,
    check_flight_director_write_guard,
    check_ledger_cluster_tables,
    check_plan_mode_lock,
    reset_flight_director_edits,
)
from harness.hooks.anti_loop_hook import check_anti_loop
from harness.hooks.command_safety_hook import (
    check_pause_safety,
    check_preflight_tool_availability,
    sanitize_command,
)
from harness.hooks.completion_fence_hook import _is_pre_tool_denied_by_guards
from harness.hooks.fence_gates import _has_dispatched_subagents
from harness.hooks.mcp_normalizer import load_mcp_tool_schema
from harness.hooks.output_compactor_hook import compact_output, extract_output_and_status
from harness.hooks.pre_invocation_hook import main as pre_invocation_main
from harness.hooks.runner import run_hook
from harness.hooks.token_proximity_guard import format_terminal_gauge, run_token_proximity_guard
from harness.remote.triage import RemoteTriage
from harness.subagents.routing import CANONICAL_ROUTES, format_route_briefing
from harness.subagents.succession import build_succession_prompt
from harness.utils.state import load_history


class _FakeTtyBuffer(io.StringIO):
    """Minimal StringIO stub reporting isatty() == True for ANSI TTY tests."""

    def isatty(self) -> bool:
        return True


class TestTokenGaugeAndBelRemoval(unittest.TestCase):
    """Verifies zero ASCII BEL and Orbital Aegis TrueColor / 256 / NO_COLOR gauge modes."""

    def test_no_color_and_dumb_term_emit_plain_gauge_without_bel(self) -> None:
        for env in (
            {"NO_COLOR": "1", "FORCE_COLOR": "1", "COLORTERM": "truecolor"},
            {"TERM": "dumb", "NO_COLOR": "", "FORCE_COLOR": "1"},
        ):
            with patch.dict(os.environ, env):
                for tokens in (10_000, 195_000, 245_000):
                    gauge = format_terminal_gauge(tokens, threshold=256_000)
                    self.assertIn("[AGYIS TOKEN GAUGE]", gauge)
                    self.assertNotIn("\033[", gauge)
                    self.assertNotIn("\a", gauge)

    def test_truecolor_and_256_color_orbital_aegis_styles(self) -> None:
        with patch.dict(os.environ, {"FORCE_COLOR": "1", "COLORTERM": "truecolor", "NO_COLOR": "", "TERM": "xterm-256color"}):
            safe_tc = format_terminal_gauge(10_000, threshold=256_000)
            warn_tc = format_terminal_gauge(195_000, threshold=256_000)
            crit_tc = format_terminal_gauge(245_000, threshold=256_000)
        self.assertIn("\033[38;2;42;208;137m", safe_tc)
        self.assertIn("\033[38;2;245;183;79m", warn_tc)
        self.assertIn("\033[38;2;255;107;107m", crit_tc)
        for g in (safe_tc, warn_tc, crit_tc):
            self.assertNotIn("\a", g)

        with patch.dict(os.environ, {"FORCE_COLOR": "1", "COLORTERM": "", "NO_COLOR": "", "TERM": "xterm-256color"}):
            safe_256 = format_terminal_gauge(10_000, threshold=256_000)
            warn_256 = format_terminal_gauge(195_000, threshold=256_000)
            crit_256 = format_terminal_gauge(245_000, threshold=256_000)
        self.assertIn("\033[38;5;42m", safe_256)
        self.assertIn("\033[38;5;214m", warn_256)
        self.assertIn("\033[38;5;203m", crit_256)
        for g in (safe_256, warn_256, crit_256):
            self.assertNotIn("\a", g)

    def test_tty_stream_styled_while_pipe_stays_plain(self) -> None:
        tty_buf = _FakeTtyBuffer()
        pipe_buf = io.StringIO()
        with patch.dict(os.environ, {"NO_COLOR": "", "FORCE_COLOR": "", "CLICOLOR_FORCE": "", "COLORTERM": "truecolor", "TERM": "xterm"}):
            tty_gauge = format_terminal_gauge(245_000, threshold=256_000, stream=tty_buf)
            pipe_gauge = format_terminal_gauge(245_000, threshold=256_000, stream=pipe_buf)
        self.assertIn("\033[38;2;255;107;107m", tty_gauge)
        self.assertNotIn("\033[", pipe_gauge)
        self.assertNotIn("\a", tty_gauge)
        self.assertNotIn("\a", pipe_gauge)

    def test_hooks_directory_contains_zero_bel_characters(self) -> None:
        hooks_dir = Path(__file__).resolve().parent.parent / "harness" / "hooks"
        for py_file in sorted(hooks_dir.glob("*.py")):
            text = py_file.read_text(encoding="utf-8")
            self.assertNotIn("\a", text, f"Raw ASCII BEL found in {py_file.name}")
            self.assertNotIn('"\\a"', text, f"Escaped BEL literal found in {py_file.name}")
            self.assertNotIn("'\\a'", text, f"Escaped BEL literal found in {py_file.name}")

    def test_run_token_proximity_guard_no_bel_on_critical_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conv_id = "brand-critical-conv"
            db_dir = Path(tmp)
            import sqlite3
            db_path = db_dir / f"{conv_id}.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data TEXT)")
            conn.execute(
                "INSERT INTO gen_metadata VALUES (1, ?)",
                (json.dumps({"chatStartMetadata": {"contextWindowMetadata": {"estimatedTokensUsed": 245_000, "maxContextTokens": 256_000}}}),),
            )
            conn.commit()
            conn.close()
            err = io.StringIO()
            with patch.dict(os.environ, {"ANTIGRAVITY_CONVERSATIONS_DIR": str(db_dir), "NO_COLOR": "1"}):
                res = run_token_proximity_guard({"conversationId": conv_id}, stderr=err)
            self.assertEqual(res, {"decision": "allow"})
            self.assertIn("[AGYIS TOKEN GAUGE]", err.getvalue())
            self.assertNotIn("\a", err.getvalue())
            self.assertNotIn("\033[", err.getvalue())


class TestHookBrandingUnifiedAgyis(unittest.TestCase):
    """Verifies unified [AGYIS ...] banners and stderr prefixes across hook modules."""

    def test_compactor_banners_and_warning(self) -> None:
        long_text = "\n".join(
            [f"line {i}" for i in range(120)] + ["fatal: test failure detected"] + [f"tail {i}" for i in range(120)]
        )
        compacted_diag = compact_output(long_text, max_chars=400)
        self.assertIn("[... AGYIS Compactor:", compacted_diag)
        self.assertNotIn("PSL Compactor", compacted_diag)

        plain_long = "\n".join(f"plain line {i}" for i in range(250))
        compacted_plain = compact_output(plain_long, max_chars=400)
        self.assertIn("[... AGYIS Compactor:", compacted_plain)

        with tempfile.TemporaryDirectory() as tmp:
            bad_transcript = Path(tmp) / "transcript.jsonl"
            bad_transcript.write_text("{corrupt json\n", encoding="utf-8")
            err = io.StringIO()
            with patch("sys.stderr", err):
                extract_output_and_status({"transcriptPath": str(bad_transcript), "stepIdx": 1})
            self.assertIn("[AGYIS COMPACTOR] Warning:", err.getvalue())

    def test_anti_loop_banners(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sd = Path(tmp)
            for _ in range(4):
                res = check_anti_loop("read_file", {"Path": "a.py"}, conv_id="loop-c", state_dir=sd)
            self.assertEqual(res["decision"], "deny")
            self.assertTrue(res["reason"].startswith("[AGYIS ANTI-LOOP] "))

            err = io.StringIO()
            with patch("sys.stderr", err), patch("harness.hooks.anti_loop_hook.save_history", side_effect=OSError("ro")):
                check_anti_loop("read_file", {"Path": "b.py"}, conv_id="loop-err", state_dir=sd)
            self.assertIn("[AGYIS ANTI-LOOP] Warning:", err.getvalue())

    def test_anti_drift_and_guard_prefixes(self) -> None:
        self.assertTrue(check_drift("b.py", {"a.py"}, strict=True)["reason"].startswith("[AGYIS ANTI-DRIFT] Gate:"))
        self.assertTrue(check_drift("b.py", {"a.py"}, strict=False)["reason"].startswith("[AGYIS ANTI-DRIFT] Notice:"))

        plan_deny = check_plan_mode_lock({"mode": "plan", "toolCall": {"name": "edit_file", "args": {"Path": "src/x.py"}}})
        self.assertIsNotNone(plan_deny)
        self.assertTrue(plan_deny["reason"].startswith("[AGYIS PLAN LOCK] (ADR-031):"))

        inv_deny = check_auditor_write_block({"role": "agyis_investigator", "toolCall": {"name": "edit_file", "args": {"Path": "src/x.py"}}})
        aud_deny = check_auditor_write_block({"role": "harness_auditor", "toolCall": {"name": "edit_file", "args": {"Path": "src/x.py"}}})
        cus_deny = check_auditor_write_block({"role": "agyis_custodian", "toolCall": {"name": "edit_file", "args": {"Path": "src/x.py"}}})
        pln_deny = check_auditor_write_block({"role": "agyis_planner", "toolCall": {"name": "edit_file", "args": {"Path": "src/x.py"}}})
        shl_deny = check_auditor_write_block({"role": "agyis_reviewer", "toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf build"}}})
        self.assertTrue(inv_deny["reason"].startswith("[AGYIS WRITE GUARD] Investigator Invariant:"))
        self.assertTrue(aud_deny["reason"].startswith("[AGYIS WRITE GUARD] Auditor Invariant:"))
        self.assertTrue(cus_deny["reason"].startswith("[AGYIS WRITE GUARD] Custodian Invariant:"))
        self.assertTrue(pln_deny["reason"].startswith("[AGYIS WRITE GUARD] "))
        self.assertTrue(shl_deny["reason"].startswith("[AGYIS SHELL GUARD] "))

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"AGYIS_HARNESS_STATE_DIR": tmp, "PSL_STRICT_FLIGHT_DIRECTOR": "1"}):
                reset_flight_director_edits("fd-brand")
                for idx in range(4):
                    fd_res = check_flight_director_write_guard({
                        "role": "flight_director",
                        "conversation_id": "fd-brand",
                        "toolCall": {"name": "edit_file", "args": {"Path": f"src/m{idx}.py"}},
                    })
                self.assertIsNotNone(fd_res)
                self.assertTrue(fd_res["reason"].startswith("[AGYIS FLIGHT DIRECTOR] Advisory:"))
                reset_flight_director_edits("fd-brand")

            ledger_deny = check_ledger_cluster_tables(
                "operator_ledger.md",
                "| Node | Hardware Role | Status |\n| :--- | :--- | :--- |\n| @desktop | Anchor | ACTIVE |\n",
                conv_id="ledger-brand",
                state_dir=Path(tmp),
            )
            self.assertIsNotNone(ledger_deny)
            self.assertTrue(ledger_deny["reason"].startswith("[AGYIS ANTI-DRIFT] Gate:"))

    def test_command_safety_and_mcp_normalizer_prefixes(self) -> None:
        with patch("shutil.which", return_value=None), patch("harness.hooks.command_safety_hook.get_user_path_shims", return_value=[]):
            pf = check_preflight_tool_availability("missing_tool_xyz --version")
        self.assertTrue(pf["warning"].startswith("[AGYIS PREFLIGHT] (ADR-013):"))

        _, _, mod_reason = sanitize_command("git status", promote_scratch=False)
        self.assertIn("[AGYIS COMMAND SAFETY] ", mod_reason or "")

        dec_rm, _, rm_reason = sanitize_command("rm -rf /", promote_scratch=False)
        self.assertEqual(dec_rm, "deny")
        self.assertTrue((rm_reason or "").startswith("[AGYIS COMMAND SAFETY] "))

        dec_vim, _, vim_reason = sanitize_command("vim foo.py", promote_scratch=False)
        self.assertEqual(dec_vim, "deny")
        self.assertTrue((vim_reason or "").startswith("[AGYIS COMMAND SAFETY] "))

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            gate = ws / ".agents" / "artifacts" / "pause_gate.json"
            gate.parent.mkdir(parents=True, exist_ok=True)
            gate.write_text('{"status": "paused"}', encoding="utf-8")
            p_dec, p_reason = check_pause_safety("manage_task", {"Action": "kill", "TaskId": "t1"}, workspace_dir=ws)
            self.assertEqual(p_dec, "deny")
            self.assertTrue((p_reason or "").startswith("[AGYIS COMMAND SAFETY] (Zero-Kill Swarm Parking Invariant):"))

            schema_dir = ws / "rea"
            schema_dir.mkdir(parents=True, exist_ok=True)
            (schema_dir / "bad_tool.json").write_text("{corrupt", encoding="utf-8")
            err = io.StringIO()
            with patch("sys.stderr", err), patch("harness.hooks.mcp_normalizer._get_mcp_schema_dirs", return_value=[ws]):
                load_mcp_tool_schema("rea", "bad_tool")
            self.assertIn("[AGYIS COMMAND SAFETY] Warning:", err.getvalue())

    def test_fence_preinvocation_runner_and_state_prefixes(self) -> None:
        err_fence = io.StringIO()
        with patch("sys.stderr", err_fence), patch("harness.hooks.anti_drift_hook.check_plan_mode_lock", side_effect=RuntimeError("boom")):
            _is_pre_tool_denied_by_guards("edit_file", {}, {}, None)
        self.assertIn("[AGYIS FENCE] Warning:", err_fence.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            tw = Path(tmp) / ".agents" / "teamwork"
            tw.mkdir(parents=True, exist_ok=True)
            err_tw = io.StringIO()
            with patch("sys.stderr", err_tw), patch("pathlib.Path.iterdir", side_effect=OSError("perm")):
                _has_dispatched_subagents(tmp, None)
            self.assertIn("[AGYIS FENCE] Warning:", err_tw.getvalue())

            hist = Path(tmp) / "history_bad_hist.json"
            hist.write_text("{invalid", encoding="utf-8")
            err_state = io.StringIO()
            with patch("sys.stderr", err_state):
                self.assertEqual(load_history("bad_hist", target_dir=Path(tmp)), [])
            self.assertIn("[AGYIS STATE] Warning:", err_state.getvalue())

        err_pre = io.StringIO()
        out_pre = io.StringIO()
        with patch("harness.hooks.pre_invocation_hook.evaluate_pre_invocation", side_effect=RuntimeError("boom")), \
             patch("sys.stdin", io.StringIO("{}")), \
             patch("sys.stdout", out_pre), \
             patch("sys.stderr", err_pre):
            self.assertEqual(pre_invocation_main([]), 0)
        self.assertIn("[AGYIS PRE-INVOCATION HOOK] Error:", err_pre.getvalue())

        err_run = io.StringIO()
        out_run = io.StringIO()
        with patch("sys.stdout", out_run), patch("sys.stderr", err_run):
            rc = run_hook("nonexistent-hook-xyz", payload_str="{}")
        self.assertEqual(rc, 0)
        self.assertIn("[AGYIS FAIL-OPEN HOOK RUNNER]", err_run.getvalue())


class TestMarkdownReportHarmonization(unittest.TestCase):
    """Verifies single-width geometric glyphs and clean Markdown output across report generators."""

    def test_compaction_checkpoint_markdown_and_cli_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            plan = ws / ".agents" / "artifacts" / "implementation_plan.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Test Plan\n\n"
                "## Phase 1: Done\n- [x] Task A\n\n"
                "## Phase 2: Active\n- [x] Task B\n- [ ] Task C\n\n"
                "## Phase 3: Later\n- [ ] Task D\n",
                encoding="utf-8",
            )
            fake_git = GitState("feat/b3", "1234567890abcdef", "1234567", True, ["a.py"], [], "1 file changed")
            fake_subs = [
                SubagentEntry("sub-1", "builder", 5, 1000, "HEALTHY", "KEEP"),
                SubagentEntry("sub-2", "reviewer", 20, 195_000, "AMBER", "MONITOR"),
                SubagentEntry("sub-3", "auditor", 40, 240_000, "RED_ALERT", "COMPACT"),
            ]
            with patch("harness.delivery.compaction_checkpoint.inspect_git_state", return_value=fake_git), \
                 patch("harness.delivery.compaction_checkpoint.collect_active_subagents", return_value=fake_subs):
                res = generate_compaction_checkpoint(ws, session_id="sess-brand-1")

            self.assertIn("# ◆ Agyis Compaction & Succession Checkpoint", res.content)
            self.assertIn("● HEALTHY", res.content)
            self.assertIn("▲ AMBER", res.content)
            self.assertIn("✕ RED_ALERT", res.content)
            self.assertIn("◆ COMPLETED", res.content)
            self.assertIn("● IN_PROGRESS", res.content)
            self.assertIn("○ PENDING", res.content)
            self.assertIn("▲ DIRTY", res.content)
            for old in ("🧭", "🟢", "🟡", "🔴", "✅", "🔄", "⏳"):
                self.assertNotIn(old, res.content)

            out_main = io.StringIO()
            with patch.dict(os.environ, {"AGYIS_WORKSPACE_DIR": str(ws)}), patch("sys.stdout", out_main):
                self.assertEqual(checkpoint_main(), 0)
            self.assertIn("● Checkpoint written:", out_main.getvalue())

    def test_succession_triage_routing_and_probe_markdown(self) -> None:
        prompt = build_succession_prompt(1, 2, "sess-1", 235_000, project_name="Agyis")
        self.assertIn("# ◆ Generation 2 Succession Hand-Off (Agyis)", prompt)
        self.assertIn("## Mandatory 6-Step Succession Boot Sequence", prompt)
        self.assertNotIn("🚀", prompt)
        self.assertNotIn("🛠️", prompt)

        raw_triage = (
            "Warning: banner text\n"
            "=== HOST ===\nup 2 days\n"
            "=== RESOURCES ===\nMem: 16G 4G 12G\n"
            "=== PORTS ===\nLISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n"
            "=== SERVICES ===\nactive running unit\n"
            "=== LOGS ===\nlog line 1\n"
        )
        triage_md = RemoteTriage.format_triage_markdown(raw_triage, "prod-vps")
        self.assertIn("### ◆ Remote Triage Report: `prod-vps`", triage_md)
        self.assertIn("#### ▲ Diagnostic & Connection Output", triage_md)
        self.assertIn("#### Host & Resources", triage_md)
        self.assertIn("#### Listening Sockets", triage_md)
        self.assertIn("#### Services Status", triage_md)
        self.assertIn("#### Diagnostic Logs", triage_md)
        self.assertLess(len(triage_md.encode("utf-8")), 2048)
        for old in ("🩺", "⚠️", "💻", "🌐", "⚙️", "📜"):
            self.assertNotIn(old, triage_md)

        briefing = format_route_briefing(CANONICAL_ROUTES[0])
        self.assertIn("─" * 72, briefing)
        self.assertIn("◆ ROUTE A:", briefing)
        self.assertIn("- **Mode**:", briefing)
        self.assertIn("### Stage Transition Dispatch Template (psl_stage_transition_payload.json)", briefing)
        for old in ("━", "🛫", "📋", "•"):
            self.assertNotIn(old, briefing)

        cmd_block = format_command_dictionary({"test": "pytest -q"})
        self.assertTrue(cmd_block.startswith("# ◆ Project Verification & Native Toolchain\n"))
        self.assertNotIn("🧪", cmd_block)


if __name__ == "__main__":
    unittest.main()
