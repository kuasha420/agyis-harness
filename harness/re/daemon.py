# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Persistent REA MCP Bridge Daemon & Process Supervisor (ADR-028, PSL-RE-001, Issue #113).
Manages a persistent background REA bridge process with direct-mount Ghidra project
acceleration, eliminating cold JVM startup penalties and enabling sub-second in-memory queries.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, IO, Optional

from harness import __version__
from harness.utils import theme

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

from harness.re.registry import resolve_nondot_ghidra_dir
from harness.re.scaffold import get_dirtyroom_root
from harness.runtime.tool_checks_rea import (
    configure_rea_mcp_server,
    find_jdk21_path,
    find_rea_binary,
    is_rea_mcp_configured,
)

_DAEMON_READ_TIMEOUT_S = 10.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise OSError(f"Refusing symlinked daemon state path: {path}")


def _atomic_write_text(target: Path, content: str) -> None:
    _reject_symlink(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_f:
            tmp_name = tmp_f.name
            tmp_f.write(content)
        os.replace(tmp_name, target)
    except OSError:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        raise


def _read_line_with_timeout(stream: IO[str], timeout_s: float = _DAEMON_READ_TIMEOUT_S) -> Optional[str]:
    """Reads a single line from stream with a fail-fast select timeout (PSL-RE-001 §2)."""
    try:
        fd = stream.fileno()
        ready, _, _ = select.select([fd], [], [], timeout_s)
        if not ready:
            return None
    except (OSError, ValueError):
        return None
    try:
        return stream.readline()
    except OSError:
        return None


def _kill_process_group_safe(pgid: Any, sig: int) -> None:
    """Terminates a child process group safely without affecting the current process group."""
    if not isinstance(pgid, int) or pgid <= 0:
        return
    try:
        if pgid == os.getpgrp():
            return
        os.killpg(pgid, sig)
    except (OSError, ProcessLookupError, PermissionError):
        pass


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


def get_socket_file(root: Optional[Path] = None) -> Path:
    """Returns path to the daemon Unix domain socket."""
    return get_daemon_dir(root) / "rea_mcp.sock"


def get_status_file(root: Optional[Path] = None) -> Path:
    """Returns path to the daemon status metadata file."""
    return get_daemon_dir(root) / "rea_daemon_status.json"


def get_log_file(root: Optional[Path] = None) -> Path:
    """Returns path to the daemon log file."""
    return get_daemon_dir(root) / "rea_daemon.log"


def _read_pid(root: Optional[Path] = None) -> Optional[int]:
    pid_p = get_pid_file(root)
    if pid_p.is_symlink() or not pid_p.is_file():
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
    if st_p.is_symlink() or not st_p.is_file():
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
        _atomic_write_text(st_p, json.dumps(payload, indent=2) + "\n")
    except OSError as exc:
        sys.stderr.write(f"[!] Warning: Could not update daemon status file {st_p}: {exc}\n")


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
            if not pid_p.is_symlink():
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
    if dr:
        ghidra_dir = resolve_nondot_ghidra_dir(dr) or (dr / "ghidra")
        if ghidra_dir.is_dir():
            gprs = sorted(ghidra_dir.glob("*.gpr"))
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
        "socket_file": str(get_socket_file(root)),
        "socket_active": get_socket_file(root).is_socket() if alive else False,
        "mcp_configured": is_rea_mcp_configured(),
        "direct_mount_active": patch_info.get("direct_mount_active", False),
        "ghidra_project": ghidra_proj,
    }


def stop_daemon(root: Optional[Path] = None, timeout: float = 4.0) -> Dict[str, Any]:
    """Gracefully terminates the background REA bridge daemon and its child process group."""
    pid = _read_pid(root)
    pid_p = get_pid_file(root)
    st = _read_status_data(root)
    child_pgid = st.get("child_pgid") or st.get("child_pid")

    if pid is None or not _is_pid_alive(pid):
        _kill_process_group_safe(child_pgid, signal.SIGTERM)
        try:
            if not pid_p.is_symlink():
                pid_p.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "success": True,
            "stopped": False,
            "message": "REA bridge daemon is not running.",
            "pid": None,
        }

    # Terminate child process group (rea mcp + Ghidra JVM) and supervisor process
    _kill_process_group_safe(child_pgid, signal.SIGTERM)
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
        _kill_process_group_safe(child_pgid, signal.SIGKILL)
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.1)
        except (OSError, ProcessLookupError):
            pass
    elif isinstance(child_pgid, int) and child_pgid > 0 and _is_pid_alive(child_pgid):
        _kill_process_group_safe(child_pgid, signal.SIGKILL)

    sock_p = get_socket_file(root)
    for p in (pid_p, sock_p):
        try:
            if not p.is_symlink():
                p.unlink(missing_ok=True)
        except OSError:
            pass

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
    """Prepares the environment dictionary for REA daemon execution (PSL-RE-001)."""
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

    # Remove stale program override so direct-mount resolves the actual target binary per request
    env.pop("REA_GHIDRA_PROGRAM_NAME", None)

    if dr:
        env["AGYIS_DIRTYROOM"] = str(dr)
        ghidra_proj_dir = resolve_nondot_ghidra_dir(dr)
        if ghidra_proj_dir and ghidra_proj_dir.is_dir():
            env["REA_GHIDRA_PROJECT_DIR"] = str(ghidra_proj_dir)
            gprs = sorted(ghidra_proj_dir.glob("*.gpr"))
            if gprs:
                env["REA_GHIDRA_PROJECT_NAME"] = gprs[0].stem
                env["REA_GHIDRA_PROJECT_PATH"] = str(gprs[0])

    env["REA_GHIDRA_DIRECT_MOUNT"] = "1"
    env["REA_MCP_INPUT_SCHEMA_PROFILE"] = "full"
    env["REA_MCP_OUTPUT_SCHEMA_PROFILE"] = "off"
    return env


def _run_worker(root: Optional[Path] = None) -> int:
    """Internal supervisor entrypoint holding open connection to rea mcp."""
    daemon_dir = get_daemon_dir(root)
    pid_p = get_pid_file(root)
    log_p = get_log_file(root)
    sock_path = get_socket_file(root)
    lock_path = daemon_dir / "rea_daemon.lock"

    try:
        for state_p in (pid_p, log_p, sock_path, get_status_file(root), lock_path):
            _reject_symlink(state_p)
    except OSError as exc:
        sys.stderr.write(f"[!] {exc}\n")
        return 1

    lock_f = open(lock_path, "a+", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_f.close()
            sys.stderr.write("[!] Another REA bridge daemon instance holds rea_daemon.lock.\n")
            return 1

    rea_bin = find_rea_binary() or shutil.which("rea")
    if not rea_bin:
        lock_f.close()
        sys.stderr.write("[!] 'rea' binary not found in PATH.\n")
        return 1

    env = _prepare_daemon_env(root)

    try:
        with open(log_p, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n--- REA Bridge Daemon Started at {_utc_now_iso()} (Supervisor PID: {os.getpid()}) ---\n")
            log_f.flush()

            cmd = [str(rea_bin), "mcp"]
            child: Optional[subprocess.Popen] = None
            srv_sock: Optional[socket.socket] = None
            child_lock = threading.Lock()
            stop_event = threading.Event()

            def _handle_term(signum, frame):
                stop_event.set()
                if srv_sock is not None:
                    try:
                        srv_sock.close()
                    except OSError:
                        pass
                if child and child.poll() is None:
                    _kill_process_group_safe(child.pid, signal.SIGTERM)
                    try:
                        child.terminate()
                    except OSError:
                        pass
                for p in (sock_path, pid_p):
                    try:
                        if not p.is_symlink():
                            p.unlink(missing_ok=True)
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
                    stdout=subprocess.PIPE,
                    stderr=log_f,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )

                # Bind Unix domain socket with restrictive 0o600 permissions
                _reject_symlink(sock_path)
                sock_path.unlink(missing_ok=True)
                srv_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                old_umask = os.umask(0o177)
                try:
                    srv_sock.bind(str(sock_path))
                finally:
                    os.umask(old_umask)
                os.chmod(sock_path, 0o600)
                srv_sock.listen(16)
                srv_sock.settimeout(0.5)

                # Perform MCP initialization handshake with 10s fail-fast timeout (PSL-RE-001 §2)
                init_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "agyis-daemon-bridge", "version": __version__},
                    },
                }
                if not child.stdin or not child.stdout:
                    raise OSError("REA child pipes were not initialized")
                child.stdin.write(json.dumps(init_payload) + "\n")
                child.stdin.flush()

                init_resp = _read_line_with_timeout(child.stdout, _DAEMON_READ_TIMEOUT_S)
                if not init_resp:
                    raise TimeoutError(
                        f"REA MCP initialize handshake did not respond within {_DAEMON_READ_TIMEOUT_S}s"
                    )
                log_f.write(f"[init] {init_resp}")
                log_f.flush()

                # Complete MCP handshake with notifications/initialized
                notif_payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                child.stdin.write(json.dumps(notif_payload) + "\n")
                child.stdin.flush()

                # Record status and publish PID atomically ONLY after Popen + socket + MCP handshake succeed
                status_data = {
                    "status": "running",
                    "supervisor_pid": os.getpid(),
                    "child_pid": child.pid,
                    "child_pgid": child.pid,
                    "started_at": _utc_now_iso(),
                    "started_at_ts": time.time(),
                    "socket_file": str(sock_path),
                    "ghidra_project": env.get("REA_GHIDRA_PROJECT_NAME"),
                    "ghidra_project_dir": env.get("REA_GHIDRA_PROJECT_DIR"),
                    "direct_mount": env.get("REA_GHIDRA_DIRECT_MOUNT"),
                }
                _write_status_data(status_data, root)
                _atomic_write_text(pid_p, f"{os.getpid()}\n")

                def _serve_socket_clients() -> None:
                    while not stop_event.is_set() and child and child.poll() is None:
                        try:
                            conn, _ = srv_sock.accept()
                        except socket.timeout:
                            continue
                        except OSError:
                            break
                        try:
                            conn.settimeout(_DAEMON_READ_TIMEOUT_S)
                            with conn, conn.makefile("r", encoding="utf-8", errors="replace") as conn_reader:
                                raw = conn_reader.readline()
                                if not raw or not child.stdin or not child.stdout:
                                    continue
                                with child_lock:
                                    child.stdin.write(raw.rstrip("\r\n") + "\n")
                                    child.stdin.flush()
                                    resp_line = _read_line_with_timeout(child.stdout, _DAEMON_READ_TIMEOUT_S)
                                if resp_line:
                                    conn.sendall(resp_line.encode("utf-8"))
                                else:
                                    err_resp = json.dumps({
                                        "jsonrpc": "2.0",
                                        "error": {"code": -32000, "message": "REA bridge timed out after 10s"},
                                    }) + "\n"
                                    conn.sendall(err_resp.encode("utf-8"))
                        except OSError:
                            pass

                srv_thread = threading.Thread(target=_serve_socket_clients, daemon=True)
                srv_thread.start()

                while child.poll() is None and not stop_event.is_set():
                    time.sleep(0.5)

                log_f.write(f"--- REA Bridge Child Exited with code {child.returncode} at {_utc_now_iso()} ---\n")
                log_f.flush()
                return child.returncode or 0

            except Exception as exc:
                log_f.write(f"[!] REA Daemon Exception: {exc}\n")
                log_f.flush()
                if child and child.poll() is None:
                    _kill_process_group_safe(child.pid, signal.SIGTERM)
                return 1
            finally:
                stop_event.set()
                if child and child.poll() is None:
                    _kill_process_group_safe(child.pid, signal.SIGTERM)
                if srv_sock is not None:
                    try:
                        srv_sock.close()
                    except OSError:
                        pass
                for p in (sock_path, pid_p):
                    try:
                        if not p.is_symlink():
                            p.unlink(missing_ok=True)
                    except OSError:
                        pass
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_f.close()


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
            "error": "'rea' CLI not found. Run 'agyis doctor --rea' or install via pnpm.",
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
        subprocess.Popen(
            cmd,
            env=spawn_env,
            stdout=subprocess.DEVNULL,
            stderr=err_out,
            start_new_session=True,
        )

    # Await daemon PID file creation (written only after socket + MCP handshake succeed)
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

    # Ensure MCP server is also configured in user config, surfacing any error cleanly
    mcp_warning: Optional[str] = None
    try:
        configure_rea_mcp_server()
    except (OSError, ValueError, RuntimeError) as exc:
        mcp_warning = f"Warning: Failed to configure REA MCP server entry: {exc}"
        sys.stderr.write(f"[!] {mcp_warning}\n")

    res: Dict[str, Any] = {
        "success": True,
        "already_running": False,
        "pid": started_pid,
        "log_file": str(log_p),
        "message": f"Started persistent REA bridge daemon (PID {started_pid}).",
    }
    if mcp_warning:
        res["mcp_warning"] = mcp_warning
    return res


def query_daemon_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    root: Optional[Path] = None,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Send one JSON-RPC tools/call request over rea_mcp.sock, returning result dict or None."""
    sock_path = get_socket_file(root)
    if sock_path.is_symlink() or not sock_path.exists():
        return None
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) & 0x7FFFFFFF or 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as cli:
            cli.settimeout(timeout)
            cli.connect(str(sock_path))
            cli.sendall(payload.encode("utf-8"))
            with cli.makefile("r", encoding="utf-8", errors="replace") as reader:
                raw = reader.readline()
    except OSError as exc:
        sys.stderr.write(f"[!] Warning: REA daemon socket query ({tool_name}) failed: {exc}; falling back to CLI.\n")
        return None
    if not raw:
        sys.stderr.write(f"[!] Warning: REA daemon returned empty response for {tool_name}; falling back to CLI.\n")
        return None
    try:
        resp = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[!] Warning: REA daemon returned invalid JSON for {tool_name}: {exc}; falling back to CLI.\n")
        return None
    if not isinstance(resp, dict) or "error" in resp:
        err_detail = resp.get("error") if isinstance(resp, dict) else type(resp).__name__
        sys.stderr.write(f"[!] Warning: REA daemon RPC error for {tool_name}: {err_detail}; falling back to CLI.\n")
        return None
    result = resp.get("result")
    return result if isinstance(result, dict) else {"value": result}


def cmd_daemon(args: argparse.Namespace) -> int:
    """CLI dispatcher for 'agyis re daemon [status|start|stop]'."""
    action = getattr(args, "daemon_action", "status") or "status"

    if action == "status":
        st = get_daemon_status()
        if getattr(args, "json", False):
            print(json.dumps(st, indent=2))
            return 0

        status_icon = theme.badge("ACTIVE", "RUNNING") if st["running"] else theme.badge("STOPPED", "STOPPED")
        print(theme.banner("Agyis Persistent REA MCP Bridge Daemon (ADR-028, Issue #113)"))
        print(f" State:               {status_icon}")
        if st["running"]:
            print(f" Supervisor PID:      {st['pid']}")
            if st.get("child_pid"):
                print(f" REA Child PID:       {st['child_pid']}")
            print(f" Uptime:              {st['uptime_seconds']:.1f}s")
            print(f" Started At:          {st['started_at']}")
        print(f" Attached Project:    {st['ghidra_project'] or 'None (Target-free)'}")
        print(f" Direct Mount Active: {theme.badge('PASS', 'YES') if st['direct_mount_active'] else theme.badge('FAIL', 'NO')}")
        print(f" MCP Configured:      {theme.badge('PASS', 'YES') if st['mcp_configured'] else theme.badge('FAIL', 'NO')}")
        print(f" Log File:            {st['log_file']}")
        print(theme.rule("━"))
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
