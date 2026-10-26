# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for Centralized Context Engine (Issue #95 / ADR-031).
Verifies canonical resolution priority for active conversation ID, brain directory,
and workspace path across environments.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.utils.context import (
    get_active_brain_dir,
    get_active_conversation_id,
    get_active_workspace,
)


class TestContextResolution(unittest.TestCase):
    """Hermetic unit tests for context resolution priority hierarchy."""

    def test_conversation_id_explicit_overrides_all(self) -> None:
        """Explicit conversation ID takes precedence over all environment variables."""
        env = {
            "ANTIGRAVITY_CONVERSATION_ID": "ag-conv-111",
            "ANTIGRAVITY_SOURCE_METADATA": json.dumps({"conversationId": "meta-conv-222"}),
            "AGYIS_CONVERSATION_ID": "agyis-conv-333",
            "GEMINI_CONVERSATION_ID": "gem-conv-444",
        }
        with patch.dict(os.environ, env, clear=True):
            res = get_active_conversation_id("explicit-conv-999")
            self.assertEqual(res, "explicit-conv-999")

    def test_conversation_id_antigravity_precedence(self) -> None:
        """ANTIGRAVITY_CONVERSATION_ID takes precedence over metadata, AGYIS, and GEMINI."""
        env = {
            "ANTIGRAVITY_CONVERSATION_ID": "ag-conv-111",
            "ANTIGRAVITY_SOURCE_METADATA": json.dumps({"conversationId": "meta-conv-222"}),
            "AGYIS_CONVERSATION_ID": "agyis-conv-333",
            "GEMINI_CONVERSATION_ID": "gem-conv-444",
        }
        with patch.dict(os.environ, env, clear=True):
            res = get_active_conversation_id()
            self.assertEqual(res, "ag-conv-111")

    def test_conversation_id_source_metadata_tool_conversation_id(self) -> None:
        """ANTIGRAVITY_SOURCE_METADATA extracts metadata.tool.conversationId."""
        meta = {"tool": {"conversationId": "meta-tool-555"}}
        env = {
            "ANTIGRAVITY_SOURCE_METADATA": json.dumps(meta),
            "AGYIS_CONVERSATION_ID": "agyis-conv-333",
            "GEMINI_CONVERSATION_ID": "gem-conv-444",
        }
        with patch.dict(os.environ, env, clear=True):
            res = get_active_conversation_id()
            self.assertEqual(res, "meta-tool-555")

    def test_conversation_id_source_metadata_root_fields(self) -> None:
        """ANTIGRAVITY_SOURCE_METADATA extracts root conversationId or conversation_id."""
        meta1 = {"conversationId": "meta-root-666"}
        with patch.dict(os.environ, {"ANTIGRAVITY_SOURCE_METADATA": json.dumps(meta1)}, clear=True):
            self.assertEqual(get_active_conversation_id(), "meta-root-666")

        meta2 = {"conversation_id": "meta-root-777"}
        with patch.dict(os.environ, {"ANTIGRAVITY_SOURCE_METADATA": json.dumps(meta2)}, clear=True):
            self.assertEqual(get_active_conversation_id(), "meta-root-777")

    def test_conversation_id_source_metadata_corrupt_json(self) -> None:
        """Corrupt or non-dict ANTIGRAVITY_SOURCE_METADATA falls back gracefully to AGYIS/GEMINI."""
        env = {
            "ANTIGRAVITY_SOURCE_METADATA": "{not valid json",
            "AGYIS_CONVERSATION_ID": "agyis-conv-fallback",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_active_conversation_id(), "agyis-conv-fallback")

    def test_conversation_id_agyis_and_gemini_fallback(self) -> None:
        """AGYIS_CONVERSATION_ID and GEMINI_CONVERSATION_ID serve as secondary fallbacks."""
        with patch.dict(os.environ, {"AGYIS_CONVERSATION_ID": "agyis-only"}, clear=True):
            self.assertEqual(get_active_conversation_id(), "agyis-only")

        with patch.dict(os.environ, {"GEMINI_CONVERSATION_ID": "gemini-only"}, clear=True):
            self.assertEqual(get_active_conversation_id(), "gemini-only")

        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_active_conversation_id())

    def test_brain_dir_explicit_overrides_all(self) -> None:
        """Explicit brain directory overrides all environment variables."""
        env = {
            "ANTIGRAVITY_BRAIN_DIR": "/env/ag/brain",
            "ANTIGRAVITY_APP_DATA_DIR": "/env/appdata",
            "GEMINI_BRAIN_DIR": "/env/gemini/brain",
        }
        with patch.dict(os.environ, env, clear=True):
            res = get_active_brain_dir("/explicit/brain")
            self.assertEqual(res, Path("/explicit/brain"))

    def test_brain_dir_antigravity_precedence(self) -> None:
        """ANTIGRAVITY_BRAIN_DIR takes precedence over APP_DATA_DIR, GEMINI, and fallback."""
        env = {
            "ANTIGRAVITY_BRAIN_DIR": "/env/ag/brain",
            "ANTIGRAVITY_APP_DATA_DIR": "/env/appdata",
            "GEMINI_BRAIN_DIR": "/env/gemini/brain",
        }
        with patch.dict(os.environ, env, clear=True):
            res = get_active_brain_dir()
            self.assertEqual(res, Path("/env/ag/brain"))

    def test_brain_dir_app_data_dir(self) -> None:
        """ANTIGRAVITY_APP_DATA_DIR appends /brain when ANTIGRAVITY_BRAIN_DIR is unset."""
        env = {
            "ANTIGRAVITY_APP_DATA_DIR": "/env/appdata",
            "GEMINI_BRAIN_DIR": "/env/gemini/brain",
        }
        with patch.dict(os.environ, env, clear=True):
            res = get_active_brain_dir()
            self.assertEqual(res, Path("/env/appdata/brain"))

    def test_brain_dir_gemini_fallback(self) -> None:
        """GEMINI_BRAIN_DIR is respected when Antigravity env vars are absent."""
        env = {"GEMINI_BRAIN_DIR": "/env/gemini/brain"}
        with patch.dict(os.environ, env, clear=True):
            res = get_active_brain_dir()
            self.assertEqual(res, Path("/env/gemini/brain"))

    def test_brain_dir_default_fallback(self) -> None:
        """Default fallback returns ~/.gemini/antigravity/brain."""
        with patch.dict(os.environ, {}, clear=True):
            res = get_active_brain_dir()
            expected = Path.home() / ".gemini" / "antigravity" / "brain"
            self.assertEqual(res, expected)

    def test_workspace_explicit(self) -> None:
        """Explicit workspace path is resolved and returned."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self.assertEqual(get_active_workspace(tmp_path), tmp_path.resolve())

    def test_workspace_git_or_cwd(self) -> None:
        """Workspace defaults to git top-level or cwd."""
        ws = get_active_workspace()
        self.assertTrue(ws.is_dir())


if __name__ == "__main__":
    unittest.main()
