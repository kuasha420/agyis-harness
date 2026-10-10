#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Hermetic unit tests for PSL Headless Fleet Screen Capture Artifact Bridge.

Validates screen capture decoding, image extraction into artifacts directory,
carousel markdown generation, and CLI remote screens command.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest

from harness.cli import main as cli_main
from harness.remote.display_bridge import (
    MINIMAL_PNG_BYTES,
    capture_fleet_screens,
)


class TestDisplayBridge(unittest.TestCase):
    """Test suite for display bridge and carousel markdown generation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.isolated_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_capture_fleet_screens_with_json_data(self) -> None:
        """Decodes base64 screen captures and generates carousel markdown artifact."""
        b64_img = base64.b64encode(MINIMAL_PNG_BYTES).decode("ascii")

        payload = {
            "screens": [
                {
                    "node": "desktop",
                    "title": "Desktop Anchor",
                    "status": "active",
                    "window_title": "Kitty Terminal",
                    "timestamp": "2026-10-08T21:00:00Z",
                    "image_base64": b64_img,
                },
                {
                    "node": "laptop",
                    "title": "CUDA Laptop Worker",
                    "status": "active",
                    "window_title": "Antigravity Worker",
                    "timestamp": "2026-10-08T21:00:00Z",
                    "image_base64": b64_img,
                },
            ]
        }

        artifact_md = capture_fleet_screens(
            brain_dir=self.isolated_path,
            json_data=payload,
        )

        self.assertTrue(artifact_md.exists(), f"Artifact file {artifact_md} not created")
        self.assertEqual(artifact_md.name, "fleet_screens.md")

        # Verify images extracted into artifacts/fleet_screens/
        screens_dir = self.isolated_path / "artifacts" / "fleet_screens"
        self.assertTrue(screens_dir.is_dir())
        desktop_img = screens_dir / "desktop.png"
        laptop_img = screens_dir / "laptop.png"
        self.assertTrue(desktop_img.exists())
        self.assertTrue(laptop_img.exists())
        self.assertEqual(desktop_img.read_bytes(), MINIMAL_PNG_BYTES)

        # Verify carousel markdown content
        content = artifact_md.read_text(encoding="utf-8")
        self.assertIn("````carousel", content)
        self.assertIn("<!-- slide -->", content)
        self.assertIn("Desktop Anchor", content)
        self.assertIn("CUDA Laptop Worker", content)
        self.assertIn(f"![Desktop Anchor]({desktop_img.resolve()})", content)
        self.assertIn(f"![CUDA Laptop Worker]({laptop_img.resolve()})", content)

    def test_capture_fleet_screens_default_fallback(self) -> None:
        """capture_fleet_screens generates default strand placeholders when json_data is None."""
        artifact_md = capture_fleet_screens(brain_dir=self.isolated_path)

        self.assertTrue(artifact_md.exists())
        content = artifact_md.read_text(encoding="utf-8")
        self.assertIn("````carousel", content)
        self.assertIn("<!-- slide -->", content)
        self.assertIn("desktop", content)
        self.assertIn("laptop", content)
        self.assertIn("steamdeck", content)

    def test_cli_remote_screens_command(self) -> None:
        """CLI invocation 'psl remote screens --brain-dir <dir> --json' executes cleanly."""
        from unittest.mock import patch
        import io

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            code = cli_main([
                "remote",
                "screens",
                "--brain-dir",
                str(self.isolated_path),
                "--json",
            ])
            self.assertEqual(code, 0)
            output = mock_out.getvalue()
            self.assertIn("fleet_screens.md", output)

        expected_md = self.isolated_path / "artifacts" / "fleet_screens.md"
        self.assertTrue(expected_md.exists())

    def test_display_bridge_data_uris_and_corruption(self) -> None:
        """
        Asserts display_bridge correctly strips data:image/png;base64, prefixes
        and handles corrupted base64 payloads with graceful warning logging and fallback.
        """
        from unittest.mock import patch
        b64_valid = base64.b64encode(MINIMAL_PNG_BYTES).decode("ascii")

        # 1. Test data URI prefix stripping (both data:image/png;base64, and data:image/jpeg;base64,)
        data_uri_payload = {
            "screens": [
                {
                    "node": "node-data-uri",
                    "title": "Data URI Screen",
                    "image_base64": f"data:image/png;base64,{b64_valid}",
                }
            ]
        }
        artifact_md = capture_fleet_screens(
            brain_dir=self.isolated_path,
            json_data=data_uri_payload,
        )
        self.assertTrue(artifact_md.exists())
        extracted_img = self.isolated_path / "artifacts" / "fleet_screens" / "node-data-uri.png"
        self.assertTrue(extracted_img.exists())
        self.assertEqual(extracted_img.read_bytes(), MINIMAL_PNG_BYTES)

        # 2. Test corrupted base64 payload handling with graceful error logging and fallback
        corrupt_payload = {
            "screens": [
                {
                    "node": "node-corrupted",
                    "title": "Corrupted Screen",
                    "image_base64": "!!!INVALID_BASE64_DATA_CORRUPTED???###",
                }
            ]
        }
        with patch("harness.remote.display_bridge.logger.warning") as mock_warn:
            artifact_corrupt_md = capture_fleet_screens(
                brain_dir=self.isolated_path,
                json_data=corrupt_payload,
            )
            self.assertTrue(artifact_corrupt_md.exists())
            mock_warn.assert_called_once()
            self.assertIn("Failed to decode base64 screenshot", mock_warn.call_args[0][0])
            self.assertEqual(mock_warn.call_args[0][1], "node-corrupted")

            corrupt_img = self.isolated_path / "artifacts" / "fleet_screens" / "node-corrupted.png"
            self.assertTrue(corrupt_img.exists())
            self.assertEqual(corrupt_img.read_bytes(), MINIMAL_PNG_BYTES)


if __name__ == "__main__":
    unittest.main()
