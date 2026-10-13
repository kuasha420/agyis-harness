# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: Remote Execution Engine & OpenSSH Multiplexer (ADR-027).

Provides hermetic, multiplexed SSH connection management, zero-reconnect latency,
and non-login PATH safety for remote agent operations.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple


def get_socket_dir() -> Path:
    """
    Returns the user-space socket directory for OpenSSH ControlMaster sockets.
    Honors AGYIS_HARNESS_STATE_DIR and PSL_HARNESS_STATE_DIR if configured.
    Ensures directory exists with strict 0700 permissions to satisfy SSH security requirements.
    """
    state_dir = os.environ.get("AGYIS_HARNESS_STATE_DIR") or os.environ.get("PSL_HARNESS_STATE_DIR")
    if state_dir:
        sock_dir = Path(state_dir) / "ssh"
    else:
        sock_dir = Path.home() / ".cache" / "psl" / "ssh"

    try:
        sock_dir.mkdir(parents=True, exist_ok=True)
        sock_dir.chmod(0o700)
    except OSError:
        pass
    return sock_dir


class RemoteRunner:
    """
    Manages multiplexed SSH execution, socket lifecycles, and toolchain environment isolation.
    """

    def __init__(
        self,
        socket_dir: Optional[Path] = None,
        default_timeout: int = 30,
    ) -> None:
        self.socket_dir = socket_dir or get_socket_dir()
        self.default_timeout = default_timeout

    def get_multiplex_options(self) -> List[str]:
        """
        Generates OpenSSH multiplexing and timeout flags.
        Uses cm_%C (%C = hash of identifying connection parameters) to stay
        strictly under the 108-byte UNIX domain socket path length limit.
        """
        control_path = self.socket_dir / "cm_%C"
        return [
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={control_path}",
            "-o", "ControlPersist=10m",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=15",
        ]

    def build_command(
        self,
        target: str,
        remote_cmd: Optional[str] = None,
        port: Optional[int] = None,
        extra_options: Optional[List[str]] = None,
        login_shell: bool = False,
    ) -> List[str]:
        """
        Builds the SSH argv list suitable for subprocess execution.
        """
        cmd: List[str] = ["ssh"]
        cmd.extend(self.get_multiplex_options())

        if port is not None:
            cmd.extend(["-p", str(port)])

        if extra_options:
            cmd.extend(extra_options)

        cmd.append(target)

        if remote_cmd:
            if login_shell:
                escaped = remote_cmd.replace("'", "'\\''")
                cmd.append(f"bash -l -c '{escaped}'")
            else:
                cmd.append(remote_cmd)

        return cmd

    def run(
        self,
        target: str,
        remote_cmd: Optional[str] = None,
        input: Optional[str] = None,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
        login_shell: bool = False,
        extra_options: Optional[List[str]] = None,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """
        Executes a remote command over multiplexed SSH.
        """
        cmd = self.build_command(
            target=target,
            remote_cmd=remote_cmd,
            port=port,
            extra_options=extra_options,
            login_shell=login_shell,
        )
        effective_timeout = timeout if timeout is not None else self.default_timeout

        proc = subprocess.run(
            cmd,
            input=input,
            timeout=effective_timeout,
            capture_output=capture_output,
            text=text,
            check=check,
        )
        if proc.returncode == 255:
            self.cleanup_target_socket(target=target, port=port, extra_options=extra_options)
        return proc

    def get_target_socket_path(
        self,
        target: str,
        port: Optional[int] = None,
        extra_options: Optional[List[str]] = None,
    ) -> Optional[Path]:
        """
        Determines the ControlMaster socket path for a given target.
        Attempts to calculate the OpenSSH %C SHA-1 hash or probe OpenSSH configuration.
        """
        computed_path: Optional[Path] = None
        try:
            import hashlib
            import socket

            hostname = socket.gethostname()
            remote_user = os.environ.get("USER", "")
            remote_host = target
            remote_port = str(port) if port is not None else "22"
            if "@" in target:
                remote_user, remote_host = target.split("@", 1)

            ident = f"{hostname}{remote_host}{remote_port}{remote_user}"
            digest = hashlib.sha1(ident.encode("utf-8")).hexdigest()
            computed_path = self.socket_dir / f"cm_{digest}"
            if computed_path.exists():
                return computed_path
        except Exception:
            pass

        try:
            cmd = ["ssh", "-G"]
            cmd.extend(self.get_multiplex_options())
            if port is not None:
                cmd.extend(["-p", str(port)])
            if extra_options:
                cmd.extend(extra_options)
            cmd.append(target)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    if line.startswith("controlpath "):
                        cp = line.split(" ", 1)[1].strip()
                        if cp and cp != "none":
                            return Path(cp)
        except (subprocess.SubprocessError, OSError):
            pass

        return computed_path

    def cleanup_target_socket(
        self,
        target: str,
        port: Optional[int] = None,
        extra_options: Optional[List[str]] = None,
    ) -> List[Path]:
        """
        Cleans up ControlMaster socket specifically scoped to the failing target.
        Attempts graceful shutdown via 'ssh -O exit' and removes any stale target socket.
        Does not affect ControlMaster sockets for other active hosts.
        """
        cmd = ["ssh", "-O", "exit"]
        cmd.extend(self.get_multiplex_options())
        if port is not None:
            cmd.extend(["-p", str(port)])
        if extra_options:
            cmd.extend(extra_options)
        cmd.append(target)
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
        except (subprocess.SubprocessError, OSError):
            pass

        removed: List[Path] = []
        target_sock = self.get_target_socket_path(target, port=port, extra_options=extra_options)
        if target_sock and target_sock.exists():
            try:
                target_sock.unlink()
                removed.append(target_sock)
            except OSError:
                pass
        return removed


    def list_sockets(self) -> List[Dict[str, Any]]:
        """
        Discovers existing OpenSSH ControlMaster socket files in the socket directory.
        """
        if not self.socket_dir.exists():
            return []

        results: List[Dict[str, Any]] = []
        for item in sorted(self.socket_dir.iterdir()):
            if item.name.startswith("cm_"):
                stat_res = item.stat()
                results.append({
                    "path": str(item),
                    "name": item.name,
                    "mtime": stat_res.st_mtime,
                    "size": stat_res.st_size,
                    "is_socket": item.is_socket(),
                })
        return results

    def cleanup_sockets(self) -> List[Path]:
        """
        Cleans up and removes all ControlMaster sockets in user space.
        """
        removed: List[Path] = []
        if not self.socket_dir.exists():
            return removed

        for item in self.socket_dir.iterdir():
            if item.name.startswith("cm_"):
                try:
                    item.unlink()
                    removed.append(item)
                except OSError:
                    pass
        return removed


SSHRunner = RemoteRunner
