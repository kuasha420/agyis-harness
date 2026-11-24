# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Antigravity Desktop Launcher & CDP Process Detection Helpers (DRIFT-P0-06).

Provides reusable helpers for:
1. Detecting live Antigravity Electron main processes launched without
   `--remote-debugging-port` (which causes v2.34.0 to delete DevToolsActivePort).
2. Installing a user-level `.desktop` override at
   `~/.local/share/applications/antigravity.desktop` with
   `Exec=/usr/bin/antigravity --remote-debugging-port=0 %U`.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
from typing import Any, Dict, List, Optional

DEFAULT_SYSTEM_DESKTOP_FILE = Path("/usr/share/applications/antigravity.desktop")
DEFAULT_USER_DESKTOP_FILE = Path.home() / ".local" / "share" / "applications" / "antigravity.desktop"
DEFAULT_ANTIGRAVITY_BIN = "/usr/bin/antigravity"
_OPT_ANTIGRAVITY_BIN = "/opt/Antigravity/antigravity"


def get_default_user_desktop_file() -> Path:
    """Resolves user-level .desktop override path honoring XDG_DATA_HOME."""
    xdg_data = (os.environ.get("XDG_DATA_HOME") or "").strip()
    base_dir = Path(xdg_data) if xdg_data else (Path.home() / ".local" / "share")
    return base_dir / "applications" / "antigravity.desktop"


def resolve_antigravity_bin(
    explicit_bin: Optional[str] = None,
    desktop_text: Optional[str] = None,
) -> str:
    """Resolves Antigravity executable path from explicit arg, existing desktop file, PATH, or defaults."""
    if explicit_bin and explicit_bin.strip():
        return explicit_bin.strip()
    if desktop_text:
        for line in desktop_text.splitlines():
            if line.startswith("Exec="):
                raw_cmd = line[len("Exec="):].strip()
                try:
                    parts = shlex.split(raw_cmd)
                except ValueError:
                    parts = raw_cmd.split()
                if parts and parts[0]:
                    cand = parts[0]
                    if Path(cand).is_file() or shutil.which(cand):
                        return cand
    found = shutil.which("antigravity")
    if found:
        return found
    if Path(_OPT_ANTIGRAVITY_BIN).is_file():
        return _OPT_ANTIGRAVITY_BIN
    return DEFAULT_ANTIGRAVITY_BIN


def _rewrite_exec_line(raw_exec: str, default_bin: str, port: int) -> str:
    """Updates an Exec= value preserving action arguments while enforcing --remote-debugging-port."""
    try:
        tokens = shlex.split(raw_exec.strip())
    except ValueError:
        tokens = raw_exec.strip().split()
    if not tokens:
        return f"{default_bin} --remote-debugging-port={int(port)} %U"

    bin_tok = tokens[0]
    if not (Path(bin_tok).is_file() or shutil.which(bin_tok)):
        bin_tok = default_bin

    rest = [
        tok for tok in tokens[1:]
        if tok != "--remote-debugging-port" and not tok.startswith("--remote-debugging-port=")
    ]
    # Drop orphaned port value if previous line used `--remote-debugging-port <N>`
    cleaned_rest: List[str] = []
    skip_next = False
    for tok in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok == "--remote-debugging-port":
            skip_next = True
            continue
        if tok.startswith("--remote-debugging-port="):
            continue
        cleaned_rest.append(tok)
    rest = cleaned_rest

    if not any(tok in ("%U", "%u", "%F", "%f") for tok in rest):
        rest.append("%U")

    quoted_bin = shlex.quote(bin_tok) if any(ch.isspace() for ch in bin_tok) else bin_tok
    quoted_rest = [shlex.quote(t) if (any(ch.isspace() for ch in t) and not t.startswith("%")) else t for t in rest]
    return " ".join([quoted_bin, f"--remote-debugging-port={int(port)}"] + quoted_rest)

_DEFAULT_DESKTOP_TEMPLATE = """[Desktop Entry]
Name=Antigravity
Comment=Experience liftoff
GenericName=Agentic Platform
Exec={exec_line}
Icon=antigravity
Type=Application
StartupNotify=false
StartupWMClass=Antigravity
Categories=Development;Utility;
"""


def _is_antigravity_main_process(argv: List[str]) -> bool:
    """Returns True if argv represents an Antigravity Electron main process (not a child helper)."""
    if not argv:
        return False
    exe = argv[0].strip()
    if not exe:
        return False
    base = Path(exe).name.lower()
    if base != "antigravity" and "/antigravity/" not in exe.lower():
        return False
    # Exclude Electron helper subprocesses (--type=renderer, --type=gpu-process, etc.)
    if any(arg.startswith("--type=") for arg in argv[1:]):
        return False
    return True


def detect_antigravity_without_cdp(proc_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Scans `/proc` (or custom `proc_root`) for live Antigravity main processes
    running without `--remote-debugging-port`.
    """
    root = proc_root or Path("/proc")
    if not root.is_dir():
        return []

    matches: List[Dict[str, Any]] = []
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        argv = [part for part in raw.decode("utf-8", errors="replace").split("\x00") if part]
        if not _is_antigravity_main_process(argv):
            continue
        has_cdp = any(
            arg == "--remote-debugging-port" or arg.startswith("--remote-debugging-port=")
            for arg in argv[1:]
        )
        if not has_cdp:
            matches.append({
                "pid": int(entry.name),
                "exe": argv[0],
                "cmdline": argv,
            })
    matches.sort(key=lambda item: item["pid"])
    return matches


def format_cdp_restart_instructions(
    missing_cdp_procs: Optional[List[Dict[str, Any]]] = None,
    exec_bin: Optional[str] = None,
) -> List[str]:
    """Returns actionable human-readable restart instructions for Antigravity CDP."""
    resolved_bin = resolve_antigravity_bin(explicit_bin=exec_bin)
    procs = missing_cdp_procs or []
    pids = ", ".join(str(p["pid"]) for p in procs)
    lines: List[str] = []
    if pids:
        lines.append(
            f"   Live Antigravity process detected (PID {pids}) without --remote-debugging-port."
        )
        lines.append(
            "   Antigravity v2.34.0 deletes DevToolsActivePort unless launched with --remote-debugging-port,"
        )
        lines.append(
            "   and its single-instance lock prevents a second launch from enabling CDP."
        )
    lines.extend([
        "   To unlock CDP:",
        "     1. Quit all running Antigravity windows (or run: pkill -x antigravity)",
        f"     2. Relaunch with: {resolved_bin} --remote-debugging-port=0",
        "     3. Persist for desktop launches: agyis gui --install-launcher",
    ])
    return lines


def install_cdp_launcher(
    desktop_path: Optional[Path] = None,
    system_desktop_path: Optional[Path] = None,
    exec_bin: Optional[str] = None,
    port: int = 0,
) -> Dict[str, Any]:
    """
    Installs or updates `~/.local/share/applications/antigravity.desktop` (or `$XDG_DATA_HOME`)
    so all desktop entry and `[Desktop Action ...]` launches include `--remote-debugging-port=0`.
    """
    target = Path(desktop_path) if desktop_path is not None else get_default_user_desktop_file()
    sys_src = Path(system_desktop_path) if system_desktop_path is not None else DEFAULT_SYSTEM_DESKTOP_FILE

    base_text: Optional[str] = None
    if target.is_file():
        try:
            base_text = target.read_text(encoding="utf-8")
        except OSError:
            base_text = None
    if base_text is None and sys_src.is_file():
        try:
            base_text = sys_src.read_text(encoding="utf-8")
        except OSError:
            base_text = None

    resolved_bin = resolve_antigravity_bin(explicit_bin=exec_bin, desktop_text=base_text)
    exec_line = f"{resolved_bin} --remote-debugging-port={int(port)} %U"

    if base_text is not None:
        lines = base_text.splitlines()
        new_lines: List[str] = []
        primary_exec_line: Optional[str] = None
        for line in lines:
            if line.startswith("Exec="):
                updated_exec = _rewrite_exec_line(line[len("Exec="):], resolved_bin, port)
                if primary_exec_line is None:
                    primary_exec_line = updated_exec
                new_lines.append(f"Exec={updated_exec}")
            else:
                new_lines.append(line)
        if primary_exec_line is None:
            new_lines.append(f"Exec={exec_line}")
        else:
            exec_line = primary_exec_line
        content = "\n".join(new_lines).rstrip("\n") + "\n"
    else:
        content = _DEFAULT_DESKTOP_TEMPLATE.format(exec_line=exec_line)

    target.parent.mkdir(parents=True, exist_ok=True)
    previous = target.read_text(encoding="utf-8") if target.is_file() else None
    changed = previous != content
    if changed:
        target.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "path": str(target),
        "exec": exec_line,
        "changed": changed,
    }
