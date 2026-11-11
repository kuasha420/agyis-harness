# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Systemd user path/service unit management for Antigravity Trajectory Debug HUD."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, List, Optional, Union

GUI_PATH_UNIT = "antigravity-trajectory.path"
GUI_SERVICE_UNIT = "antigravity-trajectory.service"


def get_gui_systemd_unit_dir(custom_dir: Optional[Union[str, Path]] = None) -> Path:
    """Returns destination directory for user systemd units."""
    if custom_dir:
        return Path(custom_dir)
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return base_dir / "systemd" / "user"


def generate_gui_systemd_path_unit() -> str:
    """Generates the systemd user path unit definition to monitor DevToolsActivePort creation."""
    return """[Unit]
Description=Watch for Antigravity DevToolsActivePort Creation
Documentation=https://github.com/kuasha420/agyis-harness

[Path]
PathChanged=%h/.config/Antigravity/DevToolsActivePort
Unit=antigravity-trajectory.service

[Install]
WantedBy=default.target
"""


def generate_gui_systemd_service_unit(working_dir: Optional[Union[str, Path]] = None) -> str:
    """Generates the systemd user service unit definition to auto-unlock Trajectory Debug HUD."""
    resolved_work_dir: Path
    if working_dir:
        resolved_work_dir = Path(working_dir).resolve()
    else:
        cand = Path(__file__).resolve().parents[2]
        if (cand / "harness").is_dir():
            resolved_work_dir = cand
        elif (Path.cwd() / "harness").is_dir():
            resolved_work_dir = Path.cwd().resolve()
        else:
            resolved_work_dir = Path.home()

    work_dir = str(resolved_work_dir)
    discovered_agyis = shutil.which("agyis")
    if discovered_agyis:
        exec_cmd = f"{discovered_agyis} gui --no-popup --wait 15.0"
    else:
        py_path = sys.executable or "/usr/bin/python3"
        exec_cmd = f"{py_path} -m harness.cli gui --no-popup --wait 15.0"

    return f"""[Unit]
Description=Antigravity In-Situ Trajectory Debug HUD Auto-Unlock
Documentation=https://github.com/kuasha420/agyis-harness
After=default.target

[Service]
Type=oneshot
WorkingDirectory={work_dir}
ExecStart={exec_cmd}
MemoryMax=500M
MemoryHigh=300M
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def _run_gui_systemctl(args: List[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    """Invokes systemctl with standard arguments and error trapping."""
    systemctl_bin = shutil.which("systemctl")
    if not systemctl_bin:
        raise FileNotFoundError("systemctl executable not found in PATH")
    cmd = ["systemctl", "--user"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _emit_gui_service_msg(json_output: bool, payload: dict[str, Any], text: str, err: bool = False) -> None:
    """Emit uniform JSON or plain-text output for GUI systemd unit operations."""
    if json_output:
        print(json.dumps(payload, indent=2))
    elif err:
        sys.stderr.write(f"✘ {text}\n")
    else:
        print(text)


def handle_gui_service_command(
    action: str,
    json_output: bool = False,
    unit_dir: Optional[Union[str, Path]] = None,
    working_dir: Optional[Union[str, Path]] = None,
    run_systemctl: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> int:
    """Manages systemd user path and service units for automatic Trajectory Debug HUD unlocking."""
    action = (action or "").strip().lower()
    udir = get_gui_systemd_unit_dir(unit_dir)
    path_file = udir / GUI_PATH_UNIT
    service_file = udir / GUI_SERVICE_UNIT
    systemctl_fn = run_systemctl or _run_gui_systemctl

    if not shutil.which("systemctl"):
        err_msg = "systemctl command not found. Systemd user services are not available on this system."
        _emit_gui_service_msg(
            json_output,
            {"service": "antigravity-trajectory", "action": action, "success": False, "error": err_msg},
            err_msg,
            err=True,
        )
        return 1

    if action == "install":
        try:
            udir.mkdir(parents=True, exist_ok=True)
            path_file.write_text(generate_gui_systemd_path_unit(), encoding="utf-8")
            service_file.write_text(generate_gui_systemd_service_unit(working_dir=working_dir), encoding="utf-8")

            for sc_args, label in (
                (["daemon-reload"], "reload systemd daemon"),
                (["enable", GUI_PATH_UNIT], f"enable {GUI_PATH_UNIT}"),
                (["start", GUI_PATH_UNIT], f"start {GUI_PATH_UNIT}"),
            ):
                res = systemctl_fn(sc_args)
                if res.returncode != 0:
                    err = res.stderr.strip() or f"{sc_args[0]} failed with exit code {res.returncode}"
                    _emit_gui_service_msg(
                        json_output,
                        {"service": "antigravity-trajectory", "action": "install", "success": False, "error": err},
                        f"Failed to {label}: {err}",
                        err=True,
                    )
                    return 1
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            _emit_gui_service_msg(
                json_output,
                {"service": "antigravity-trajectory", "action": "install", "success": False, "error": str(exc)},
                f"Failed to install systemd service: {exc}",
                err=True,
            )
            return 1

        if json_output:
            print(json.dumps({
                "service": "antigravity-trajectory",
                "action": "install",
                "success": True,
                "path_unit": str(path_file),
                "service_unit": str(service_file),
            }, indent=2))
        else:
            print(f"✔ Installed systemd user path unit: {path_file}")
            print(f"✔ Installed systemd user service unit: {service_file}")
            print("✔ Enabled and started antigravity-trajectory.path monitor")
        return 0

    if action == "status":
        if not path_file.exists() and not service_file.exists():
            _emit_gui_service_msg(
                json_output,
                {"service": "antigravity-trajectory", "installed": False, "active": False, "status": "not_installed"},
                f"Antigravity GUI trajectory service is not installed in {udir}.",
                err=True,
            )
            return 1

        try:
            res = systemctl_fn(["status", GUI_PATH_UNIT])
            is_active = res.returncode == 0
            out = res.stdout or res.stderr
            if res.returncode not in (0, 3):
                err = res.stderr.strip() or f"systemctl status returned code {res.returncode}"
                _emit_gui_service_msg(
                    json_output,
                    {"service": "antigravity-trajectory", "installed": True, "active": False, "error": err},
                    f"Failed to get status: {err}",
                    err=True,
                )
                return 1
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            _emit_gui_service_msg(
                json_output,
                {"service": "antigravity-trajectory", "installed": True, "active": False, "error": str(exc)},
                f"Failed to query systemctl: {exc}",
                err=True,
            )
            return 1

        if json_output:
            print(json.dumps({
                "service": "antigravity-trajectory",
                "installed": True,
                "active": is_active,
                "output": out.strip(),
            }, indent=2))
        else:
            print(f"● antigravity-trajectory.path (active={is_active})")
            if out:
                print(out.strip())
        return 0

    if action in ("start", "stop"):
        if action == "start" and not path_file.exists():
            sys.stderr.write(f"✘ Service not installed at {path_file}. Run 'agyis gui --service install' first.\n")
            return 1
        try:
            res = systemctl_fn([action, GUI_PATH_UNIT])
            if res.returncode != 0:
                err = res.stderr.strip() or f"{action} failed with exit code {res.returncode}"
                _emit_gui_service_msg(
                    json_output,
                    {"service": "antigravity-trajectory", "action": action, "success": False, "error": err},
                    f"Failed to {action} service: {err}",
                    err=True,
                )
                return 1
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            _emit_gui_service_msg(
                json_output,
                {"service": "antigravity-trajectory", "action": action, "success": False, "error": str(exc)},
                f"Failed to {action} service: {exc}",
                err=True,
            )
            return 1

        verb = "Started" if action == "start" else "Stopped"
        _emit_gui_service_msg(
            json_output,
            {"service": "antigravity-trajectory", "action": action, "success": True},
            f"✔ {verb} antigravity-trajectory.path monitor",
        )
        return 0

    if action == "uninstall":
        for sc_args in (["stop", GUI_PATH_UNIT], ["disable", GUI_PATH_UNIT]):
            try:
                systemctl_fn(sc_args)
            except (FileNotFoundError, subprocess.SubprocessError, OSError):
                pass

        for fp in (path_file, service_file):
            if fp.exists():
                fp.unlink()

        try:
            res_reload = systemctl_fn(["daemon-reload"])
            if res_reload.returncode != 0:
                err = res_reload.stderr.strip() or f"daemon-reload failed with exit code {res_reload.returncode}"
                _emit_gui_service_msg(
                    json_output,
                    {"service": "antigravity-trajectory", "action": "uninstall", "success": False, "error": err},
                    f"Failed to reload systemd daemon: {err}",
                    err=True,
                )
                return 1
        except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
            _emit_gui_service_msg(
                json_output,
                {"service": "antigravity-trajectory", "action": "uninstall", "success": False, "error": str(exc)},
                f"Failed to reload systemd daemon: {exc}",
                err=True,
            )
            return 1

        _emit_gui_service_msg(
            json_output,
            {"service": "antigravity-trajectory", "action": "uninstall", "success": True},
            "✔ Uninstalled antigravity-trajectory systemd units",
        )
        return 0

    sys.stderr.write(f"✘ Unknown service action '{action}'. Choose from: install, status, start, stop, uninstall.\n")
    return 1
