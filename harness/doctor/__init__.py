# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Agyis Doctor Package: System diagnostics, runtime integrity, and anti-synthetic test auditing.
"""

from harness.doctor.test_smells import (
    BoundaryExemptionRecord,
    SmellAuditReport,
    SmellSeverity,
    SmellType,
    TestSmell,
    TestSmellIssue,
    audit_file_smells,
    audit_workspace_test_smells,
    run_anti_synthetic_doctor,
)

__all__ = [
    "BoundaryExemptionRecord",
    "SmellAuditReport",
    "SmellSeverity",
    "SmellType",
    "TestSmell",
    "TestSmellIssue",
    "audit_file_smells",
    "audit_workspace_test_smells",
    "run_anti_synthetic_doctor",
]
