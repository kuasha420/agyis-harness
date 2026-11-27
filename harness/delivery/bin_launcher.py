# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Launcher script generation and binary installation for Agyis & PSL shims (ADR-030).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import List, Optional, Tuple

from harness.delivery.constants import is_packaged_wheel_install
from harness.runtime.tool_checks_common import find_hermetic_uv_python


def _resolve_launcher_python(source_dir: Optional[Path] = None) -> Optional[str]:
    """Resolve active venv/uv python interpreter for packaged wheel or non-repo venv installs."""
    src = Path(source_dir).resolve() if source_dir is not None else None
    in_packaged = is_packaged_wheel_install(src)
    repo_venv = (src / ".venv").resolve() if src is not None else None
    in_non_repo_venv = (
        sys.prefix != sys.base_prefix
        and (repo_venv is None or Path(sys.prefix).resolve() != repo_venv)
    )
    if not (in_packaged or in_non_repo_venv):
        return None

    exe = os.path.abspath(sys.executable) if sys.executable else None
    if in_non_repo_venv and exe:
        return exe
    uv_py = find_hermetic_uv_python()
    if uv_py is not None:
        return str(uv_py)
    return exe


def _build_launcher_content(
    target_resolved: str,
    source_resolved: str,
    entrypoint_func: str = "main",
    python_executable: Optional[str] = None,
) -> str:
    """Builds executable python launcher script content."""
    import_line = (
        "from harness.cli import main\n"
        if entrypoint_func == "main"
        else "from harness.cli import main, deprecated_psl_main\n"
    )
    call_line = f"    sys.exit({entrypoint_func}())\n"

    use_direct_shebang = bool(
        python_executable
        and len(python_executable) <= 120
        and not any(ch.isspace() for ch in python_executable)
    )
    shebang = f"#!{python_executable}\n" if use_direct_shebang else "#!/usr/bin/env python3\n"

    if python_executable:
        reexec_target_block = f"target_py_abs = os.path.abspath({python_executable!r})\n"
    else:
        reexec_target_block = (
            "_cwd_venv_py = _cwd_repo / '.venv' / 'bin' / 'python' if _cwd_repo is not None else None\n"
            "target_py_abs = (\n"
            "    os.path.abspath(str(_cwd_venv_py))\n"
            "    if _cwd_venv_py is not None and _cwd_venv_py.is_file() and os.access(str(_cwd_venv_py), os.X_OK)\n"
            "    else os.path.abspath(str(source_dir / '.venv' / 'bin' / 'python'))\n"
            ")\n"
        )
    reexec_block = (
        f"{reexec_target_block}"
        "if os.path.exists(target_py_abs) and os.path.abspath(sys.executable) != target_py_abs:\n"
        "    if not os.environ.get('_AGYIS_LAUNCHER_REEXEC'):\n"
        "        os.environ['_AGYIS_LAUNCHER_REEXEC'] = '1'\n"
        "        os.execv(target_py_abs, [target_py_abs] + sys.argv)\n"
        "os.environ.pop('_AGYIS_LAUNCHER_REEXEC', None)\n\n"
    )

    return (
        f"{shebang}"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "def _detect_cwd_checkout():\n"
        "    try:\n"
        "        cwd = Path.cwd().resolve()\n"
        "    except OSError:\n"
        "        return None\n"
        "    for candidate in (cwd, *cwd.parents):\n"
        "        if (\n"
        "            (candidate / 'pyproject.toml').is_file()\n"
        "            and (candidate / 'harness' / 'cli.py').is_file()\n"
        "            and (candidate / 'tests').is_dir()\n"
        "        ):\n"
        "            return candidate\n"
        "    return None\n\n"
        f"target_dir = Path({target_resolved!r})\n"
        "if target_dir.exists() and str(target_dir) not in sys.path:\n"
        "    sys.path.insert(0, str(target_dir))\n\n"
        "for plugin_dir in [\n"
        "    Path.home() / '.gemini' / 'config' / 'plugins' / 'agyis-harness',\n"
        "    Path.home() / '.gemini' / 'config' / 'plugins' / 'psl-agy-harness',\n"
        "]:\n"
        "    if plugin_dir.exists() and str(plugin_dir) not in sys.path:\n"
        "        sys.path.insert(0, str(plugin_dir))\n\n"
        f"source_dir = Path({source_resolved!r})\n"
        "if source_dir.exists() and str(source_dir) not in sys.path:\n"
        "    sys.path.insert(0, str(source_dir))\n\n"
        "_cwd_repo = _detect_cwd_checkout()\n"
        "if _cwd_repo is not None:\n"
        "    _cwd_repo_str = str(_cwd_repo)\n"
        "    if _cwd_repo_str in sys.path:\n"
        "        sys.path.remove(_cwd_repo_str)\n"
        "    sys.path.insert(0, _cwd_repo_str)\n\n"
        f"{reexec_block}"
        f"{import_line}\n"
        "if __name__ == '__main__':\n"
        f"{call_line}"
    )


def install_launchers(
    bin_dir: Path,
    aux_bin_dirs: List[Path],
    source_dir: Path,
    target: Path,
) -> Tuple[Path, Path]:
    """
    Installs both primary 'agyis' and backward-compatible 'psl' deprecation shim
    launchers into bin_dir and all writable auxiliary bin directories with mode 0o755.
    Returns (agyis_bin_path, psl_bin_path).
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    target_resolved = str(target.resolve()) if target.exists() else str(target)
    source_resolved = str(source_dir.resolve())
    python_executable = _resolve_launcher_python(source_dir)

    agyis_content = _build_launcher_content(
        target_resolved,
        source_resolved,
        entrypoint_func="main",
        python_executable=python_executable,
    )
    psl_content = _build_launcher_content(
        target_resolved,
        source_resolved,
        entrypoint_func="deprecated_psl_main",
        python_executable=python_executable,
    )

    def _deploy_file(dest: Path, content: str) -> None:
        if dest.is_symlink() or dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o755)

    # 1. Primary directory deployment
    agyis_bin = bin_dir / "agyis"
    psl_bin = bin_dir / "psl"
    _deploy_file(agyis_bin, agyis_content)
    _deploy_file(psl_bin, psl_content)

    # 2. Deploy to auxiliary bin directories
    for aux_dir in aux_bin_dirs:
        if aux_dir == bin_dir:
            continue
        # Skip unwritable /usr/local/bin unless elevated
        if str(aux_dir).startswith("/usr/local/bin") or aux_dir == Path("/usr/local/bin"):
            try:
                if not aux_dir.exists() or not os.access(aux_dir, os.W_OK):
                    continue
                for fname in ("agyis", "psl"):
                    cand = aux_dir / fname
                    if cand.exists() and not os.access(cand, os.W_OK):
                        continue
            except OSError:
                continue

        try:
            aux_dir.mkdir(parents=True, exist_ok=True)
            _deploy_file(aux_dir / "agyis", agyis_content)
            _deploy_file(aux_dir / "psl", psl_content)
        except (PermissionError, OSError):
            pass

    return agyis_bin, psl_bin


def install_psl_launcher(
    bin_dir: Path,
    aux_bin_dirs: List[Path],
    source_dir: Path,
    target: Path,
) -> Path:
    """Backward-compatible facade installing launchers and returning primary psl launcher."""
    _, psl_bin = install_launchers(bin_dir, aux_bin_dirs, source_dir, target)
    return psl_bin
