# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Remote operations and cloud/mesh triage CLI command (ADR-014, ADR-027).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def cmd_remote(args: argparse.Namespace) -> int:
    """Dispatches remote execution, script streaming, and triage subcommands."""
    sub = getattr(args, "remote_cmd", None)
    if not sub:
        sys.stderr.write("Usage: psl remote <exec|script|triage|socket> ...\n")
        return 1

    from harness.remote import RemoteRunner, ScriptStreamer, RemoteTriage

    runner = RemoteRunner()

    if sub == "exec":
        login_shell = getattr(args, "login_shell", False)
        if not login_shell:
            from harness.hooks.command_safety_hook import REMOTE_TOOLCHAIN_REGEX
            if REMOTE_TOOLCHAIN_REGEX.search(args.command):
                login_shell = True

        res = runner.run(
            target=args.target,
            remote_cmd=args.command,
            port=args.port,
            timeout=args.timeout,
            login_shell=login_shell,
            capture_output=True,
            text=True,
        )
        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        return res.returncode

    elif sub == "script":
        script_path = Path(args.script)
        if not script_path.exists():
            sys.stderr.write(f"Error: Local script not found: {script_path}\n")
            return 1

        script_args = getattr(args, "args", [])
        if getattr(args, "stage", False):
            res = ScriptStreamer.stage_script(
                runner=runner,
                target=args.target,
                script_path=script_path,
                args=script_args,
                port=args.port,
                timeout=args.timeout,
            )
        else:
            res = ScriptStreamer.stream_script(
                runner=runner,
                target=args.target,
                script_path=script_path,
                args=script_args,
                port=args.port,
                timeout=args.timeout,
            )

        if res.stdout:
            sys.stdout.write(res.stdout)
        if res.stderr:
            sys.stderr.write(res.stderr)
        return res.returncode

    elif sub == "triage":
        report_data = RemoteTriage.run_triage(
            runner=runner,
            target=args.target,
            profile=args.profile,
            service=args.service,
            lines=args.lines,
            port=args.port,
            timeout=args.timeout,
        )

        if getattr(args, "json", False):
            print(json.dumps(report_data, indent=2))
        else:
            print(report_data["report_markdown"])
        return int(report_data.get("exit_code", 0))

    elif sub == "socket":
        action = getattr(args, "socket_action", None) or "status"
        if action == "cleanup":
            removed = runner.cleanup_sockets()
            print(f"🧹 Cleaned up {len(removed)} active ControlMaster socket(s).")
            for sock in removed:
                print(f"  ✔ Removed: {sock.name}")
            return 0
        else:
            sockets = runner.list_sockets()
            if not sockets:
                print(f"No active OpenSSH ControlMaster sockets found in {runner.socket_dir}")
                return 0
            print(f"Active OpenSSH ControlMaster sockets ({len(sockets)}):")
            for sock in sockets:
                print(f"  ✔ {sock['name']} (Path: {sock['path']})")
            return 0

    elif sub == "screens":
        from harness.remote.display_bridge import capture_fleet_screens

        raw_data = getattr(args, "data", None)
        json_data = None
        if raw_data:
            p = Path(raw_data)
            if p.is_file():
                try:
                    json_data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                except Exception as exc:
                    sys.stderr.write(f"Error parsing JSON from {p}: {exc}\n")
                    return 1
            else:
                try:
                    json_data = json.loads(raw_data)
                except Exception as exc:
                    sys.stderr.write(f"Error parsing inline JSON: {exc}\n")
                    return 1

        md_path = capture_fleet_screens(
            brain_dir=getattr(args, "brain_dir", None),
            json_data=json_data,
        )
        if getattr(args, "json", False):
            print(json.dumps({"artifact": str(md_path), "status": "ok"}, indent=2))
        else:
            print(f"✔ Fleet screens carousel generated at {md_path}")
        return 0

    return 0
