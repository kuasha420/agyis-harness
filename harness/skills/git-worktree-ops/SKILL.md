---
name: git-worktree-ops
description: >-
  Standardized multi-branch Git worktree management runbook for isolated feature development,
  safe worktree creation, branch cleanup, orphan worktree pruning, and stash hygiene without index or lock corruption.
  Use when delegating tasks to isolated branches, recovering from locked index files, or managing parallel development trees.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Agyis Git Worktree Operations: Isolated Trees & Index Hygiene Runbook

This skill establishes empirical runbooks for Git worktree isolation, multi-branch task delegation, stale worktree pruning, and index lock recovery within Google Antigravity environments.

---

## 1. Git Worktree Invariants

### Invariant 1: No Concurrent Branch Checkout
Git forbids checking out the same branch in multiple worktrees at once. Attempting to do so fails with:
`fatal: '<branch>' is already checked out at '<path>'`.
Always create a new dedicated branch or use detached HEAD for read-only inspection.

### Invariant 2: Never Use Raw `rm -rf` on Active Worktrees
Deleting a worktree folder with `rm -rf` leaves Git's administrative metadata intact in `.git/worktrees/<name>/`. This causes subsequent checkouts or branch deletions to fail with orphaned metadata errors. Always remove with `git worktree remove` or immediately follow manual directory cleanup with `git worktree prune`.

---

## 2. Worktree Lifecycle & Creation Patterns

### 2.1 Inspect Active Worktrees
List all attached worktrees and their current checked-out branches/commits:
```bash
# Human-readable worktree list
git worktree list

# Script/machine-readable porcelain format
git worktree list --porcelain
```

### 2.2 Create Isolated Worktree with New Branch
Safely branch off `HEAD` (or a base branch) into an isolated directory:
```bash
# Create new branch 'feat/isolated-task' and attach to '../worktrees/isolated-task'
git worktree add -b feat/isolated-task ../worktrees/isolated-task HEAD
```

### 2.3 Attach Worktree to Existing Tracking Branch
```bash
# Attach existing remote tracking branch into a clean worktree
git worktree add ../worktrees/fix-branch fix-branch
```

### 2.4 Detached HEAD Worktree for Read-Only Inspection
When an agent needs to inspect, test, or bisect a commit without branching:
```bash
git worktree add --detach ../worktrees/inspect-commit <commit-hash>
```

---

## 3. Worktree Removal & Orphan Pruning

### 3.1 Clean Worktree Removal
Safely delete an unneeded worktree and its working directory:
```bash
# Clean removal (refuses if worktree contains uncommitted modifications)
git worktree remove ../worktrees/isolated-task

# Force removal (discards untracked and modified files if abandon is intended)
git worktree remove --force ../worktrees/isolated-task
```

### 3.2 Prune Stale & Orphaned Worktree Metadata
When worktree directories were moved or deleted by external tools:
```bash
# Prune orphaned worktree entries from .git/worktrees
git worktree prune -v
```

### 3.3 Lock and Unlock Persistent Worktrees
Prevent automated maintenance scripts from pruning critical long-lived worktrees:
```bash
# Lock worktree with explanatory reason
git worktree lock --reason "Active subagent testing run" ../worktrees/isolated-task

# Unlock when ready for decommissioning
git worktree unlock ../worktrees/isolated-task
```

---

## 4. Git Index Locks & Stash Hygiene

### 4.1 Index Lock Recovery (`index.lock`)
When an interrupted or crashed git command leaves `.git/index.lock` behind, preventing subsequent git operations (`fatal: Unable to create '.git/index.lock': File exists`):
```bash
# 1. Verify no git processes are actively running on the machine
if ! pgrep -f "git " >/dev/null 2>&1; then
    echo "No active git processes. Removing stale index.lock..."
    rm -f .git/index.lock
else
    echo "Warning: git processes still running. Do not remove index.lock yet."
fi
```

### 4.2 Safe Stash Management Across Worktrees
Stashing is scoped to individual worktree working trees:
```bash
# Push dirty changes with descriptive label and include untracked files
git stash push -u -m "wip: subagent worktree checkpoint"

# Inspect stash list
git stash list

# Pop top stash and verify clean index
git stash pop
```

### 4.3 Clean Merged Branches After Worktree Decommissioning
Safely remove branches that have been merged upstream:
```bash
# List local branches merged into current HEAD
git branch --merged

# Delete merged branch safely
git branch -d feat/isolated-task
```
