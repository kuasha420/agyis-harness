---
name: psl-harmonize
description: >-
  Inspect, diagnose, and harmonize legacy Antigravity agent configurations.
  Use when migrating legacy .agent/ directories to .agents/, migrating legacy
  workflows to modular skills, or aligning AGENTS.md rules with Agyis harness blocks.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Workspace Harmonization Protocol (`psl-harmonize`)

This skill provides deterministic instructions for inspecting, diagnosing, and harmonizing legacy Google Antigravity configurations across internal and external repositories (`Jasper`, `purrmission`, `sunshine-physio`, `knot-mesh`, etc.) into the unified Agyis 3-tier architecture.

---

## 1. When to Use

Trigger this skill whenever:
- A project contains a legacy `.agent/` directory (singular) instead of modern `.agents/` (plural).
- A project has deprecated `.agent/workflows/` or loose workflow files that should become modular skills.
- Legacy configuration notices are reported during workspace initialization.
- Project rules in `AGENTS.md` need to be aligned with the tagged Agyis marker while preserving domain rules.

---

## 2. Harmonization Lifecycle

### Phase 1: Inspection & Diagnosis
Run a non-destructive audit of the workspace configuration using the native Agyis CLI:

```bash
# Audit workspace configuration status
agyis status

# Test harmonization in dry-run mode
agyis harmonize [path] --prune-legacy --backup --dry-run
```

### Phase 2: Automated Harmonization & Deterministic Pruning
Antigravity and Agyis harness standardize on `.agents/` for workspace-local customizations (Layer 3). Rather than executing manual shell copy loops, use the unified CLI command:

```bash
agyis harmonize [path] --prune-legacy --backup
```

**Automated Guarantees (ADR-031)**:
1. **Asset Migration**: Custom agents and legacy workflows are migrated safely into `.agents/agents/` and `.agents/skills/<name>/SKILL.md`.
2. **Pre-Pruning Backup**: Legacy contents are archived to `.agents/archive/agent-backup-<timestamp>.tar.gz`.
3. **Deterministic 2-Step Pruning**:
   - Executes `git rm -rf .agent` for git-tracked files.
   - Filesystem sweep cleans untracked debris via `shutil.rmtree()`.
   - Invariant assertion confirms `.agent` directory no longer exists on disk.
4. **Git Ignore Automation**: Ensures `.agents/archive/` is automatically ignored in git.

### Phase 3: Tagged Rules Harmonization (`AGENTS.md`)
Agyis manages empirical invariants via a tagged block, ensuring project-specific domain rules (such as custom PR delays or branch policies) remain untouched:

```markdown
<!-- Added by AGYIS-HARNESS -->
... Agyis Universal Invariants ...
<!-- End AGYIS-HARNESS -->
```

1. **Preserve Existing Domain Rules**:
   Inspect `AGENTS.md`. If project-specific instructions exist, keep them intact outside the markers.
2. **Synchronize via CLI**:
   Run `agyis skills --sync` or `agyis install --workspace` to update the tagged block idempotently.

### Phase 4: Verification & Coexistence Audit
Verify that the workspace is fully harmonized:

```bash
# 1. Audit active skills and specialist agents
agyis skills
agyis agents

# 2. Check workspace runtime status
agyis status

# 3. Verify clean git status (zero runtime debris)
git status -s
```
