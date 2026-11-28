# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Hermetic verification suite for Track A (`harness/ux/widgets.py`, `pills.py`, HTML assets)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.ux import (  # noqa: E402
    conversation_pill,
    customization_pill,
    is_desktop_surface,
    load_ux_asset,
    normalize_crosstalk_view_data,
    render_cli_fallback,
    render_crosstalk_widget,
    render_pill_strip,
    sidecar_pill,
)


class TestUXAssetsAndWidgets(unittest.TestCase):
    """Validates externalized Generative UI templates, schema safety, and CLI fallbacks."""

    def test_templates_load_via_importlib_and_obey_generative_ui_rules(self) -> None:
        for fname in ("crosstalk_preflight.html", "crosstalk_constellation.html"):
            html = load_ux_asset(fname)
            self.assertIn(
                '<script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>',
                html,
                fname,
            )
            self.assertIn('<body class="bg-transparent text-[var(--foreground)] antialiased p-0 m-0">', html, fname)
            self.assertIn("var(--foreground)", html, fname)
            self.assertIn("var(--card-border)", html, fname)
            self.assertIn("var(--primary)", html, fname)
            self.assertIn("window.addEventListener(\"themechange\"", html, fname)
            self.assertIn("classList.contains(\"light\")", html, fname)
            self.assertIn('id="crosstalk-data"', html, fname)
            self.assertIn("__CROSSTALK_VIEW_DATA__", html, fname)

            lower = html.lower()
            for forbidden in (
                "100vh",
                "min-h-screen",
                "h-screen",
                "height: 100%",
                "min-height: 100%",
                "<agent-embed height=",
                ":root {",
                ":root{",
                "--vscode-",
                "--app-",
                "innerhtml",
                "outerhtml",
                "insertadjacenthtml",
                "document.write",
                "font-size: 11px",
                "font-size: 10px",
            ):
                self.assertNotIn(forbidden, lower, f"{fname} violated constraint: {forbidden}")

            external_urls = re.findall(r'https?://[^\s"\'<>]+', html)
            self.assertEqual(
                external_urls,
                ["https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"],
                f"Unexpected external URL in {fname}: {external_urls}",
            )

        with self.assertRaises(ValueError):
            load_ux_asset("../pills.py")

    def test_xss_script_breakout_is_escaped_in_embedded_json(self) -> None:
        evil = '</script><script>alert("xss")</script><!-- &'
        evil_excerpt = f"{evil} mid\u2028line\u2029end"
        view = {
            "goal": {"title": evil, "line": "Check escaping"},
            "route": {"from_project": "repo-a", "to_project": "repo-b", "to_branch": evil},
            "redaction": {
                "tokens_scrubbed": 1,
                "blocked_files": [evil],
                "excerpt_preview": evil_excerpt,
                "cli_command": "agyis crosstalk status",
            },
            "entities": [
                {
                    "id": "conv-1234",
                    "title": evil,
                    "outcome": "active",
                    "surface": "desktop",
                    "activity": evil,
                    "refs": [{"label": "#step-1", "target": "#step-1"}],
                }
            ],
        }
        res = render_crosstalk_widget(view, mode="constellation", surface="desktop")
        html = res["html"]
        self.assertNotIn('</script><script>alert("xss")', html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("\u2028", html)
        self.assertNotIn("\u2029", html)

        match = re.search(
            r'<script type="application/json" id="crosstalk-data">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        parsed = json.loads(match.group(1))
        self.assertEqual(parsed["goal"]["title"], evil)
        self.assertEqual(parsed["entities"][0]["title"], evil)
        self.assertEqual(parsed["redaction"]["excerpt_preview"], evil_excerpt)

    def test_preflight_widget_desktop_and_cli_fallback_fidelity(self) -> None:
        view = {
            "goal": {"title": "Handoff auth refactor", "line": "Move contract sync to purrmission"},
            "route": {
                "from_project": "agyis-harness",
                "from_branch": "feat/v1-2-0-crosstalk",
                "from_cid": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
                "to_project": "purrmission",
                "to_branch": "master",
                "visibility": "Private -> OSS",
                "hop": 1,
                "max_hops": 2,
                "intent": "handoff",
            },
            "redaction": {
                "tokens_scrubbed": 2,
                "paths_anonymized": 4,
                "blocked_files": [".dirtyroom/secret.md"],
                "warnings": ["Home paths anonymized"],
                "passed": True,
                "excerpt_preview": "Sanitized summary excerpt",
                "cli_command": "agyis crosstalk handoff --to purrmission",
            },
            "artifacts": [{"label": "Checkpoint cp_01", "path": ".agents/artifacts/crosstalk/in.json"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            desktop_res = render_crosstalk_widget(
                view,
                mode="preflight",
                artifact_dir=Path(tmp),
                surface="desktop",
            )
            self.assertTrue(desktop_res["is_desktop"])
            self.assertEqual(desktop_res["suggested_filename"], "crosstalk_preflight.html")
            expected_uri = (Path(tmp).resolve() / "crosstalk_preflight.html").as_uri()
            self.assertEqual(desktop_res["embed_hint"], f'<agent-embed src="{expected_uri}"></agent-embed>')
            self.assertNotIn("height=", desktop_res["embed_hint"])
            self.assertIn("Private -> OSS", desktop_res["fallback_markdown"])
            self.assertIn("Hop 1/2", desktop_res["fallback_markdown"])
            self.assertIn(".dirtyroom/secret.md", desktop_res["fallback_markdown"])

            cli_res = render_crosstalk_widget(
                view,
                mode="preflight",
                artifact_dir=Path(tmp),
                surface="cli",
            )
            self.assertFalse(cli_res["is_desktop"])
            self.assertEqual(cli_res["embed_hint"], "")
            self.assertIn("agyis crosstalk handoff --to purrmission", cli_res["fallback_markdown"])
            self.assertNotIn("conversation://", cli_res["fallback_markdown"])

        with self.assertRaises(ValueError):
            render_crosstalk_widget(view, mode="unknown", surface="cli")

    def test_constellation_schema_citation_enforcement_and_ranking(self) -> None:
        view = {
            "version": "1.0",
            "goal": {"title": "Fleet Crosstalk Status", "line": "Unified Desktop + CLI threads"},
            "entities": [
                {
                    "id": "unverified-done-1",
                    "title": "Claimed done without ref",
                    "outcome": "done",
                    "surface": "cli",
                    "project": "repo-a",
                    "refs": [],
                },
                {
                    "id": "verified-done-2",
                    "title": "Verified wheel build",
                    "outcome": "done",
                    "surface": "desktop",
                    "project": "repo-b",
                    "generation": 2,
                    "hop": 1,
                    "max_hops": 2,
                    "refs": [{"label": "2695/2695 pass", "target": "#step-42"}],
                },
                {
                    "id": "blocked-3",
                    "title": "Resolve port collision",
                    "outcome": "blocked",
                    "surface": "cli",
                    "project": "repo-c",
                    "refs": [{"seq": 9}],
                },
                {
                    "id": "active-4",
                    "title": "Run Track A builder",
                    "outcome": "active",
                    "surface": "desktop",
                    "project": "repo-d",
                    "archived": False,
                    "refs": [{"label": "#step-15", "target": "#step-15"}],
                },
            ],
            "threads": [
                {"id": "t-1", "title": "Thread missing ref", "outcome": "verified", "refs": []},
            ],
            "edges": [{"from": "blocked-3", "to": "verified-done-2", "kind": "handoff", "hop": 1}],
            "attention": [
                {"id": "a-fyi", "kind": "fyi", "title": "FYI notice", "refs": []},
                {"id": "a-fail", "kind": "failure", "title": "Build failure", "refs": ["#step-3"]},
                {"id": "a-dec", "kind": "decision", "title": "Confirm OSS handoff", "refs": ["redaction#1"]},
            ],
        }
        res = render_crosstalk_widget(view, mode="constellation", artifact_dir="/tmp/brain/c1", surface="desktop")
        payload = res["json_payload"]

        for key in ("version", "mode", "goal", "entities", "threads", "edges", "redaction", "attention", "links"):
            self.assertIn(key, payload)

        # Ranking: decision > failure > fyi
        self.assertEqual([a["kind"] for a in payload["attention"]], ["decision", "failure", "fyi"])

        # Outcome order: blocked -> active -> idle -> done; unverified "done" downgraded to idle
        by_id = {ent["id"]: ent for ent in payload["entities"]}
        self.assertEqual(by_id["unverified-done-1"]["outcome"], "idle")
        self.assertTrue(by_id["unverified-done-1"]["unverified_claim"])
        self.assertEqual(by_id["verified-done-2"]["outcome"], "done")
        self.assertFalse(by_id["verified-done-2"]["unverified_claim"])
        self.assertEqual(payload["threads"][0]["outcome"], "idle")
        self.assertTrue(payload["threads"][0]["unverified_claim"])
        self.assertEqual([ent["outcome"] for ent in payload["entities"]], ["blocked", "active", "idle", "done"])

        # >= 4 distinct projects switches Constellation embed_hint to standalone artifact link
        self.assertTrue(res["embed_hint"].startswith("[Crosstalk Constellation](file://"))

        # CLI fallback preserves unverified downgrade and emits agy --conversation hints
        cli_md = render_cli_fallback(view, mode="constellation", surface="cli")
        self.assertIn("IDLE/UNVERIFIED", cli_md)
        self.assertIn("agy --conversation verified-done-2", cli_md)
        self.assertIn("[DECISION] Confirm OSS handoff (ref: redaction#1)", cli_md)
        self.assertNotIn("conversation://", cli_md)

        # Desktop CLI fallback emits clickable conversation:// pills
        desktop_md = render_cli_fallback(view, mode="constellation", surface="desktop")
        self.assertIn("[Verified wheel build](conversation://verified-done-2)", desktop_md)


class TestUXPillsAndSurfaceDetection(unittest.TestCase):
    """Validates deep-link pill builders, ID guards, and surface precedence."""

    def test_surface_detection_precedence(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_desktop_surface())
            self.assertTrue(is_desktop_surface("desktop"))
            self.assertFalse(is_desktop_surface("cli"))

        with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": "/home/u/.gemini/antigravity"}, clear=True):
            self.assertTrue(is_desktop_surface())
            self.assertFalse(is_desktop_surface("cli"))

        with patch.dict(os.environ, {"ANTIGRAVITY_APP_DATA_DIR": "/home/u/.gemini/antigravity-cli"}, clear=True):
            self.assertFalse(is_desktop_surface())
            self.assertTrue(is_desktop_surface("desktop"))

        with patch.dict(
            os.environ,
            {
                "ANTIGRAVITY_APP_DATA_DIR": "/home/u/.gemini/antigravity-cli",
                "AGYIS_UX_SURFACE": "desktop",
            },
            clear=True,
        ):
            self.assertTrue(is_desktop_surface())

        with self.assertRaises(ValueError):
            is_desktop_surface("invalid-surface")

    def test_pill_builders_and_validation(self) -> None:
        cid = "4eacf503-1111-4222-8333-abcdef123456"
        self.assertEqual(
            conversation_pill(cid, "Verify [v1]\nRelease", surface="desktop"),
            f"[Verify (v1) Release](conversation://{cid})",
        )
        self.assertEqual(
            conversation_pill(cid, "Verify", surface="desktop", include_cli_hint=True),
            f"[Verify](conversation://{cid}) (`agy --conversation {cid}`)",
        )
        self.assertEqual(
            conversation_pill(cid, None, surface="cli"),
            f"Thread 4eacf503 (`agy --conversation {cid}`)",
        )
        self.assertEqual(
            customization_pill("agyis-harness", "Agyis Harness", surface="desktop"),
            "[Agyis Harness](customization://agyis-harness)",
        )
        self.assertEqual(
            customization_pill("-1870732469773246571", "Legacy Plugin", surface="cli"),
            "Legacy Plugin (plugin dir: `-1870732469773246571`)",
        )
        self.assertEqual(
            sidecar_pill("swarm/board", "/", "Swarm Board", surface="desktop"),
            "[Swarm Board](sidecar://swarm/board/)",
        )
        self.assertEqual(
            sidecar_pill("my-plugin/panel", "/host.html?view=auxpane", "Panel", surface="desktop"),
            "[Panel](sidecar://my-plugin/panel/host.html?view=auxpane)",
        )
        self.assertEqual(
            sidecar_pill("my-panel", "/", "Panel", surface="cli"),
            "Panel (sidecar: `my-panel/`)",
        )
        self.assertEqual(render_pill_strip(["A", "", "B"]), "A · B")

        for bad_cid in ("", " ", "../secret", "-flag", "a/b", "a b", "id?q=1", "id\nx"):
            with self.assertRaises(ValueError):
                conversation_pill(bad_cid, "Bad")

        for bad_dir in ("", ".", "..", "a/b", "../x", "dir name"):
            with self.assertRaises(ValueError):
                customization_pill(bad_dir, "Bad")

        for bad_sidecar, bad_view in (
            ("a/b/c", "/"),
            ("../bad", "/"),
            ("swarm/board", "../etc"),
            ("swarm/board", "javascript:alert(1)"),
        ):
            with self.assertRaises(ValueError):
                sidecar_pill(bad_sidecar, bad_view, "Bad")

    def test_normalize_drops_unsafe_entity_links_without_crashing(self) -> None:
        normalized = normalize_crosstalk_view_data(
            {
                "entities": [
                    {"id": "../bad-id", "title": "Unsafe", "outcome": "active"},
                    {"id": "good-id-1", "title": "Safe", "outcome": "active"},
                ]
            },
            mode="constellation",
            surface="desktop",
        )
        self.assertEqual(len(normalized["links"]), 1)
        self.assertEqual(normalized["links"][0]["id"], "good-id-1")
        self.assertEqual(normalized["entities"][0]["id"], "")
        self.assertEqual(normalized["entities"][0]["cli_command"], "")

    def test_unsafe_link_schemes_dropped_and_constellation_fallback_id_guarded(self) -> None:
        normalized = normalize_crosstalk_view_data(
            {
                "entities": [
                    {"id": "../traversal", "cli_command": "agy --conversation ../traversal", "title": "Bad", "outcome": "idle"},
                ],
                "links": [
                    {"kind": "web", "label": "JS", "uri": "javascript:alert(1)"},
                    {"kind": "web", "label": "Data", "uri": "data:text/html,<script>alert(1)</script>"},
                    {"kind": "web", "label": "VBS", "uri": "vbscript:msgbox(1)"},
                    {"kind": "web", "label": "EvilMD", "uri": "https://example.com", "markdown": "[X](javascript:alert(1))"},
                    {"kind": "web", "label": "HTTPS", "uri": "https://example.com/docs"},
                    {"kind": "web", "label": "File", "uri": "file:///tmp/report.html"},
                    {"kind": "web", "label": "Agyis", "uri": "agyis://status"},
                    {"kind": "conversation", "id": "conv-safe-9", "label": "Safe"},
                ],
            },
            mode="constellation",
            surface="desktop",
        )
        self.assertEqual(normalized["entities"][0]["id"], "")
        self.assertEqual(normalized["entities"][0]["cli_command"], "")
        uris = [lnk["uri"] for lnk in normalized["links"]]
        self.assertEqual(
            uris,
            [
                "https://example.com",
                "https://example.com/docs",
                "file:///tmp/report.html",
                "agyis://status",
                "conversation://conv-safe-9",
            ],
        )
        self.assertEqual(normalized["links"][0]["markdown"], "EvilMD")
        html = load_ux_asset("crosstalk_constellation.html")
        self.assertIn('/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(rawId)', html)
        self.assertIn('!rawId.includes("..")', html)


if __name__ == "__main__":
    unittest.main()
