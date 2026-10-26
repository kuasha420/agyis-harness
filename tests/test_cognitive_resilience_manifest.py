# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""Automated verification test suite for Cognitive Resilience Manifest (v1.0.0-rc7).

Validates:
1. Manifest existence and comprehensive line count (>= 1,000 lines).
2. Presence and complete specification of all 15 issues (3 Epics + 12 Child Issues).
3. Empirical grounding: all cited session IDs and step indices match valid rows in data/telemetry.db.
4. Target integrity: all cited repository code targets exist on disk.
5. Strict scope boundary: no multi-node mesh networking, Tailscale, WireGuard, or cross-device cluster concepts.
6. Sub-second benchmark execution (<1.0s).
"""

import os
import re
import sqlite3
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "specs" / "cognitive_resilience_github_issues_manifest.md"
TELEMETRY_DB_PATH = REPO_ROOT / "data" / "telemetry.db"

EXPECTED_ISSUE_NUMBERS = [f"#{n}" for n in range(64, 79)]
EXPECTED_EPICS = ["#64", "#69", "#74"]
EXPECTED_CHILD_ISSUES = [f"#{n}" for n in range(64, 79) if f"#{n}" not in EXPECTED_EPICS]


class TestCognitiveResilienceManifest(unittest.TestCase):
    """Hermetic unit tests validating the v1.0.0-rc7 Master Staging Manifest."""

    @classmethod
    def setUpClass(cls):
        cls.start_time = time.perf_counter()
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(f"Manifest missing at {MANIFEST_PATH}")
        cls.content = MANIFEST_PATH.read_text(encoding="utf-8")
        cls.lines = cls.content.splitlines()

    @classmethod
    def tearDownClass(cls):
        elapsed = time.perf_counter() - cls.start_time
        # Assert sub-second benchmark invariant (<1.0s)
        if elapsed >= 1.0:
            raise AssertionError(f"Test suite exceeded sub-second benchmark: {elapsed:.3f}s")

    def test_01_manifest_exists_and_comprehensiveness(self):
        """Manifest must exist and contain at least 1,000 lines of detailed specifications."""
        self.assertTrue(MANIFEST_PATH.is_file(), "Manifest file must exist on disk.")
        line_count = len(self.lines)
        self.assertGreaterEqual(
            line_count,
            1000,
            f"Manifest must be comprehensive (>= 1,000 lines), but found {line_count} lines.",
        )
        # Check standard document metadata
        self.assertIn("PSL-MANIFEST-2026-RC7-001", self.content)
        self.assertIn("v1.0.0-rc7", self.content)
        self.assertIn("kuasha420/agyis-harness", self.content)

    def test_02_all_15_issues_in_matrix_and_specifications(self):
        """All 15 issues (3 Epics + 12 Child Issues) must appear in both Matrix and Specifications."""
        self.assertEqual(len(EXPECTED_ISSUE_NUMBERS), 15)

        # 1. Section 2 Master Issue Matrix validation
        self.assertIn("## 2. Master Issue Matrix", self.content)
        matrix_section = self.content.split("## 2. Master Issue Matrix")[1].split("## 3. Detailed Issue Specifications")[0]
        for issue_num in EXPECTED_ISSUE_NUMBERS:
            self.assertIn(
                f"**{issue_num}**",
                matrix_section,
                f"Issue {issue_num} must be listed in Section 2 Master Issue Matrix.",
            )

        # 2. Section 3 Detailed Issue Specifications validation
        self.assertIn("## 3. Detailed Issue Specifications & Code Targets", self.content)
        specs_section = self.content.split("## 3. Detailed Issue Specifications & Code Targets")[1].split("## 4. Live Milestone")[0]

        for issue_num in EXPECTED_ISSUE_NUMBERS:
            self.assertIn(
                f"### Issue {issue_num}:",
                specs_section,
                f"Issue {issue_num} must have a detailed specification header in Section 3.",
            )

        # 3. Verify mandatory specification components for each issue
        issue_blocks = re.split(r"### Issue #\d+:", specs_section)[1:]
        self.assertEqual(len(issue_blocks), 15, "Must find exactly 15 issue specification blocks.")

        for idx, block in enumerate(issue_blocks):
            issue_num = EXPECTED_ISSUE_NUMBERS[idx]
            self.assertIn("- **Title**:", block, f"{issue_num} missing Title")
            self.assertIn("- **URL**:", block, f"{issue_num} missing URL")
            self.assertIn("- **Classification**:", block, f"{issue_num} missing Classification")
            self.assertIn("- **Milestone**: `v1.0.0-rc7`", block, f"{issue_num} missing Milestone v1.0.0-rc7")
            self.assertIn("#### Empirical Evidence & Grounding", block, f"{issue_num} missing Empirical Evidence")
            self.assertIn("#### Architectural Rationale & Problem Statement", block, f"{issue_num} missing Architectural Rationale")
            self.assertIn("#### Exact Code Targets in Repository", block, f"{issue_num} missing Code Targets")
            self.assertIn("#### System Architecture & Implementation Proposal", block, f"{issue_num} missing Implementation Proposal")
            self.assertIn("#### Acceptance Criteria", block, f"{issue_num} missing Acceptance Criteria")
            self.assertIn("- [ ]", block, f"{issue_num} missing checkable criteria items (- [ ])")

    def test_03_telemetry_citations_exist_in_db(self):
        """All cited session IDs and step indices must match valid records in data/telemetry.db."""
        db_path = TELEMETRY_DB_PATH
        if not db_path.is_file():
            candidates = [
                REPO_ROOT.parent.parent / "data" / "telemetry.db",
                REPO_ROOT.parent / "data" / "telemetry.db",
                Path.home() / ".gemini" / "antigravity" / "worktrees" / "d68b1207-9f6c-4c54-8751-ca53609277d4" / "data" / "telemetry.db",
            ]
            for cand in candidates:
                if cand.is_file():
                    db_path = cand
                    break
        if not db_path.is_file():
            self.skipTest("telemetry.db not found in isolated worktree")

        # Extract all session and step citations:
        # Pattern 1: Session `f2855e28-fe0d-4f60-8160-2fbe3fdf2b16`, step 242
        # Pattern 2: Session `f2855e28`, step 242
        # Pattern 3: Sessions `d93c71e7` (s40)
        citations = []

        # Regex matching "Session `([a-f0-9\-]+)`.*?step (\d+)"
        for match in re.finditer(r"Session\s*`([a-f0-9\-]{8,36})`[^\n]*?step\s*(\d+)", self.content, re.IGNORECASE):
            sess_id, step_idx = match.group(1), int(match.group(2))
            citations.append((sess_id, step_idx))

        # Regex matching "Sessions `([a-f0-9\-]+)`\s*\(s(\d+)\)"
        for match in re.finditer(r"`([a-f0-9\-]{8,36})`\s*\(s(\d+)\)", self.content, re.IGNORECASE):
            sess_id, step_idx = match.group(1), int(match.group(2))
            citations.append((sess_id, step_idx))

        # De-duplicate citations
        unique_citations = sorted(list(set(citations)))
        self.assertGreaterEqual(
            len(unique_citations),
            15,
            f"Expected at least 15 empirical citations in manifest, found {len(unique_citations)}",
        )

        # Connect to SQLite read-only
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA case_sensitive_like = ON;")
        cursor = conn.cursor()

        try:
            for sess_prefix, step_idx in unique_citations:
                cursor.execute(
                    "SELECT session_id, step_index FROM steps WHERE session_id LIKE ? AND step_index = ?",
                    (f"{sess_prefix}%", step_idx),
                )
                step_row = cursor.fetchone()

                cursor.execute(
                    "SELECT session_id, step_index FROM user_interventions WHERE session_id LIKE ? AND step_index = ?",
                    (f"{sess_prefix}%", step_idx),
                )
                intervention_row = cursor.fetchone()

                self.assertTrue(
                    step_row is not None or intervention_row is not None,
                    f"Citation Session '{sess_prefix}' at step {step_idx} not found in steps or user_interventions.",
                )
        finally:
            conn.close()

    def test_04_cited_code_targets_exist_on_disk(self):
        """All cited repository code targets in harness/, tests/, .agents/, docs/ must exist on disk."""
        specs_section = self.content.split("## 3. Detailed Issue Specifications & Code Targets")[1].split("## 4. Live Milestone")[0]

        # Extract target file paths listed under "#### Exact Code Targets in Repository"
        target_lines = []
        in_code_targets = False
        for line in specs_section.splitlines():
            if "#### Exact Code Targets in Repository" in line:
                in_code_targets = True
                continue
            elif line.startswith("#### ") or line.startswith("### "):
                in_code_targets = False
                continue

            if in_code_targets and line.strip():
                target_lines.append(line.strip())

        extracted_paths = set()
        for line in target_lines:
            m = re.match(r"^\d+\.\s*`((?:harness|tests|\.agents|docs)/[a-zA-Z0-9_\-/\.]+\.[a-zA-Z0-9]+)", line.strip())
            if m:
                extracted_paths.add(m.group(1))

        self.assertGreaterEqual(
            len(extracted_paths),
            20,
            f"Expected at least 20 unique code target paths, found {len(extracted_paths)}",
        )

        missing_paths = []
        for rel_path in sorted(extracted_paths):
            full_path = REPO_ROOT / rel_path
            if not full_path.exists():
                missing_paths.append(rel_path)

        self.assertEqual(
            missing_paths,
            [],
            f"The following cited code targets do not exist on disk: {missing_paths}",
        )

    def test_05_strict_scope_boundary(self):
        """Manifest must strictly respect the scope boundary: zero multi-node mesh networking, Tailscale, or WireGuard."""
        lower_content = self.content.lower()

        # Assert no multi-node networking or VPN concepts
        forbidden_terms = ["tailscale", "wireguard", "cross-device cluster"]
        for term in forbidden_terms:
            self.assertNotIn(
                term,
                lower_content,
                f"Forbidden scope term '{term}' found in manifest. Multi-node mesh is out of scope.",
            )

        # Assert presence of explicit scope boundary declarations
        self.assertIn("Scope Boundary     : Strictly single root agent -> delegate subagents within a local workspace", self.content)
        self.assertIn("CRITICAL SCOPE MANDATE", self.content)
        self.assertIn("strictly limited to the `agyis-harness` surface of a single root agent managing local delegate subagents", self.content)


if __name__ == "__main__":
    unittest.main()
