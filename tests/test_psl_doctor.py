#!/usr/bin/env python3
"""
Unit tests for pipeline/psl_doctor.py
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.psl_doctor import (
    check_duplicate_agents,
    check_hooks_health,
    check_node_script_hygiene,
    check_psl_collision,
    check_tool,
    detect_os_family,
    find_hermetic_uv_python,
    parse_version,
    run_doctor,
)


class TestPslDoctor(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("3.12.8"), (3, 12, 8))
        self.assertEqual(parse_version("10.5"), (10, 5))
        self.assertEqual(parse_version("v20.11.0"), (20, 11, 0))
        self.assertEqual(parse_version("git version 2.55.0"), (2, 55, 0))
        self.assertEqual(parse_version("unknown"), (0,))

    def test_version_comparisons(self):
        self.assertTrue(parse_version("3.12.0") >= parse_version("3.12.0"))
        self.assertTrue(parse_version("3.12.8") > parse_version("3.12.0"))
        self.assertTrue(parse_version("3.10.13") < parse_version("3.12.0"))
        self.assertTrue(parse_version("10.5.0") > parse_version("8.7.0"))

    def test_detect_os_family(self):
        os_fam = detect_os_family()
        self.assertIn(os_fam, ("arch", "debian", "fedora", "darwin", "linux"))

    def test_check_tool_missing(self):
        spec = {
            "binary": "nonexistent_binary_xyz_12345",
            "min_version": "1.0.0",
        }
        res = check_tool("nonexistent", spec)
        self.assertEqual(res["status"], "MISSING")
        self.assertIsNone(res["path"])

    def test_check_tool_optional_missing(self):
        spec = {
            "binary": "nonexistent_binary_xyz_12345",
            "optional": True,
        }
        res = check_tool("optional_nonexistent", spec)
        self.assertEqual(res["status"], "OPTIONAL_MISSING")

    def test_check_tool_existing(self):
        spec = {
            "binary": "git",
            "min_version": "2.0.0",
            "version_command": "git --version",
            "version_regex": r"git version\s+([0-9]+\.[0-9]+\.[0-9]+)",
        }
        res = check_tool("git", spec)
        self.assertEqual(res["status"], "OK")
        self.assertIsNotNone(res["path"])
        self.assertIsNotNone(res["version"])

    def test_find_hermetic_uv_python(self):
        # Verify function executes without crash and returns Path or None
        herm = find_hermetic_uv_python()
        if herm is not None:
            self.assertTrue(herm.exists())
            self.assertTrue(str(herm).endswith("python3"))

    def test_run_doctor_with_canonical_matrix(self):
        matrix_path = Path(__file__).parent.parent / "harness/runtime/matrix.json"
        self.assertTrue(matrix_path.exists())

        def mock_run(cmd, *args, **kwargs):
            proc = unittest.mock.MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            cmd_str = str(cmd)
            if "python" in cmd_str:
                proc.stdout = "Python 3.12.8"
            elif "uv" in cmd_str:
                proc.stdout = "uv 0.5.2"
            elif "node" in cmd_str:
                proc.stdout = "v22.0.0"
            elif "pnpm" in cmd_str:
                proc.stdout = "9.15.0"
            elif "git" in cmd_str:
                proc.stdout = "git version 2.45.0"
            elif "gh" in cmd_str:
                proc.stdout = "gh version 2.50.0"
            elif "rg" in cmd_str:
                proc.stdout = "ripgrep 14.1.0"
            elif "fd" in cmd_str:
                proc.stdout = "fd 9.0.0"
            elif "ssh" in cmd_str:
                proc.stdout = "OpenSSH_9.5"
            elif "knot" in cmd_str:
                proc.stdout = "knot 1.0.0"
            else:
                proc.stdout = "99.0.0"
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            audit = run_doctor(matrix_path)

        self.assertIn("os_family", audit)
        self.assertIn("tiers", audit)
        self.assertIn("summary", audit)
        self.assertIn("tier_1_languages", audit["tiers"])
        self.assertIn("tier_2_swe_cli", audit["tiers"])
        self.assertIn("tier_3_mesh_host", audit["tiers"])
        self.assertGreater(audit["summary"]["total_tools"], 5)

    def test_check_tool_uv_candidate_paths(self):
        """Candidate user paths ~/.local/bin/uv and ~/.cargo/bin/uv are probed when uv is not in PATH."""
        spec = {
            "binary": "uv",
            "min_version": "0.4.0",
            "version_command": "uv --version",
            "version_regex": r"uv\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)",
        }
        with tempfile.TemporaryDirectory() as tmp_home:
            fake_home = Path(tmp_home)
            fake_uv = fake_home / ".local/bin/uv"
            fake_uv.parent.mkdir(parents=True)
            fake_uv.write_text("#!/bin/sh\n")
            fake_uv.chmod(0o755)

            mock_proc = unittest.mock.MagicMock()
            mock_proc.stdout = "uv 0.5.2"
            mock_proc.stderr = ""
            with patch("shutil.which", return_value=None), \
                 patch("pathlib.Path.home", return_value=fake_home), \
                 patch("subprocess.run", return_value=mock_proc):
                res = check_tool("uv", spec)
                self.assertEqual(res["status"], "OK")
                self.assertEqual(res["path"], str(fake_uv))
                self.assertEqual(res["version"], "0.5.2")

    def test_check_psl_collision_system_libpsl(self):
        """Detects collision when psl resolves to /usr/bin/psl."""
        with patch("shutil.which", return_value="/usr/bin/psl"):
            res = check_psl_collision()
            self.assertEqual(res["status"], "WARNING")
            self.assertTrue(res["collision"])
            self.assertIn("system libpsl", res["details"])
            self.assertIsNotNone(res["remediation"])

    def test_check_psl_collision_foreign_binary(self):
        """Detects collision when psl resolves to foreign non-harness script."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            foreign_bin = Path(tmp_dir) / "psl"
            foreign_bin.write_text("#!/bin/sh\necho 'other tool'\n")
            with patch("shutil.which", return_value=str(foreign_bin)):
                res = check_psl_collision()
                self.assertEqual(res["status"], "WARNING")
                self.assertTrue(res["collision"])
                self.assertIn("non-harness binary", res["details"])

    def test_check_psl_collision_harness_binary(self):
        """Passes when psl resolves to PSL harness launcher."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_bin = Path(tmp_dir) / "psl"
            harness_bin.write_text("#!/usr/bin/env python3\nfrom harness.cli import main\nmain()\n")
            with patch("shutil.which", return_value=str(harness_bin)):
                res = check_psl_collision()
                self.assertEqual(res["status"], "OK")
                self.assertFalse(res["collision"])
                self.assertIsNone(res["remediation"])

    def test_check_duplicate_agents_none(self):
        """Passes when no duplicate agent definitions exist between standalone config and plugins."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = Path(tmp_dir)
            (cfg / "agents").mkdir(parents=True)
            (cfg / "plugins" / "my-plugin" / "agents").mkdir(parents=True)

            (cfg / "agents" / "agent-a.md").write_text("# Agent A\n")
            (cfg / "plugins" / "my-plugin" / "agents" / "agent-b.md").write_text("# Agent B\n")

            res = check_duplicate_agents(config_dir=cfg)
            self.assertEqual(res["status"], "OK")
            self.assertEqual(res["duplicates"], [])
            self.assertIsNone(res["remediation"])

    def test_check_duplicate_agents_found(self):
        """Detects duplicate agent definitions between standalone config and plugins."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = Path(tmp_dir)
            (cfg / "agents").mkdir(parents=True)
            (cfg / "plugins" / "my-plugin" / "agents").mkdir(parents=True)

            (cfg / "agents" / "shared-agent.md").write_text("# Standalone Agent\n")
            (cfg / "plugins" / "my-plugin" / "agents" / "shared-agent.md").write_text("# Plugin Agent\n")

            res = check_duplicate_agents(config_dir=cfg)
            self.assertEqual(res["status"], "WARNING")
            self.assertIn("shared-agent.md", res["duplicates"])
            self.assertIsNotNone(res["remediation"])
            self.assertEqual(len(res["duplicate_items"]), 1)

    def test_check_node_script_hygiene_non_esm(self):
        """Non-ESM package (no 'type': 'module') passes node script hygiene with status OK."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ws = Path(tmp_dir)
            (ws / "package.json").write_text(json.dumps({"name": "cjs-pkg"}), encoding="utf-8")
            (ws / "index.js").write_text("const x = require('x');\nmodule.exports = x;\n", encoding="utf-8")

            res = check_node_script_hygiene(workspace_root=ws)
            self.assertEqual(res["status"], "OK")
            self.assertFalse(res["is_esm"])
            self.assertEqual(res["violations"], [])

    def test_check_node_script_hygiene_esm_clean(self):
        """ESM package ('type': 'module') with pure ESM scripts and .cjs files passes with status OK."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ws = Path(tmp_dir)
            (ws / "package.json").write_text(json.dumps({"name": "esm-pkg", "type": "module"}), encoding="utf-8")
            (ws / "index.js").write_text("import x from 'x';\nexport default x;\n", encoding="utf-8")
            (ws / "helper.cjs").write_text("const x = require('x');\nmodule.exports = x;\n", encoding="utf-8")

            res = check_node_script_hygiene(workspace_root=ws)
            self.assertEqual(res["status"], "OK")
            self.assertTrue(res["is_esm"])
            self.assertEqual(res["violations"], [])

    def test_check_node_script_hygiene_esm_violations(self):
        """ESM package ('type': 'module') flags .js files containing CommonJS syntax with status WARNING."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ws = Path(tmp_dir)
            (ws / "package.json").write_text(json.dumps({"name": "esm-pkg", "type": "module"}), encoding="utf-8")
            (ws / "broken.js").write_text("const path = require('path');\nmodule.exports = {};\n", encoding="utf-8")

            res = check_node_script_hygiene(workspace_root=ws)
            self.assertEqual(res["status"], "WARNING")
            self.assertTrue(res["is_esm"])
            self.assertEqual(len(res["violations"]), 1)
            self.assertIn("broken.js", res["violations"][0]["file"])
            self.assertIsNotNone(res["remediation"])

    def test_check_hooks_health_canonical(self):
        """Canonical repo hooks.json passes health audit with status OK and all 5 hooks verified."""
        res = check_hooks_health()
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["failures"], [])
        self.assertIsNone(res["remediation"])
        expected_hooks = {"anti-drift", "anti-loop", "command-safety", "compactor", "verification-fence"}
        self.assertTrue(expected_hooks.issubset(set(res["checked_hooks"])))

    def test_check_hooks_health_missing_file(self):
        """Missing hooks.json yields WARNING with diagnostic failures and remediation."""
        missing = Path("/nonexistent/hooks/path/hooks.json")
        res = check_hooks_health(hooks_path=missing)
        self.assertEqual(res["status"], "WARNING")
        self.assertEqual(res["checked_hooks"], [])
        self.assertGreater(len(res["failures"]), 0)
        self.assertIsNotNone(res["remediation"])
        self.assertIn("not found", res["failures"][0])

    def test_check_hooks_health_malformed_json(self):
        """Malformed JSON in hooks.json yields WARNING with parsing failure."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write("{bad json content:")
            tf.flush()
            temp_path = Path(tf.name)

        try:
            res = check_hooks_health(hooks_path=temp_path)
            self.assertEqual(res["status"], "WARNING")
            self.assertEqual(res["checked_hooks"], [])
            self.assertGreater(len(res["failures"]), 0)
            self.assertIn("Malformed hooks.json", res["failures"][0])
            self.assertIsNotNone(res["remediation"])
        finally:
            temp_path.unlink(missing_ok=True)

    def test_check_hooks_health_empty_hooks(self):
        """hooks.json with no hook commands yields WARNING."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write("{}")
            tf.flush()
            temp_path = Path(tf.name)

        try:
            res = check_hooks_health(hooks_path=temp_path)
            self.assertEqual(res["status"], "WARNING")
            self.assertEqual(res["checked_hooks"], [])
            self.assertIn("No hook commands found", res["failures"][0])
            self.assertIsNotNone(res["remediation"])
        finally:
            temp_path.unlink(missing_ok=True)

    def test_check_hooks_health_unknown_hook(self):
        """hooks.json referencing unknown hook runner argument yields WARNING."""
        content = json.dumps({
            "test-guard": {
                "PreToolUse": [{
                    "hooks": [{"command": "python3 -m harness.hooks.runner totally-unknown-hook-name"}]
                }]
            }
        })
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(content)
            tf.flush()
            temp_path = Path(tf.name)

        try:
            res = check_hooks_health(hooks_path=temp_path)
            self.assertEqual(res["status"], "WARNING")
            self.assertIn("totally-unknown-hook-name", res["failures"][0])
            self.assertIsNotNone(res["remediation"])
        finally:
            temp_path.unlink(missing_ok=True)

    def test_check_hooks_health_import_failure(self):
        """hooks.json referencing unimportable module yields WARNING."""
        content = json.dumps({
            "test-guard": {
                "PreToolUse": [{
                    "hooks": [{"command": "python3 -m completely_nonexistent_hook_module_xyz"}]
                }]
            }
        })
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tf.write(content)
            tf.flush()
            temp_path = Path(tf.name)

        try:
            res = check_hooks_health(hooks_path=temp_path)
            self.assertEqual(res["status"], "WARNING")
            self.assertIn("Failed to load hook module", res["failures"][0])
            self.assertIsNotNone(res["remediation"])
        finally:
            temp_path.unlink(missing_ok=True)

    def test_run_doctor_with_hooks_health(self):
        """run_doctor includes hooks_health and reflects warnings in summary."""
        matrix_path = Path(__file__).parent.parent / "harness/runtime/matrix.json"

        def mock_run(cmd, *args, **kwargs):
            proc = unittest.mock.MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = "1.0.0"
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            audit = run_doctor(matrix_path)
            self.assertIn("hooks_health", audit)
            self.assertIn(audit["hooks_health"]["status"], ("OK", "WARNING"))


if __name__ == "__main__":
    unittest.main()
