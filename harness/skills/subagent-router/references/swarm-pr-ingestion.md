<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Multi-Node Swarm PR Ingestion Protocol

When coordinating distributed campaigns across parallel feature worktrees, multi-agent branches, or remote contributor PRs, follow this protocol to discover, isolate, audit, and merge branch deliverables:

## 1. Distributed PR & Branch Discovery
Subagents or external contributors push branches or open Pull Requests asynchronously. The Router coordinator discovers and ingests remote PRs using GitHub CLI (`gh`):
```bash
# Ingest open PRs across fleet
gh pr list --state open --json number,title,headRefName,author,updatedAt

# Inspect specific PR diff
gh pr diff <pr_number>
```

## 2. Swarm Ingestion Lifecycle
1. **Branch Fetch & Isolation**: Coordinator fetches feature / subagent worktrees into dedicated tracking branches (`git fetch origin pull/<id>/head:pr-<id>`).
2. **Phase Partitioning**: Coordinator maps ingested PR branches to Router milestones in `implementation_plan.md`.
3. **Router Verification Sweep**:
   - `agyis_builder`: Integrates or rebases branch changes cleanly against upstream HEAD.
   - `agyis_reviewer`: Audits multi-agent diffs against PSL invariants (The Hammer).
   - `agyis_custodian`: Re-verifies clean staging, enforces AC5, and executes DRY deduplication check across merged modules.
   - `agyis_auditor`: Executes local hermetic tests (`agyis test`).
4. **Automated Review Approval**: On Auditor PASS, Coordinator approves or merges the PR via `gh pr merge --squash` or `gh pr review --approve`.
