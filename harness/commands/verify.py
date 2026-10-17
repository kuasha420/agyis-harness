# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Cleanroom and specification verification CLI command (ADR-028).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from harness.hooks.completion_fence_hook import clear_spec_dirty, is_manifest_verified


def cmd_verify(args: argparse.Namespace) -> int:
    """
    Verifies cleanroom specifications in docs/specs/** and reconstruction manifest
    in .agents/ledger/manifest.json (ADR-028).

    - If 'rea' executable is found and not in explicit spec mode, delegates to
      'rea verify-reconstruction' if applicable.
    - Otherwise validates cleanroom manifest and specs directory.
    - Returns 0 on valid/clean specs or manifest, or if cleanroom specs are present.
    - Returns 1 if manifest exists but is invalid.
    """
    workspace_val = getattr(args, "workspace", None)
    workspace = Path(workspace_val).resolve() if workspace_val else Path.cwd().resolve()
    is_spec = getattr(args, "spec", False)
    is_json = getattr(args, "json", False)

    # 1. Spec Mode: explicitly validates cleanroom specifications in docs/specs/**
    if is_spec:
        specs_dir = workspace / "docs" / "specs"
        spec_files = [p for p in specs_dir.rglob("*") if p.is_file()] if specs_dir.is_dir() else []

        code_exts = {".py", ".ts", ".js", ".rs", ".go", ".sh", ".c", ".cpp"}
        code_specs = [p for p in spec_files if p.suffix.lower() in code_exts]
        if code_specs:
            if is_json:
                print(
                    json.dumps(
                        {
                            "status": "failed",
                            "reason": "Executable code files detected inside cleanroom specifications directory.",
                            "workspace": str(workspace),
                            "code_specs": [str(p.relative_to(workspace)) for p in code_specs],
                        },
                        indent=2,
                    )
                )
            else:
                print(
                    f"❌ Verification failed: Code files detected in docs/specs: {[str(p.name) for p in code_specs]}",
                    file=sys.stderr,
                )
            return 1

        if is_json:
            print(
                json.dumps(
                    {
                        "status": "verified",
                        "workspace": str(workspace),
                        "specs_dir": str(specs_dir) if specs_dir.is_dir() else None,
                        "specs_count": len(spec_files),
                        "spec_files": [str(p.relative_to(workspace)) for p in spec_files],
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"✔ Cleanroom specifications verified ({len(spec_files)} specifications found in docs/specs/)."
            )
        try:
            clear_spec_dirty()
        except Exception:
            pass
        return 0

    # 2. Delegation to 'rea verify-reconstruction' if applicable
    if shutil.which("rea"):
        try:
            res = subprocess.run(
                ["rea", "verify-reconstruction"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
            )
            out = (res.stdout or "") + (res.stderr or "")
            if "is not a command" not in out and "unrecognized" not in out.lower():
                if res.returncode == 0:
                    if is_json:
                        print(
                            json.dumps(
                                {
                                    "status": "verified",
                                    "delegated": "rea",
                                    "command": "rea verify-reconstruction",
                                    "output": res.stdout.strip(),
                                },
                                indent=2,
                            )
                        )
                    else:
                        if res.stdout.strip():
                            print(res.stdout.strip())
                        print("✔ Cleanroom reconstruction verified via 'rea verify-reconstruction'.")
                    try:
                        clear_spec_dirty()
                    except Exception:
                        pass
                    return 0
                else:
                    if is_json:
                        print(
                            json.dumps(
                                {
                                    "status": "failed",
                                    "delegated": "rea",
                                    "command": "rea verify-reconstruction",
                                    "returncode": res.returncode,
                                    "stderr": res.stderr.strip(),
                                },
                                indent=2,
                            )
                        )
                    else:
                        if res.stderr.strip():
                            print(res.stderr.strip(), file=sys.stderr)
                        print(
                            f"❌ Verification failed: 'rea verify-reconstruction' returned exit code {res.returncode}.",
                            file=sys.stderr,
                        )
                    return res.returncode if res.returncode != 0 else 1
        except OSError:
            pass

    # 3. Native cleanroom manifest and specifications validation
    manifest_path = workspace / ".agents" / "ledger" / "manifest.json"
    manifest_exists = manifest_path.is_file()
    manifest_verified = is_manifest_verified(workspace) if manifest_exists else False

    # Return 1 if manifest exists but is invalid
    if manifest_exists and not manifest_verified:
        if is_json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": f"Manifest at {manifest_path} exists but failed formal cleanroom verification.",
                        "workspace": str(workspace),
                        "manifest": str(manifest_path),
                        "manifest_verified": False,
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"❌ Verification failed: Manifest at {manifest_path} exists but is invalid.",
                file=sys.stderr,
            )
        return 1

    specs_dir = workspace / "docs" / "specs"
    spec_files = [p for p in specs_dir.rglob("*") if p.is_file()] if specs_dir.is_dir() else []

    # Report success
    if is_json:
        print(
            json.dumps(
                {
                    "status": "verified",
                    "workspace": str(workspace),
                    "manifest_path": str(manifest_path) if manifest_exists else None,
                    "manifest_verified": manifest_verified,
                    "specs_dir": str(specs_dir) if specs_dir.is_dir() else None,
                    "specs_count": len(spec_files),
                    "spec_files": [str(p.relative_to(workspace)) for p in spec_files],
                },
                indent=2,
            )
        )
    else:
        manifest_desc = "verified" if manifest_verified else ("none" if not manifest_exists else "invalid")
        print(
            f"✔ Cleanroom verification passed ({len(spec_files)} specifications found, manifest: {manifest_desc})."
        )

    try:
        clear_spec_dirty()
    except Exception:
        pass
    return 0
