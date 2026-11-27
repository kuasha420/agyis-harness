#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic unit and hook-integration tests for Issue #93 Anti-Clobber Guard."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.hooks import anti_drift_hook, command_safety_hook, completion_fence_hook
from harness.hooks.anti_clobber import (
    check_anti_clobber,
    detect_conflict_markers,
    extract_h2_headers,
    is_append_only_target,
    is_ephemeral_clobber_exempt_path,
)


def _make_write_payload(
    tool_name: str,
    target: str,
    content: str,
    *,
    overwrite: bool | None = True,
    legacy: bool = False,
    workspace: str | None = None,
    append: bool | None = None,
) -> dict:
    args: dict = {}
    if legacy:
        args["TargetFile"] = target
        args["CodeContent"] = content
    else:
        args["Path"] = target
        args["Content"] = content
    if overwrite is not None:
        args["Overwrite"] = overwrite
    if append is not None:
        args["Append"] = append
    payload: dict = {"toolCall": {"name": tool_name, "args": args}}
    if workspace is not None:
        payload["workspacePaths"] = [workspace]
    return payload


def _invoke_hook_main(hook_mod, payload: dict) -> dict:
    stdout_buf = io.StringIO()
    with patch("sys.stdin", io.StringIO(json.dumps(payload))), patch("sys.stdout", stdout_buf):
        hook_mod.main()
    return json.loads(stdout_buf.getvalue().strip())


class TestConflictMarkerGuard(unittest.TestCase):
    """Layer 1A: Git merge conflict marker detection without Setext false positives."""

    def test_detects_standard_and_diff3_conflict_markers(self) -> None:
        conflicted = "alpha\n<<<<<<< HEAD\nfoo\n||||||| base\nold\n=======\nbar\n>>>>>>> feature\n"
        markers = detect_conflict_markers(conflicted)
        self.assertEqual(markers, ["<<<<<<<", "|||||||", "=======", ">>>>>>>"])

    def test_allows_markdown_setext_heading_without_false_positive(self) -> None:
        setext_doc = "Project Overview\n=======\n\nSection body without conflict markers.\n"
        self.assertEqual(detect_conflict_markers(setext_doc), [])

    def test_denies_incoming_conflict_markers_and_honors_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            target = ws / "module.py"
            target.write_text("x = 1\n", encoding="utf-8")

            bad = "x = 1\n<<<<<<< HEAD\ny = 2\n=======\ny = 3\n>>>>>>> main\n"
            res = check_anti_clobber(_make_write_payload("write_file", str(target), bad, workspace=tmp))
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("[AGYIS ANTI-CLOBBER]", res["reason"])
            self.assertIn("incoming content", res["reason"])

            overridden = "# agyis: allow-conflict-markers\n" + bad
            self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(target), overridden, workspace=tmp)))

    def test_denies_clobbering_existing_conflicted_file_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            target = ws / "service.py"
            target.write_text("<<<<<<< HEAD\na = 1\n=======\na = 2\n>>>>>>> branch\n", encoding="utf-8")

            clean_overwrite = "a = 1\n"
            res = check_anti_clobber(
                _make_write_payload("write_to_file", "service.py", clean_overwrite, legacy=True, workspace=tmp),
            )
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("existing target file", res["reason"])


class TestCatastrophicContractionGuard(unittest.TestCase):
    """Layer 1B: Blocks destructive >50% / >100-line shrinkage on non-scratch files."""

    def test_denies_over_fifty_percent_contraction_on_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            target = ws / "app.py"
            target.write_text("\n".join(f"line_{i} = {i}" for i in range(80)) + "\n", encoding="utf-8")

            shrunk = "\n".join(f"line_{i} = {i}" for i in range(20)) + "\n"
            res = check_anti_clobber(_make_write_payload("write_file", str(target), shrunk, workspace=tmp))
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("80 -> 20 lines", res["reason"])

    def test_denies_over_hundred_line_drop_even_above_half_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            target = ws / "large.py"
            target.write_text("\n".join(f"x_{i} = {i}" for i in range(300)) + "\n", encoding="utf-8")

            dropped = "\n".join(f"x_{i} = {i}" for i in range(190)) + "\n"
            res = check_anti_clobber(
                _make_write_payload("create_file", "large.py", dropped, overwrite=None, workspace=tmp),
            )
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("300 -> 190 lines", res["reason"])

    def test_allows_small_files_and_modest_refactors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            small = ws / "small.py"
            small.write_text("\n".join(f"v = {i}" for i in range(40)) + "\n", encoding="utf-8")
            self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(small), "v = 0\n", workspace=tmp)))

            medium = ws / "medium.py"
            medium.write_text("\n".join(f"v = {i}" for i in range(80)) + "\n", encoding="utf-8")
            modest = "\n".join(f"v = {i}" for i in range(60)) + "\n"
            self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(medium), modest, workspace=tmp)))

    def test_exempts_scratch_checkpoint_and_out_of_workspace_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            for rel in ("scratch/probe.py", ".agents/artifacts/checkpoints/cp.md", ".system_generated/dump.txt"):
                fpath = ws / rel
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text("\n".join(f"row {i}" for i in range(90)) + "\n", encoding="utf-8")
                self.assertTrue(is_ephemeral_clobber_exempt_path(fpath, raw_target=rel, workspace_root=ws))
                self.assertIsNone(
                    check_anti_clobber(_make_write_payload("write_file", rel, "row 0\n", workspace=tmp))
                )

            with tempfile.TemporaryDirectory() as outside_tmp:
                out_file = Path(outside_tmp) / "ephemeral.log"
                out_file.write_text("\n".join(f"log {i}" for i in range(90)) + "\n", encoding="utf-8")
                self.assertTrue(is_ephemeral_clobber_exempt_path(out_file, workspace_root=ws))
                self.assertIsNone(
                    check_anti_clobber(_make_write_payload("write_file", str(out_file), "log 0\n", workspace=tmp))
                )

    def test_honors_inline_and_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            target = ws / "module.py"
            target.write_text("\n".join(f"x = {i}" for i in range(90)) + "\n", encoding="utf-8")

            with_token = "# agyis: allow-shrink\nx = 1\n"
            self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(target), with_token, workspace=tmp)))

            with patch.dict(os.environ, {"AGYIS_ALLOW_CLOBBER": "1"}):
                self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(target), "x = 1\n", workspace=tmp)))


class TestAppendOnlyMonotonicContract(unittest.TestCase):
    """Layer 2: Monotonic `##` section enforcement on changelogs, ledgers, and tagged files."""

    def test_extract_h2_skips_fenced_code_blocks(self) -> None:
        doc = (
            "# Changelog\n\n"
            "## v1.0.0\n"
            "```markdown\n"
            "## Fake Code Block Heading\n"
            "```\n"
            "~~~\n"
            "## Another Fenced Heading\n"
            "~~~\n"
            "### Subheading\n"
            "## v1.1.0\n"
        )
        self.assertEqual(extract_h2_headers(doc), ["v1.0.0", "v1.1.0"])

    def test_denies_dropped_h2_in_changelog_and_allows_append_or_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            changelog = ws / "CHANGELOG.md"
            original = "# Changelog\n\n## v1.0.0\n- Initial\n\n## v1.1.0\n- Feature\n"
            changelog.write_text(original, encoding="utf-8")

            dropped = "# Changelog\n\n## v1.1.0\n- Feature\n"
            res = check_anti_clobber(_make_write_payload("write_file", str(changelog), dropped, workspace=tmp))
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")
            self.assertIn("v1.0.0", res["reason"])

            # tool_args Append=False takes precedence over top-level payload append=True
            precedence_payload = _make_write_payload(
                "write_file", str(changelog), dropped, workspace=tmp, append=False,
            )
            precedence_payload["append"] = True
            res_prec = check_anti_clobber(precedence_payload)
            self.assertIsNotNone(res_prec)
            self.assertEqual(res_prec["decision"], "deny")

            appended = original + "\n## v1.2.0\n- Shield\n"
            self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(changelog), appended, workspace=tmp)))

            archived = "<!-- ARCHIVED: v1.0.0 moved to CHANGELOG-2025.md -->\n" + dropped
            self.assertIsNone(check_anti_clobber(_make_write_payload("write_file", str(changelog), archived, workspace=tmp)))

    def test_enforces_ledger_glob_and_append_only_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            ledger = ws / "session_ledger.md"
            ledger.write_text("# Ledger\n\n## Phase 1\nDone\n\n## Phase 2\nDone\n", encoding="utf-8")
            self.assertTrue(is_append_only_target(ledger, ledger.read_text(encoding="utf-8"), ""))
            res = check_anti_clobber(
                _make_write_payload("write_file", str(ledger), "# Ledger\n\n## Phase 2\nDone\n", workspace=tmp),
            )
            self.assertIsNotNone(res)
            self.assertEqual(res["decision"], "deny")

            tagged = ws / "notes.md"
            tagged.write_text("<!-- AGYIS: APPEND-ONLY -->\n## Entry A\nA\n## Entry B\nB\n", encoding="utf-8")
            res_tagged = check_anti_clobber(
                _make_write_payload("write_file", str(tagged), "<!-- AGYIS: APPEND-ONLY -->\n## Entry B\nB\n", workspace=tmp),
            )
            self.assertIsNotNone(res_tagged)
            self.assertEqual(res_tagged["decision"], "deny")
            self.assertIn("Entry A", res_tagged["reason"])

            # Append=True is monotonic and must be allowed
            self.assertIsNone(
                check_anti_clobber(
                    _make_write_payload("write_file", str(tagged), "\n## Entry C\nC\n", overwrite=False, append=True, workspace=tmp),
                )
            )


class TestHookWiringIntegration(unittest.TestCase):
    """End-to-end PreToolUse wiring in anti_drift_hook, command_safety_hook, and completion_fence_hook."""

    def test_anti_drift_hook_blocks_changelog_clobber_despite_md_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            changelog = ws / "CHANGELOG.md"
            changelog.write_text("# Changelog\n\n## v1.0.0\nInit\n\n## v1.1.0\nFix\n", encoding="utf-8")

            payload = _make_write_payload(
                "write_file",
                str(changelog),
                "# Changelog\n\n## v1.1.0\nFix\n",
                workspace=tmp,
            )
            payload["conversationId"] = "conv-anti-clobber-test"
            out = _invoke_hook_main(anti_drift_hook, payload)
            self.assertEqual(out["decision"], "deny")
            self.assertIn("[AGYIS ANTI-CLOBBER]", out["reason"])

    def test_command_safety_hook_blocks_direct_write_file_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            target = ws / "core.py"
            target.write_text("\n".join(f"line_{i} = {i}" for i in range(70)) + "\n", encoding="utf-8")

            payload = _make_write_payload("write_file", str(target), "line_0 = 0\n", workspace=tmp)
            out = _invoke_hook_main(command_safety_hook, payload)
            self.assertEqual(out["decision"], "deny")
            self.assertIn("[AGYIS ANTI-CLOBBER]", out["reason"])

            safe_payload = _make_write_payload(
                "write_file",
                str(target),
                "\n".join(f"line_{i} = {i}" for i in range(65)) + "\n",
                workspace=tmp,
            )
            safe_out = _invoke_hook_main(command_safety_hook, safe_payload)
            self.assertEqual(safe_out["decision"], "allow")

    def test_completion_fence_does_not_taint_code_dirty_on_clobber_deny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            state_dir = ws / "state"
            target = ws / "service.py"
            target.write_text("\n".join(f"row_{i} = {i}" for i in range(80)) + "\n", encoding="utf-8")

            payload = _make_write_payload("write_file", str(target), "row_0 = 0\n", workspace=tmp)
            payload["hookEventName"] = "PreToolUse"
            payload["conversationId"] = "conv-fence-clobber"
            payload["state_dir"] = str(state_dir)

            out = _invoke_hook_main(completion_fence_hook, payload)
            self.assertEqual(out["decision"], "allow")
            state = completion_fence_hook.load_state(conv_id="conv-fence-clobber", state_dir=state_dir)
            self.assertFalse(state.get("code_dirty", False))


if __name__ == "__main__":
    unittest.main()
