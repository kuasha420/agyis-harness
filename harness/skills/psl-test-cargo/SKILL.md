---
name: psl-test-cargo
description: >-
  Modular Rust test runner skill for Agyis Harness. Codifies cargo test
  execution contracts, isolated build targets, sub-second targeted testing, clippy verification,
  and panic-free test hygiene.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# PSL Test Skill: Cargo & Rust Test Runner

This skill establishes standardized execution contracts and hermetic testing standards for Rust and Cargo test suites across Agyis Harness.

---

## 1. Test Runner Invariants

### 1.1 Hermetic Test Invocation
- Execute Rust tests using targeted, quiet cargo commands:
  ```bash
  # Standard unit test execution
  cargo test --quiet

  # Run specific module or integration test
  cargo test --test <integration_test_name> -- --nocapture

  # Run with all features enabled
  cargo test --all-features --quiet
  ```
- Use `CARGO_TARGET_DIR` redirection for isolated builds in clean-room or CI environments.

### 1.2 Clippy & Compile Verification
- Run clippy checks alongside unit tests to verify memory and idiom hygiene:
  ```bash
  cargo clippy --all-targets -- -D warnings
  ```
- Ensure zero unhandled compiler warnings and zero implicit panics in production logic under test.

---

## 2. Failure Transparency & Clean Teardown

- Tests that fail must panic or return `Result::Err(...)`, triggering an immediate non-zero cargo exit code.
- Isolate file system side-effects using `tempfile` crate fixtures that auto-delete on Drop.
- Keep unit tests focused and fast (<1s) by avoiding heavy end-to-end network bindings or sleep timeouts.
