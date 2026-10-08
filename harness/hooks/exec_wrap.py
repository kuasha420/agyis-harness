#!/usr/bin/env python3
"""
PSL Harness: In-Band Command Execution Compactor Wrapper (ADR-011 / ADR-014)

Executes commands in-band, streaming and compacting stdout/stderr:
1. Emits output verbatim if length <= 2048 characters.
2. If output > 2048 characters and exit code is 0:
   Compacts in-band (500 chars head context, truncation marker,
   preserved exit/fatal/error keyword lines, 1000 chars tail).
3. If exit code != 0:
   Preserves full uncompacted diagnostic output to assist root-cause debugging.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Mapping, Sequence, Tuple, Union

from harness.hooks.output_compactor_hook import (
    HEAD_CHARS,
    MAX_OUTPUT_CHARS,
    TAIL_CHARS,
    compact_output,
)


def run_with_compaction(
    command: Union[str, Sequence[str]],
    shell: bool = True,
    cwd: Union[str, Path, None] = None,
    env: Union[Mapping[str, str], None] = None,
    max_chars: int = MAX_OUTPUT_CHARS,
) -> Tuple[int, str]:
    """
    Executes a command and returns (exit_code, compacted_output).

    Invariants:
    - Exit code != 0: Full output is preserved verbatim.
    - Exit code == 0 and len <= max_chars: Output is preserved verbatim.
    - Exit code == 0 and len > max_chars: Compacted in-band preserving head, tail,
      and diagnostic lines.
    """
    if isinstance(command, (list, tuple)) and shell:
        cmd_arg = shlex.join(str(c) for c in command)
    else:
        cmd_arg = command

    run_env = dict(env) if env is not None else None

    proc = subprocess.run(
        cmd_arg,
        shell=shell,
        cwd=str(cwd) if cwd else None,
        env=run_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )

    raw_output = proc.stdout or ""
    exit_code = proc.returncode

    if exit_code != 0:
        return exit_code, raw_output

    if len(raw_output) <= max_chars:
        return exit_code, raw_output

    compacted = compact_output(raw_output, exit_code=0, max_chars=max_chars)
    return exit_code, compacted


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for psl-exec-wrap."""
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        sys.stderr.write("Usage: exec_wrap.py [-c] <command...>\n")
        return 1

    if args[0] == "-c" and len(args) > 1:
        cmd = " ".join(args[1:])
    else:
        cmd = " ".join(args)

    exit_code, output = run_with_compaction(cmd, shell=True)
    if output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
