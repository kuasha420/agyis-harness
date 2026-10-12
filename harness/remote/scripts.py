# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
PSL Harness: Remote Script Streaming & Staging Engine (ADR-027).

Enforces zero remote disk footprint by streaming scripts via stdin into
language interpreters (python3 -s -, node -, bash -l -s), with an optional
hermetic staging mode (--stage) that guarantees trap cleanup.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import subprocess
import uuid
from typing import Any, Dict, List, Optional

from harness.remote.runner import RemoteRunner


class ScriptStreamer:
    """
    Streams local scripts directly to remote processes over SSH stdin,
    or stages them safely with automatic EXIT trap cleanup.
    """

    @staticmethod
    def determine_runtime(script_path: Path, content: Optional[str] = None) -> List[str]:
        """
        Determines the appropriate remote interpreter command based on shebang or file extension.
        Defaults to bash -l -s.
        """
        shebang_line: Optional[str] = None
        if content:
            first_line = content.splitlines()[0] if content else ""
            if first_line.startswith("#!"):
                shebang_line = first_line
        elif script_path.exists():
            try:
                with open(script_path, "r", encoding="utf-8", errors="replace") as f:
                    first_line = f.readline()
                    if first_line.startswith("#!"):
                        shebang_line = first_line
            except OSError:
                pass

        if shebang_line:
            lower_sb = shebang_line.lower()
            if "python" in lower_sb:
                return ["python3", "-s", "-"]
            if "node" in lower_sb:
                return ["node", "-"]
            if "bash" in lower_sb or "sh" in lower_sb:
                return ["bash", "-l", "-s"]

        ext = script_path.suffix.lower()
        if ext == ".py":
            return ["python3", "-s", "-"]
        elif ext in (".js", ".mjs", ".cjs", ".ts"):
            return ["node", "-"]
        elif ext in (".sh", ".bash"):
            return ["bash", "-l", "-s"]

        return ["bash", "-l", "-s"]

    @classmethod
    def stream_script(
        cls,
        runner: RemoteRunner,
        target: str,
        script_path: Path,
        args: Optional[List[str]] = None,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        """
        Reads local script and streams via stdin to remote interpreter.
        Guarantees zero remote disk footprint.
        """
        if not script_path.exists():
            raise FileNotFoundError(f"Local script not found: {script_path}")

        content = script_path.read_text(encoding="utf-8", errors="replace")
        runtime_tokens = cls.determine_runtime(script_path, content)

        # Build remote execution command
        remote_tokens = list(runtime_tokens)
        if args:
            if runtime_tokens[0] == "bash":
                remote_tokens.append("--")
            remote_tokens.extend(shlex.quote(a) for a in args)

        remote_cmd = " ".join(remote_tokens)

        return runner.run(
            target=target,
            remote_cmd=remote_cmd,
            input=content,
            port=port,
            timeout=timeout,
        )

    @classmethod
    def stage_script(
        cls,
        runner: RemoteRunner,
        target: str,
        script_path: Path,
        args: Optional[List[str]] = None,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        """
        Stages local script in /tmp/.psl_remote_<id>/ on the remote target,
        executes it, and guarantees cleanup via trap 'rm -rf ...' EXIT.
        """
        if not script_path.exists():
            raise FileNotFoundError(f"Local script not found: {script_path}")

        content = script_path.read_text(encoding="utf-8", errors="replace")
        stage_id = uuid.uuid4().hex[:8]
        stage_dir = f"/tmp/.psl_remote_{stage_id}"
        dest_filename = script_path.name
        dest_file = f"{stage_dir}/{dest_filename}"

        stage_dir_q = shlex.quote(stage_dir)
        dest_file_q = shlex.quote(dest_file)
        sentinel = f"EOF_PSL_STAGE_{stage_id}"

        has_shebang = content.startswith("#!")
        args_str = " ".join(shlex.quote(a) for a in args) if args else ""

        if has_shebang:
            exec_part = f"{dest_file_q} {args_str}".strip()
        else:
            runtime_tokens = cls.determine_runtime(script_path, content)
            runtime_bin = runtime_tokens[0]
            if runtime_bin == "python3":
                interpreter = "python3 -s"
            elif runtime_bin == "node":
                interpreter = "node"
            elif runtime_bin == "bash":
                interpreter = "bash -l"
            else:
                interpreter = runtime_bin
            exec_part = f"{interpreter} {dest_file_q} {args_str}".strip()

        # Wrap in trap script
        remote_script = (
            f"mkdir -p {stage_dir_q} && "
            f"trap 'rm -rf {stage_dir_q}' EXIT && "
            f"cat << '{sentinel}' > {dest_file_q}\n"
            f"{content}\n"
            f"{sentinel}\n"
            f"chmod +x {dest_file_q} && "
            f"{exec_part}"
        )

        return runner.run(
            target=target,
            remote_cmd=remote_script,
            login_shell=True,
            port=port,
            timeout=timeout,
        )


RemoteScriptStreamer = ScriptStreamer

