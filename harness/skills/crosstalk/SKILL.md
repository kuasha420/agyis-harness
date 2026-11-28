---
name: crosstalk
description: >-
  Native cross-conversation, cross-project, and horizontal context succession protocol (/crosstalk).
  Use when continuing work in a fresh thread, bridging tasks or insights across repositories,
  discovering or inspecting Desktop and CLI conversations, steering peer threads with sanitized
  batons, or emitting tiered Desktop/CLI UX widgets and deep-link pills.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Native Cross-Conversation & Horizontal Succession Protocol (`/crosstalk`)

`/crosstalk` (`agyis crosstalk`) bridges top-level Antigravity conversations across **Desktop (`antigravity`)**, **CLI (`antigravity-cli`)**, and **registered workspace projects** (`<config_dir>/projects/*.json`). It replaces ad-hoc context restarts and fragile `TypeName="self"` recursion with sanitized baton handoffs, read-only SQLite + live RPC discovery, and surface-adaptive UX.

## Table of Contents
1. [Intent Inference and Trigger Modes](#1-intent-inference-and-trigger-modes)
2. [Live Discovery First and Inbound Baton Check](#2-live-discovery-first-and-inbound-baton-check)
3. [Tiered Visual UX and Surface Adaptation](#3-tiered-visual-ux-and-surface-adaptation)
4. [Dispatch Priority and D6 Safety Guards](#4-dispatch-priority-and-d6-safety-guards)
5. [Zero-Polling and 4-Way Native Routing Table](#5-zero-polling-and-4-way-native-routing-table)
6. [CLI Palette and Protocol References](#6-cli-palette-and-protocol-references)

---

## 1. Intent Inference and Trigger Modes

Classify every `/crosstalk` request into one of five primary operational intents before invoking tools:

| Intent | Trigger Signal | Canonical Command |
| :--- | :--- | :--- |
| **Horizontal Context Succession** | Current thread hits `70%–90%` runway (`512k`/`1M`), `80+` steps, or operator asks to continue cleanly in a fresh thread | `agyis crosstalk handoff --new --title "..." --summary "..." --task "..."` |
| **Cross-Project Bridge** | Moving specs, bug reports, API contracts, or tasks into another registered repo (including `Private -> OSS`) | `agyis crosstalk handoff --to <repo> --summary "..." --task "..."` |
| **Thread Discovery & Inspection** | Locating prior Desktop or CLI sessions, checking decisions, or hydrating truncated steps | `agyis crosstalk list` / `search "<q>"` / `inspect <cid> --steps 20` |
| **Mid-Flight Steering** | Sending an incremental update or unblock signal to an existing active thread | `agyis crosstalk send <cid> "<message>"` |
| **Thread Archive Hygiene** | Decluttering finished crosstalk threads non-destructively (soft-archive only) | `agyis crosstalk archive <cid>` (`--unarchive` to restore) |

---

## 2. Live Discovery First and Inbound Baton Check

Always ground `/crosstalk` decisions in live disk and RPC state before rendering links or creating threads:

1. **Check Inbound Baton & Surface Context First**:
   ```bash
   agyis crosstalk status --json
   ```
   - Inspects `.agents/artifacts/crosstalk/inbound_<cid>.json` (or `inbound_latest.json`), active hop count (`hop/max_hops`), detected runtime surface (`desktop` vs `cli`), and recent threads.
   - On new target conversations, `SessionStart` (`pre_invocation_hook.py`) automatically consumes the unconsumed inbound baton once and injects a `[AGYIS CROSSTALK SESSION BOOT]` banner + role pin (`role_hint`).
2. **Discover Across Desktop + CLI + Live RPC**:
   ```bash
   agyis crosstalk list --surface all --limit 15 --json
   agyis crosstalk search "auth contract" --project purrmission --json
   agyis crosstalk inspect <conversation_id> --steps 20 --json
   ```
   - Queries `conversation_summaries.db` read-only (`?mode=ro` + `PRAGMA query_only = ON`, `conversations_fts` FTS5, `conversation_parents`) across both `antigravity` and `antigravity-cli`, merged with `ConversationService.ListConversations`.
   - `inspect` reads `transcript.jsonl` tail and selectively hydrates ONLY `truncated_fields` rows from `transcript_full.jsonl`.
   - **Sandbox Awareness**: If loopback HTTP returns `sandbox_blocked` (HTTP 403 / `Port ... not allowed for HTTP`), never loop-retry RPC; fall back cleanly to local SQLite discovery and `agy --conversation <id>` hints.

---

## 3. Tiered Visual UX and Surface Adaptation

Crosstalk adapts its UI footprint to the complexity, ambiguity, and visibility risk of each operation (`D4` UX discipline):

### Tier 1: Unambiguous / Same-Project Read-Only
- When a single target thread is unambiguous and read-only within the same workspace/visibility tier, emit a clickable deep-link pill inline via `harness.ux.conversation_pill` without widget noise:
  `[Thread Title](conversation://<id>)`
- For plugin/sidecar jumps when relevant, use validated `customization://<install-dir>` or `sidecar://<id>/<path>` pills.

### Tier 2: Multi-Candidate, Fork/Handoff, Cross-Project, or `Private -> OSS` Boundary
When crossing projects, crossing visibility boundaries (`Private -> OSS`), starting a successor handoff, or resolving multiple candidate threads:
1. **Emit Compact Monochrome Widget (`<agent-embed>`) + Clickable Pills**:
   Run `agyis crosstalk widget` inside Desktop App sessions to render a flush, host-tokenized (`var(--foreground)`, `var(--card-border)`, `var(--primary)`, `<= 450px` inline height) widget HTML and embed it cleanly:
   ```bash
   agyis crosstalk widget --kind preflight --artifact-dir <artifactDir> --write --title "..." --from-project <src> --to-project <dst>
   ```
   Use `--kind constellation` for multi-thread status overviews (outcomes ordered `blocked > active > idle > done`, with strict ref citation discipline) or `--kind preflight` before outbound handoffs.
2. **Visual Preflight Shield & `ask_question` Confirmation**:
   - Before executing `handoff --send` across projects or across `Private -> OSS`, inspect the dry-run preflight output (`secrets_redacted`, `paths_anonymized`, `blocked_categories`, `visibility_crossing`, `hop/max_hops`).
   - Use `ask_question` to disambiguate multiple candidate conversations or obtain explicit operator confirmation on the Visual Preflight Shield before passing `--send`.

### Terminal / CLI Auto-Fallback
- On headless / `antigravity-cli` surfaces (`is_desktop_surface() == False`), `agyis crosstalk` and `harness.ux.render_cli_fallback` automatically suppress `<agent-embed>` HTML and `conversation://` markdown noise, rendering crisp plain-Unicode tables + `agy --conversation <id>` commands.

---

## 4. Dispatch Priority and D6 Safety Guards

### Transport Priority Ladder
- **`handoff`** (`agyis crosstalk handoff`):
  1. Dry-run preflight runs by default unless `--send` is explicitly supplied.
  2. Resolves target project (`<config_dir>/projects/*.json`; use `--ensure-project` when registering an unregistered repo).
  3. Validates D6 guards and sanitizes payload (`strict=True` forced automatically on `--source-visibility private --target-visibility oss`).
  4. On `--send`, calls `product.v1.ConversationService/CreateConversation` with `[CROSSTALK-V1]` envelope + `crosstalk` tags, links `conversationGroupId` via `UpdateConversation` if set, and writes `.agents/artifacts/crosstalk/{inbound,outbound}_<cid>.json` with `.git/info/exclude` hygiene.
- **`send`** (`agyis crosstalk send`):
  1. Enforces hop/self/cycle/redaction guards first.
  2. Dispatches via `agentapi` (priority 1 — inserting the `"agentapi"` subcommand automatically when `ANTIGRAVITY_AGENTAPI_EXE` points to `language_server`: `language_server agentapi send-message`, injecting `CORTEX_STEP_TYPE_SYSTEM_MESSAGE` with `renderInfo.title`), falling back to `exa.language_server_pb.LanguageServerService/SendUserCascadeMessage` (priority 2 — injecting `CORTEX_STEP_TYPE_USER_INPUT` to wake the cascade with an explicit user turn) when LS credentials are available.

### Mandatory D6 Safety Guards
- **Hop Bounds**: `MAX_CROSSTALK_HOPS = 2` default budget (`HARD_MAX_CROSSTALK_HOPS = 3`). Never exceed `max_hops`; reject `hop > max_hops` cleanly.
- **Self-Target & Cycle Rejection**: Block `target_cid == caller_cid`, repeated `cid` in `lineage`, and cross-project bounce-back cycles (`project_lineage`).
- **Secret, CSRF & `.dirtyroom/` Quarantine**: Scrubs API keys, Bearer/Authorization headers, `ANTIGRAVITY_CSRF_TOKEN`/`CODEIUM_CSRF_TOKEN`, home/workspace paths, `.env`, and `*.pem`/`*.key` blocks. Any reference to `.dirtyroom/` (`PSL-RE-001`) is **hard-blocked** (`dirtyroom_leakage`).
- **Non-Destructive Archive Only**: `agyis crosstalk archive <cid>` uses soft `UpdateConversation(archived=true|false)`. **NEVER** expose or invoke `DeleteConversation` (`delete` is strictly excluded from `agyis crosstalk`).

---

## 5. Zero-Polling and 4-Way Native Routing Table

- **Zero-Polling Invariant (`PSL-INV-004`)**: Never loop-poll `agyis crosstalk list`, `inspect`, `status`, or `ListConversations` waiting for a peer thread to finish. Emit one concise briefing with clickable `conversation://` pills or `agy --conversation <id>` hints and stop cleanly or rely on `SessionStart` baton handback.

| Primitive | Scope & Workspace | Topology & State Transfer | Best Used For |
| :--- | :--- | :--- | :--- |
| **`invoke_subagent`** | Vertical child inside current session | Registered specialist (`agyis_*`, `Workspace="share"` or `"inherit"`); returns via `send_message` | Single bounded specialist task (RCA, plan, laser edit, diff review, QA) |
| **`/swarm` (`swarm` / `run_workflow`)** | Multi-worker DAG inside current campaign | Blackboard files + `post_message` / `swarm_wait` + `share`/`branch` worktrees | Parallel workstreams, tournament boosts (`/boost`), coordinated multi-file builds |
| **`conversations` (Native)** | Platform read-only thread tool | Direct native Antigravity lookup when available inside Desktop host | Quick native read of a known thread inside Desktop UI without CLI hop |
| **`/crosstalk` (`agyis crosstalk`)** | Top-level peer threads across Desktop, CLI, and **multiple repos** | `[CROSSTALK-V1]` envelope + sanitized `.agents/artifacts/crosstalk/` baton + `SessionStart` boot | Cross-project bridges, horizontal context succession (`--new`), Desktop/CLI cross-surface discovery & steering |

---

## 6. CLI Palette and Protocol References

```bash
# Discover & inspect across Desktop + CLI
agyis crosstalk status --json
agyis crosstalk list --project <slug> --surface all --limit 15
agyis crosstalk search "<query>" --include-archived --json
agyis crosstalk inspect <conversation_id> --steps 20

# Render Generative UI widget or terminal fallback
agyis crosstalk widget --kind preflight --title "Handoff" --from-project repo-a --to-project repo-b
agyis crosstalk widget --kind constellation --artifact-dir <artifactDir> --write

# Preflight -> confirm -> dispatch handoff / succession
agyis crosstalk handoff --new --title "Continue milestone" --summary "..." --task "..." --dry-run --json
agyis crosstalk handoff --to <repo> --source-visibility private --target-visibility oss --summary "..." --task "..." --send

# Mid-flight steer & soft archive hygiene
agyis crosstalk send <conversation_id> "Updated schema contract in PR #42" --dry-run
agyis crosstalk archive <conversation_id>
```

For wire schemas, `[CROSSTALK-V1]` baton fields, ConnectRPC contracts, `SessionStart` injection payloads, and widget view-model structures, see [Protocol, Schemas, and Transports](references/protocol-and-transports.md).
