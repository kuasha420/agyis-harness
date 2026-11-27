# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Systemd unit generation for telemetry background sync (ADR-030).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Union

from harness.utils import theme

SERVICE_NAME = "agyis-sync.service"


def get_default_service_path() -> Path:
    """Returns the default destination path for the user systemd unit."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return base_dir / "systemd" / "user" / SERVICE_NAME


def get_service_unit_path(custom_path: Optional[Union[str, Path]] = None) -> Path:
    """Returns the resolved destination path for the user systemd unit."""
    if custom_path is not None:
        return Path(custom_path)
    return get_default_service_path()


def _quote_systemd_token(value: str) -> str:
    """Quotes a systemd path/argument if it contains whitespace or metacharacters."""
    if not value:
        return '""'
    if any(ch.isspace() or ch in ('"', "'", "\\", ";") for ch in value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _is_transient_dir(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    norm = path.as_posix().lower()
    return (
        bool(parts.intersection({"worktrees", "site-packages", "dist-packages", "plugins"}))
        or "/.gemini/config/plugins" in norm
        or norm.startswith("/tmp/")
    )


def generate_systemd_service(
    python_bin: Optional[str] = None,
    interval_sec: float = 5.0,
    working_dir: Optional[Union[str, Path]] = None,
    agyis_bin: Optional[str] = None,
) -> str:
    """Generates the systemd user service unit definition for agyis-sync.service."""
    resolved_work_dir: Path
    if working_dir:
        resolved_work_dir = Path(working_dir).resolve()
    else:
        # Detect stable repo root without pinning to transient worktrees, plugin dirs, or site-packages
        cand = Path(__file__).resolve().parents[3]
        if (cand / "harness").is_dir() and not _is_transient_dir(cand):
            resolved_work_dir = cand
        else:
            try:
                cwd_resolved = Path.cwd().resolve()
            except OSError:
                cwd_resolved = None
            if cwd_resolved is not None and (cwd_resolved / "harness").is_dir() and not _is_transient_dir(cwd_resolved):
                resolved_work_dir = cwd_resolved
            else:
                resolved_work_dir = Path.home()

    work_dir = _quote_systemd_token(str(resolved_work_dir))

    if python_bin:
        exec_cmd = f"{_quote_systemd_token(python_bin)} -m harness.cli sync --watch --interval {interval_sec}"
    elif agyis_bin:
        exec_cmd = f"{_quote_systemd_token(agyis_bin)} sync --watch --interval {interval_sec}"
    else:
        discovered_agyis = shutil.which("agyis")
        if discovered_agyis:
            exec_cmd = f"{_quote_systemd_token(discovered_agyis)} sync --watch --interval {interval_sec}"
        else:
            py_path = sys.executable or "/usr/bin/python3"
            exec_cmd = f"{_quote_systemd_token(py_path)} -m harness.cli sync --watch --interval {interval_sec}"

    return f"""[Unit]
Description=Agyis Telemetry Background Sync Service
Documentation=https://github.com/kuasha420/agyis-harness
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={work_dir}
ExecStart={exec_cmd}
Restart=on-failure
RestartSec=10s
MemoryMax=500M
MemoryHigh=300M
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def _run_systemctl(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    """Invokes systemctl with standard arguments and error trapping."""
    systemctl_bin = shutil.which("systemctl")
    if not systemctl_bin:
        raise FileNotFoundError("systemctl executable not found in PATH")
    cmd = ["systemctl", "--user"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _handle_systemctl_error(err_str: str) -> None:
    """Prints formatted error diagnosis for systemd failures."""
    if "Failed to connect to bus" in err_str or "not been booted with systemd" in err_str:
        sys.stderr.write(
            theme.badge("FAIL", "Unable to communicate with systemd user session bus.", stream=sys.stderr) + "\n"
            f"  • Verbatim error: {err_str.strip()}\n"
            "  • Diagnosis: Systemd user session is inactive or XDG_RUNTIME_DIR is not set.\n"
            "  • Remediation: Ensure XDG_RUNTIME_DIR is set (e.g. export XDG_RUNTIME_DIR=/run/user/$(id -u)), or use foreground watch mode ('agyis sync --watch').\n"
        )
    else:
        sys.stderr.write(theme.badge("FAIL", f"systemctl command failed: {err_str.strip()}", stream=sys.stderr) + "\n")


def install_service(
    interval: float = 5.0,
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Installs and enables the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write(
            theme.badge("FAIL", "systemctl command not found.", stream=sys.stderr) + "\n"
            "  • Systemd is not installed or not available in PATH on this system.\n"
            "  • Background service management requires systemd user services.\n"
            "  • Remediation: Use foreground watch mode instead: 'agyis sync --watch --interval 10.0'\n"
        )
        return 1

    target = get_service_unit_path(unit_path or service_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        content = generate_systemd_service(interval_sec=interval)
        target.write_text(content, encoding="utf-8")
        res_reload = _run_systemctl(["daemon-reload"])
        if res_reload.returncode != 0:
            _handle_systemctl_error(res_reload.stderr)
            return 1
        res = _run_systemctl(["enable", SERVICE_NAME])
        if res.returncode != 0:
            _handle_systemctl_error(res.stderr)
            return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write(theme.badge("FAIL", "Timed out: operation timed out communicating with systemd daemon (15s limit).", stream=sys.stderr) + "\n")
        return 1
    except Exception as exc:
        sys.stderr.write(theme.badge("FAIL", f"Failed to install service: {exc}", stream=sys.stderr) + "\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "install", "installed": True, "path": str(target)}, indent=2))
    else:
        print(theme.badge("PASS", f"Installed systemd user service unit: {target}"))
        print(theme.badge("PASS", "Executed systemctl --user daemon-reload"))
        print(theme.badge("PASS", f"Enabled {SERVICE_NAME}"))
        print("  • To start the service: agyis sync --service start")
        print("  • To check status: agyis sync --service status")
    return 0


def service_status(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Reports status of the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write(theme.badge("FAIL", "systemctl command not found. Systemd is not available on this system.", stream=sys.stderr) + "\n")
        return 1

    target = get_service_unit_path(unit_path or service_path)
    if not target.exists():
        if json_output:
            print(json.dumps({"service": SERVICE_NAME, "installed": False, "active": False, "status": "not_installed"}, indent=2))
        else:
            sys.stderr.write(
                theme.badge("FAIL", f"Service '{SERVICE_NAME}' is not installed.", stream=sys.stderr) + "\n"
                f"  • Unit file not found at: {target}\n"
                "  • Remediation: Run 'agyis sync --service install' to install and enable.\n"
            )
        return 1

    try:
        res = _run_systemctl(["status", SERVICE_NAME])
        if "Failed to connect to bus" in res.stderr:
            _handle_systemctl_error(res.stderr)
            return 1
        is_active = (res.returncode == 0)
        if json_output:
            print(json.dumps({
                "service": SERVICE_NAME,
                "installed": True,
                "active": is_active,
                "exit_code": res.returncode,
                "output": res.stdout,
            }, indent=2))
        else:
            if res.stdout:
                print(res.stdout.rstrip())
            elif res.stderr:
                print(res.stderr.rstrip())
        # Returncode 0 (active) or 3 (inactive/dead) indicates loaded unit state
        return 0 if res.returncode in (0, 3) else 1
    except subprocess.TimeoutExpired:
        sys.stderr.write(theme.badge("FAIL", "Timed out: operation timed out querying systemd status.", stream=sys.stderr) + "\n")
        return 1


def start_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Starts the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write(theme.badge("FAIL", "systemctl command not found. Systemd is not available on this system.", stream=sys.stderr) + "\n")
        return 1

    target = get_service_unit_path(unit_path or service_path)
    if not target.exists():
        sys.stderr.write(theme.badge("FAIL", f"Service '{SERVICE_NAME}' is not installed. Run 'agyis sync --service install' first.", stream=sys.stderr) + "\n")
        return 1

    try:
        res = _run_systemctl(["start", SERVICE_NAME])
        if res.returncode != 0:
            _handle_systemctl_error(res.stderr)
            return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write(theme.badge("FAIL", "Timed out: operation timed out starting service.", stream=sys.stderr) + "\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "start", "success": True}, indent=2))
    else:
        print(theme.badge("PASS", f"Started {SERVICE_NAME}"))
    return 0


def stop_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Stops the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write(theme.badge("FAIL", "systemctl command not found. Systemd is not available on this system.", stream=sys.stderr) + "\n")
        return 1

    try:
        res = _run_systemctl(["stop", SERVICE_NAME])
        if res.returncode != 0:
            _handle_systemctl_error(res.stderr)
            return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write(theme.badge("FAIL", "Timed out: operation timed out stopping service.", stream=sys.stderr) + "\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "stop", "success": True}, indent=2))
    else:
        print(theme.badge("PASS", f"Stopped {SERVICE_NAME}"))
    return 0


def restart_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Restarts the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write(theme.badge("FAIL", "systemctl command not found. Systemd is not available on this system.", stream=sys.stderr) + "\n")
        return 1

    target = get_service_unit_path(unit_path or service_path)
    if not target.exists():
        sys.stderr.write(theme.badge("FAIL", f"Service '{SERVICE_NAME}' is not installed. Run 'agyis sync --service install' first.", stream=sys.stderr) + "\n")
        return 1

    try:
        res = _run_systemctl(["restart", SERVICE_NAME])
        if res.returncode != 0:
            _handle_systemctl_error(res.stderr)
            return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write(theme.badge("FAIL", "Timed out: operation timed out restarting service.", stream=sys.stderr) + "\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "restart", "success": True}, indent=2))
    else:
        print(theme.badge("PASS", f"Restarted {SERVICE_NAME}"))
    return 0


def try_restart_service(timeout: float = 5.0) -> Dict[str, Any]:
    """Safely runs systemctl --user try-restart agyis-sync.service without failing on bus-less hosts."""
    if not shutil.which("systemctl"):
        return {"service": SERVICE_NAME, "attempted": False, "restarted": False, "reason": "systemctl_not_found"}
    try:
        res = _run_systemctl(["try-restart", SERVICE_NAME], timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return {"service": SERVICE_NAME, "attempted": True, "restarted": False, "reason": str(exc)}
    if res.returncode == 0:
        return {"service": SERVICE_NAME, "attempted": True, "restarted": True, "reason": "ok"}
    err = (res.stderr or res.stdout or "").strip()
    return {"service": SERVICE_NAME, "attempted": True, "restarted": False, "reason": err or f"exit_{res.returncode}"}


def uninstall_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Stops, disables, deletes the unit file, and reloads systemd."""
    if not shutil.which("systemctl"):
        sys.stderr.write(theme.badge("FAIL", "systemctl command not found. Systemd is not available on this system.", stream=sys.stderr) + "\n")
        return 1

    target = get_service_unit_path(unit_path or service_path)
    try:
        # Ignore non-zero returncodes during stop/disable if service was not running or not enabled
        _run_systemctl(["stop", SERVICE_NAME])
        _run_systemctl(["disable", SERVICE_NAME])
        if target.exists():
            target.unlink()
        _run_systemctl(["daemon-reload"])
    except subprocess.TimeoutExpired:
        sys.stderr.write(theme.badge("FAIL", "Timed out: operation timed out uninstalling service.", stream=sys.stderr) + "\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "uninstall", "success": True}, indent=2))
    else:
        print(theme.badge("PASS", f"Stopped and disabled {SERVICE_NAME}"))
        print(theme.badge("PASS", f"Removed unit file: {target}"))
        print(theme.badge("PASS", "Executed systemctl --user daemon-reload"))
        print(theme.badge("PASS", f"Successfully uninstalled {SERVICE_NAME}"))
    return 0


def manage_service(
    action: str,
    interval: float = 5.0,
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Central dispatcher for systemd user service management."""
    target_path = unit_path or service_path
    dispatch = {
        "install": lambda: install_service(interval=interval, unit_path=target_path, json_output=json_output),
        "status": lambda: service_status(unit_path=target_path, json_output=json_output),
        "start": lambda: start_service(unit_path=target_path, json_output=json_output),
        "stop": lambda: stop_service(unit_path=target_path, json_output=json_output),
        "restart": lambda: restart_service(unit_path=target_path, json_output=json_output),
        "uninstall": lambda: uninstall_service(unit_path=target_path, json_output=json_output),
    }
    handler = dispatch.get(action)
    if not handler:
        sys.stderr.write(theme.badge("FAIL", f"Unknown service action '{action}'. Choose from: install, status, start, stop, restart, uninstall.", stream=sys.stderr) + "\n")
        return 2
    return handler()
