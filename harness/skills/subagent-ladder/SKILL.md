---
name: subagent-ladder
description: >-
  Backwards-compatible alias for 'subagent-router'. Dynamically routes specialized agent pipelines
  (Investigator -> Planner -> Builder -> Reviewer -> Custodian -> Auditor) across 12 canonical workflows.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Subagent Ladder (Legacy Alias for Subagent Router) 🪜🤖

> [!IMPORTANT]
> **This skill is a backwards-compatible alias that imports [**`subagent-router`**](../subagent-router/SKILL.md).**  
> All active development, the 12 Canonical Routing Workflows, the 4 execution modes (Ladder, Fan-out, Teamwork, Boost), and flight director integration live in [**`subagent-router`**](../subagent-router/SKILL.md).

## Imported Protocols & Invariants
This skill imports the complete dynamic routing specification from [**`subagent-router`**](../subagent-router/SKILL.md):
- **6-Stage Pipeline Lifecycle**: Investigation $\rightarrow$ Planning $\rightarrow$ Execution $\rightarrow$ Review $\rightarrow$ Custody $\rightarrow$ Audit. See [6-Stage Pipeline Lifecycle](../subagent-router/SKILL.md#3-the-6-stage-pipeline-lifecycle).
- **Anti-Bypass Invariant**: Under no circumstances may an Executioner remedy bypass Hammer review or Custodian commit gate.
- **Multi-Node Swarm PR Ingestion Protocol**: Discovers and ingests remote PRs using `gh pr list`.
- **12 Canonical Routing Workflows**: See [12-Workflow Decision Table](../subagent-router/SKILL.md#2-autonomous-routing-architecture--12-workflow-decision-table).

To execute tasks, invoke [**`subagent-router`**](../subagent-router/SKILL.md) directly or run `agyis router <workflow>` (or `agyis ladder <workflow>`).
