#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Hermetic unit and integration tests for GitHub Issue Forms and Configuration (Issue #46, ADR-014, ADR-015).

Tests:
- Zero-dependency hermetic YAML parsing and tab character syntax verification
- Schema validation for bug_report.yml, feature_request.yml, and config.yml
- AC-1: Mandatory agyis-harness version enforcement (tag or git commit SHA)
- AC-2: Structured optional fields for Antigravity environment (CLI and Electron App/IDE)
- AC-3: Structured optional fields for host SWE toolchain (Python, Node/pnpm, Git/gh, REA CLI)
- AC-4: Reference codebase / reproduction repository field
- AC-5: GitHub Issue Form schema validity and simulated submission validation
- Sub-second execution benchmark (<1.0s invariant)
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Tuple, Union
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"


def parse_yaml_simple(text: str) -> Union[Dict[str, Any], List[Any]]:
    """Zero-dependency indentation-aware YAML parser for GitHub Issue Forms."""
    lines = text.splitlines()

    def get_indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def parse_block(idx: int, current_indent: int) -> Tuple[Any, int]:
        i = idx
        while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
            i += 1
        if i >= len(lines):
            return {}, i

        first_line = lines[i]
        first_indent = get_indent(first_line)
        if first_indent < current_indent:
            return {}, i

        stripped = first_line.strip()
        if stripped.startswith("- "):
            items: List[Any] = []
            curr_i = i
            while curr_i < len(lines):
                line = lines[curr_i]
                if not line.strip() or line.strip().startswith("#"):
                    curr_i += 1
                    continue
                ind = get_indent(line)
                if ind < first_indent:
                    break
                if ind == first_indent and line.strip().startswith("- "):
                    content = line.strip()[2:].strip()
                    if content and ":" in content:
                        sub_lines = [" " * (first_indent + 2) + content]
                        curr_i += 1
                        while curr_i < len(lines):
                            l = lines[curr_i]
                            if not l.strip() or l.strip().startswith("#"):
                                sub_lines.append(l)
                                curr_i += 1
                                continue
                            if get_indent(l) > first_indent:
                                sub_lines.append(l)
                                curr_i += 1
                            else:
                                break
                        sub_obj = parse_yaml_simple("\n".join(sub_lines))
                        items.append(sub_obj)
                    elif content:
                        items.append(content)
                        curr_i += 1
                    else:
                        child, next_i = parse_block(curr_i + 1, first_indent + 1)
                        items.append(child)
                        curr_i = next_i
                else:
                    break
            return items, curr_i
        else:
            res: Dict[str, Any] = {}
            curr_i = i
            while curr_i < len(lines):
                line = lines[curr_i]
                if not line.strip() or line.strip().startswith("#"):
                    curr_i += 1
                    continue
                ind = get_indent(line)
                if ind < first_indent:
                    break
                if ind == first_indent and ":" in line:
                    k, v = line.strip().split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v in ("|", "|-", ">", ">-"):
                        multiline: List[str] = []
                        curr_i += 1
                        str_indent = None
                        while curr_i < len(lines):
                            ml_line = lines[curr_i]
                            if not ml_line.strip():
                                multiline.append("")
                                curr_i += 1
                                continue
                            ml_ind = get_indent(ml_line)
                            if str_indent is None:
                                if ml_ind <= first_indent:
                                    break
                                str_indent = ml_ind
                            if ml_ind < str_indent:
                                break
                            multiline.append(ml_line[str_indent:])
                            curr_i += 1
                        res[k] = "\n".join(multiline).rstrip()
                    elif not v:
                        child, next_i = parse_block(curr_i + 1, first_indent + 1)
                        res[k] = child
                        curr_i = next_i
                    else:
                        if v.lower() == "true":
                            res[k] = True
                        elif v.lower() == "false":
                            res[k] = False
                        elif v.startswith("[") and v.endswith("]"):
                            inner = v[1:-1].strip()
                            res[k] = [
                                x.strip().strip("'\"")
                                for x in inner.split(",")
                                if x.strip()
                            ] if inner else []
                        elif (
                            (v.startswith('"') and v.endswith('"'))
                            or (v.startswith("'") and v.endswith("'"))
                        ):
                            res[k] = v[1:-1]
                        else:
                            res[k] = v
                        curr_i += 1
                else:
                    curr_i += 1
            return res, curr_i

    obj, _ = parse_block(0, 0)
    return obj


def validate_issue_form_submission(template: Dict[str, Any], answers: Dict[str, Any]) -> List[str]:
    """Validates simulated user responses against issue form template validation rules."""
    errors: List[str] = []
    for item in template.get("body", []):
        if not isinstance(item, dict):
            continue
        field_id = item.get("id")
        validations = item.get("validations", {})
        is_required = validations.get("required", False) if isinstance(validations, dict) else False
        field_label = item.get("attributes", {}).get("label", field_id or "Field")

        if is_required:
            val = answers.get(field_id) if field_id else None
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"Missing required field: {field_label} (id: {field_id})")

        if item.get("type") == "checkboxes":
            options = item.get("attributes", {}).get("options", [])
            for opt in options:
                if isinstance(opt, dict) and opt.get("required", False):
                    opt_label = opt.get("label", "")
                    checked = answers.get(f"{field_id}:{opt_label}", False)
                    if not checked:
                        errors.append(f"Required checkbox not confirmed: {opt_label}")
    return errors


class TestIssueTemplates(unittest.TestCase):
    """Test suite for GitHub Issue Templates (.github/ISSUE_TEMPLATE/)."""

    def test_templates_directory_and_files_exist(self) -> None:
        """Issue template directory and required files must exist."""
        self.assertTrue(TEMPLATE_DIR.is_dir(), f"{TEMPLATE_DIR} directory does not exist")
        self.assertTrue((TEMPLATE_DIR / "bug_report.yml").is_file(), "bug_report.yml missing")
        self.assertTrue((TEMPLATE_DIR / "feature_request.yml").is_file(), "feature_request.yml missing")
        self.assertTrue((TEMPLATE_DIR / "config.yml").is_file(), "config.yml missing")

    def test_templates_no_tab_characters(self) -> None:
        """YAML specification forbids tab characters in indentation."""
        for path in TEMPLATE_DIR.glob("*.yml"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("\t", content, f"File {path.name} contains invalid tab character")

    def test_templates_valid_yaml_syntax(self) -> None:
        """All templates must parse cleanly into Python dictionaries."""
        for path in TEMPLATE_DIR.glob("*.yml"):
            content = path.read_text(encoding="utf-8")
            data = parse_yaml_simple(content)
            self.assertIsInstance(data, dict, f"File {path.name} did not parse into a dictionary")

    def test_bug_report_top_level_schema(self) -> None:
        """bug_report.yml must have name, description, title, labels, and body."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "Bug Report")
        self.assertTrue(data.get("description"))
        self.assertTrue(data.get("title", "").startswith("[Bug]:"))
        self.assertIn("bug", data.get("labels", []))
        self.assertIsInstance(data.get("body"), list)
        self.assertGreater(len(data.get("body")), 0)

    def test_bug_report_ac1_mandatory_harness_version(self) -> None:
        """AC-1: Active agyis-harness version must be an input field with required: true."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        body = data.get("body", [])
        harness_field = next((item for item in body if item.get("id") == "harness_version"), None)
        self.assertIsNotNone(harness_field, "Field with id 'harness_version' missing in bug_report.yml")
        self.assertEqual(harness_field.get("type"), "input")
        self.assertTrue(harness_field.get("attributes", {}).get("label"))
        self.assertTrue(harness_field.get("validations", {}).get("required"), "harness_version must be required: true")

    def test_bug_report_ac2_antigravity_platform_fields(self) -> None:
        """AC-2: Structured optional fields for Antigravity CLI and Electron App / IDE."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        body = data.get("body", [])
        ids = {item.get("id"): item for item in body if isinstance(item, dict)}

        self.assertIn("antigravity_cli_version", ids)
        self.assertEqual(ids["antigravity_cli_version"].get("type"), "input")
        self.assertFalse(ids["antigravity_cli_version"].get("validations", {}).get("required", False))

        self.assertIn("antigravity_ide_version", ids)
        self.assertEqual(ids["antigravity_ide_version"].get("type"), "input")
        self.assertFalse(ids["antigravity_ide_version"].get("validations", {}).get("required", False))

    def test_bug_report_ac3_host_swe_toolchain_fields(self) -> None:
        """AC-3: Structured optional fields for host SWE toolchain dependencies."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        body = data.get("body", [])
        ids = {item.get("id"): item for item in body if isinstance(item, dict)}

        for field_id in ("python_version", "node_package_manager", "vcs_tooling", "rea_tooling"):
            self.assertIn(field_id, ids, f"Field '{field_id}' missing from bug_report.yml")
            self.assertEqual(ids[field_id].get("type"), "input")
            self.assertFalse(ids[field_id].get("validations", {}).get("required", False))

    def test_bug_report_ac4_reproduction_repo_field(self) -> None:
        """AC-4: Optional/recommended field for reference codebase or reproduction repository."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        body = data.get("body", [])
        ids = {item.get("id"): item for item in body if isinstance(item, dict)}

        self.assertIn("reproduction_repo", ids)
        self.assertEqual(ids["reproduction_repo"].get("type"), "input")
        self.assertFalse(ids["reproduction_repo"].get("validations", {}).get("required", False))

    def test_bug_report_ac5_elements_and_checklist(self) -> None:
        """AC-5: Standard valid YAML form elements, markdown intro, and pre-flight checklist."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        body = data.get("body", [])
        valid_types = {"markdown", "input", "textarea", "dropdown", "checkboxes"}

        for elem in body:
            self.assertIn(elem.get("type"), valid_types)

        checklist = next((item for item in body if item.get("id") == "checklist"), None)
        self.assertIsNotNone(checklist)
        self.assertEqual(checklist.get("type"), "checkboxes")
        options = checklist.get("attributes", {}).get("options", [])
        self.assertGreater(len(options), 0)

    def test_feature_request_schema(self) -> None:
        """feature_request.yml must have name, description, title, labels, and structured body fields."""
        data = parse_yaml_simple((TEMPLATE_DIR / "feature_request.yml").read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "Feature Request")
        self.assertTrue(data.get("description"))
        self.assertTrue(data.get("title", "").startswith("[Feature]:"))
        self.assertIn("enhancement", data.get("labels", []))

        body = data.get("body", [])
        ids = {item.get("id"): item for item in body if isinstance(item, dict)}
        self.assertIn("proposal_summary", ids)
        self.assertTrue(ids["proposal_summary"].get("validations", {}).get("required", False))
        self.assertIn("proposed_solution", ids)
        self.assertTrue(ids["proposed_solution"].get("validations", {}).get("required", False))
        self.assertIn("alternatives_considered", ids)

    def test_config_yaml_schema(self) -> None:
        """config.yml must set blank_issues_enabled: false and provide contact_links."""
        data = parse_yaml_simple((TEMPLATE_DIR / "config.yml").read_text(encoding="utf-8"))
        self.assertIs(data.get("blank_issues_enabled"), False)
        links = data.get("contact_links", [])
        self.assertIsInstance(links, list)
        self.assertGreater(len(links), 0)
        for link in links:
            self.assertIn("name", link)
            self.assertIn("url", link)
            self.assertIn("about", link)

    def test_simulated_submission_missing_harness_version_fails(self) -> None:
        """Validation gate: issue submission without active harness version fails."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        answers: Dict[str, Any] = {
            "problem_description": "Hook error during step execution",
            "reproduction_steps": "Run command with flags",
            "checklist:I have verified that this issue occurs on the specified agyis-harness version.": True,
        }
        errors = validate_issue_form_submission(data, answers)
        self.assertTrue(any("harness_version" in err for err in errors), f"Expected harness_version error in: {errors}")

    def test_simulated_submission_with_only_mandatory_fields_succeeds(self) -> None:
        """Validation gate: issue submission with only mandatory fields succeeds (optional fields omitted)."""
        data = parse_yaml_simple((TEMPLATE_DIR / "bug_report.yml").read_text(encoding="utf-8"))
        answers: Dict[str, Any] = {
            "harness_version": "1.0.0-rc3",
            "problem_description": "Hook error during step execution",
            "reproduction_steps": "Run command with flags",
            "checklist:I have verified that this issue occurs on the specified agyis-harness version.": True,
        }
        errors = validate_issue_form_submission(data, answers)
        self.assertEqual(errors, [], f"Expected zero validation errors, got: {errors}")

    def test_subsecond_benchmark(self) -> None:
        """Execution of all template validations must complete in <0.10s (ADR-015 benchmark <1.0s)."""
        start = time.perf_counter()
        for path in TEMPLATE_DIR.glob("*.yml"):
            data = parse_yaml_simple(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
        duration = time.perf_counter() - start
        self.assertLess(duration, 0.10, f"Template parsing exceeded 0.10s: {duration:.4f}s")


if __name__ == "__main__":
    unittest.main()
