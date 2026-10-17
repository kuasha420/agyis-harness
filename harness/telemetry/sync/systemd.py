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


def generate_systemd_service(
    python_bin: Optional[str] = None,
    interval_sec: float = 5.0,
    working_dir: Optional[Union[str, Path]] = None,
    agyis_bin: Optional[str] = None,
) -> str:
    """Generates the systemd user service unit definition for agyis-sync.service."""
    if python_bin:
        exec_cmd = f"{python_bin} -m harness.cli sync --watch --interval {interval_sec}"
    elif agyis_bin:
        exec_cmd = f"{agyis_bin} sync --watch --interval {interval_sec}"
    else:
        discovered_agyis = shutil.which("agyis")
        if discovered_agyis:
            exec_cmd = f"{discovered_agyis} sync --watch --interval {interval_sec}"
        else:
            py_path = sys.executable or "/usr/bin/python3"
            exec_cmd = f"{py_path} -m harness.cli sync --watch --interval {interval_sec}"

    work_dir = str(working_dir) if working_dir else str(Path.home())
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
            "✘ Unable to communicate with systemd user session bus.\n"
            f"  • Verbatim error: {err_str.strip()}\n"
            "  • Diagnosis: Systemd user session is inactive or XDG_RUNTIME_DIR is not set.\n"
            "  • Remediation: Ensure XDG_RUNTIME_DIR is set (e.g. export XDG_RUNTIME_DIR=/run/user/$(id -u)), or use foreground watch mode ('agyis sync --watch').\n"
        )
    else:
        sys.stderr.write(f"✘ systemctl command failed: {err_str.strip()}\n")


def install_service(
    interval: float = 5.0,
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Installs and enables the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write(
            "✘ systemctl command not found.\n"
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
        sys.stderr.write("✘ Timed out: operation timed out communicating with systemd daemon (15s limit).\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"✘ Failed to install service: {exc}\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "install", "installed": True, "path": str(target)}, indent=2))
    else:
        print(f"✔ Installed systemd user service unit: {target}")
        print("✔ Executed systemctl --user daemon-reload")
        print(f"✔ Enabled {SERVICE_NAME}")
        print(f"  • To start the service: agyis sync --service start")
        print(f"  • To check status: agyis sync --service status")
    return 0


def service_status(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Reports status of the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write("✘ systemctl command not found. Systemd is not available on this system.\n")
        return 1

    target = get_service_unit_path(unit_path or service_path)
    if not target.exists():
        if json_output:
            print(json.dumps({"service": SERVICE_NAME, "installed": False, "active": False, "status": "not_installed"}, indent=2))
        else:
            sys.stderr.write(
                f"✘ Service '{SERVICE_NAME}' is not installed.\n"
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
        sys.stderr.write("✘ Timed out: operation timed out querying systemd status.\n")
        return 1


def start_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Starts the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write("✘ systemctl command not found. Systemd is not available on this system.\n")
        return 1

    target = get_service_unit_path(unit_path or service_path)
    if not target.exists():
        sys.stderr.write(f"✘ Service '{SERVICE_NAME}' is not installed. Run 'agyis sync --service install' first.\n")
        return 1

    try:
        res = _run_systemctl(["start", SERVICE_NAME])
        if res.returncode != 0:
            _handle_systemctl_error(res.stderr)
            return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write("✘ Timed out: operation timed out starting service.\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "start", "success": True}, indent=2))
    else:
        print(f"✔ Started {SERVICE_NAME}")
    return 0


def stop_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Stops the systemd user service."""
    if not shutil.which("systemctl"):
        sys.stderr.write("✘ systemctl command not found. Systemd is not available on this system.\n")
        return 1

    try:
        res = _run_systemctl(["stop", SERVICE_NAME])
        if res.returncode != 0:
            _handle_systemctl_error(res.stderr)
            return 1
    except subprocess.TimeoutExpired:
        sys.stderr.write("✘ Timed out: operation timed out stopping service.\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "stop", "success": True}, indent=2))
    else:
        print(f"✔ Stopped {SERVICE_NAME}")
    return 0


def uninstall_service(
    unit_path: Optional[Union[str, Path]] = None,
    json_output: bool = False,
    service_path: Optional[Union[str, Path]] = None,
) -> int:
    """Stops, disables, deletes the unit file, and reloads systemd."""
    if not shutil.which("systemctl"):
        sys.stderr.write("✘ systemctl command not found. Systemd is not available on this system.\n")
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
        sys.stderr.write("✘ Timed out: operation timed out uninstalling service.\n")
        return 1

    if json_output:
        print(json.dumps({"service": SERVICE_NAME, "action": "uninstall", "success": True}, indent=2))
    else:
        print(f"✔ Stopped and disabled {SERVICE_NAME}")
        print(f"✔ Removed unit file: {target}")
        print("✔ Executed systemctl --user daemon-reload")
        print(f"✔ Successfully uninstalled {SERVICE_NAME}")
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
        "uninstall": lambda: uninstall_service(unit_path=target_path, json_output=json_output),
    }
    handler = dispatch.get(action)
    if not handler:
        sys.stderr.write(f"✘ Unknown service action '{action}'. Choose from: install, status, start, stop, uninstall.\n")
        return 2
    return handler()
