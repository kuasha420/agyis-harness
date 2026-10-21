<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# 📊 Empirical Tool & Command Character Volume Distribution Report
**Project**: PSL Harness for Google Antigravity™ (`psl-agy-harness`)  
**Publisher**: Purrfect Software Limited (PSL)  
**Generated At**: 2026-10-18T18:29:33.892099+00:00  
**Data Source**: Workstation telemetry database (`data/telemetry.db`) across all ingested developer sessions  

---

## 1. Executive Summary & Aggregate Payload Volume

- **Total Tool Executions Analyzed**: **237,583** calls
- **Total Tool Output Volume**: **226,198,363** characters (~**56,549,590** estimated tokens)
- **Total Arguments Payload**: **158,273,807** characters (~**39,568,451** estimated tokens)
- **Platform-Truncated Outputs**: **23,483** calls (9.88% of all calls)
- **Tool Failure Invariant Count**: **6,084** calls strictly exempted from compaction

```text
┌────────────────────────────────────────────────────────────────────────┐
│                 MACRO PAYLOAD VOLUME BREAKDOWN                         │
├───────────────────────────────┬───────────────────┬────────────────────┤
│ Metric                        │ Characters        │ Estimated Tokens   │
├───────────────────────────────┼───────────────────┼────────────────────┤
│ Tool Results / Output         │       226,198,363 │         56,549,590 │
│ Tool Arguments / Input        │       158,273,807 │         39,568,451 │
│ Combined Tool Payload         │       384,472,170 │         96,118,042 │
└───────────────────────────────┴───────────────────┴────────────────────┘
```

---
## 2. Per-Tool Volume & Percentile Distribution

Tools sorted by total output volume impact:

| Tool Name | Calls | Total Chars | Avg Chars | Median | p90 | p99 | Max Chars | >2KB % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `view_file` | 70,039 | 116,721,397 | 1,666.5 | 1,173 | 4,119 | 5,479 | 49,780 | 38.97% |
| `run_command` | 101,940 | 73,392,037 | 720.0 | 175 | 2,639 | 4,120 | 8,360 | 12.4% |
| `replace_file_content` | 14,729 | 14,425,524 | 979.4 | 843 | 2,682 | 4,120 | 10,239 | 15.55% |
| `grep_search` | 11,444 | 7,177,084 | 627.1 | 94 | 2,493 | 4,120 | 10,239 | 11.57% |
| `manage_task` | 8,084 | 3,075,062 | 380.4 | 0 | 1,305 | 1,569 | 4,120 | 0.07% |
| `write_to_file` | 13,506 | 2,955,072 | 218.8 | 301 | 323 | 509 | 4,121 | 0.02% |
| `list_dir` | 4,117 | 2,134,198 | 518.4 | 231 | 1,303 | 4,120 | 10,239 | 6.56% |
| `manage_subagents` | 1,906 | 1,730,006 | 907.7 | 392 | 3,172 | 4,120 | 5,138 | 18.1% |
| `search_web` | 914 | 1,689,196 | 1,848.1 | 1,826 | 4,120 | 5,416 | 6,739 | 47.37% |
| `find_by_name` | 2,661 | 825,838 | 310.3 | 93 | 1,037 | 2,575 | 4,121 | 1.77% |
| `schedule` | 2,278 | 605,403 | 265.8 | 124 | 626 | 781 | 4,120 | 0.04% |
| `invoke_subagent` | 1,264 | 475,943 | 376.5 | 458 | 1,081 | 1,676 | 4,113 | 0.08% |
| `multi_replace_file_content` | 158 | 328,402 | 2,078.5 | 1,881 | 4,114 | 4,120 | 4,120 | 45.57% |
| `send_message` | 3,345 | 272,720 | 81.5 | 133 | 133 | 133 | 4,113 | 0.03% |
| `call_mcp_tool` | 218 | 126,979 | 582.5 | 190 | 2,096 | 4,093 | 4,120 | 10.09% |
| `mcp_chrome_devtools_evaluate_script` | 102 | 72,866 | 714.4 | 0 | 3,193 | 4,120 | 4,121 | 14.71% |
| `list_permissions` | 16 | 56,918 | 3,557.4 | 3,746 | 4,055 | 4,118 | 4,118 | 93.75% |
| `ask_question` | 353 | 52,625 | 149.1 | 0 | 365 | 884 | 4,120 | 0.57% |
| `read_url_content` | 152 | 36,290 | 238.8 | 355 | 458 | 717 | 1,459 | 0.0% |
| `mcp_chrome_devtools_take_screenshot` | 82 | 9,675 | 118.0 | 0 | 255 | 265 | 265 | 0.0% |
| `ask_permission` | 10 | 5,004 | 500.4 | 0 | 611 | 4,120 | 4,120 | 10.0% |
| `mcp_chrome_devtools_list_network_requests` | 4 | 4,949 | 1,237.2 | 0 | 3,306 | 3,306 | 3,306 | 25.0% |
| `mcp_chrome_devtools_navigate_page` | 43 | 4,782 | 111.2 | 0 | 222 | 552 | 552 | 0.0% |
| `define_subagent` | 45 | 4,096 | 91.0 | 159 | 178 | 234 | 234 | 0.0% |
| `mcp_chrome_devtools_click` | 54 | 3,322 | 61.5 | 0 | 113 | 293 | 293 | 0.0% |
| `mcp_chrome_devtools_wait_for` | 2 | 3,169 | 1,584.5 | 0 | 3,169 | 3,169 | 3,169 | 50.0% |
| `generate_image` | 2 | 2,330 | 1,165.0 | 936 | 1,394 | 1,394 | 1,394 | 0.0% |
| `mcp_chrome_devtools_get_network_request` | 2 | 2,085 | 1,042.5 | 0 | 2,085 | 2,085 | 2,085 | 50.0% |
| `mcp_chrome_devtools_resize_page` | 17 | 1,615 | 95.0 | 0 | 269 | 498 | 498 | 0.0% |
| `list_resources` | 24 | 1,049 | 43.7 | 0 | 132 | 132 | 132 | 0.0% |
| `mcp_chrome_devtools_list_console_messages` | 5 | 678 | 135.6 | 125 | 340 | 340 | 340 | 0.0% |
| `mcp_chrome_devtools_list_pages` | 6 | 510 | 85.0 | 0 | 214 | 214 | 214 | 0.0% |
| `mcp_chrome_devtools_fill` | 8 | 452 | 56.5 | 0 | 113 | 113 | 113 | 0.0% |
| `mcp_chrome_devtools_new_page` | 2 | 269 | 134.5 | 0 | 269 | 269 | 269 | 0.0% |
| `mcp_chrome_devtools_emulate` | 2 | 235 | 117.5 | 0 | 235 | 235 | 235 | 0.0% |
| `mcp_chrome_devtools_select_page` | 2 | 214 | 107.0 | 0 | 214 | 214 | 214 | 0.0% |
| `mcp_chrome_devtools_close_page` | 1 | 173 | 173.0 | 173 | 173 | 173 | 173 | 0.0% |
| `mcp_chrome_devtools_fill_form` | 2 | 110 | 55.0 | 0 | 110 | 110 | 110 | 0.0% |
| `browser_subagent` | 1 | 86 | 86.0 | 86 | 86 | 86 | 86 | 0.0% |
| `browser_get_dom` | 2 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `browser_navigate` | 4 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `chrome_devtools:navigate_page` | 4 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `click` | 2 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `command_status` | 30 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |
| `kill_all` | 1 | 0 | 0.0 | 0 | 0 | 0 | 0 | 0.0% |


### Size Bucket Distribution by Tool

| Tool Name | < 500 B | 500 B – 2 KB | 2 KB – 10 KB | 10 KB – 50 KB | > 50 KB |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `view_file` | 32,127 | 10,620 | 27,038 | 254 | 0 |
| `run_command` | 68,507 | 20,795 | 12,638 | 0 | 0 |
| `replace_file_content` | 6,658 | 5,781 | 2,290 | 0 | 0 |
| `grep_search` | 8,561 | 1,559 | 1,324 | 0 | 0 |
| `manage_task` | 5,549 | 2,529 | 6 | 0 | 0 |
| `write_to_file` | 13,146 | 357 | 3 | 0 | 0 |
| `list_dir` | 3,237 | 610 | 270 | 0 | 0 |
| `manage_subagents` | 1,181 | 380 | 345 | 0 | 0 |
| `search_web` | 401 | 80 | 433 | 0 | 0 |
| `find_by_name` | 2,146 | 468 | 47 | 0 | 0 |
| `schedule` | 1,480 | 797 | 1 | 0 | 0 |
| `invoke_subagent` | 643 | 620 | 1 | 0 | 0 |
| `multi_replace_file_content` | 17 | 69 | 72 | 0 | 0 |
| `send_message` | 3,344 | 0 | 1 | 0 | 0 |
| `call_mcp_tool` | 174 | 22 | 22 | 0 | 0 |
| `mcp_chrome_devtools_evaluate_script` | 74 | 13 | 15 | 0 | 0 |
| `list_permissions` | 1 | 0 | 15 | 0 | 0 |
| `ask_question` | 346 | 5 | 2 | 0 | 0 |
| `read_url_content` | 148 | 4 | 0 | 0 | 0 |
| `mcp_chrome_devtools_take_screenshot` | 82 | 0 | 0 | 0 | 0 |
| `ask_permission` | 8 | 1 | 1 | 0 | 0 |
| `mcp_chrome_devtools_list_network_requests` | 2 | 1 | 1 | 0 | 0 |
| `mcp_chrome_devtools_navigate_page` | 42 | 1 | 0 | 0 | 0 |
| `define_subagent` | 45 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_click` | 54 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_wait_for` | 1 | 0 | 1 | 0 | 0 |
| `generate_image` | 0 | 2 | 0 | 0 | 0 |
| `mcp_chrome_devtools_get_network_request` | 1 | 0 | 1 | 0 | 0 |
| `mcp_chrome_devtools_resize_page` | 17 | 0 | 0 | 0 | 0 |
| `list_resources` | 24 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_list_console_messages` | 5 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_list_pages` | 6 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_fill` | 8 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_new_page` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_emulate` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_select_page` | 2 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_close_page` | 1 | 0 | 0 | 0 | 0 |
| `mcp_chrome_devtools_fill_form` | 2 | 0 | 0 | 0 | 0 |
| `browser_subagent` | 1 | 0 | 0 | 0 | 0 |
| `browser_get_dom` | 2 | 0 | 0 | 0 | 0 |
| `browser_navigate` | 4 | 0 | 0 | 0 | 0 |
| `chrome_devtools:navigate_page` | 4 | 0 | 0 | 0 | 0 |
| `click` | 2 | 0 | 0 | 0 | 0 |
| `command_status` | 30 | 0 | 0 | 0 | 0 |
| `kill_all` | 1 | 0 | 0 | 0 | 0 |

---

## 3. Shell Command (`run_command`) Category De-Aggregation

Breakdown of `run_command` volume across operational categories:

| Category | Calls | Total Chars | Avg Chars | Median | p90 | Max Chars | >2KB % | Errors |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `other` | 44,022 | 39,036,767 | 886.8 | 353 | 3,031 | 8,289 | 15.12% | 2472 |
| `test_runner` | 10,529 | 9,513,427 | 903.5 | 221 | 4,017 | 8,339 | 16.72% | 709 |
| `grep_search` | 9,218 | 8,527,902 | 925.1 | 154 | 4,116 | 8,276 | 18.59% | 490 |
| `git` | 12,409 | 5,226,247 | 421.2 | 0 | 1,213 | 8,360 | 6.11% | 210 |
| `file_system` | 5,859 | 3,936,388 | 671.9 | 0 | 2,434 | 8,227 | 11.33% | 112 |
| `package_manager` | 2,925 | 2,147,173 | 734.1 | 0 | 2,832 | 8,232 | 12.89% | 234 |
| `file_search` | 4,644 | 1,782,868 | 383.9 | 0 | 1,121 | 8,253 | 5.04% | 149 |
| `python_exec` | 6,572 | 1,529,307 | 232.7 | 0 | 397 | 8,349 | 3.42% | 107 |
| `system_probe` | 2,314 | 1,152,290 | 498.0 | 0 | 1,763 | 6,427 | 8.34% | 86 |
| `network` | 2,920 | 336,286 | 115.2 | 0 | 282 | 7,070 | 1.2% | 40 |
| `build_compile` | 517 | 201,678 | 390.1 | 0 | 745 | 5,981 | 4.45% | 17 |
| `unclassified` | 11 | 1,704 | 154.9 | 213 | 213 | 213 | 0.0% | 3 |

---

## 4. Empirical Compactor Simulation & Savings Curve

Evaluating deterministic output compaction thresholds (head 500 chars + tail 1,000 chars) while strictly asserting the **Failure Preservation Invariant (ADR-008)**:

| Threshold | Impacted Calls | Characters Saved | Estimated Tokens Saved | Volume Reduction % | Failures Preserved | Violations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1KB** (1,024 B) | 51,682 | 91,359,246 | **22,839,811** | **40.39%** | 1348 | 0 |
| **2KB** (2,048 B) | 43,884 | 89,774,815 | **22,443,703** | **39.69%** | 897 | 0 |
| **4KB** (4,096 B) | 20,229 | 57,512,511 | **14,378,127** | **25.43%** | 385 | 0 |
| **8KB** (8,192 B) | 558 | 6,314,513 | **1,578,628** | **2.79%** | 8 | 0 |
| **16KB** (16,384 B) | 116 | 2,586,093 | **646,523** | **1.14%** | 0 | 0 |


> [!IMPORTANT]
> **Failure Preservation Audit (ADR-008)**: Across all tested thresholds, `failure_preservation_violations` is strictly **0**. Every tool execution terminating with non-zero exit code or error status is preserved 100% in full for developer diagnosis.

---
## 5. Architectural Findings & Next Steps

1. **2KB Sweet Spot Validated**: The 2KB threshold provides an optimal balance, reducing total output volume by over **20%** while compacting only the long-tail bloaters (>2KB) and leaving short commands completely unmodified.
2. **Category Heavyweights**: Test runners and package managers generate the largest individual payloads, highlighting the need for project-level test runner output compactors.
3. **Input vs. Output Asymmetry**: File modification tools (`write_to_file`) are dominated by input arguments rather than outputs, confirming that output compaction correctly targets the read/exec tools (`run_command`, `view_file`, `grep_search`).
