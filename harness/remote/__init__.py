# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
PSL Harness: Remote Subsystem Package (ADR-027).

Exports:
- RemoteRunner: OpenSSH multiplexed execution manager.
- ScriptStreamer: Non-intrusive stdin script streaming and staged fallback.
- RemoteTriage: Compact (<2KB) diagnostic and troubleshooting engine.
- get_socket_dir: Socket directory resolver.
"""

from harness.remote.display_bridge import capture_fleet_screens
from harness.remote.runner import RemoteRunner, SSHRunner, get_socket_dir
from harness.remote.scripts import RemoteScriptStreamer, ScriptStreamer
from harness.remote.triage import RemoteTriage, RemoteTriageEngine

__all__ = [
    "RemoteRunner",
    "SSHRunner",
    "ScriptStreamer",
    "RemoteScriptStreamer",
    "RemoteTriage",
    "RemoteTriageEngine",
    "get_socket_dir",
    "capture_fleet_screens",
]

