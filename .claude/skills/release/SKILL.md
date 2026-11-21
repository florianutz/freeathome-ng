---
name: release
description: Prepare a freeathome_ng release (quality gate, SemVer bump in manifest.json and pyproject.toml, CHANGELOG, Hassfest/HACS checks, release PR). Tagging and publishing need explicit maintainer approval.
---

# /release

## 1. Decide the version

Read `CHANGELOG.md` `[Unreleased]`. SemVer: breaking change (removed/renamed service, event payload change, raised minimum HA version, changed entity naming) → major; new feature → minor; fixes only → patch. Propose the version and wait for confirmation if it is a major release.

## 2. Pre-flight

1. Start from an up-to-date `main` on a branch `release/vX.Y.Z`.
2. Run `/check-quality`; everything must be green.
3. Check the latest CI run on `main` is green (`gh api repos/{owner}/{repo}/actions/runs?branch=main&per_page=1`), including Hassfest and HACS validation.
4. Confirm `quality_scale.yaml` matches reality and README documents every user-visible change.

## 3. Bump

1. `custom_components/freeathome_ng/manifest.json` → `"version": "X.Y.Z"` (keep key order: `domain`, `name`, then alphabetical).
2. `pyproject.toml` → `version = "X.Y.Z"`.
3. `hacs.json` → `homeassistant` if the minimum HA version changed.
4. `CHANGELOG.md`: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add a fresh empty `[Unreleased]`, group entries as Added / Changed / Fixed / Removed / Breaking changes. Breaking changes need migration instructions.

## 4. Release PR

Commit (`Release vX.Y.Z`), push the branch, open a PR with the CHANGELOG section as body. Wait for green CI.

## 5. Tag and publish (only after explicit maintainer approval)

After the PR is merged and the maintainer approves: create the GitHub release `vX.Y.Z` from `main` with the CHANGELOG section as notes. HACS / Marketplace picks the release up from the tag. Never create tags or releases without that approval.

## 6. After the release

Note in the thread/PR what the maintainer should check on a live instance: integration loads without errors, diagnostics download works, no deprecation warnings in the log.
