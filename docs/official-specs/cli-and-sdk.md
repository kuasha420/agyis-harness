<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# Official CLI (`agy`) & Python SDK Reference

## 1. Antigravity CLI (`agy`)
The official CLI provides terminal access to agent workflows and programmatic execution.

### Key Invocation Modes
- **Interactive TUI**:
  ```bash
  agy
  agy --continue
  agy --conversation <session-id>
  ```
- **Non-Interactive Batch / Print Mode**:
  ```bash
  agy --print --effort high "Audit this repository for security flaws"
  agy -p -i "Run tests and explain failure"
  ```
- **Structured NDJSON Streaming**:
  ```bash
  agy --input-format stream-json --output-format stream-json
  ```
- **Permission Bypass (Safe Automation Fences)**:
  ```bash
  agy --dangerously-skip-permissions --print "npm test"
  ```

### CLI Subcommands
- `agy plugin list | install | uninstall | enable | disable`: Manage plugin lifecycle.
- `agy mcp list | add | remove | enable | disable`: Manage stdio/SSE MCP servers.
- `agy agent list`: Discover available agents.
- `agy models`: List available Gemini model targets.

---

## 2. Python SDK (`google-antigravity`)
The Python SDK allows embedding agent loops and tools into external orchestration services.

### Core Interface Patterns
```python
from google_antigravity import AgentClient, ToolDefinition

# 1. Initialize client connected to local or remote runtime
client = AgentClient(profile="primary")

# 2. Expose deterministic tools via standard schemas
@client.tool(name="knot_mesh_exec", description="Execute command on Knot mesh node")
def knot_mesh_exec(node: str, command: str) -> dict:
    ...

# 3. Lease agent session with boundary fences
session = client.start_session(
    model="gemini-3.5-flash",
    effort="high",
    mode="plan"
)
```
