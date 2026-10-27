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
    is_scaffold = getattr(args, "scaffold", False)

    # 0. Scaffold Mode: generate typed obligation ledger adhering to REA 6.8.0
    if is_scaffold:
        ledger_path = workspace / ".agents" / "ledger" / "obligation_ledger.json"
        from harness.cleanroom.obligation import scaffold_obligation_ledger
        scaffold_obligation_ledger(ledger_path)
        if is_json:
            print(
                json.dumps(
                    {
                        "status": "scaffolded",
                        "workspace": str(workspace),
                        "path": str(ledger_path),
                    },
                    indent=2,
                )
            )
        else:
            print(f"✔ Scaffolded typed obligation ledger at {ledger_path}")
        return 0

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

    # 2. Delegation to REA obligation engine if applicable
    typed_ledger_path = workspace / ".agents" / "ledger" / "obligation_ledger.json"
    if shutil.which("rea"):
        if typed_ledger_path.is_file():
            try:
                res_build = subprocess.run(
                    ["rea", "build-reconstruction-obligation-ledger", str(typed_ledger_path)],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                )
                res_eval = subprocess.run(
                    ["rea", "evaluate-reconstruction-coverage"],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                )
                if res_build.returncode == 0 and res_eval.returncode == 0:
                    combined_out = (res_build.stdout or "") + ("\n" if res_build.stdout and res_eval.stdout else "") + (res_eval.stdout or "")
                    if is_json:
                        print(
                            json.dumps(
                                {
                                    "status": "verified",
                                    "delegated": "rea",
                                    "command": "rea evaluate-reconstruction-coverage",
                                    "output": combined_out.strip(),
                                },
                                indent=2,
                            )
                        )
                    else:
                        if combined_out.strip():
                            print(combined_out.strip())
                        print("✔ Cleanroom reconstruction verified via REA obligation engine.")
                    try:
                        clear_spec_dirty()
                    except Exception:
                        pass
                    return 0
                else:
                    err_code = res_build.returncode if res_build.returncode != 0 else res_eval.returncode
                    err_out = (res_build.stderr or "") + "\n" + (res_eval.stderr or "")
                    if is_json:
                        print(
                            json.dumps(
                                {
                                    "status": "failed",
                                    "delegated": "rea",
                                    "command": "rea evaluate-reconstruction-coverage",
                                    "returncode": err_code,
                                    "stderr": err_out.strip(),
                                },
                                indent=2,
                            )
                        )
                    else:
                        if err_out.strip():
                            print(err_out.strip(), file=sys.stderr)
                        print(
                            f"❌ Verification failed: REA commands returned exit code {err_code}.",
                            file=sys.stderr,
                        )
                    return err_code if err_code != 0 else 1
            except OSError:
                pass
        else:
            # Fallback for environments without typed obligation_ledger.json
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
    target_ledger = typed_ledger_path if typed_ledger_path.is_file() else manifest_path
    ledger_exists = target_ledger.is_file()
    manifest_verified = is_manifest_verified(workspace) if ledger_exists else False

    # Return 1 if manifest/ledger exists but is invalid
    if ledger_exists and not manifest_verified:
        if is_json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": f"Ledger at {target_ledger} exists but failed formal cleanroom verification.",
                        "workspace": str(workspace),
                        "manifest": str(target_ledger),
                        "manifest_verified": False,
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"❌ Verification failed: Ledger at {target_ledger} exists but is invalid.",
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
                    "manifest_path": str(target_ledger) if ledger_exists else None,
                    "manifest_verified": manifest_verified,
                    "specs_dir": str(specs_dir) if specs_dir.is_dir() else None,
                    "specs_count": len(spec_files),
                    "spec_files": [str(p.relative_to(workspace)) for p in spec_files],
                },
                indent=2,
            )
        )
    else:
        manifest_desc = "verified" if manifest_verified else ("none" if not ledger_exists else "invalid")
        print(
            f"✔ Cleanroom verification passed ({len(spec_files)} specifications found, manifest: {manifest_desc})."
        )

    try:
        clear_spec_dirty()
    except Exception:
        pass
    return 0
