---
name: psl-test-go
description: >-
  Modular Go test runner skill for Google Antigravity harnesses. Codifies go test
  execution contracts, race condition detection (-race), hermetic package testing,
  and strict error-checking hygiene.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Purrfect Software Limited (PSL) -->

# PSL Test Skill: Go Test Runner & Hermetic Verification

This skill establishes standardized execution contracts and hermetic testing standards for Go test suites across Google Antigravity harnesses.

---

## 1. Test Runner Invariants

### 1.1 Hermetic Test Invocation
- Execute Go tests using hermetic package traversal and race detector:
  ```bash
  # Standard hermetic test execution across all packages
  go test ./...

  # Race detection enabled for concurrency-safe testing
  go test -race ./...

  # Verbose execution for specific package
  go test -v ./pkg/...
  ```

### 1.2 Resource Cleanup & Isolation
- Always register cleanup actions using `t.Cleanup()` to guarantee deterministic teardown even upon test failures:
  ```go
  func TestComponent(t *testing.T) {
      dir := t.TempDir() // Automatically deleted when test completes
      t.Cleanup(func() {
          // Additional custom resource release
      })
  }
  ```

---

## 2. Failure Transparency & Error Reporting

- Use `t.Fatalf()` or `t.Errorf()` to fail tests explicitly; never hide error values (`err != nil`).
- Do not ignore returned errors from production methods in test functions.
- Strive for sub-second test benchmarks by avoiding wall-clock `time.Sleep()` synchronization; use channel signaling, timeouts, or sync primitives.
