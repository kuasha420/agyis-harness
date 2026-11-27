# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit tests for harness.utils.theme (Orbital Aegis CLI theme & display-width primitives).
Sub-second benchmark SLA: <0.10s.
"""

from __future__ import annotations

import ast
import io
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from harness.utils import theme


class _FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


class TestThemeColorDetection(unittest.TestCase):
    """Tests NO_COLOR, TERM=dumb, FORCE_COLOR, COLORTERM, and TTY detection."""

    def test_no_color_and_term_dumb_override_force_color_and_tty(self) -> None:
        tty = _FakeTTY()
        with patch.dict(os.environ, {"NO_COLOR": "1", "FORCE_COLOR": "1"}, clear=False):
            self.assertFalse(theme.use_color(tty))

        with patch.dict(os.environ, {"NO_COLOR": "", "TERM": "dumb", "FORCE_COLOR": "1"}, clear=False):
            self.assertFalse(theme.use_color(tty))

    def test_force_color_and_tty_fallback(self) -> None:
        non_tty = io.StringIO()
        tty = _FakeTTY()
        env_clean = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "TERM")}
        with patch.dict(os.environ, env_clean, clear=True):
            self.assertFalse(theme.use_color(non_tty))
            self.assertTrue(theme.use_color(tty))

        with patch.dict(os.environ, {**env_clean, "FORCE_COLOR": "1"}, clear=True):
            self.assertTrue(theme.use_color(non_tty))

        with patch.dict(os.environ, {**env_clean, "FORCE_COLOR": "0", "CLICOLOR_FORCE": "false"}, clear=True):
            self.assertFalse(theme.use_color(non_tty))
            self.assertTrue(theme.use_color(tty))

    def test_truecolor_vs_256_fallback(self) -> None:
        non_tty = io.StringIO()
        with patch.dict(os.environ, {"FORCE_COLOR": "1", "COLORTERM": "truecolor", "NO_COLOR": "", "TERM": "xterm-256color"}, clear=False):
            self.assertTrue(theme.supports_truecolor())
            styled = theme.style("PASS", "pass", stream=non_tty)
            self.assertIn("\033[38;2;42;208;137m", styled)

        with patch.dict(os.environ, {"FORCE_COLOR": "1", "COLORTERM": "", "NO_COLOR": "", "TERM": "xterm-256color"}, clear=False):
            self.assertFalse(theme.supports_truecolor())
            styled = theme.style("PASS", "pass", stream=non_tty)
            self.assertIn("\033[38;5;42m", styled)


class TestThemeDisplayWidthAndTables(unittest.TestCase):
    """Tests ANSI stripping, Unicode width calculation, banners, badges, and tables."""

    def test_single_width_geometric_glyphs_and_ansi_stripping(self) -> None:
        for glyph in ("●", "▲", "✕", "○", "◆", "▸", "━", "─"):
            self.assertEqual(theme.display_width(glyph), 1, f"Glyph {glyph!r} must have display width 1")

        self.assertEqual(theme.display_width("🟢"), 2)
        self.assertEqual(theme.display_width("e\u0301"), 1)
        self.assertEqual(theme.display_width("\033[38;2;42;208;137m● PASS\033[0m"), 6)
        self.assertEqual(theme.strip_ansi("\033[32m[PASS]\033[0m"), "[PASS]")

    def test_pad_display_aligns_colored_and_plain_identically(self) -> None:
        plain = theme.pad_display("[PASS]", 10)
        colored = theme.pad_display("[\033[32mPASS\033[0m]", 10)
        self.assertEqual(len(plain), 10)
        self.assertEqual(theme.display_width(colored), 10)
        self.assertEqual(theme.strip_ansi(colored), plain)
        self.assertEqual(theme.pad_display("42", 5, align="right"), "   42")
        self.assertEqual(theme.pad_display("ab", 6, align="center"), "  ab  ")

    def test_term_width_clamping(self) -> None:
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((40, 24))):
            self.assertEqual(theme.term_width(), 64)
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((200, 50))):
            self.assertEqual(theme.term_width(), 88)
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((76, 24))):
            self.assertEqual(theme.term_width(), 76)

    def test_banner_rule_badge_status_line_no_color(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            b = theme.banner("AGYIS TEST", subtitle="Subline", badge_label="PASS", status="PASS", width=64)
            self.assertNotIn("\033[", b)
            self.assertIn("━" * 64, b)
            self.assertIn("◆ AGYIS TEST [PASS]", b)
            self.assertIn("   Subline", b)
            self.assertEqual(theme.rule(width=64), "─" * 64)
            self.assertEqual(theme.badge("PASS", "HEALTHY"), "● HEALTHY")
            self.assertEqual(theme.badge("WARN", "STALE"), "▲ STALE")
            self.assertEqual(theme.badge("FAIL", "DEAD"), "✕ DEAD")
            self.assertEqual(theme.badge("INFO", "PARKED"), "○ PARKED")
            self.assertEqual(theme.badge("COMPLETED", "COMPLETED"), "◆ COMPLETED")
            self.assertEqual(theme.status_line("Hooks", "ok", status="PASS", label_width=10), "  ● Hooks      ok")

    def test_format_table_uniform_visual_width_colored_and_plain(self) -> None:
        headers = ["ID", "State", "Latency"]
        with patch.dict(os.environ, {"FORCE_COLOR": "1", "NO_COLOR": "", "TERM": "xterm-256color"}, clear=False):
            tty = _FakeTTY()
            rows_colored = [
                ["conv-1", theme.badge("ACTIVE", "ACTIVE", stream=tty), "1.2ms"],
                ["conv-2", theme.badge("PARKED", "PARKED", stream=tty), "12.4ms"],
                ["conv-3", theme.badge("DEAD", "DEAD", stream=tty), "0.8ms"],
            ]
            colored_table = theme.format_table(headers, rows_colored, stream=tty, alignments=["left", "left", "right"])
            widths_colored = {theme.display_width(line) for line in colored_table.splitlines()}
            self.assertEqual(len(widths_colored), 1, f"Mismatched colored line widths: {widths_colored}")

        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            rows_plain = [
                ["conv-1", theme.badge("ACTIVE", "ACTIVE"), "1.2ms"],
                ["conv-2", theme.badge("PARKED", "PARKED"), "12.4ms"],
                ["conv-3", theme.badge("DEAD", "DEAD"), "0.8ms"],
            ]
            plain_table = theme.format_table(headers, rows_plain, alignments=["left", "left", "right"])
            self.assertNotIn("\033[", plain_table)
            self.assertEqual(theme.strip_ansi(colored_table), plain_table)

    def test_pure_stdlib_leaf_invariant(self) -> None:
        theme_path = Path(__file__).resolve().parent.parent / "harness" / "utils" / "theme.py"
        tree = ast.parse(theme_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.startswith("harness"), f"Forbidden harness import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertFalse(mod.startswith("harness"), f"Forbidden harness import: {mod}")

    def test_benchmark_sla(self) -> None:
        t0 = time.perf_counter()
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            for i in range(50):
                theme.banner(f"Title {i}", subtitle="Sub", width=72)
                theme.format_table(["A", "B"], [[theme.badge("PASS", "OK"), f"{i}ms"]])
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.10, f"Theme SLA exceeded: {elapsed:.4f}s >= 0.10s")


if __name__ == "__main__":
    unittest.main()
