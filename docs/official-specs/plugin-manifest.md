<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Official Plugin Specification & Manifest Architecture

## 1. Directory Structure

An official Antigravity plugin packages skills, rules, lifecycle hooks, and MCP servers into a distributable unit:

```text
<plugin-root>/
├── plugin.json       # Required: Manifest marker
├── mcp_config.json   # Optional: Exposes stdio MCP servers
├── hooks.json        # Optional: Registers lifecycle hooks
├── rules/            # Optional: Merged into active rules (AGENTS.md)
│   └── AGENTS.md
└── skills/           # Optional: On-demand skill definitions
    └── <skill-name>/
        └── SKILL.md
```

---

## 2. Manifest Schema (`plugin.json`)

```json
{
  "name": "agyis-harness",
  "displayName": "Agyis Harness for Google Antigravity™",
  "version": "1.0.0-rc7",
  "description": "Empirical audit pipeline and reference extension harness for Google Antigravity™",
  "author": {
    "name": "Purrfect Software Limited (PSL)"
  },
  "license": "Apache-2.0",
  "keywords": [
    "antigravity",
    "harness",
    "telemetry",
    "audit",
    "gemini"
  ],
  "disabled": false
}
```

### Precedence & Loading Semantics
1. **Workspace Project Level**: Discovered hierarchically walking up from CWD to `.git` root. Highest priority.
2. **Explicit Registrations**: Listed in workspace `plugins.json`.
3. **Global Discovery**: `~/.gemini/config/plugins/`.
4. **Built-in Bundles**: Bundled in Antigravity app binaries.
