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
from typing import List, Tuple


def _build_launcher_content(
    target_resolved: str,
    source_resolved: str,
    entrypoint_func: str = "main",
) -> str:
    """Builds executable python launcher script content."""
    import_line = (
        "from harness.cli import main\n"
        if entrypoint_func == "main"
        else "from harness.cli import main, deprecated_psl_main\n"
    )
    call_line = f"    sys.exit({entrypoint_func}())\n"

    return (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n\n"
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
        "venv_py = source_dir / '.venv' / 'bin' / 'python'\n"
        "if venv_py.exists() and sys.executable != str(venv_py):\n"
        "    import os\n"
        "    os.execv(str(venv_py), [str(venv_py)] + sys.argv)\n\n"
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

    agyis_content = _build_launcher_content(target_resolved, source_resolved, entrypoint_func="main")
    psl_content = _build_launcher_content(target_resolved, source_resolved, entrypoint_func="deprecated_psl_main")

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
