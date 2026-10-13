---
name: psl-harmonize
description: >-
  Inspect, diagnose, and harmonize legacy Antigravity agent configurations.
  Use when migrating legacy .agent/ directories to .agents/, migrating legacy
  workflows to modular skills, or aligning AGENTS.md rules with PSL harness blocks.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# PSL Workspace Harmonization Protocol (`psl-harmonize`)

This skill provides deterministic instructions for inspecting, diagnosing, and harmonizing legacy Google Antigravity configurations across internal repositories (`Jasper`, `purrmission`, `sunshine-physio`, `knot-mesh`, etc.) into the unified PSL 3-layer architecture.

---

## 1. When to Use

Trigger this skill whenever:
- A project contains a legacy `.agent/` directory (singular) instead of modern `.agents/` (plural).
- A project has deprecated `.agent/workflows/` or loose workflow files that should become modular skills.
- Legacy configuration notices are reported during workspace initialization.
- Project rules in `AGENTS.md` need to be aligned with the tagged PSL marker while preserving domain rules.

---

## 2. Harmonization Lifecycle

### Phase 1: Inspection & Diagnosis
Run a non-destructive audit of the workspace configuration:

```bash
# Check for legacy and modern configuration directories
ls -ld .agent .agents 2>/dev/null || true

# Check for existing rule files
ls -l AGENTS.md .agents/AGENTS.md .agent/AGENTS.md 2>/dev/null || true

# Audit existing custom agents and skills
ls -la .agent/agents/ .agent/workflows/ .agents/agents/ .agents/skills/ 2>/dev/null || true
```

### Phase 2: Directory Harmonization (`.agent/` -> `.agents/`)
Antigravity and PSL harness standardize on `.agents/` for workspace-local customizations (Layer 3):

1. **Create Standard Subdirectories**:
   ```bash
   mkdir -p .agents/skills .agents/agents
   ```

2. **Migrate Custom Subagent Definitions**:
   If `.agent/agents/` exists with project-specific definitions:
   ```bash
   if [ -d ".agent/agents" ]; then
     cp -rn .agent/agents/* .agents/agents/ 2>/dev/null || true
   fi
   ```

3. **Migrate Workflows to Modular Skills**:
   If legacy workflows exist in `.agent/workflows/`:
   ```bash
   for wf in .agent/workflows/*.md; do
     [ -f "$wf" ] || continue
     skill_name=$(basename "$wf" .md)
     mkdir -p ".agents/skills/$skill_name"
     cp "$wf" ".agents/skills/$skill_name/SKILL.md"
   done
   ```

4. **Retire Legacy `.agent/` Directory**:
   Verify all custom assets have been safely copied to `.agents/`, then remove the legacy `.agent/` directory or move it to a temporary backup.

### Phase 3: Tagged Rules Harmonization (`AGENTS.md`)
PSL manages empirical invariants via a tagged block, ensuring project-specific domain rules (such as custom PR delays or branch policies) remain untouched:

```markdown
<!-- Added by PSL-HARNESS -->
... PSL Universal Invariants ...
<!-- End PSL-HARNESS -->
```

1. **Preserve Existing Domain Rules**:
   Inspect `AGENTS.md`. If project-specific instructions exist, keep them intact outside the markers.
2. **Synchronize via CLI**:
   Run `psl skills --sync` or `psl install --workspace` to update the tagged block idempotently.

### Phase 4: Verification & Coexistence Audit
Verify that the workspace is fully harmonized:

```bash
# 1. Audit active skills and specialist agents
psl skills
psl agents

# 2. Check workspace runtime status
psl status

# 3. Verify clean git status (zero runtime debris)
git status -s
```
