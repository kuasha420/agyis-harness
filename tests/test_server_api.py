#!/usr/bin/env python3
"""
Hermetic Unit and Integration Tests for Centralized Telemetry Hub API (ADR-030).

Tests:
- /api/v1/health endpoint probe.
- /api/v1/auth/verify endpoint (200, 401, 403, and GitHub API mock).
- /api/v1/sync/push and /api/v1/telemetry/batch batch upsert.
- /api/v1/sync/pull and /api/v1/telemetry/delta delta replication with anti-echo filtering.
- Zero external daemon requirement (hermetic in-memory SQLite).
"""

from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import warnings

warnings.filterwarnings("ignore", message=".*httpx.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from starlette.testclient import TestClient

    from server import auth
    from server.app import create_app
    from server.storage import Storage
    HAS_SERVER_DEPS = True
except ImportError:
    HAS_SERVER_DEPS = False


@unittest.skipUnless(HAS_SERVER_DEPS, "Starlette or server dependencies not installed")
class TestServerApi(unittest.TestCase):
    """Hermetic tests for the Starlette telemetry gateway."""

    def setUp(self):
        # Enable hermetic test auth bypass by default
        self.patcher_env = patch.dict(os.environ, {
            "PSL_HUB_TEST_AUTH": "1",
            "PSL_GITHUB_ORG": "purrfectsoft",
        })
        self.patcher_env.start()
        auth.clear_auth_cache()

        # Initialize fresh in-memory database app
        self.app = create_app("sqlite:///:memory:")
        self.client = TestClient(self.app)

    def tearDown(self):
        self.patcher_env.stop()
        auth.clear_auth_cache()
        if hasattr(self, "app") and hasattr(self.app.state, "storage"):
            self.app.state.storage.close()

    def test_health_endpoint(self):
        """Verifies GET /api/v1/health returns 200 and connected database status."""
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["database"], "connected")

    def test_auth_verify_success_and_failures(self):
        """Verifies POST /api/v1/auth/verify handles valid, invalid, and forbidden tokens."""
        # 1. Valid token in header
        resp = self.client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer test-token-alice"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["username"], "alice")
        self.assertEqual(data["org"], "purrfectsoft")

        # 2. Valid token in JSON body
        resp = self.client.post(
            "/api/v1/auth/verify",
            json={"token": "test-token-bob"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "bob")

        # 3. Invalid token (401)
        resp = self.client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()["authenticated"])

        # 4. Forbidden token / non-member (403)
        resp = self.client.post(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer forbidden-token"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["authenticated"])

    def test_auth_verify_real_api_mock(self):
        """Verifies GitHub API queries and caching when not in test bypass mode."""
        with patch.dict(os.environ, {"PSL_HUB_TEST_AUTH": "0"}):
            # Mock GitHub /user response and /orgs/purrfectsoft/members/charlie response
            mock_user_resp = MagicMock()
            mock_user_resp.read.return_value = json.dumps({"login": "charlie"}).encode("utf-8")
            mock_user_resp.__enter__.return_value = mock_user_resp

            mock_org_resp = MagicMock()
            mock_org_resp.read.return_value = b""
            mock_org_resp.__enter__.return_value = mock_org_resp

            with patch("urllib.request.urlopen", side_effect=[mock_user_resp, mock_org_resp]) as mock_open:
                resp = self.client.post(
                    "/api/v1/auth/verify",
                    headers={"Authorization": "Bearer ghp_real_mock_token"},
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["username"], "charlie")
                self.assertEqual(mock_open.call_count, 2)

                # Second call should hit the in-memory cache and NOT call urlopen
                resp2 = self.client.post(
                    "/api/v1/auth/verify",
                    headers={"Authorization": "Bearer ghp_real_mock_token"},
                )
                self.assertEqual(resp2.status_code, 200)
                self.assertEqual(mock_open.call_count, 2)  # Call count unchanged

    def test_sync_push_and_upsert(self):
        """Verifies POST /api/v1/sync/push ingests and updates sessions and steps."""
        payload = {
            "sessions": [{
                "session_id": "sess-alpha-1",
                "start_time": "2026-03-01T10:00:00Z",
                "end_time": "2026-03-01T10:05:00Z",
                "duration_seconds": 300.0,
                "total_steps": 1,
                "model": "gemini-2.5-pro",
                "workspace_path": "[WORKSPACE_ROOT]",
                "transcript_path": "[WORKSPACE_ROOT]/logs/transcript.jsonl",
                "file_size_bytes": 2048,
                "has_errors": 0,
                "tool_call_count": 1,
                "tool_error_count": 0,
                "intervention_count": 0,
                "origin_developer": None,  # Should become requesting user ('alice')
            }],
            "steps": [{
                "session_id": "sess-alpha-1",
                "step_index": 0,
                "step_type": "AGENT_OUTPUT",
                "source": "MODEL",
                "status": "DONE",
                "created_at": "2026-03-01T10:01:00Z",
                "content_length": 40,
                "content_snippet": "Hello world snippet",
                "has_thinking": 0,
                "thinking_length": 0,
                "tool_count": 1,
            }],
            "tool_calls": [{
                "session_id": "sess-alpha-1",
                "step_index": 0,
                "result_step_index": 1,
                "tool_name": "view_file",
                "arguments_json": '{"AbsolutePath": "/workspace/main.py"}',
                "arguments_snippet": "main.py",
                "target_path": "/workspace/main.py",
                "command_line": None,
                "started_at": "2026-03-01T10:01:05Z",
                "completed_at": "2026-03-01T10:01:06Z",
                "duration_seconds": 1.0,
                "status": "SUCCESS",
                "exit_code": 0,
                "error_snippet": None,
                "is_loop_candidate": 0,
                "output_length_chars": 100,
                "output_lines": 10,
                "arguments_length_chars": 20,
                "command_category": "read",
                "is_truncated": 0,
            }],
            "user_interventions": [],
        }

        # Push payload with alice credentials
        resp = self.client.post(
            "/api/v1/sync/push",
            headers={"Authorization": "Bearer test-token-alice"},
            json=payload,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["accepted_sessions"], 1)
        self.assertEqual(data["accepted_steps"], 1)
        self.assertEqual(data["accepted_tool_calls"], 1)

        # Also verify backward-compatible route /api/v1/telemetry/batch accepts pushes
        resp_alias = self.client.post(
            "/api/v1/telemetry/batch",
            headers={"Authorization": "Bearer test-token-alice"},
            json=payload,
        )
        self.assertEqual(resp_alias.status_code, 200)

    def test_sync_pull_anti_echo_filter(self):
        """Verifies GET /api/v1/sync/pull excludes sessions where origin_developer == requesting_user."""
        # 1. Alice pushes a session
        payload_alice = {
            "sessions": [{
                "session_id": "sess-by-alice",
                "start_time": "2026-03-01T10:00:00Z",
                "duration_seconds": 120.0,
                "total_steps": 1,
                "origin_developer": "alice",
            }],
            "steps": [{
                "session_id": "sess-by-alice",
                "step_index": 0,
                "step_type": "AGENT_OUTPUT",
                "source": "MODEL",
                "status": "DONE",
                "created_at": "2026-03-01T10:01:00Z",
                "content_length": 20,
                "content_snippet": "Alice code",
                "has_thinking": 0,
                "thinking_length": 0,
                "tool_count": 0,
            }],
            "tool_calls": [],
            "user_interventions": [],
        }
        resp = self.client.post(
            "/api/v1/sync/push",
            headers={"Authorization": "Bearer test-token-alice"},
            json=payload_alice,
        )
        self.assertEqual(resp.status_code, 200)

        # 2. Alice pulls: anti-echo filter must EXCLUDE her own session!
        pull_alice = self.client.get(
            "/api/v1/sync/pull?since=1970-01-01T00:00:00Z",
            headers={"Authorization": "Bearer test-token-alice"},
        )
        self.assertEqual(pull_alice.status_code, 200)
        alice_data = pull_alice.json()
        self.assertEqual(len(alice_data["sessions"]), 0)
        self.assertEqual(len(alice_data["steps"]), 0)

        # 3. Bob pulls: Bob MUST receive Alice's session!
        pull_bob = self.client.get(
            "/api/v1/sync/pull?since=1970-01-01T00:00:00Z",
            headers={"Authorization": "Bearer test-token-bob"},
        )
        self.assertEqual(pull_bob.status_code, 200)
        bob_data = pull_bob.json()
        self.assertEqual(len(bob_data["sessions"]), 1)
        self.assertEqual(bob_data["sessions"][0]["session_id"], "sess-by-alice")
        self.assertEqual(bob_data["sessions"][0]["origin_developer"], "alice")
        self.assertEqual(len(bob_data["steps"]), 1)

        # 4. Backward-compatible alias /api/v1/telemetry/delta works identically
        pull_alias = self.client.get(
            "/api/v1/telemetry/delta?since=1970-01-01T00:00:00Z",
            headers={"Authorization": "Bearer test-token-bob"},
        )
        self.assertEqual(pull_alias.status_code, 200)
        self.assertEqual(len(pull_alias.json()["sessions"]), 1)


if __name__ == "__main__":
    unittest.main()
