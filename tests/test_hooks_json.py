# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Unit tests for hooks.json configuration contracts (DEF-04 / ADR-028).
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestHooksJson(unittest.TestCase):
    def test_post_tool_use_matcher_includes_call_mcp_tool(self) -> None:
        """Asserts that hooks.json PostToolUse matcher includes call_mcp_tool (DEF-04)."""
        hooks_path = REPO_ROOT / "harness" / "hooks" / "hooks.json"
        self.assertTrue(hooks_path.is_file(), f"Missing hooks.json at {hooks_path}")

        with open(hooks_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        fence = cfg.get("psl-stop-verification-fence")
        self.assertIsNotNone(fence, "psl-stop-verification-fence hook configuration missing")

        post_tool_use = fence.get("PostToolUse", [])
        self.assertTrue(len(post_tool_use) > 0, "psl-stop-verification-fence has empty PostToolUse")

        matchers = [entry.get("matcher", "") for entry in post_tool_use]
        self.assertTrue(
            any("call_mcp_tool" in m for m in matchers),
            f"Expected 'call_mcp_tool' in PostToolUse matcher, got: {matchers}",
        )


if __name__ == "__main__":
    unittest.main()
