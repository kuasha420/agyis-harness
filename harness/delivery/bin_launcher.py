# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Purrfect Software Limited (PSL)

"""
Launcher script generation and binary installation (ADR-030).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


def install_psl_launcher(
    bin_dir: Path,
    aux_bin_dirs: List[Path],
    source_dir: Path,
    target: Path,
) -> Path:
    """Installs standalone CLI executable launcher into bin_dir and auxiliary bin paths with mode 0o755."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    psl_bin = bin_dir / "psl"
    if psl_bin.is_symlink() or psl_bin.exists():
        try:
            psl_bin.unlink()
        except OSError:
            pass

    target_resolved = str(target.resolve()) if target.exists() else str(target)
    source_resolved = str(source_dir.resolve())
    launcher_content = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        f"target_dir = Path({target_resolved!r})\n"
        "if target_dir.exists() and str(target_dir) not in sys.path:\n"
        "    sys.path.insert(0, str(target_dir))\n\n"
        "plugin_default = Path.home() / '.gemini' / 'config' / 'plugins' / 'psl-agy-harness'\n"
        "if plugin_default.exists() and str(plugin_default) not in sys.path:\n"
        "    sys.path.insert(0, str(plugin_default))\n\n"
        f"source_dir = Path({source_resolved!r})\n"
        "if source_dir.exists() and str(source_dir) not in sys.path:\n"
        "    sys.path.insert(0, str(source_dir))\n\n"
        "venv_py = source_dir / '.venv' / 'bin' / 'python'\n"
        "if venv_py.exists() and sys.executable != str(venv_py):\n"
        "    import os\n"
        "    os.execv(str(venv_py), [str(venv_py)] + sys.argv)\n\n"
        "from harness.cli import main\n\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(main())\n"
    )
    psl_bin.write_text(launcher_content, encoding="utf-8")
    psl_bin.chmod(0o755)

    # Deploy launcher to auxiliary bin directories
    for aux_dir in aux_bin_dirs:
        if aux_dir == bin_dir:
            continue
        aux_bin = aux_dir / "psl"
        # For system directory /usr/local/bin, only attempt if writable
        if str(aux_dir).startswith("/usr/local/bin") or aux_dir == Path("/usr/local/bin"):
            try:
                if not aux_dir.exists() or not os.access(aux_dir, os.W_OK):
                    continue
                if aux_bin.exists() and not os.access(aux_bin, os.W_OK):
                    continue
            except OSError:
                continue
        try:
            aux_dir.mkdir(parents=True, exist_ok=True)
            if aux_bin.is_symlink() or aux_bin.exists():
                try:
                    aux_bin.unlink()
                except OSError:
                    pass
            aux_bin.write_text(launcher_content, encoding="utf-8")
            aux_bin.chmod(0o755)
        except (PermissionError, OSError):
            # Safely skip without error if permission denied
            pass

    return psl_bin
