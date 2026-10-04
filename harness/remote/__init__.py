"""
PSL Harness: Remote Subsystem Package (ADR-027).

Exports:
- RemoteRunner: OpenSSH multiplexed execution manager.
- ScriptStreamer: Non-intrusive stdin script streaming and staged fallback.
- RemoteTriage: Compact (<2KB) diagnostic and troubleshooting engine.
- get_socket_dir: Socket directory resolver.
"""

from harness.remote.runner import RemoteRunner, get_socket_dir
from harness.remote.scripts import ScriptStreamer
from harness.remote.triage import RemoteTriage

__all__ = [
    "RemoteRunner",
    "ScriptStreamer",
    "RemoteTriage",
    "get_socket_dir",
]
