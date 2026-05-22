# Changelog

This page documents the changes in each Pythinker Code release.

All notable changes to `pythinker-code` are tracked in this file.

Pythinker Code uses a `0.MINOR.PATCH` version scheme. `MINOR` is a release
counter that continues advancing with each release. `PATCH` is reserved for
hotfixes against an already-released `MINOR`. There is no `1.0.0` milestone
planned on this line.

Releases earlier than `0.8.0` were published as `pythinker-code` 1.x/2.x
under a different scheme. The full pre-`0.8.0` history is preserved in
[`../../history/CHANGELOG-pre-0.8.0.md`](../../history/CHANGELOG-pre-0.8.0.md).
All 1.x and 2.x releases have been yanked from PyPI and removed from the
GitHub Releases page; `0.8.0` is the new starting line.

## Unreleased

## 0.8.0 (2026-05-21)

Version-scheme reset. `pythinker-code` now ships as `0.8.0` under the new
`0.MINOR.PATCH` line.

### What changed in this release

- **Version line reset.** `pyproject.toml` `version` is `0.8.0` under the new release design.
  All prior `pythinker-code` 1.x/2.x releases have been yanked from PyPI and
  removed from the GitHub Releases page. New installs of
  `pip install --upgrade pythinker-code==0.8.0` resolve to the `0.x` line.
- **Tag scheme standardised** on `v<MAJOR>.<MINOR>.<PATCH>`. The
  `release-pythinker-cli.yml` workflow trigger now matches `v[0-9]+.[0-9]+.[0-9]+`
  and `scripts/check_version_tag.py` strips the leading `v` before comparing the
  tag to `pyproject.toml`.
- **Release gate preserved.** The `What's New in <version>` section,
  `pythinker-code==<version>` install snippet, and `## <version> (YYYY-MM-DD)`
  CHANGELOG entry are still required for every tag — only the version values
  change.
- **CHANGELOG restart.** Pre-`0.8.0` history archived to
  `../../history/CHANGELOG-pre-0.8.0.md`; this file starts fresh at `0.8.0`.
- **README "What's New" trimmed.** The cascading 2.x "What's New" wall is
  replaced by a single `0.8.0` section. Past release notes live in the archived
  CHANGELOG and the per-tag GitHub Releases (from `v0.8.0` onward).
- **Test refactor.** `tests/telemetry/test_otel_resource.py` now reads the
  expected service version from `importlib.metadata.version("pythinker-code")`
  instead of a hard-coded string, so future version bumps don't require a test
  edit.

### Included in 0.8.0

All functionality included in `pythinker-code` 0.8.0 is preserved:
review-first workflows (`pythinker review`, `pythinker secscan`,
`pythinker security-scan`, `pythinker debug`), Reviewflow stateful
review/fix workflows, the new `code-reviewer` / `security-reviewer` /
`debugger` subagent roles, hardened review-output validation, and the
read-only PR artifact helpers (`describe`, `improve` / `suggest`, `ask`,
`labels`, `changelog`, `docs`, `compliance`, etc.).

See [`../../history/CHANGELOG-pre-0.8.0.md`](../../history/CHANGELOG-pre-0.8.0.md)
for the archived pre-reset release-by-release notes.

Upgrade with `pythinker update` or `pip install --upgrade pythinker-code==0.8.0`.
