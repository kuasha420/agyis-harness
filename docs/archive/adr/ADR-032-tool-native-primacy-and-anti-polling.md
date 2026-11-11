<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# ADR-032: Tool-Native Primacy and Task Log Anti-Polling Invariant

* **Status**: Accepted
* **Date**: 2026-10-10
* **Authors**: Antigravity & PSL Lead Architect
* **Scope**: `harness/hooks/anti_loop_hook.py`, `harness/skills/`, `.agents/skills/`, `harness/rules/AGENTS.md`
* **Related Issues & PRs**: Issue #32, PR #33

---

## Context & Motivation

Through empirical trace analysis of multi-turn autonomous execution across a local developer `$HOME` workspace (including sessions `d3fbdfad-63f8-4578-a39a-6e3b2cd62690` and `171165ea-f64b-4916-ba80-b11115b3e31c`, totaling over 12,446 steps), two severe operational failure modes were observed:

1. **Circumvention of Task Polling Guards**:
   Agents evaded `manage_task` anti-polling guidance by running shell commands (`cat`, `tail -n 20`, `head`, `grep`) targeting `.system_generated/tasks/task-*.log` or `.system_generated/logs/`, or using `view_file` / `grep_search` on task logs. In long-running background downloads or builds, this produced 45+ redundant tool invocations, consuming context window and thrashing the tool execution loop.

2. **Premature Cognitive Intervention**:
   When faced with network timeouts, CloudFront IP stalls, or Cloudflare HTTP 403 responses during media acquisition and format conversion, agents prematurely engaged in complex cognitive improvisation—attempting to decompile internal Python extractors, inject manual socket monkeypatches, write custom HTTP client scripts, or run multi-stage manual chunk downloads. In reality, modern native CLI tooling already provides hardened, battle-tested options (e.g., `yt-dlp --impersonate chrome -N 16` and `ffmpeg -vf vflip -c:a copy`) that solve these exact failure modes natively and in single-digit seconds without cognitive overhead.

---

## Architectural Decisions

```mermaid
flowchart TD
    subgraph Antigravity Reactive Messaging Loop
        SCHED["Background Task / Timer<br/>(manage_task, schedule)"]
        NOTIF["Reactive System Notification<br/>(Task Exited / Timer Expired)"]
    end

    subgraph Hook Layer: anti_loop_hook.py
        INTERCEPT["PreToolUse Interceptor<br/>run_command / view_file / grep_search / manage_task"]
        CHECK_MT{"manage_task<br/>Action='status'?"}
        ALLOW_ADV["Non-Blocking Allow + Advisory<br/>(Issue #41)"]
        CHECK_LOG{"Target in .system_generated/tasks/<br/>or .system_generated/logs/?"}
        WINDOW["Sliding Window & Streak Check<br/>• >= 2 prior consecutive (>= 3rd blocked)<br/>• >= 3 within 10-call window"]
        DENY["Block Invariant Violation (Exit 2)<br/>Strict Reactive Wait Invariant"]
        ALLOW["Allow Tool Execution"]
    end

    INTERCEPT --> CHECK_MT
    CHECK_MT -- Yes --> ALLOW_ADV
    CHECK_MT -- No --> CHECK_LOG
    CHECK_LOG -- Yes --> WINDOW
    CHECK_LOG -- No --> ALLOW
    WINDOW -- Violation --> DENY
    WINDOW -- Under Limit --> ALLOW
    DENY --> NOTIF
    NOTIF --> SCHED
```

### 1. The Strict Reactive Wait Invariant
- **Decision**: The Antigravity agentic runtime operates on an event-driven reactive messaging model. When a command or background task is running, the agent must **yield its turn** and wait for the system wakeup notification.
- **Enforcement**:
  - `harness/hooks/anti_loop_hook.py` inspects `run_command` command lines, `view_file` paths, and `grep_search` targets (`_is_task_log_inspection`) for references to `.system_generated/tasks/`, `.system_generated/logs/`, or `/tasks/task-` `.log` files.
  - Any attempt to inspect task/session logs $\ge 2$ prior consecutive times (`MAX_TASK_INSPECTION_CONSECUTIVE = 2`, blocking on the 3rd consecutive call) or $\ge 3$ times within a 10-call sliding window (`MAX_TASK_INSPECTION_WINDOW_FREQUENCY = 3`, `TASK_INSPECTION_WINDOW = 10`) is deterministically denied with exit code 2 and `{"decision": "deny", "reason": ...}` instructing the agent to stop calling tools and await reactive wakeup.
  - Per Issue #41 remediation, direct `manage_task(Action='status')` calls return a non-blocking advisory allow (`{"decision": "allow", "reason": "Advisory: Background tasks notify reactively upon exit. Avoid polling status to conserve steps."}`) while still recording the signature in the sliding history.

### 2. The Tool-Native Primacy Invariant
- **Decision**: Agents must exhaust idiomatic native tool flags and system commands before writing bespoke scripts, reverse-engineering libraries, or monkeypatching network layers.
- **Rule Definition**: Codified in `harness/rules/AGENTS.md` and `.agents/rules/AGENTS.md`:
  - When acquiring streams or handling restricted downloads: Always test native impersonation (`--impersonate chrome`) and multi-threading (`-N 16`) before attempting custom scrapers.
  - When manipulating video/audio: Always use native hardware-accelerated or losslessly remuxed `ffmpeg` (`-c:a copy`, native filters) rather than decoding and re-encoding with custom Python libraries.
  - When managing system services, storage, audio, or displays: Always invoke established OS user-space tools (`wpctl`, `kscreen-doctor`, `du -xhd 1`, `paccache`) rather than destructive system calls or ad-hoc process killing (`kill -9`).

### 3. Modular Workstation and Operations Skill Taxonomy
To anchor the Tool-Native Primacy Invariant in discoverable, repeatable protocols, 5 modular skills were codified and mirrored symmetrically across `harness/skills/` and `.agents/skills/`:

| Skill | Category | Native Tools & Protocols | Invariants & Guardrails |
| :--- | :--- | :--- | :--- |
| **`media-ops`** | Streaming & Video | `yt-dlp` (`--impersonate chrome`, `-N 16`, `--cookies-from-browser`), `ffmpeg` (`vflip`, `-c:a copy`), `ffprobe` | Exhaust native flags before cognitive scripting; preserve lossless audio streams. |
| **`storage-ops`** | Disk & Cache Hygiene | `du -xhd 1`, `uv cache clean`, `pnpm store prune`, `paccache -r -k 2`, `journalctl --vacuum-size=200M`, `docker system prune` | Bounded-depth exploration only; never run unbound `find` or `rm -rf` without dry-run confirmation; verify `ntfs3` mount options. |
| **`audio-ops`** | Audio Routing | PipeWire / WirePlumber (`wpctl status`, `wpctl inspect`, `wpctl set-default`), `bluetoothctl`, `loudnorm` filter | Strictly user-space routing via `wpctl`; never delete system configurations or kill core audio daemons. |
| **`display-ops`** | Wayland & Portals | `kscreen-doctor -o`, `systemctl --user restart xdg-desktop-portal`, Electron `--enable-features=UseOzonePlatform --ozone-platform=wayland`, Sunshine KMS capabilities | Never `killall -9` portal processes; probe modes before mutation; verify KMS DRM capture permissions. |
| **`sec-forensics`** | Security & Triage | `docker run --rm -v /:/host:ro`, `gcloud iam service-accounts keys delete`, `harness.cli remote script`, Typst headless PDF | Enforce strictly read-only filesystem mounts (`:ro`); immediate credential revocation; non-interactive remote script streaming. |

---

## Verification & Metrics

- **Unit Test Coverage**:
  - `tests/test_anti_loop.py`: Validates streak/window violations for shell/file task log inspection (`.system_generated/tasks/`, `.system_generated/logs/`) and Issue #41 non-blocking allow + advisory for `manage_task(Action='status')`.
  - `tests/test_skills.py`: Validates contract schemas, discoverability, command listings, and frontmatter across the modular ops skill catalog.
  - `test_agents_rules_mirror_in_sync`: Enforces 100% bitwise parity between `harness/rules/AGENTS.md` and `.agents/rules/AGENTS.md`.
- **Benchmark Performance**: All 377 initial baseline test cases execute in **1.57 seconds** (maintaining the PSL sub-2.0s execution invariant).
- **Telemetry Verification**: Verified central hub synchronization (`agyis sync --push` and `agyis sync --pull`) against `<central-telemetry-hub-url>`, confirming anti-echo filtering across multi-developer environments.
