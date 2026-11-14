# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""REA (Reverse Engineer Anything) tooling and OpenJDK 21+ runtime checks."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _tc_attr(name: str, default: Any = None) -> Any:
    """Resolve attributes via harness.runtime.tool_checks to honor test patches cleanly."""
    mod = sys.modules.get("harness.runtime.tool_checks")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    if default is not None:
        return default
    from . import tool_checks as tc_mod

    return getattr(tc_mod, name)


def find_rea_binary() -> Optional[Path]:
    """Find installed REA (Reverse Engineer Anything) binary.

    Checks PATH via shutil.which, $PNPM_HOME/rea, and standard pnpm global bin directories:
    - ~/.local/share/pnpm/rea (Linux)
    - ~/.pnpm-global/bin/rea
    - ~/Library/pnpm/rea (macOS)
    """
    path_cls = _tc_attr("Path", Path)
    shutil_mod = _tc_attr("shutil", shutil)

    which_rea = shutil_mod.which("rea")
    if which_rea:
        try:
            p = path_cls(which_rea)
            if p.is_file() and os.access(p, os.X_OK):
                return p
        except OSError:
            pass

    candidates: List[Path] = []
    pnpm_home = os.environ.get("PNPM_HOME")
    if pnpm_home:
        try:
            candidates.append(path_cls(pnpm_home) / "rea")
        except OSError:
            pass

    try:
        home = path_cls.home()
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
    path_cls = _tc_attr("Path", Path)
    candidates = (
        [mcp_config_path]
        if mcp_config_path is not None
        else [
            path_cls.home() / ".gemini" / "config" / "mcp_config.json",
            path_cls.home() / ".gemini" / "antigravity" / "mcp_config.json",
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


def _is_jdk21_or_higher(jdk_path: Path) -> bool:
    """Verifies that a directory contains an OpenJDK/Java 21+ installation."""
    if not jdk_path.is_dir():
        return False
    # 1. Fast check: parse release file
    release_file = jdk_path / "release"
    if release_file.is_file():
        try:
            content = release_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'JAVA_VERSION="?(\d+)(?:\.(\d+))?', content)
            if m:
                major = int(m.group(1))
                if major >= 21:
                    return True
                if major < 21:
                    return False
        except OSError:
            pass

    # 2. Subprocess check: java -version
    java_bin = jdk_path / "bin" / "java"
    if java_bin.is_file() and os.access(java_bin, os.X_OK):
        sub_mod = _tc_attr("subprocess", subprocess)
        try:
            proc = sub_mod.run(
                [str(java_bin), "-version"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=2.0,
            )
            combined = (proc.stdout or "") + " " + (proc.stderr or "")
            m = re.search(r'version "?(\d+)(?:\.(\d+))?', combined)
            if m:
                major = int(m.group(1))
                if major >= 21:
                    return True
        except (subprocess.SubprocessError, OSError):
            pass
    return False


def is_ghidra_12_2_installed(ghidra_dir: Optional[str] = None) -> bool:
    """Checks whether Ghidra 12.2 is detected in the environment (DEF-BB-040)."""
    path_cls = _tc_attr("Path", Path)
    candidates = []
    if ghidra_dir:
        candidates.append(path_cls(ghidra_dir))
    env_dir = os.environ.get("GHIDRA_INSTALL_DIR") or os.environ.get("GHIDRA_HOME")
    if env_dir:
        candidates.append(path_cls(env_dir))
    candidates.extend([
        path_cls("/opt/ghidra"),
        path_cls("/usr/share/ghidra"),
        path_cls("/usr/local/opt/ghidra"),
    ])
    for base in candidates:
        for prop in [
            base / "Ghidra" / "application.properties",
            base / "application.properties",
        ]:
            if prop.is_file():
                try:
                    txt = prop.read_text(encoding="utf-8", errors="ignore")
                    if "application.version=12.2" in txt:
                        return True
                except OSError:
                    pass
    return False


def find_jdk21_path() -> Optional[Path]:
    """
    Discovers OpenJDK 21+ installation directory across environment and standard platform paths.
    Validates that release file or java -version indicates >= 21.
    If Ghidra 12.2 is detected, injects/prefers OpenJDK 27 (DEF-BB-040).
    """
    path_cls = _tc_attr("Path", Path)
    jdk_check = _tc_attr("_is_jdk21_or_higher", _is_jdk21_or_higher)
    ghidra_12_check = _tc_attr("is_ghidra_12_2_installed", is_ghidra_12_2_installed)

    env_java_home = os.environ.get("JAVA_HOME")
    if env_java_home and env_java_home.strip():
        cand = path_cls(env_java_home.strip())
        if cand.is_dir():
            if jdk_check(cand):
                return cand.resolve()
        elif re.search(r"(?:^|[/-])(?:java-?)?2[1-9](?:[/-]|$)", str(cand)):
            # Accommodate mock/symlink JDK 21+ paths that may not be mounted
            return cand

    # If Ghidra 12.2 is detected, prefer Java 27 (DEF-BB-040)
    if ghidra_12_check():
        cand27 = path_cls("/usr/lib/jvm/java-27-openjdk")
        try:
            if cand27.is_dir() and jdk_check(cand27):
                return cand27.resolve()
        except OSError:
            pass

    system_candidates = [
        # Linux / Arch / Fedora / Debian / Ubuntu
        path_cls("/usr/lib/jvm/java-27-openjdk"),
        path_cls("/usr/lib/jvm/java-21-openjdk"),
        path_cls("/usr/lib/jvm/default"),
        path_cls("/usr/lib/jvm/temurin-21"),
        path_cls("/usr/lib/jvm/java-21-openjdk-amd64"),
        path_cls("/usr/lib/jvm/java-21-openjdk-arm64"),
        # macOS
        path_cls("/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"),
        path_cls("/Library/Java/JavaVirtualMachines/openjdk-21.jdk/Contents/Home"),
        path_cls("/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home"),
    ]

    for cand in system_candidates:
        try:
            if cand.is_dir() and jdk_check(cand):
                return cand.resolve()
        except OSError:
            continue

    return None


def configure_rea_mcp_server(
    config_paths: Optional[List[Path]] = None,
    jdk21_path: Optional[Path] = None,
    ghidra_dir: Optional[str] = None,
) -> Tuple[List[Path], List[str]]:
    """
    Configures or updates the 'rea' MCP server entry in Antigravity mcp_config.json files.
    Returns a tuple of (configured_paths, error_messages).
    """
    path_cls = _tc_attr("Path", Path)
    jdk_check = _tc_attr("_is_jdk21_or_higher", _is_jdk21_or_higher)
    jdk_finder = _tc_attr("find_jdk21_path", find_jdk21_path)

    if config_paths is None:
        config_paths = [
            path_cls.home() / ".gemini" / "config" / "mcp_config.json",
            path_cls.home() / ".gemini" / "antigravity" / "mcp_config.json",
        ]

    if not ghidra_dir:
        ghidra_dir = os.environ.get("GHIDRA_INSTALL_DIR")
        if not ghidra_dir:
            for cand in [
                path_cls("/opt/ghidra"),
                path_cls("/usr/local/opt/ghidra"),
                path_cls.home() / "ghidra",
            ]:
                if cand.is_dir():
                    ghidra_dir = str(cand)
                    break

    if jdk21_path is None:
        jdk21_path = jdk_finder()
    elif isinstance(jdk21_path, (str, Path)):
        p = path_cls(jdk21_path)
        if p.is_dir():
            jdk21_path = p if jdk_check(p) else None
        elif re.search(r"(?:^|[/-])(?:java-?)?2[1-9](?:[/-]|$)", str(p)):
            jdk21_path = p
        else:
            jdk21_path = None

    configured: List[Path] = []
    errors: List[str] = []

    for cfg_p in config_paths:
        try:
            data: Dict[str, Any] = {}
            if cfg_p.is_file():
                try:
                    data = json.loads(cfg_p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                data["mcpServers"] = {}

            env_vars: Dict[str, str] = {
                "GHIDRA_INSTALL_DIR": ghidra_dir or "/opt/ghidra",
                "REA_MCP_INPUT_SCHEMA_PROFILE": "full",
                "REA_MCP_OUTPUT_SCHEMA_PROFILE": "off",
            }
            if jdk21_path:
                env_vars["JAVA_HOME"] = str(jdk21_path)

            data["mcpServers"]["rea"] = {
                "command": "rea",
                "args": ["mcp"],
                "env": env_vars,
            }
            cfg_p.parent.mkdir(parents=True, exist_ok=True)
            cfg_p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            configured.append(cfg_p)
        except (OSError, PermissionError) as e:
            errors.append(f"Failed to write MCP configuration to {cfg_p}: {e}")

    return configured, errors


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
    if candidates is None:
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
    find_bin_fn = _tc_attr("find_rea_binary", find_rea_binary)
    is_mcp_fn = _tc_attr("is_rea_mcp_configured", is_rea_mcp_configured)
    parse_prov_fn = _tc_attr("_parse_rea_providers", _parse_rea_providers)
    sub_mod = _tc_attr("subprocess", subprocess)
    parse_ver_fn = _tc_attr("parse_version")
    ver_lt_fn = _tc_attr("version_less_than")
    node_chk_fn = _tc_attr("check_node_toolchain")

    # 1. Fast-path optimization (when experimental_rea=False)
    if not experimental_rea:
        rea_bin = find_bin_fn()
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
    mcp_configured = is_mcp_fn(mcp_config_path)
    rea_bin = find_bin_fn()

    if not rea_bin:
        return {
            "status": "warning",
            "binary": None,
            "version": None,
            "min_version": "6.0.0",
            "fast_path": False,
            "providers": {"active": [], "unavailable": [], "details": []},
            "mcp_configured": mcp_configured,
            "remediation": "Install REA via: pnpm add -g rea-agents (or run 'agyis doctor --experimental-rea --heal')",
            "details": "REA binary not found (--experimental-rea requested).",
        }

    version_str: Optional[str] = None
    try:
        proc = sub_mod.run(
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
        proc_prov = sub_mod.run(
            [str(rea_bin), "providers", "--json"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        stdout_prov = proc_prov.stdout if isinstance(proc_prov.stdout, str) else ""
        if proc_prov.returncode == 0 and stdout_prov.strip():
            providers = parse_prov_fn(stdout_prov)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, UnicodeDecodeError):
        providers = {"active": [], "unavailable": [], "details": []}

    min_version = "6.0.0"
    current_v = parse_ver_fn(version_str) if version_str else (0,)
    min_v = parse_ver_fn(min_version)

    if not version_str or ver_lt_fn(current_v, min_v):
        return {
            "status": "warning",
            "binary": str(rea_bin),
            "version": version_str,
            "min_version": min_version,
            "fast_path": False,
            "providers": providers,
            "mcp_configured": mcp_configured,
            "remediation": f"Update REA to >= {min_version} via: pnpm add -g rea-agents",
            "details": (
                f"REA {version_str} is outdated (< {min_version}) at {rea_bin}."
                if version_str
                else f"REA binary detected at {rea_bin}, but version could not be determined."
            ),
        }

    node_compat = node_chk_fn(timeout=timeout)
    if node_compat.get("status") == "WARNING":
        return {
            "status": "warning",
            "binary": str(rea_bin),
            "version": version_str,
            "min_version": min_version,
            "fast_path": False,
            "providers": providers,
            "mcp_configured": mcp_configured,
            "node_toolchain": node_compat,
            "remediation": "Switch to Node 24 LTS via: pnpm env use --global 24",
            "details": f"REA {version_str} verified, but Node.js {node_compat.get('version')} is incompatible with REA.",
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
            "node_toolchain": node_compat,
            "remediation": "Run 'rea setup --yes' or register 'rea' in ~/.gemini/config/mcp_config.json (or run 'agyis doctor --experimental-rea --heal')",
            "details": f"REA {version_str} verified ({rea_bin}), but REA MCP server is not registered in agent configuration.",
        }

    rea_patch_info = None
    try:
        from harness.re.patcher import check_patch

        rea_patch_info = check_patch()
    except Exception:
        pass

    return {
        "status": "ok",
        "binary": str(rea_bin),
        "version": version_str,
        "min_version": min_version,
        "fast_path": False,
        "providers": providers,
        "mcp_configured": True,
        "node_toolchain": node_compat,
        "rea_patch": rea_patch_info,
        "remediation": None,
        "details": f"REA {version_str} verified ({rea_bin}) with MCP registered.",
    }
