---
name: psl-audit-toolkit
description: >-
  Empirical telemetry analysis and audit toolkit for Google Antigravity.
  Use when the user requests an audit of session performance, failure mode classification,
  loop detection, tool error metrics, or optimization of agent harnesses.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# PSL Audit Toolkit for Google Antigravity™

The PSL Audit Toolkit provides empirical telemetry extraction, classification, and reporting
for Antigravity developer sessions across workstations and the Knot mesh.

---

## 1. Quick Capabilities

- **Customization Inventory**: Scans active plugins, skills, MCP servers, hooks, and rules.
- **Transcript Harvester**: Parses `~/.gemini/antigravity/brain/*/transcript.jsonl` into SQLite (`data/telemetry.db`).
- **Failure Taxonomy Classifier**: Categorizes trajectories into:
  - 🟢 `WHAT_WORKED`
  - 🔴 `WHAT_FAILED`
  - 🟡 `OPERATOR_GUIDANCE`
  - 🚀 `HARNESS_OPPORTUNITY`
- **Intervention Summarizer**: Analyzes operator steering prompts, drift halts, and rescue events.

---

## 2. Command Reference

### Run the Full Audit Pipeline via Unified CLI
```bash
python3 -m harness.cli audit all
```

### Run Specific Audit Stages
```bash
# Ingest local developer sessions into data/telemetry.db
python3 -m harness.cli audit extract

# Classify failure taxonomy and generate metrics
python3 -m harness.cli audit classify

# Scan active plugins, skills, MCP servers, and hooks
python3 -m harness.cli audit inventory

# Analyze token cliff and context dynamics
python3 -m harness.cli audit dynamics

# Summarize operator interventions and drift halts
python3 -m harness.cli audit interventions
```

### Inspect Specific Session Telemetry
To examine a specific session ID from `data/telemetry.db`:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()
c.execute('SELECT step_index, tool_name, status, exit_code FROM tool_calls WHERE session_id = ?', ('<session-id>',))
for row in c.fetchall():
    print(row)
"
```

### Query Top Failing Commands
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/telemetry.db')
c = conn.cursor()
c.execute('''
    SELECT command_line, COUNT(*) as cnt
    FROM tool_calls
    WHERE tool_name = 'run_command' AND status != 'SUCCESS'
    GROUP BY command_line
    ORDER BY cnt DESC LIMIT 10
''')
for r in c.fetchall():
    print(f'{r[1]}x: {r[0]}')
"
```
