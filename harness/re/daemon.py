# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Persistent REA MCP Bridge Daemon & Process Supervisor (ADR-028, PSL-INV-009, Issue #113).
Manages a persistent background REA bridge process with direct-mount Ghidra project
acceleration, eliminating cold JVM startup penalties and enabling sub-second in-memory queries.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from harness.re.scaffold import get_dirtyroom_root
from harness.runtime.tool_checks_rea import (
    configure_rea_mcp_server,
    find_jdk21_path,
    find_rea_binary,
    is_rea_mcp_configured,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_daemon_dir(root: Optional[Path] = None) -> Path:
    """Returns directory housing daemon state and log files (.dirtyroom/logs)."""
    dr = root or get_dirtyroom_root()
    if dr:
        d = dr / "logs"
    else:
        d = Path.cwd() / ".dirtyroom" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_pid_file(root: Optional[Path] = None) -> Path:
    """Returns path to the daemon PID file."""
    return get_daemon_dir(root) / "rea_daemon.pid"


def get_status_file(root: Optional[Path] = None) -> Path:
    """Returns path to the daemon status metadata file."""
    return get_daemon_dir(root) / "rea_daemon_status.json"


def get_log_file(root: Optional[Path] = None) -> Path:
    """Returns path to the daemon log file."""
    return get_daemon_dir(root) / "rea_daemon.log"


def _read_pid(root: Optional[Path] = None) -> Optional[int]:
    pid_p = get_pid_file(root)
    if not pid_p.is_file():
        return None
    try:
        txt = pid_p.read_text(encoding="utf-8").strip()
        if txt.isdigit():
            return int(txt)
    except OSError:
        pass
    return None


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_status_data(root: Optional[Path] = None) -> Dict[str, Any]:
    st_p = get_status_file(root)
    if not st_p.is_file():
        return {}
    try:
        data = json.loads(st_p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _write_status_data(payload: Dict[str, Any], root: Optional[Path] = None) -> None:
    st_p = get_status_file(root)
    try:
        st_p.parent.mkdir(parents=True, exist_ok=True)
        tmp = st_p.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, st_p)
    except OSError:
        pass


def get_daemon_status(root: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects the execution state of the persistent REA bridge daemon."""
    pid = _read_pid(root)
    alive = _is_pid_alive(pid) if pid is not None else False
    status_data = _read_status_data(root)
    pid_p = get_pid_file(root)
    log_p = get_log_file(root)

    # Clean up stale PID file if process is dead
    if pid is not None and not alive:
        try:
            pid_p.unlink(missing_ok=True)
        except OSError:
            pass
        pid = None

    uptime_s = 0.0
    if alive and status_data.get("started_at_ts"):
        try:
            uptime_s = max(0.0, time.time() - float(status_data["started_at_ts"]))
        except (ValueError, TypeError):
            pass

    from harness.re.patcher import check_patch

    patch_info = check_patch()
    dr = root or get_dirtyroom_root()

    ghidra_proj = None
    if dr and (dr / "ghidra").is_dir():
        gprs = list((dr / "ghidra").glob("*.gpr"))
        if gprs:
            ghidra_proj = gprs[0].stem

    return {
        "status": "running" if alive else "stopped",
        "running": alive,
        "pid": pid,
        "child_pid": status_data.get("child_pid") if alive else None,
        "started_at": status_data.get("started_at") if alive else None,
        "uptime_seconds": round(uptime_s, 1) if alive else 0.0,
        "log_file": str(log_p),
        "pid_file": str(pid_p),
        "mcp_configured": is_rea_mcp_configured(),
        "direct_mount_active": patch_info.get("direct_mount_active", False),
        "ghidra_project": ghidra_proj,
    }


def stop_daemon(root: Optional[Path] = None, timeout: float = 4.0) -> Dict[str, Any]:
    """Gracefully terminates the background REA bridge daemon."""
    pid = _read_pid(root)
    pid_p = get_pid_file(root)

    if pid is None or not _is_pid_alive(pid):
        try:
            pid_p.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "success": True,
            "stopped": False,
            "message": "REA bridge daemon is not running.",
            "pid": None,
        }

    # Terminate process group or pid with SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass

    deadline = time.time() + timeout
    terminated = False
    while time.time() < deadline:
        if not _is_pid_alive(pid):
            terminated = True
            break
        time.sleep(0.1)

    if not terminated:
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.1)
        except (OSError, ProcessLookupError):
            pass

    try:
        pid_p.unlink(missing_ok=True)
    except OSError:
        pass

    st = _read_status_data(root)
    st["status"] = "stopped"
    st["stopped_at"] = _utc_now_iso()
    _write_status_data(st, root)

    return {
        "success": True,
        "stopped": True,
        "message": f"Successfully stopped REA bridge daemon (PID {pid}).",
        "pid": pid,
    }


def _prepare_daemon_env(root: Optional[Path] = None) -> Dict[str, str]:
    """Prepares the comprehensive environment dictionary for REA daemon execution."""
    env = os.environ.copy()
    dr = root or get_dirtyroom_root()

    jdk_path = find_jdk21_path()
    if jdk_path:
        env["JAVA_HOME"] = str(jdk_path)

    ghidra_dir = env.get("GHIDRA_INSTALL_DIR")
    if not ghidra_dir:
        for cand in [Path("/opt/ghidra"), Path("/usr/local/opt/ghidra"), Path.home() / "ghidra"]:
            if cand.is_dir():
                env["GHIDRA_INSTALL_DIR"] = str(cand)
                break

    if dr and (dr / "ghidra").is_dir():
        ghidra_proj_dir = dr / "ghidra"
        env["REA_GHIDRA_PROJECT_DIR"] = str(ghidra_proj_dir)
        gprs = list(ghidra_proj_dir.glob("*.gpr"))
        if gprs:
            env["REA_GHIDRA_PROJECT_NAME"] = gprs[0].stem
            env["REA_GHIDRA_PROJECT_PATH"] = str(gprs[0])
            env["REA_GHIDRA_PROGRAM_NAME"] = gprs[0].stem
        env["AGYIS_DIRTYROOM"] = str(dr)

    env["REA_GHIDRA_DIRECT_MOUNT"] = "1"
    env["REA_MCP_INPUT_SCHEMA_PROFILE"] = "full"
    env["REA_MCP_OUTPUT_SCHEMA_PROFILE"] = "off"
    return env


def _run_worker(root: Optional[Path] = None) -> int:
    """Internal supervisor entrypoint holding open connection to rea mcp."""
    pid_p = get_pid_file(root)
    log_p = get_log_file(root)

    # Write own PID
    pid_p.write_text(f"{os.getpid()}\n", encoding="utf-8")

    rea_bin = find_rea_binary() or shutil.which("rea")
    if not rea_bin:
        sys.stderr.write("[!] 'rea' binary not found in PATH.\n")
        return 1

    env = _prepare_daemon_env(root)

    with open(log_p, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- REA Bridge Daemon Started at {_utc_now_iso()} (Supervisor PID: {os.getpid()}) ---\n")
        log_f.flush()

        cmd = [str(rea_bin), "mcp"]
        child: Optional[subprocess.Popen] = None

        def _handle_term(signum, frame):
            if child and child.poll() is None:
                try:
                    child.terminate()
                except OSError:
                    pass
            sys.exit(0)

        signal.signal(signal.SIGTERM, _handle_term)
        signal.signal(signal.SIGINT, _handle_term)

        try:
            child = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Record status
            status_data = {
                "status": "running",
                "supervisor_pid": os.getpid(),
                "child_pid": child.pid,
                "started_at": _utc_now_iso(),
                "started_at_ts": time.time(),
                "ghidra_project": env.get("REA_GHIDRA_PROJECT_NAME"),
                "ghidra_project_dir": env.get("REA_GHIDRA_PROJECT_DIR"),
                "direct_mount": env.get("REA_GHIDRA_DIRECT_MOUNT"),
            }
            _write_status_data(status_data, root)

            # Perform MCP initialization handshake to warm up JVM & language providers
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "agyis-daemon-bridge", "version": "1.0.0"},
                },
            }
            if child.stdin:
                child.stdin.write(json.dumps(init_payload) + "\n")
                child.stdin.flush()

            # Keep process alive while child is healthy
            while child.poll() is None:
                time.sleep(0.5)

            log_f.write(f"--- REA Bridge Child Exited with code {child.returncode} at {_utc_now_iso()} ---\n")
            log_f.flush()
            return child.returncode or 0

        except Exception as e:
            log_f.write(f"[!] REA Daemon Exception: {e}\n")
            log_f.flush()
            return 1
        finally:
            try:
                pid_p.unlink(missing_ok=True)
            except OSError:
                pass


def start_daemon(
    root: Optional[Path] = None,
    foreground: bool = False,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """Starts the persistent REA bridge daemon in background or foreground."""
    curr_status = get_daemon_status(root)
    if curr_status["running"]:
        return {
            "success": True,
            "already_running": True,
            "pid": curr_status["pid"],
            "message": f"REA bridge daemon is already running (PID {curr_status['pid']}).",
        }

    rea_bin = find_rea_binary() or shutil.which("rea")
    if not rea_bin:
        return {
            "success": False,
            "error": "'rea' CLI not found. Run 'agyis doctor --experimental-rea' or install via pnpm.",
        }

    if foreground:
        code = _run_worker(root)
        return {"success": code == 0, "foreground": True, "exit_code": code}

    # Spawn supervisor worker detached
    cmd = [sys.executable, "-m", "harness.re.daemon", "--worker"]
    log_p = get_log_file(root)
    spawn_env = os.environ.copy()
    if root:
        spawn_env["AGYIS_DIRTYROOM"] = str(root)

    with open(log_p, "a", encoding="utf-8") as err_out:
        proc = subprocess.Popen(
            cmd,
            env=spawn_env,
            stdout=subprocess.DEVNULL,
            stderr=err_out,
            start_new_session=True,
        )

    # Await daemon PID file creation
    deadline = time.time() + timeout
    started_pid = None
    while time.time() < deadline:
        pid = _read_pid(root)
        if pid and _is_pid_alive(pid):
            started_pid = pid
            break
        time.sleep(0.1)

    if not started_pid:
        return {
            "success": False,
            "error": "Daemon failed to start within timeout. Check log at " + str(log_p),
        }

    # Ensure MCP server is also configured in user config
    try:
        configure_rea_mcp_server()
    except Exception:
        pass

    return {
        "success": True,
        "already_running": False,
        "pid": started_pid,
        "log_file": str(log_p),
        "message": f"Started persistent REA bridge daemon (PID {started_pid}).",
    }


def cmd_daemon(args: argparse.Namespace) -> int:
    """CLI dispatcher for 'agyis re daemon [status|start|stop]'."""
    action = getattr(args, "daemon_action", "status") or "status"

    if action == "status":
        st = get_daemon_status()
        if getattr(args, "json", False):
            print(json.dumps(st, indent=2))
            return 0

        status_icon = "🟢 RUNNING" if st["running"] else "⚪ STOPPED"
        print("======================================================================")
        print(" 🔌 Agyis Persistent REA MCP Bridge Daemon (ADR-028, Issue #113)")
        print("======================================================================")
        print(f" State:               {status_icon}")
        if st["running"]:
            print(f" Supervisor PID:      {st['pid']}")
            if st.get("child_pid"):
                print(f" REA Child PID:       {st['child_pid']}")
            print(f" Uptime:              {st['uptime_seconds']:.1f}s")
            print(f" Started At:          {st['started_at']}")
        print(f" Attached Project:    {st['ghidra_project'] or 'None (Target-free)'}")
        print(f" Direct Mount Active: {'✔ YES' if st['direct_mount_active'] else '✘ NO'}")
        print(f" MCP Configured:      {'✔ YES' if st['mcp_configured'] else '✘ NO'}")
        print(f" Log File:            {st['log_file']}")
        print("======================================================================")
        return 0

    if action == "start":
        fg = getattr(args, "foreground", False)
        res = start_daemon(foreground=fg)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0 if res.get("success") else 1

        if res.get("success"):
            if res.get("already_running"):
                print(f"[*] {res['message']}")
            else:
                print(f"[+] {res['message']}")
                print(f"    - Logs: {res.get('log_file')}")
            return 0
        else:
            print(f"[!] Error starting daemon: {res.get('error')}", file=sys.stderr)
            return 1

    if action == "stop":
        res = stop_daemon()
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0 if res.get("success") else 1

        print(f"[+] {res['message']}")
        return 0

    print(f"[!] Unknown daemon action '{action}'. Use 'status', 'start', or 'stop'.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    if "--worker" in sys.argv:
        sys.exit(_run_worker())
    parser = argparse.ArgumentParser(description="Persistent REA MCP Bridge Daemon CLI")
    parser.add_argument("daemon_action", choices=["status", "start", "stop"], nargs="?", default="status")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--foreground", action="store_true", help="Run daemon in foreground")
    parsed = parser.parse_args()
    sys.exit(cmd_daemon(parsed))
