# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Systemd unit generation for telemetry background sync (ADR-030).
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional, Union


def generate_systemd_service(
    python_bin: Optional[str] = None,
    interval_sec: float = 5.0,
    working_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Generates the systemd user service unit definition for psl-sync-watch."""
    py_path = python_bin or sys.executable or "/usr/bin/python3"
    work_dir = str(working_dir) if working_dir else str(Path.home())
    return f"""[Unit]
Description=PSL Telemetry Background Sync Watcher
Documentation=https://github.com/kuasha420/psl-agy-harness
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={work_dir}
ExecStart={py_path} -m harness.cli sync --watch --interval {interval_sec}
Restart=on-failure
RestartSec=10s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
