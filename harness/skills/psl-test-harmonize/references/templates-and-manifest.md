<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# Test Harmonization Templates & Manifest Schema

Reference templates and full manifest specification for [SKILL.md](../SKILL.md).

## 1. Polyglot Manifest Injection Snippets

### Node / TypeScript (`package.json`)
- **Vitest**:
  ```json
  "scripts": {
    "test:diff": "vitest related --run",
    "test:watch": "vitest",
    "test:affected": "vitest related --run",
    "test:pkg": "vitest --project",
    "test:full": "vitest run"
  }
  ```
- **Jest**:
  ```json
  "scripts": {
    "test:diff": "jest --findRelatedTests --passWithNoTests",
    "test:watch": "jest --watch",
    "test:affected": "jest --findRelatedTests --passWithNoTests",
    "test:pkg": "pnpm --filter",
    "test:full": "jest --runInBand"
  }
  ```
- **Monorepo Root (`pnpm-workspace.yaml`, Turborepo)**:
  ```json
  "scripts": {
    "test:diff": "pnpm -r --filter ...[HEAD] test:diff",
    "test:affected": "turbo run test:affected --filter=...[HEAD]",
    "test:pkg": "pnpm --filter",
    "test:full": "pnpm -r test"
  }
  ```

### Rust (`.cargo/config.toml`)
```toml
[alias]
test-diff = "test"
test-watch = "watch -x test"
test-pkg = "test --package"
test-full = "test --workspace"
```

### Python (`pyproject.toml` & `Makefile`)
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
```
```makefile
.PHONY: test test:diff test:watch test:affected test:full

test:
	pytest

test:diff:
	pytest --picked -q

test:watch:
	ptw

test:affected:
	pytest -q

test:full:
	pytest -v
```

## 2. Anti-Synthetic Runner Snippets

### Vitest DOM Configuration (`vitest.config.ts`)
```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'happy-dom',
    globals: true,
  },
});
```

### Pixel-Based Visual Regression Testing (VRT)
```ts
// ILLEGAL SYNTHETIC TEST: Passes without verifying rendering
expect(fs.existsSync('screenshot.png')).toBe(true);

// AUTHENTIC VRT: Performs real pixel buffer diff against baseline
await expect(page).toHaveScreenshot('homepage.png', {
  maxDiffPixelRatio: 0.01,
});
```

### Computed Style & Contrast Auditing (`@axe-core/playwright`)
```ts
import { injectAxe, checkA11y } from 'axe-playwright';

test('contrast and a11y compliance', async ({ page }) => {
  await page.goto('/dashboard');
  await injectAxe(page);
  await checkA11y(page, undefined, {
    detailedReport: true,
    detailedReportOptions: { html: true },
  });
});
```

## 3. `.agyis/test_manifest.json` Example Schema

```json
{
  "version": "1.0.0",
  "generated_at": "2026-10-21T16:00:00Z",
  "workspace_root": "/path/to/workspace",
  "stack": "typescript",
  "role": "frontend",
  "framework": "vitest",
  "package_manager": "pnpm",
  "is_monorepo": false,
  "backup_patch": ".agyis/backups/test_harmonize_20261021_160000.patch",
  "tiers": {
    "tier_1a_diff": {
      "name": "test:diff",
      "command": "pnpm test:diff",
      "supported": true,
      "clears_turn_code_dirty": true
    },
    "tier_1b_affected": {
      "name": "test:affected",
      "command": "pnpm test:affected",
      "supported": true,
      "required_for_handoff": true
    },
    "tier_2b_full": {
      "name": "test:full",
      "command": "pnpm test:full",
      "supported": true,
      "required_for_commit": true
    }
  },
  "human_loop": {
    "watch_command": "pnpm test:watch",
    "non_interactive_guard": "--no-watch CI=true"
  },
  "ui_mounting": {
    "detected_frontend": true,
    "environment": "happy-dom",
    "has_dom_testing_library": true
  }
}
```
