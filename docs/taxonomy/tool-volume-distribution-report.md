<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 📊 Empirical Tool & Command Character Volume Distribution Report
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**Generated At**: 2026-10-10T19:30:29.361711+00:00  
**Data Source**: Workstation telemetry database (`data/telemetry.db`) across all ingested developer sessions  

---

## 1. Executive Summary & Aggregate Payload Volume

- **Total Tool Executions Analyzed**: **160,226** calls
- **Total Tool Output Volume**: **133,744,804** characters (~**33,436,201** estimated tokens)
- **Total Arguments Payload**: **105,818,184** characters (~**26,454,546** estimated tokens)
- **Platform-Truncated Outputs**: **14,155** calls (8.83% of all calls)
- **Tool Failure Invariant Count**: **4,062** calls strictly exempted from compaction

```text
┌────────────────────────────────────────────────────────────────────────┐
│                 MACRO PAYLOAD VOLUME BREAKDOWN                         │
├───────────────────────────────┬───────────────────┬────────────────────┤
│ Metric                        │ Characters        │ Estimated Tokens   │
├───────────────────────────────┼───────────────────┼────────────────────┤
│ Tool Results / Output         │       133,744,804 │         33,436,201 │
│ Tool Arguments / Input        │       105,818,184 │         26,454,546 │
│ Combined Tool Payload         │       239,562,988 │         59,890,747 │
└───────────────────────────────┴───────────────────┴────────────────────┘
```

---
## 2. Per-Tool Volume & Percentile Distribution

Tools sorted by total output volume impact:

| Tool Name | Calls | Total Chars | Avg Chars | Median | p90 | p99 | Max Chars | >2KB % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `view_file` | 45,991 | 62,790,151 | 1,365.3 | 146 | 4,116 | 4,121 | 4,121 | 33.08% |
| `run_command` | 72,127 | 47,640,203 | 660.5 | 146 | 2,366 | 4,120 | 8,216 | 11.17% |
| `replace_file_content` | 11,279 | 10,884,771 | 965.0 | 809 | 2,803 | 4,120 | 4,121 | 15.83% |
| `grep_search` | 8,379 | 4,591,529 | 548.0 | 0 | 2,053 | 4,120 | 4,121 | 10.01% |
| `manage_task` | 6,479 | 2,688,775 | 415.0 | 120 | 1,314 | 1,607 | 4,120 | 0.08% |
| `search_web` | 696 | 1,357,561 | 1,950.5 | 2,223 | 4,119 | 4,120 | 4,120 | 51.87% |
| `write_to_file` | 5,511 | 992,589 | 180.1 | 272 | 331 | 655 | 898 | 0.0% |
| `list_dir` | 2,304 | 718,348 | 311.8 | 179 | 778 | 2,433 | 4,121 | 1.87% |
| `find_by_name` | 1,763 | 504,642 | 286.2 | 83 | 931 | 2,803 | 4,119 | 2.04% |
| `schedule` | 1,710 | 456,526 | 267.0 | 124 | 613 | 727 | 4,120 | 0.06% |
| `multi_replace_file_content` | 159 | 329,192 | 2,070.4 | 1,881 | 4,114 | 4,120 | 4,120 | 45.28% |
| `manage_subagents` | 862 | 201,713 | 234.0 | 0 | 641 | 2,608 | 4,120 | 1.62% |
| `invoke_subagent` | 692 | 160,689 | 232.2 | 0 | 546 | 1,081 | 4,113 | 0.14% |
| `call_mcp_tool` | 212 | 123,431 | 582.2 | 190 | 2,096 | 4,093 | 4,120 | 10.38% |
| `ask_question` | 364 | 64,810 | 178.0 | 119 | 378 | 884 | 4,120 | 0.55% |
| `send_message` | 1,126 | 64,462 | 57.2 | 0 | 133 | 133 | 4,113 | 0.09% |
| `list_permissions` | 17 | 60,799 | 3,576.4 | 3,842 | 4,055 | 4,118 | 4,118 | 94.12% |
| `mcp_chrome_devtools_evaluate_script` | 87 | 45,674 | 525.0 | 0 | 2,434 | 4,121 | 4,121 | 10.34% |
| `read_url_content` | 125 | 27,801 | 222.4 | 0 | 460 | 717 | 1,459 | 0.0% |
| `mcp_chrome_devtools_take_screenshot` | 78 | 8,739 | 112.0 | 0 | 256 | 265 | 265 | 0.0% |
| `ask_permission` | 6 | 5,004 | 834.0 | 131 | 4,120 | 4,120 | 4,120 | 16.67% |
| `mcp_chrome_devtools_list_network_requests` | 4 | 4,949 | 1,237.2 | 0 | 3,306 | 3,306 | 3,306 | 25.0% |
| `mcp_chrome_devtools_navigate_page` | 43 | 4,782 | 111.2 | 0 | 222 | 552 | 552 | 0.0% |
| `define_subagent` | 44 | 3,383 | 76.9 | 0 | 170 | 234 | 234 | 0.0% |
| `mcp_chrome_devtools_click` | 54 | 3,322 | 61.5 | 0 | 113 | 293 | 293 | 0.0% |
| `mcp_chrome_devtools_wait_for` | 2 | 3,169 | 1,584.5 | 0 | 3,169 | 3,169 | 3,169 | 50.0% |
| `mcp_chrome_devtools_get_network_request` | 2 | 2,085 | 1,042.5 | 0 | 2,085 | 2,085 | 2,085 | 50.0% |
| `generate_image` | 1 | 1,394 | 1,394.0 | 1,394 | 1,394 | 1,394 | 1,394 | 0.0% |
| `mcp_chrome_devtools_resize_page` | 16 | 1,346 | 84.1 | 0 | 214 | 498 | 498 | 0.0% |
| `list_resources` | 24 | 1,049 | 43.7 | 0 | 132 | 132 | 132 | 0.0% |
| `mcp_chrome_devtools_fill` | 8 | 452 | 56.5 | 0 | 113 | 113 | 113 | 0.0% |
| `mcp_chrome_devtools_list_console_messages` | 4 | 338 | 84.5 | 0 | 213 | 213 | 213 | 0.0% |
| `mcp_chrome_devtools_list_pages` | 5 | 337 | 67.4 | 0 | 214 | 214 | 214 | 0.0% |
| `mcp_chrome_devtools_emulate` | 2 | 235 | 117.5 | 0 | 235 | 235 | 235 | 0.0% |
| `mcp_chrome_devtools_select_page` | 2 | 214 | 107.0 | 0 | 214 | 214 | 214 | 0.0% |
| `kill_all` | 2 | 144 | 72.0 | 0 | 144 | 144 | 144 | 0.0% |
| `mcp_chrome_devtools_fill_form` | 2 | 110 | 55.0 | 0 | 110 | 110 | 110 | 0.0% |
| `browser_subagent` | 1 | 86 | 86.0 | 86 | 86 | 86 | 86 | 0.0% |
| `browser_get_dom` | 2 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `browser_navigate` | 4 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `chrome_devtools:navigate_page` | 4 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `click` | 2 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `command_status` | 30 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `mcp_chrome_devtools_new_page` | 1 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |


### Size Bucket Distribution by Tool

| Tool Name | < 500 B | 500 B – 2 KB | 2 KB – 10 KB | 10 KB – 50 KB | > 50 KB |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `view_file` | 23,587 | 7,190 | 15,214 | 0 | 0 |
| `run_command` | 49,901 | 14,171 | 8,055 | 0 | 0 |
| `replace_file_content` | 5,279 | 4,214 | 1,786 | 0 | 0 |
| `grep_search` | 6,481 | 1,059 | 839 | 0 | 0 |
| `manage_task` | 4,267 | 2,207 | 5 | 0 | 0 |
| `search_web` | 298 | 37 | 361 | 0 | 0 |
| `write_to_file` | 5,180 | 331 | 0 | 0 | 0 |
| `list_dir` | 1,853 | 408 | 43 | 0 | 0 |
| `find_by_name` | 1,464 | 263 | 36 | 0 | 0 |
| `schedule` | 1,111 | 598 | 1 | 0 | 0 |
| `multi_replace_file_content` | 17 | 70 | 72 | 0 | 0 |
| `manage_subagents` | 725 | 123 | 14 | 0 | 0 |
| `invoke_subagent` | 423 | 268 | 1 | 0 | 0 |
| `call_mcp_tool` | 169 | 21 | 22 | 0 | 0 |
| `ask_question` | 352 | 10 | 2 | 0 | 0 |
| `send_message` | 1,125 | 0 | 1 | 0 | 0 |
| `list_permissions` | 1 | 0 | 16 | 0 | 0 |
| `mcp_chrome_devtools_evaluate_script` | 68 | 10 | 9 | 0 | 0 |
| `read_url_content` | 122 | 3 | 0 | 0 | 0 |
| `mcp_chrome_devtools_take_screenshot` | 78 | 0 | 0 | 0 | 0 |
| `ask_permission` | 4 | 1 | 1 | 0 | 0 |
| `mcp_chrome_devtools_list_network_requests` | 2 | 1 | 1 | 0 | 0 |
| `mcp_chrome_devtools_navigate_page` | 42 | 1 | 0 | 0 | 0 |
| `define_subagent` | 44 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_click` | 54 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_wait_for` | 1 | 0 | 1 | 0 | 0 |
| `mcp_chrome_devtools_get_network_request` | 1 | 0 | 1 | 0 | 0 |
| `generate_image` | 0 | 1 | 0 | 0 | 0 |
| `mcp_chrome_devtools_resize_page` | 16 | 0 | 0 | 0 | 0 |
| `list_resources` | 24 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_fill` | 8 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_list_console_messages` | 4 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_list_pages` | 5 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_emulate` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_select_page` | 2 | 0 | 0 | 0 | 0 |
| `kill_all` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_fill_form` | 2 | 0 | 0 | 0 | 0 |
| `browser_subagent` | 1 | 0 | 0 | 0 | 0 |
| `browser_get_dom` | 2 | 0 | 0 | 0 | 0 |
| `browser_navigate` | 4 | 0 | 0 | 0 | 0 |
| `chrome_devtools:navigate_page` | 4 | 0 | 0 | 0 | 0 |
| `click` | 2 | 0 | 0 | 0 | 0 |
| `command_status` | 30 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_new_page` | 1 | 0 | 0 | 0 | 0 |

---

## 3. Shell Command (`run_command`) Category De-Aggregation

Breakdown of `run_command` volume across operational categories:

| Category | Calls | Total Chars | Avg Chars | Median | p90 | Max Chars | >2KB % | Errors |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `other` | 31,940 | 26,999,653 | 845.3 | 310 | 2,991 | 8,207 | 13.94% | 1872 |
| `grep_search` | 6,741 | 5,340,317 | 792.2 | 140 | 3,594 | 8,153 | 15.35% | 422 |
| `test_runner` | 5,799 | 4,042,555 | 697.1 | 0 | 2,906 | 8,210 | 13.64% | 387 |
| `git` | 9,442 | 3,342,281 | 354.0 | 0 | 1,002 | 8,216 | 5.36% | 160 |
| `file_system` | 4,033 | 2,943,102 | 729.8 | 129 | 2,624 | 8,204 | 12.08% | 82 |
| `package_manager` | 2,308 | 1,701,520 | 737.2 | 0 | 2,846 | 8,204 | 12.87% | 187 |
| `file_search` | 3,171 | 1,169,226 | 368.7 | 0 | 1,170 | 8,202 | 5.05% | 88 |
| `system_probe` | 1,914 | 1,038,605 | 542.6 | 0 | 1,970 | 6,427 | 9.35% | 73 |
| `python_exec` | 3,662 | 575,913 | 157.3 | 0 | 186 | 8,216 | 2.62% | 49 |
| `network` | 2,661 | 326,211 | 122.6 | 0 | 282 | 5,089 | 1.32% | 37 |
| `build_compile` | 456 | 160,820 | 352.7 | 0 | 744 | 4,120 | 3.51% | 12 |

---

## 4. Empirical Compactor Simulation & Savings Curve

Evaluating deterministic output compaction thresholds (head 500 chars + tail 1,000 chars) while strictly asserting the **Failure Preservation Invariant (ADR-008)**:

| Threshold | Impacted Calls | Characters Saved | Estimated Tokens Saved | Volume Reduction % | Failures Preserved | Violations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1KB** (1,024 B) | 31,090 | 49,289,535 | **12,322,383** | **36.85%** | 958 | 0 |
| **2KB** (2,048 B) | 25,858 | 48,230,255 | **12,057,563** | **36.06%** | 623 | 0 |
| **4KB** (4,096 B) | 10,544 | 26,932,353 | **6,733,088** | **20.14%** | 222 | 0 |
| **8KB** (8,192 B) | 22 | 144,851 | **36,212** | **0.11%** | 0 | 0 |
| **16KB** (16,384 B) | 0 | 0 | **0** | **0.0%** | 0 | 0 |


> [!IMPORTANT]
> **Failure Preservation Audit (ADR-008)**: Across all tested thresholds, `failure_preservation_violations` is strictly **0**. Every tool execution terminating with non-zero exit code or error status is preserved 100% in full for developer diagnosis.

---
## 5. Architectural Findings & Next Steps

1. **2KB Sweet Spot Validated**: The 2KB threshold provides an optimal balance, reducing total output volume by over **20%** while compacting only the long-tail bloaters (>2KB) and leaving short commands completely unmodified.
2. **Category Heavyweights**: Test runners and package managers generate the largest individual payloads, highlighting the need for project-level test runner output compactors.
3. **Input vs. Output Asymmetry**: File modification tools (`write_to_file`) are dominated by input arguments rather than outputs, confirming that output compaction correctly targets the read/exec tools (`run_command`, `view_file`, `grep_search`).
