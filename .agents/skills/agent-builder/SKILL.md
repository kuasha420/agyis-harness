---
name: agent-builder
description: >-
  Interactive creation, scaffolding, and validation of custom codebase-aware and workspace-aware agents.
  Use when designing new specialist subagents, scoping tool permissions, preventing the platform hanging bug,
  or configuring project-level and global-level agents in Google Antigravity.
---

# Agent Builder & Custom Specialist Scaffolding Protocol

This skill codifies the protocol for authoring, scaffolding, and validating custom codebase-aware and workspace-aware specialist subagents within the PSL Subagent Ladder architecture.

---

## 1. Triggers & When to Use
Invoke this protocol when:
1. Creating a new specialist subagent persona for a project or global workspace.
2. Scoping toolgroup permissions for a role (e.g. read-only auditor, verifier, swarm lead, executioner).
3. Hardening agent markdown definitions against the **Antigravity Platform Hanging Bug** (where declaring unsupported or non-existent tools causes subagent sessions to hang indefinitely).
4. Synchronizing agent catalogs between `harness/agents/` and `.agents/agents/`.

---

## 2. Automated Workspace Scanning Runbook
When designing an agent tailored to a specific codebase, leverage automated workspace inspection to ground the agent in deterministic project facts:

```bash
# Automated inspection via Python API
python3 -c "from harness.subagents import inspect_workspace_context; import json; print(json.dumps(inspect_workspace_context(), indent=2))"
```

The scanner probes the following project files:
- `pyproject.toml` / `package.json` / `Cargo.toml`: Project name, primary languages, dependency toolchains, test runners, and executable scripts.
- `AGENTS.md`: Active behavioral rules, developer constraints, and architectural invariants.
- `matrix.json`: Toolchain matrix versions, platform configurations, and environment variables.
- `roadmap.md`: Active development horizons, project milestones, and delivery priorities.

---

## 3. Verified Capability Bundles

To prevent session freezes and maintain strict toolgroup scoping, custom agents must use pre-verified capability bundles from `ANTIGRAVITY_PLATFORM_TOOLS`:

| Bundle | Allowed Tools | Permissions | Intended Roles |
| :--- | :--- | :--- | :--- |
| `read_only` | `view_file`, `list_dir`, `grep_search`, `find_by_name`, `read_url_content`, `search_web` | `read: true`, `write: false`, `execute: false`, `subagents: false` | Hammer, Code Reviewer, Security Inspector |
| `verifier` | `read_only` + `run_command`, `manage_task` | `read: true`, `write: false`, `execute: true`, `subagents: false` | QA Verifier, Benchmark Auditor, Linter |
| `builder` | `verifier` + `write_to_file`, `replace_file_content` | `read: true`, `write: true`, `execute: true`, `subagents: false` | Executioner, Implementer, Refactorer |
| `orchestrator` | `read_only` + `invoke_subagent`, `send_message`, `manage_subagents`, `manage_task` | `read: true`, `write: false`, `execute: false`, `subagents: true` | Swarm Coordinator, Milestone Lead |
| `full` | All 20 platform tools (`ANTIGRAVITY_PLATFORM_TOOLS`) | `read: true`, `write: true`, `execute: true`, `subagents: true`, `mcp: true`, `enable_write_tools: true` | Main Agent (`main` archetype), Lead Architect |

> [!CAUTION]
> **Platform Hanging Bug**: Never declare tools outside `ANTIGRAVITY_PLATFORM_TOOLS` (such as `edit_file` or speculative MCP tool names) in frontmatter `tools:` or `allowed_tools:`. Doing so causes the Antigravity subagent dispatcher to hang without returning an error.

---

## 4. CLI Creation & Validation Gate

### Scaffold a New Agent
```bash
# Interactive creation
python3 -m harness.cli agents create <agent_name>

# Create lead architect / main agent with full capability bundle
python3 -m harness.cli agents create psl_main --archetype main --bundle full --scope project

# Non-interactive / scripted creation with bundle and archetype
python3 -m harness.cli agents create security_auditor --archetype auditor --bundle verifier --scope project

# Global agent creation (written to ~/.gemini/antigravity/agents/)
python3 -m harness.cli agents create global_planner --archetype planner --bundle read_only --scope global
```

### Validate Agent Definition
Every generated or manually edited agent specification must pass the automated validation gate:
```bash
# Validate by name or relative path
python3 -m harness.cli agents validate security_auditor
python3 -m harness.cli agents validate .agents/agents/security_auditor.md
```

The validation gate verifies:
1. **Frontmatter Integrity**: Required keys (`name`, `archetype`, `role`, `description`, `permissions`).
2. **Customization Inheritance**: Validates `inheritCustomizations: true` boolean frontmatter property to ensure workspace-level instructions and developer rules (`AGENTS.md`) propagate down.
3. **Tool Existence**: Asserts all declared tools exist in `ANTIGRAVITY_PLATFORM_TOOLS`.
4. **Contradiction Guard**: Rejects contradictory configs (e.g. declaring `write_to_file` when `permissions.write: false`).
5. **Prompt Invariants**: Ensures `Zero-Exploration Invariant` is declared and explicitly references `list_dir` and `find_by_name`.

### Synchronize Agent Definitions
```bash
python3 -m harness.cli agents --sync
```

---

## 5. UI Activation & Platform Behaviors

1. **Native `@<subagent>` Prompt Syntax (Antigravity v1.2.9+)**:
   - Subagents can be invoked directly inside any prompt turn using native `@<agent_name>` inline syntax (e.g. `@harness_builder`, `@harness_reviewer`, `@psl_main`).
   - Seamlessly hand off context across stages in the Subagent Ladder protocol without manual session reconstruction.
2. **Tool Prerequisite Pruning in `/` Menu (Antigravity v1.2.16+)**:
   - In Antigravity v1.2.16+, when invoking commands or subagents from the `/` menu, tools lacking declared prerequisite capabilities or masked by restrictive permissions are pruned from the execution environment.
   - Using the `full` capability bundle and `inheritCustomizations: true` ensures all platform tools, MCP capabilities, and custom rule prompts remain accessible without unexpected tool pruning.
3. **Project Scope (`.agents/agents/<name>.md`)**:
   - Files in `.agents/agents/` are automatically discovered by Antigravity for the active workspace.
   - Invoke in chat by typing `@<agent_name>` or selecting the agent from the subagent dispatch dropdown.
4. **Global Scope (`~/.gemini/antigravity/agents/<name>.md`)**:
   - Files in `~/.gemini/antigravity/agents/` are globally available across all repositories and workspaces.
5. **PreToolUse Interception**:
   - All subagents are governed by the `anti_drift_hook.py` PreToolUse hook. Any unauthorized file mutations by read-only archetypes (`auditor`, `planner`, `coordinator`, `hammer`) are deterministically blocked at runtime.
