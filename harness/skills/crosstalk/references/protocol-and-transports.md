<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Crosstalk Protocol, Baton Schemas, and Transport Reference

## 1. `[CROSSTALK-V1]` Prompt Envelope

Every dispatched `handoff_conversation` prepends a deterministic `[CROSSTALK-V1]` block (`harness/delivery/crosstalk.py`):

```text
[CROSSTALK-V1] [CROSSTALK-HOP: 1/2] [CROSSTALK-ROLE: agyis_coordinator]
from_cid: <caller-conversation-uuid-or-none>
from_project: <source-project-slug>
to_project: <target-project-slug>
intent: handoff
hop: 1/2
role_hint: agyis_coordinator
group_id: <conversationGroupId-or-none>
lineage: <comma-separated-cids>
project_lineage: <comma-separated-projects>
artifacts: <comma-separated-safe-paths>
[/CROSSTALK-V1]
```

## 2. Tier-1 Baton Ledger (`crosstalk.baton.v1`)

Written atomically to `<target_ws>/.agents/artifacts/crosstalk/inbound_<new_cid>.json` and `<source_ws>/.agents/artifacts/crosstalk/outbound_<new_cid>.json` (ignored via `.git/info/exclude`):

```json
{
  "schema_version": "crosstalk.baton.v1",
  "conversation_id": "<new_cid>",
  "from_cid": "<caller_cid>",
  "from_project": "<src_project>",
  "to_project": "<target_project>",
  "to_project_id": "<project_uuid>",
  "intent": "handoff",
  "hop": 1,
  "max_hops": 2,
  "role_hint": "agyis_coordinator",
  "group_id": null,
  "title": "[handoff] target",
  "lineage": ["<caller_cid>"],
  "project_lineage": ["<src_project>", "<target_project>"],
  "artifacts": [],
  "brief_preview": "...",
  "redaction": {
    "secrets_redacted": 0,
    "paths_anonymized": 0,
    "blocked_refs": 0,
    "blocked_categories": [],
    "has_blocked_refs": false,
    "dirtyroom_detected": false,
    "strict": false
  },
  "created_at": "2026-11-28T00:00:00Z",
  "consumed": false
}
```

## 3. `SessionStart` One-Shot Handover Injection

When a target thread starts (`hookEventName == "SessionStart"`), `harness/hooks/pre_invocation_hook.py::evaluate_session_start()` inspects active workspaces for unconsumed `inbound_<cid>.json` (or fresh `inbound_latest.json` within 3600s), atomically marks `"consumed": true`, pins sticky role if `role_hint` is set, and returns `{"injectSteps": [build_system_message_step(...)]}` populating `injectSteps[0].systemMessage.metadata.user_markdown` with a baton banner alongside the compact `[AGYIS CROSSTALK SESSION BOOT]` instruction.

## 4. Connect HTTP+JSON & CLI Transports (`harness/delivery/crosstalk_db.py`, `harness/delivery/crosstalk.py`)

- **Credentials**: `ANTIGRAVITY_LS_ADDRESS` (`host:port`) + `ANTIGRAVITY_CSRF_TOKEN` (`x-antigravity-csrf-token` header, `Connect-Protocol-Version: 1`). Never echoed or serialized into outbound payloads.
- **`product.v1.ConversationService`** (lifecycle management):
  - `ListConversations` (`pageSize`, `includeArchived`, optional `projectId`, `parentConversationId`, `tags`)
  - `GetConversation` (`conversationId`)
  - `CreateConversation` (`projectId`, `title`, `model`, `tags`, `prompt`)
  - `UpdateConversation` (`conversationId`, `annotations`: `{"archived": true|false}` or `{"conversationGroupId": ...}`)
  - **`DeleteConversation` is strictly prohibited** (`D6`).
- **`agentapi` Steer Wrapper & `exa.language_server_pb.LanguageServerService` (Live-Verified D5 Distinction)**:
  - **`agentapi`** (`language_server agentapi send-message [--title=...] <cid> <message>`): `_build_agentapi_send_cmd()` automatically inserts the `"agentapi"` subcommand when `ANTIGRAVITY_AGENTAPI_EXE` points to a `language_server` binary (preserving `[exe, "send-message", ...]` for standalone `agentapi` binaries). Injects `CORTEX_STEP_TYPE_SYSTEM_MESSAGE` (`eventType: "agent_message"`, `priority: MESSAGE_PRIORITY_HIGH`, `isInterruptingStep: true`, `renderInfo.title`).
  - **`LanguageServerService/SendUserCascadeMessage`** (`cascadeId`, `items`): fallback (or explicit `transport="ls_rpc"`) steer transport. Injects `CORTEX_STEP_TYPE_USER_INPUT` and wakes the cascade immediately with an explicit user turn.
  - **`SessionStart` Hook Injection**: returns `injectSteps[0].systemMessage.metadata.user_markdown` for rich Desktop handover banners.
- **SQLite Read-Only Discovery**:
  - Opens `conversation_summaries.db` across `antigravity`, `antigravity-cli`, and `antigravity-ide` with `?mode=ro` and `PRAGMA query_only = ON`, querying `conversations_fts` FTS5 and `conversation_parents`.
  - Transcript tail reading hydrates only `truncated_fields` rows from `transcript_full.jsonl` via `step_index`.

## 5. Generative UI Widget View Model (`harness/ux/widgets.py`)

- **Modes**: `preflight` (`crosstalk_preflight.html`) and `constellation` (`crosstalk_constellation.html`).
- **Top-Level Keys**: `version`, `mode`, `goal` (`{title, line, status}`), `route` (`{from_project, from_branch, from_cid, to_project, to_branch, to_cid, visibility, hop, max_hops, generation, role_hint, intent}`), `redaction` (`{policy, visibility_crossing, tokens_scrubbed, paths_anonymized, blocked_files, warnings, passed, excerpt_preview, cli_command}`), `entities`, `threads`, `edges`, `attention`, `artifacts`, `links`.
- **Citation Discipline**: Entities or threads claiming `outcome: "done"` without non-empty `refs` are downgraded automatically to `idle` with `unverified_claim: true`.
- **HTML Embedding**: Emits `<agent-embed src="file:///.../crosstalk_<mode>.html"></agent-embed>` (switching to `[Crosstalk Constellation](file:///...)` standalone link when `standalone: true` or `>= 4` projects in constellation mode).
