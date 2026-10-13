# Project: Agyis Harness Fleet Onboarding & Wave 1 Reconciliation (v1.0.0-rc2)

## Architecture
Agyis Harness (`v1.0.0-rc2`) provides autonomous agent workspace harmonization, preset decoupling, deterministic legacy `.agent/` migration/pruning, and multi-tier environment diagnostics.
This project coordinates fleet-wide reconciliation of 17 open Wave 1 pull requests and onboarding of 4 Tier 1 local repositories in `/home/kuasha/Dev` under strict WIP safeguarding and decoupled architectural roles.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Wave 1 PR Inventory & Checkout Verification | Map 17 open PRs to local checkouts on branch `chore/agyis-harness-onboarding` | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Preset Decoupling (Frontend & Mobile) | Ensure `sunshine-physio-webapp`, `mm-website`, `react-native-template-ts-plus`, and `purrfectcore-client` contain only relevant stack skills and strictly omit `psl-stack-backend` and `db-ops` | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Legacy Debris Pruning | Ensure zero legacy `.agent/` directories or `.agent/workflows` remain in any Wave 1 or Tier 1 repository | M1, M2 | ORIGINAL_REQUEST §R1, §R2 |
| 4 | Invariant Rules Fencing | Ensure `AGENTS.md` rule fences (`<!-- Added by AGYIS-HARNESS -->` / `<!-- End AGYIS-HARNESS -->`) are present and intact | M1, M2 | ORIGINAL_REQUEST §R1 |
| 5 | WIP Safeguarding (bookcover-craft) | Create dual-shield backup: isolated patch file `wip-safety-pre-onboarding.patch` and backup branch `backup/wip-pre-onboarding-staging` before any modification | M2 | ORIGINAL_REQUEST §R3 |
| 6 | WIP Safeguarding (bookcover-craft-api) | Create dual-shield backup: isolated patch file `wip-safety-pre-onboarding.patch` and backup branch `backup/wip-pre-onboarding-dev` before any modification | M2 | ORIGINAL_REQUEST §R3 |
| 7 | Tier 1 Clean Reset | Reset `bookcover-craft` to clean `origin/staging` and `bookcover-craft-api` to clean `origin/dev` after backup | M2 | ORIGINAL_REQUEST §R3 |
| 8 | Tier 1 Onboarding Branches & PRs | Run `agyis onboard` with explicit decoupled roles and tracking branches for `arbiter`, `bookcover-craft`, `bookcover-craft-api`, and `chakra-ui-icons-compat` | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Native Test Suite Verification | Execute native test suites / typecheck / build commands across targeted repositories | M3 | ORIGINAL_REQUEST §R4 |
| 10 | Agyis Doctor Diagnostics | Verify `agyis doctor` passes with exit code 0 across all target repositories | M3 | ORIGINAL_REQUEST §R4 |
| 11 | Push Updated Branches to Origin | Push updated `chore/agyis-harness-onboarding` branches to remote origin / fork targets without merging PRs | M3 | ORIGINAL_REQUEST §R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Wave 1 PR Reconciliation | Reconcile all 17 Wave 1 repositories to v1.0.0-rc2 with decoupled presets in frontend/mobile repos and intact rules fences | none | DONE |
| M2 | Tier 1 Repositories Safeguarding & Onboarding | Safeguard in-flight WIP in bookcover-craft and bookcover-craft-api via dual-shield patches and backup branches; onboard arbiter, bookcover-craft, bookcover-craft-api, chakra-ui-icons-compat with clean branches and PRs | none | DONE |
| M3 | Fleet Verification Gate & Remote Push | Automated verification gate (agyis doctor, preset audit, legacy audit, test suites) across all 21 repos and push to origin/fork remotes | M1, M2 | DONE |

## Code Layout
- Target Workspaces:
  - `/home/kuasha/Dev/psl-agy-harness` (Harness host toolchain)
  - Wave 1 Repos (17 checkouts in `/home/kuasha/Dev/`):
    - `jasper-hosted`
    - `chronicle-time-keeper`
    - `sunshine-physio-universalapp` (upstream `sunshine-physio-webapp`)
    - `purrmission`
    - `mm-website`
    - `psl-website`
    - `purrfect-download-manager`
    - `psl-scaffold`
    - `psl-boilerplate`
    - `Jasper`
    - `purrfectcore-client`
    - `purrfectcore-001`
    - `react-native-template-ts-plus`
    - `purr`
    - `knot-mesh`
    - `jimha`
  - Tier 1 Repos (4 local checkouts in `/home/kuasha/Dev/`):
    - `arbiter` (base: `develop`)
    - `bookcover-craft` (base: `staging`, role: `frontend`)
    - `bookcover-craft-api` (base: `dev`, role: `backend`)
    - `chakra-ui-icons-compat` (base: `develop`, role: `frontend`)

## Interface Contracts
### Agyis Onboard Invariants
- `agyis onboard <path> --base-branch <branch> [--role <role>] [--prune-legacy] [--pr]`
- Fences: `<!-- Added by AGYIS-HARNESS -->` and `<!-- End AGYIS-HARNESS -->`
- Decoupled roles:
  - `frontend`: `modern-web-guidance`, `psl-stack-typescript`, `psl-test-node` (NO `psl-stack-backend`, NO `db-ops`)
  - `mobile`: `android-cli`, `psl-stack-typescript`, `psl-test-node` (NO `psl-stack-backend`, NO `db-ops`)
  - `backend`: `psl-stack-backend`, `db-ops`, plus runtime skills
