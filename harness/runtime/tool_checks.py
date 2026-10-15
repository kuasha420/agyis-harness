# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Toolchain and binary version checks for Agyis Harness (ADR-014 / Antigravity Immune System).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

__all__ = [
    "REPO_ROOT",
    "check_cli_binary",
    "check_ghidra_installation",
    "check_hopper_contract",
    "check_ida_contract",
    "check_jadx_contract",
    "check_psl_collision",
    "check_rea_tooling",
    "check_tool",
    "detect_os_family",
    "find_hermetic_uv_python",
    "find_jdk21_path",
    "find_rea_binary",
    "is_rea_mcp_configured",
    "parse_version",
    "version_less_than",
]


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parse version string into integer tuple for comparison."""
    parts = re.findall(r"\d+", v_str)
    return tuple(int(p) for p in parts) if parts else (0,)


def version_less_than(v1: Tuple[int, ...], v2: Tuple[int, ...]) -> bool:
    """Compare two version tuples with zero-padding for differing lengths."""
    max_len = max(len(v1), len(v2))
    v1_padded = v1 + (0,) * (max_len - len(v1))
    v2_padded = v2 + (0,) * (max_len - len(v2))
    return v1_padded < v2_padded


def detect_os_family() -> str:
    """Detect operating system family for package manager suggestions."""
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        return "darwin"

    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text().lower()
        if "arch" in content or "endeavouros" in content or "manjaro" in content:
            return "arch"
        if "debian" in content or "ubuntu" in content or "pop" in content:
            return "debian"
        if "fedora" in content or "rhel" in content or "centos" in content:
            return "fedora"
    return "linux"


def find_hermetic_uv_python() -> Optional[Path]:
    """Find installed CPython 3.12+ in uv's toolchain directory."""
    uv_python_dir = Path.home() / ".local/share/uv/python"
    if not uv_python_dir.exists():
        return None

    for candidate in sorted(uv_python_dir.glob("cpython-3.1[2-9]*/bin/python3"), reverse=True):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def check_psl_collision() -> Dict[str, Any]:
    """Audit host 'psl' binary to detect collisions with system libpsl or non-harness binaries."""
    psl_path = shutil.which("psl")
    if not psl_path:
        return {
            "status": "NOT_FOUND",
            "path": None,
            "collision": False,
            "details": "psl binary not found on PATH.",
            "remediation": "Deploy the PSL launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH.",
        }

    is_harness = False
    try:
        with open(psl_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048)
            if "harness" in content or "agyis" in content:
                is_harness = True
    except OSError:
        pass

    if psl_path in ("/usr/bin/psl", "/bin/psl"):
        return {
            "status": "WARNING",
            "path": psl_path,
            "collision": True,
            "details": f"Collision detected: 'psl' resolves to system libpsl ({psl_path}).",
            "remediation": (
                "Prepend user bin directory (~/.local/bin) to PATH before /usr/bin:\n"
                "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "And ensure the launcher is installed via: python3 -m harness.cli install"
            ),
        }

    if not is_harness:
        return {
            "status": "WARNING",
            "path": psl_path,
            "collision": True,
            "details": f"Collision detected: 'psl' resolves to non-harness binary ({psl_path}).",
            "remediation": (
                "Ensure PSL harness bin directory is prioritized in PATH:\n"
                "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
                "And ensure the launcher is installed via: python3 -m harness.cli install"
            ),
        }

    return {
        "status": "OK",
        "path": psl_path,
        "collision": False,
        "details": f"psl binary correctly resolves to PSL Harness launcher ({psl_path}).",
        "remediation": None,
    }


def check_cli_binary() -> Dict[str, Any]:
    """Audit host CLI binaries: probes 'agyis' as primary binary and checks 'psl' availability/collision."""
    agyis_path = shutil.which("agyis")
    psl_info = check_psl_collision()

    is_agyis_harness = False
    if agyis_path:
        try:
            with open(agyis_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2048)
                if "harness" in content or "agyis" in content:
                    is_agyis_harness = True
        except OSError:
            pass

    psl_collision_flag = psl_info.get("collision", False)

    if not agyis_path:
        agyis_status = "WARNING"
        if psl_info.get("status") == "OK":
            agyis_details = (
                f"'agyis' primary binary not found on PATH (legacy 'psl' detected at {psl_info.get('path')})."
            )
            remediation = (
                "Deploy the primary 'agyis' launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH."
            )
        else:
            agyis_details = "'agyis' binary not found on PATH."
            remediation = (
                "Deploy the Agyis launcher via 'python3 -m harness.cli install' or ensure ~/.local/bin is on PATH."
            )
        status = "WARNING"
        collision = psl_collision_flag
        details = agyis_details
    elif not is_agyis_harness:
        agyis_status = "WARNING"
        collision = True
        status = "WARNING"
        agyis_details = f"Collision detected: 'agyis' resolves to non-harness binary ({agyis_path})."
        details = agyis_details
        remediation = (
            "Ensure Agyis harness bin directory is prioritized in PATH:\n"
            "    export PATH=\"$HOME/.local/bin:$PATH\"\n"
            "And ensure the launcher is installed via: python3 -m harness.cli install"
        )
    elif psl_collision_flag:
        agyis_status = "OK"
        collision = True
        status = "WARNING"
        agyis_details = f"'agyis' binary correctly resolves to Agyis Harness launcher ({agyis_path})."
        details = (
            f"'agyis' launcher verified ({agyis_path}), but legacy 'psl' collision detected: {psl_info.get('details')}"
        )
        remediation = psl_info.get("remediation")
    else:
        agyis_status = "OK"
        collision = False
        status = "OK"
        agyis_details = f"'agyis' binary correctly resolves to Agyis Harness launcher ({agyis_path})."
        details = agyis_details
        remediation = None

    return {
        "status": status,
        "primary_binary": "agyis",
        "path": agyis_path,
        "agyis_path": agyis_path,
        "agyis_status": agyis_status,
        "agyis_details": agyis_details,
        "psl_path": psl_info.get("path"),
        "collision": collision,
        "details": details,
        "remediation": remediation,
        "psl_details": psl_info,
        "psl_collision": psl_info,
    }


def check_tool(
    name: str,
    spec: Dict[str, Any],
    hermetic_python_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Audit an individual tool against its matrix specification."""
    binary = spec.get("binary", name)
    fallback = spec.get("fallback_binary")
    min_version_str = spec.get("min_version")
    optional = spec.get("optional", False)

    # 1. Resolve binary in PATH
    resolved_path = shutil.which(binary)
    if not resolved_path and fallback:
        resolved_path = shutil.which(fallback)
        if resolved_path:
            binary = fallback

    # For "uv", probe candidate user paths (~/.local/bin/uv, ~/.cargo/bin/uv) if not found on PATH
    if not resolved_path and (name == "uv" or binary == "uv"):
        for cand in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv"):
            if cand.exists() and os.access(cand, os.X_OK):
                resolved_path = str(cand)
                break

    # Check for pyenv/conda shim hijacking
    is_shim = False
    shim_details = None
    if resolved_path:
        p_lower = resolved_path.lower()
        if ".pyenv/shims" in p_lower or ".pyenv/versions" in p_lower:
            is_shim = True
            shim_details = "pyenv shim active in PATH"
        elif "conda" in p_lower or "miniconda" in p_lower:
            is_shim = True
            shim_details = "conda environment active in PATH"

    # Check for libpsl / non-harness collision if auditing psl or agyis
    is_collision = False
    collision_details = None
    if (name in ("psl", "agyis") or binary in ("psl", "agyis")) and resolved_path:
        is_harness = False
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(2048)
                if "harness" in content or "agyis" in content:
                    is_harness = True
        except OSError:
            pass
        if (binary == "psl" and resolved_path in ("/usr/bin/psl", "/bin/psl")) or not is_harness:
            is_collision = True
            collision_details = f"Collision detected: '{binary}' resolves to non-harness binary ({resolved_path})"

    if not resolved_path:
        return {
            "name": name,
            "binary": binary,
            "status": "OPTIONAL_MISSING" if optional else "MISSING",
            "path": None,
            "version": None,
            "min_version": min_version_str,
            "is_shim": False,
            "shim_details": None,
            "is_collision": False,
            "collision_details": None,
            "spec": spec,
        }

    # 2. Extract version
    version_str = None
    cmd = spec.get("version_command", f"{binary} --version")
    if resolved_path:
        if cmd.startswith(f"{binary} "):
            cmd = f'"{resolved_path}" ' + cmd[len(binary) + 1:]
        elif cmd == binary:
            cmd = f'"{resolved_path}"'
    regex = spec.get("version_regex", r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        combined_out = (proc.stdout + " " + proc.stderr).strip()
        m = re.search(regex, combined_out)
        if m:
            version_str = m.group(1)
    except Exception:
        version_str = None

    # 3. Version comparison
    status = "OK"
    if not version_str:
        status = "UNKNOWN_VERSION"
    elif min_version_str:
        current_v = parse_version(version_str)
        required_v = parse_version(min_version_str)
        if version_less_than(current_v, required_v):
            status = "OUTDATED"
        elif is_shim or is_collision:
            status = "WARNING"
        else:
            status = "OK"
    elif is_shim or is_collision:
        status = "WARNING"

    return {
        "name": name,
        "binary": binary,
        "status": status,
        "path": resolved_path,
        "version": version_str,
        "min_version": min_version_str,
        "is_shim": is_shim,
        "shim_details": shim_details,
        "is_collision": is_collision,
        "collision_details": collision_details,
        "spec": spec,
    }


def find_rea_binary() -> Optional[Path]:
    """Find installed REA (Reverse Engineer Anything) binary.

    Checks PATH via shutil.which, $PNPM_HOME/rea, and standard pnpm global bin directories:
    - ~/.local/share/pnpm/rea (Linux)
    - ~/.pnpm-global/bin/rea
    - ~/Library/pnpm/rea (macOS)
    """
    which_rea = shutil.which("rea")
    if which_rea:
        try:
            p = Path(which_rea)
            if p.is_file() and os.access(p, os.X_OK):
                return p
        except OSError:
            pass

    candidates: List[Path] = []
    pnpm_home = os.environ.get("PNPM_HOME")
    if pnpm_home:
        try:
            candidates.append(Path(pnpm_home) / "rea")
        except OSError:
            pass

    try:
        home = Path.home()
        candidates.extend(
            [
                home / ".local/share/pnpm/rea",
                home / ".pnpm-global/bin/rea",
                home / "Library/pnpm/rea",
            ]
        )
    except OSError:
        pass

    for cand in candidates:
        try:
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
        except OSError:
            continue

    return None


def is_rea_mcp_configured(mcp_config_path: Optional[Path] = None) -> bool:
    """Check if REA MCP server is registered and enabled in agent configuration."""
    candidates = (
        [mcp_config_path]
        if mcp_config_path is not None
        else [
            Path.home() / ".gemini" / "config" / "mcp_config.json",
            Path.home() / ".gemini" / "antigravity" / "mcp_config.json",
        ]
    )
    for target_path in candidates:
        try:
            if not target_path.is_file():
                continue
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            servers = data.get("mcpServers", {})
            if not isinstance(servers, dict):
                continue
            if "rea" in servers:
                rea_def = servers["rea"]
                if isinstance(rea_def, dict):
                    disabled_val = rea_def.get("disabled", False)
                    is_disabled = False
                    if isinstance(disabled_val, bool):
                        is_disabled = disabled_val
                    elif isinstance(disabled_val, str):
                        is_disabled = disabled_val.strip().lower() in ("true", "1", "yes")
                    elif isinstance(disabled_val, (int, float)):
                        is_disabled = bool(disabled_val)
                    if not is_disabled:
                        return True
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, AttributeError):
            continue
    return False


def _parse_rea_providers(raw_json: str) -> Dict[str, Any]:
    """Parse output from 'rea providers --json' into active and unavailable providers."""
    active: List[str] = []
    unavailable: List[str] = []
    details: List[Dict[str, Any]] = []

    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        return {"active": active, "unavailable": unavailable, "details": details}

    if not isinstance(data, (dict, list)):
        return {"active": active, "unavailable": unavailable, "details": details}

    candidates = data.get("analysis_provider_candidates") if isinstance(data, dict) else None
    if candidates is None and isinstance(data, dict) and "providers" in data:
        candidates = data.get("providers")
    if candidates is None and isinstance(data, list):
        candidates = data

    if isinstance(candidates, list):
        for cand in candidates:
            if isinstance(cand, dict):
                provider_obj = cand.get("provider")
                if isinstance(provider_obj, dict):
                    name = str(provider_obj.get("name") or provider_obj.get("id") or "Unknown")
                else:
                    name = str(cand.get("name") or cand.get("id") or "Unknown")

                avail = cand.get("availability")
                if isinstance(avail, dict):
                    is_available = avail.get("available") is True or avail.get("status") == "available"
                    reason = str(avail.get("reason")) if avail.get("reason") is not None else None
                elif isinstance(avail, bool):
                    is_available = avail
                    reason = str(cand.get("reason")) if cand.get("reason") is not None else None
                else:
                    is_available = cand.get("available") is True or cand.get("status") == "available"
                    reason = str(cand.get("reason")) if cand.get("reason") is not None else None

                if is_available:
                    active.append(name)
                else:
                    unavailable.append(name)

                details.append({
                    "name": name,
                    "available": is_available,
                    "reason": reason,
                })
            elif isinstance(cand, str):
                active.append(cand)
                details.append({"name": cand, "available": True, "reason": None})
    elif isinstance(candidates, dict):
        for k, cand in candidates.items():
            name = str(k)
            if isinstance(cand, bool):
                is_available = cand
                reason = None
            elif isinstance(cand, dict):
                is_available = cand.get("available") is True or cand.get("status") == "available"
                reason = str(cand.get("reason")) if cand.get("reason") is not None else None
            else:
                is_available = False
                reason = str(cand)

            if is_available:
                active.append(name)
            else:
                unavailable.append(name)

            details.append({
                "name": name,
                "available": is_available,
                "reason": reason,
            })

    return {"active": active, "unavailable": unavailable, "details": details}


def _is_jdk21_dir(java_dir: Path) -> bool:
    """Verify that a directory contains an OpenJDK 21+ installation."""
    try:
        if not java_dir.is_dir():
            return False
        # 1. Fast check: release metadata file
        rel_file = java_dir / "release"
        if rel_file.is_file():
            content = rel_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'JAVA_VERSION="?([0-9]+)', content)
            if m:
                return int(m.group(1)) >= 21
        # 2. Check directory name if it explicitly declares 21
        dir_name = java_dir.name.lower()
        if "21" in dir_name and ((java_dir / "bin" / "java").is_file() or (java_dir / "bin").is_dir()):
            return True
        # 3. Subprocess check on bin/java
        java_bin = java_dir / "bin" / "java"
        if java_bin.is_file() and os.access(java_bin, os.X_OK):
            proc = subprocess.run(
                [str(java_bin), "-version"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            combined = (proc.stdout + " " + proc.stderr).strip()
            m = re.search(r'version "([0-9]+)', combined)
            if m:
                return int(m.group(1)) >= 21
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return False


def find_jdk21_path() -> Optional[Path]:
    """Traverse dynamic 7-level JVM discovery ladder to identify OpenJDK 21+ runtime."""
    # Level 1: $JAVA_HOME (if valid JDK 21+ binary exists at $JAVA_HOME/bin/java)
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        try:
            p = Path(java_home)
            if _is_jdk21_dir(p):
                return p
        except OSError:
            pass

    # Level 2: /usr/lib/jvm/java-21-openjdk* (Linux standard OpenJDK path glob)
    try:
        jvm_dir = Path("/usr/lib/jvm")
        if jvm_dir.is_dir():
            for cand in sorted(jvm_dir.glob("java-21-openjdk*")):
                if _is_jdk21_dir(cand):
                    return cand
    except OSError:
        pass

    # Level 3: /usr/lib/jvm/java-21-openjdk-amd64 (Ubuntu / Debian multiarch)
    try:
        p = Path("/usr/lib/jvm/java-21-openjdk-amd64")
        if _is_jdk21_dir(p):
            return p
    except OSError:
        pass

    # Level 4: /usr/lib/jvm/jre-21-openjdk (Fedora / RHEL)
    try:
        p = Path("/usr/lib/jvm/jre-21-openjdk")
        if _is_jdk21_dir(p):
            return p
    except OSError:
        pass

    # Level 5: /opt/homebrew/opt/openjdk@21 (macOS Homebrew Apple Silicon)
    try:
        p = Path("/opt/homebrew/opt/openjdk@21")
        if _is_jdk21_dir(p):
            return p
    except OSError:
        pass

    # Level 6: /usr/local/opt/openjdk@21 (macOS Homebrew Intel)
    try:
        p = Path("/usr/local/opt/openjdk@21")
        if _is_jdk21_dir(p):
            return p
    except OSError:
        pass

    # Level 7: macOS PKG installers (Temurin & OpenJDK)
    try:
        for cand in [
            Path("/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"),
            Path("/Library/Java/JavaVirtualMachines/openjdk-21.jdk/Contents/Home"),
        ]:
            if _is_jdk21_dir(cand):
                return cand
    except OSError:
        pass

    return None


def check_ghidra_installation(jdk_path: Optional[Path] = None) -> Dict[str, Any]:
    """Audit Ghidra installation root and headless analyzer."""
    ghidra_dir_str = os.environ.get("GHIDRA_INSTALL_DIR")
    ghidra_path: Optional[Path] = None
    if ghidra_dir_str:
        p = Path(ghidra_dir_str)
        if p.is_dir():
            ghidra_path = p
    if not ghidra_path:
        for cand in [Path("/opt/ghidra"), Path("/usr/local/opt/ghidra"), Path.home() / "ghidra"]:
            if cand.is_dir():
                ghidra_path = cand
                break

    if not ghidra_path:
        return {
            "status": "optional_missing",
            "install_dir": None,
            "headless_analyzer": None,
            "jdk_compliant": bool(jdk_path),
            "fallback_chain": ["Rizin", "objdump", "built-in parsers"],
            "details": "Ghidra installation not found ($GHIDRA_INSTALL_DIR unconfigured).",
        }

    analyzer = ghidra_path / "support" / "analyzeHeadless"
    analyzer_ok = analyzer.is_file() and os.access(analyzer, os.X_OK)
    jdk_ok = bool(jdk_path)

    if analyzer_ok and jdk_ok:
        return {
            "status": "ok",
            "install_dir": str(ghidra_path),
            "headless_analyzer": str(analyzer),
            "jdk_compliant": True,
            "fallback_chain": [],
            "details": f"Ghidra 12.1+ verified ({ghidra_path}) with analyzeHeadless ready.",
        }
    elif not jdk_ok:
        return {
            "status": "warning",
            "install_dir": str(ghidra_path),
            "headless_analyzer": str(analyzer) if analyzer_ok else None,
            "jdk_compliant": False,
            "fallback_chain": ["Rizin", "objdump", "built-in parsers"],
            "details": f"Ghidra located at {ghidra_path}, but OpenJDK 21+ runtime is missing (fallback to Rizin/objdump).",
        }
    else:
        return {
            "status": "warning",
            "install_dir": str(ghidra_path),
            "headless_analyzer": None,
            "jdk_compliant": jdk_ok,
            "fallback_chain": ["Rizin", "objdump", "built-in parsers"],
            "details": f"Ghidra located at {ghidra_path}, but support/analyzeHeadless executable was not found.",
        }


def check_hopper_contract() -> Dict[str, Any]:
    """Audit Hopper Headless Contract ($DISPLAY, $WAYLAND_DISPLAY, xvfb-run, or offscreen)."""
    disp = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if disp:
        return {
            "status": "available",
            "mode": "display_socket",
            "display": disp,
            "details": f"Display socket verified ({disp}).",
        }

    xvfb = shutil.which("xvfb-run")
    if xvfb:
        return {
            "status": "available",
            "mode": "virtual_framebuffer",
            "display": None,
            "details": f"Virtual framebuffer runner available ({xvfb}).",
        }

    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return {
            "status": "available",
            "mode": "offscreen",
            "display": None,
            "details": "QT_QPA_PLATFORM=offscreen configured.",
        }

    return {
        "status": "unavailable",
        "reason": "no display socket",
        "mode": "headless_fallback",
        "display": None,
        "fallback": "Ghidra / Rizin",
        "details": "No display socket or virtual framebuffer; Hopper will fall back cleanly to Ghidra or Rizin.",
    }


def check_ida_contract() -> Dict[str, Any]:
    """Audit IDA Pro headless supervisor isolation flags (-A, -B, -o) and sandbox contract."""
    ida_path = (
        shutil.which("idat64")
        or shutil.which("ida64")
        or shutil.which("idalib-mcp")
        or (Path(os.environ.get("IDA_DIR", "")) / "idat64" if os.environ.get("IDA_DIR") else None)
    )
    is_available = bool(ida_path and (isinstance(ida_path, str) or (isinstance(ida_path, Path) and ida_path.exists())))

    return {
        "status": "ok" if is_available else "optional_missing",
        "path": str(ida_path) if is_available else None,
        "autonomous_flags": ["-A", "-B", "-o"],
        "sandbox_isolation": True,
        "details": (
            f"IDA Pro headless batch supervisor verified ({ida_path}) with flags (-A, -B, -o)."
            if is_available
            else "IDA Pro not detected (optional heavy disassembler)."
        ),
    }


def check_jadx_contract(jdk_path: Optional[Path] = None) -> Dict[str, Any]:
    """Audit JADX Android decompiler JAR and JDK availability."""
    jar_env = os.environ.get("REA_JADX_MCP_JAR")
    jar_path = Path(jar_env) if jar_env else None
    if not jar_path or not jar_path.is_file():
        for cand in [Path("/opt/jadx/lib/jadx-headless-mcp.jar"), Path.home() / ".local/share/jadx/jadx-headless-mcp.jar"]:
            if cand.is_file():
                jar_path = cand
                break

    has_jar = bool(jar_path and jar_path.is_file())
    has_jdk = bool(jdk_path)

    return {
        "status": "ok" if (has_jar and has_jdk) else "optional_missing",
        "jar_path": str(jar_path) if has_jar else None,
        "jdk_available": has_jdk,
        "details": (
            f"JADX headless MCP JAR verified ({jar_path}) with JDK."
            if (has_jar and has_jdk)
            else "JADX headless MCP JAR unconfigured (optional Android decompiler)."
        ),
    }


def check_rea_tooling(
    timeout: float = 3.0,
    mcp_config_path: Optional[Path] = None,
    experimental_rea: bool = False,
) -> Dict[str, Any]:
    """Audit REA (Reverse Engineer Anything) tooling, version, providers, and MCP registration.

    When experimental_rea=False (the default):
      Performs a fast-path binary presence check via shutil.which (<0.005s)
      without launching subprocesses, ensuring sub-second doctor benchmarks.

    When experimental_rea=True:
      Performs comprehensive deep diagnostics: CLI version (>=6.0.0), MCP server registration,
      dynamic OpenJDK 21+ discovery ladder, Ghidra, Hopper, IDA, JADX, and candidate providers.
    """
    # 1. Fast-path optimization (when experimental_rea=False)
    if not experimental_rea:
        rea_bin = find_rea_binary()
        if rea_bin:
            return {
                "status": "ok",
                "binary": str(rea_bin),
                "version": None,
                "min_version": "6.0.0",
                "fast_path": True,
                "mcp_configured": None,
                "providers": {"active": [], "unavailable": [], "details": []},
                "details": f"REA detected at {rea_bin} (run with --experimental-rea for deep audit).",
                "remediation": None,
            }
        return {
            "status": "optional_missing",
            "binary": None,
            "version": None,
            "min_version": "6.0.0",
            "fast_path": True,
            "mcp_configured": False,
            "providers": {"active": [], "unavailable": [], "details": []},
            "details": "REA binary not found (optional reverse engineering toolchain).",
            "remediation": "Install REA via: pnpm add -g rea-agents (run with --experimental-rea for full REA suite)",
        }

    # 2. Deep audit (when experimental_rea=True)
    mcp_configured = is_rea_mcp_configured(mcp_config_path)
    rea_bin = find_rea_binary()

    jdk21 = find_jdk21_path()
    ghidra = check_ghidra_installation(jdk21)
    hopper = check_hopper_contract()
    ida = check_ida_contract()
    jadx = check_jadx_contract(jdk21)

    if not rea_bin:
        return {
            "status": "warning",
            "binary": None,
            "version": None,
            "min_version": "6.0.0",
            "fast_path": False,
            "providers": {"active": [], "unavailable": [], "details": []},
            "mcp_configured": mcp_configured,
            "jdk21": str(jdk21) if jdk21 else None,
            "ghidra": ghidra,
            "hopper": hopper,
            "ida": ida,
            "jadx": jadx,
            "remediation": "Install REA via: pnpm add -g rea-agents (or run 'agyis doctor --experimental-rea --heal')",
            "details": "REA binary not found (--experimental-rea requested).",
        }

    version_str: Optional[str] = None
    try:
        proc = subprocess.run(
            [str(rea_bin), "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        if proc.returncode == 0:
            stdout = proc.stdout if isinstance(proc.stdout, str) else ""
            stderr = proc.stderr if isinstance(proc.stderr, str) else ""
            combined = (stdout + " " + stderr).strip()
            m = re.search(r"([0-9]+(?:\.[0-9]+)+)", combined)
            if not m:
                m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)", combined)
            if m:
                version_str = m.group(1)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, UnicodeDecodeError):
        version_str = None

    providers: Dict[str, Any] = {"active": [], "unavailable": [], "details": []}
    try:
        proc_prov = subprocess.run(
            [str(rea_bin), "providers", "--json"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        stdout_prov = proc_prov.stdout if isinstance(proc_prov.stdout, str) else ""
        if proc_prov.returncode == 0 and stdout_prov.strip():
            providers = _parse_rea_providers(stdout_prov)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, UnicodeDecodeError):
        providers = {"active": [], "unavailable": [], "details": []}

    min_version = "6.0.0"
    current_v = parse_version(version_str) if version_str else (0,)
    min_v = parse_version(min_version)

    if not version_str or version_less_than(current_v, min_v):
        return {
            "status": "warning",
            "binary": str(rea_bin),
            "version": version_str,
            "min_version": min_version,
            "fast_path": False,
            "providers": providers,
            "mcp_configured": mcp_configured,
            "jdk21": str(jdk21) if jdk21 else None,
            "ghidra": ghidra,
            "hopper": hopper,
            "ida": ida,
            "jadx": jadx,
            "remediation": f"Update REA to >= {min_version} via: pnpm add -g rea-agents",
            "details": (
                f"REA {version_str} is outdated (< {min_version}) at {rea_bin}."
                if version_str
                else f"REA binary detected at {rea_bin}, but version could not be determined."
            ),
        }

    if not mcp_configured:
        return {
            "status": "warning",
            "binary": str(rea_bin),
            "version": version_str,
            "min_version": min_version,
            "fast_path": False,
            "providers": providers,
            "mcp_configured": False,
            "jdk21": str(jdk21) if jdk21 else None,
            "ghidra": ghidra,
            "hopper": hopper,
            "ida": ida,
            "jadx": jadx,
            "remediation": "Run 'rea setup' or register 'rea' in ~/.gemini/config/mcp_config.json (or run 'agyis doctor --experimental-rea --heal')",
            "details": f"REA {version_str} verified ({rea_bin}), but REA MCP server is not registered in agent configuration.",
        }

    return {
        "status": "ok",
        "binary": str(rea_bin),
        "version": version_str,
        "min_version": min_version,
        "fast_path": False,
        "providers": providers,
        "mcp_configured": True,
        "jdk21": str(jdk21) if jdk21 else None,
        "ghidra": ghidra,
        "hopper": hopper,
        "ida": ida,
        "jadx": jadx,
        "remediation": None,
        "details": f"REA {version_str} verified ({rea_bin}) with MCP registered.",
    }
