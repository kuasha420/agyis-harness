#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic Unit Tests for Telemetry Sync Push Retry and Jitter Backoff (Issue #55).
"""

from __future__ import annotations

import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch
import urllib.error

from harness.telemetry.schema import init_db
from harness.telemetry.sync.push import push_local_sessions


def _make_http_error(code: int, msg: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://hub.test/api/v1/sync/push",
        code=code,
        msg=msg,
        hdrs=MagicMock(),
        fp=io.BytesIO(msg.encode("utf-8")),
    )


class TestSyncPushRetryBackoff(unittest.TestCase):
    """Verifies retry backoff calculations and behavior on 502/503/504 transient errors."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "telemetry.db"
        conn = sqlite3.connect(self.db_path)
        init_db(conn)
        cur = conn.cursor()
        # Insert a sample unsynced session
        cur.execute("""
            INSERT INTO sessions (session_id, start_time, duration_seconds, origin_developer, remote_synced_at)
            VALUES ('test-sess-001', '2026-11-08T00:00:00Z', 5.0, 'local', NULL)
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("random.uniform", return_value=0.5)
    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_retry_on_502_503_504_with_jitter_backoff(self, mock_urlopen, mock_sleep, mock_random):
        """Verifies exponential jitter backoff is calculated and invoked on 502/503/504."""
        err_503 = _make_http_error(503, "Service Unavailable")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__.return_value = mock_resp

        # First call fails with 503, second succeeds
        mock_urlopen.side_effect = [err_503, mock_resp]

        result = push_local_sessions(
            endpoint="http://hub.test",
            token="test-token",
            db_path=self.db_path,
            retry_backoff=1.0,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_sleep.call_count, 1)
        # Attempt 0: (2 ** 0) + 0.5 = 1.5
        mock_sleep.assert_called_once_with(1.5)
        err_503.close()

    @patch("random.uniform", return_value=0.25)
    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_retry_multiple_attempts_backoff_progression(self, mock_urlopen, mock_sleep, mock_random):
        """Verifies attempt 0 and attempt 1 exponential progression."""
        err_502 = _make_http_error(502, "Bad Gateway")
        err_504 = _make_http_error(504, "Gateway Timeout")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__.return_value = mock_resp

        # 502 -> 504 -> success
        mock_urlopen.side_effect = [err_502, err_504, mock_resp]

        result = push_local_sessions(
            endpoint="http://hub.test",
            token="test-token",
            db_path=self.db_path,
            retry_backoff=1.0,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(mock_sleep.call_count, 2)
        # Attempt 0: (2 ** 0) + 0.25 = 1.25
        # Attempt 1: (2 ** 1) + 0.25 = 2.25
        mock_sleep.assert_has_calls([call(1.25), call(2.25)])
        err_502.close()
        err_504.close()

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_fast_path_when_backoff_is_zero(self, mock_urlopen, mock_sleep):
        """Verifies fast path when eff_backoff == 0.0 (time.sleep never called)."""
        err_503 = _make_http_error(503, "Service Unavailable")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__.return_value = mock_resp

        mock_urlopen.side_effect = [err_503, mock_resp]

        result = push_local_sessions(
            endpoint="http://hub.test",
            token="test-token",
            db_path=self.db_path,
            retry_backoff=0.0,
        )

        self.assertEqual(result["status"], "success")
        mock_sleep.assert_not_called()
        err_503.close()

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_fast_fail_on_4xx_without_retry(self, mock_urlopen, mock_sleep):
        """Verifies 4xx errors fail immediately without retry or sleep."""
        err_403 = _make_http_error(403, "Forbidden")
        mock_urlopen.side_effect = err_403

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            push_local_sessions(
                endpoint="http://hub.test",
                token="test-token",
                db_path=self.db_path,
                retry_backoff=1.0,
            )

        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()
        ctx.exception.close()


if __name__ == "__main__":
    unittest.main()
