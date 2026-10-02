# PSL Harness for Google Antigravity™ (`psl-agy-harness`)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Target](https://img.shields.io/badge/Platform-Google_Antigravity-4285F4.svg)](https://antigravity.google)
[![Architecture](https://img.shields.io/badge/Architecture-Empirical_Audit_&_Official_Harness-emerald.svg)]()

> An open-source empirical audit pipeline and reference extension harness for **Google Antigravity™** by **Purrfect Software Limited (PSL)**.

---

## 🎯 North Star & PSL Motivation

Google's Gemini models (Gemini 1.5 Pro/Flash, Gemini 2.0, Gemini 3.x) demonstrate state-of-the-art long-context reasoning, tool fidelity, and price-to-performance efficiency for software engineering automation. However, developer productivity in long-horizon coding tasks is frequently constrained by harness-level friction:

1. **Context Cliffs & Output Flooding**: Unpruned tool outputs (verbose build logs, large diff dumps, recursive file trees) exhaust context budgets and dilute attention.
2. **Terminal Desyncs & TUI Runaways**: Subshells hanging on interactive prompts, ANSI escape code corruption, and runaway polling loops.
3. **Rigid Execution Loops**: Inability to proactively verify preconditions, dynamically branch subagents, or safely handle hardware-mesh topology.
4. **Lack of Empirical Feedback**: Agent rules and skills are often written based on anecdotal intuition rather than real telemetry of where and why models stumble.

### Our Strategy: Build On, Not Against, Official Interfaces
Rather than creating an isolated, competing framework, `psl-agy-harness`:
- **Audits Reality**: Ingests hundreds of local developer sessions (`~/.gemini/antigravity/brain/*/transcript.jsonl`) to construct an empirical taxonomy of real failure modes, loop states, and human operator interventions.
- **Dissects Official Surfaces**: Deeply analyzes the official `google-antigravity` Python SDK, `agy` CLI, plugin manifests, lifecycle hooks (`PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`), and MCP servers.
- **Builds the Reference Harness**: Delivers an optimized suite of hooks, rules, and skills entirely within the official Antigravity plugin and customization specification so enhancements can be directly upstreamed.

---

## 🏛️ Architecture & Workspace Layout

```text
psl-agy-harness/
├── LICENSE                          # Apache License 2.0
├── README.md                        # Project manifesto, architecture & telemetry findings
├── plugin.json                      # Official Antigravity Plugin manifest
├── pyproject.toml / package.json    # Dual Python (data/audit) & Node tooling
├── .gitignore                       # Ignored raw telemetry, SQLite DBs, and temp caches
├── docs/
│   ├── official-specs/              # Deconstructed Antigravity SDK, CLI, and hook lifecycles
│   └── taxonomy/                    # Empirical taxonomy of failure modes & intervention patterns
├── pipeline/                        # Modular telemetry mining & audit engine
│   ├── inventory_customizations.py  # Indexes active skills, rules, hooks, and MCP servers
│   ├── extract_transcripts.py       # Harvests session transcripts into structured SQLite
│   ├── classify_failures.py         # Categorizes events into empirical taxonomy buckets
│   └── summarize_interventions.py   # Aggregates human-in-the-loop escalations
├── data/                            # Structured extraction outputs (telemetry.db, inventories)
└── harness/                         # The reference harness components
    ├── hooks/                       # Official lifecycle hooks (hooks.json + hook handlers)
    ├── rules/                       # Telemetry-grounded rule sets (AGENTS.md)
    └── skills/                      # Targeted operational skills
```

---

## 🔬 Empirical Taxonomy Buckets

All telemetry mined across developer sessions is classified into four operational buckets:

| Category | Definition | Empirical Indicators |
| :--- | :--- | :--- |
| 🟢 **WHAT_WORKED** | Clean execution trajectories and zero-intervention workflows. | Single-pass file edits, passing tests, clean tool exit codes (`0`), direct goal completion. |
| 🔴 **WHAT_FAILED** | Mechanistic and operational breakdowns. | Loop traps (repeated `grep_search` / `view_file`), tool execution errors, runaway TUI commands, schema validation errors. |
| 🟡 **OPERATOR_GUIDANCE** | Human operator stepped in to steer or correct. | Interventions following tool errors, prompts containing redirection keywords ("stop", "drifted", "wait", "fix this"), manual architectural corrections. |
| 🚀 **HARNESS_OPPORTUNITY** | Gaps addressable via harness hooks, rules, or tooling. | Output truncators for verbose commands, anti-loop guards, pre-tool safety confirmation, subagent parallel barriers. |

---

## 🚀 Quickstart

### Prerequisites
- Python 3.10+
- Node.js 18+ (optional, for convenience scripts)
- Google Antigravity (`agy` CLI or desktop environment)

### 1. Inventory Active Customizations
Scans local machine for active built-in skills, custom skills, plugins, rules, and MCP servers:
```bash
python3 pipeline/inventory_customizations.py
```
Output is saved to `data/customization_inventory.json`.

### 2. Harvest Workstation Telemetry
Parses transcripts from `~/.gemini/antigravity/brain/*/transcript.jsonl` into SQLite:
```bash
python3 pipeline/extract_transcripts.py
```
Database generated at `data/telemetry.db`.

### 3. Classify Failure Modes & Generate Audit Report
```bash
python3 pipeline/classify_failures.py
```
Generates `docs/taxonomy/workstation-audit-report.md`.

---

## 📜 License

Licensed under the [Apache License, Version 2.0](LICENSE).  
Copyright © 2026 Purrfect Software Limited (PSL).
