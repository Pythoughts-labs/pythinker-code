# Breaking changes and migration

This page documents breaking changes in Pythinker Code releases and provides migration guidance.

## Unreleased

## 0.40.1 (2026-06-10)

No breaking changes. This release is compatible with 0.40.0 user configuration, native installs, and session data.

## 0.40.0 (2026-06-10)

**`pythinker web` / `pythinker vis` `-h` host flag renamed to `-H`.** The short flag `-h` is now a help alias on both subcommands (matching the root CLI); previously `-h <ip>` bound the host. Scripts using `-h 0.0.0.0` must switch to `-H <ip>` or `--host <ip>`.

## 0.39.0 (2026-06-09)

No breaking changes. This release is compatible with 0.38.0 user configuration, native installs, and session data.

## 0.38.0 (2026-06-08)

No breaking changes. This release is compatible with 0.37.0 user configuration, native installs, and session data.

## 0.37.0 (2026-06-07)

No breaking changes. This release is compatible with 0.36.0 user configuration, native installs, and session data.

## 0.36.0 (2026-06-05)

No breaking changes. This release is compatible with 0.35.0 user configuration, native installs, and session data.

## 0.35.0 (2026-06-04)

## 0.34.0 (2026-06-03)

No breaking changes. This release is compatible with 0.33.0 user configuration, native installs, and session data.

## 0.33.0 (2026-06-03)

No breaking changes. This release is compatible with 0.32.0 user configuration, native installs, and session data.

## 0.32.0 (2026-06-03)

No breaking changes. This release is compatible with 0.31.0 user configuration, native installs, and session data.

## 0.31.0 (2026-06-02)

No breaking changes. This release is compatible with 0.30.0 user configuration, native installs, and session data.

## 0.30.0 (2026-06-02)

No breaking changes. This release is compatible with 0.29.0 user configuration, native installs, and session data.

## 0.29.0 (2026-06-01)

No breaking changes. This release is compatible with 0.28.0 user configuration, native installs, and session data.

## 0.28.0 (2026-05-31)

**`.pythinker/AGENTS.md` is no longer loaded as project instructions.** Pythinker now merges only `AGENTS.md`/`agents.md` files from the project root down to the working directory. If you kept instructions solely in `.pythinker/AGENTS.md`, move them to a root or directory-level `AGENTS.md` or they will no longer apply. No action is needed if you did not use `.pythinker/AGENTS.md`.

Otherwise this release is compatible with 0.27.0 user configuration, native installs, and session data. The repository's move to the Pythoughts-labs GitHub org is handled transparently — the default `/feedback` repository auto-migrates and download/update URLs resolve to the new org.

## 0.27.0 (2026-05-31)

No breaking changes. This release is compatible with 0.26.0 user configuration, native installs, and session data.

## 0.26.0 (2026-05-30)

No breaking changes. This release is compatible with 0.25.0 user configuration, native installs, and session data.

## 0.25.0 (2026-05-29)

No breaking changes. This release is compatible with 0.24.0 user configuration, native installs, and session data.

## 0.24.0 (2026-05-28)

No breaking changes. This release is compatible with 0.23.0 user configuration, native installs, and session data.

## 0.23.0 (2026-05-28)

No breaking changes. This release is compatible with 0.22.0 user configuration, native installs, and session data.

## 0.22.0 (2026-05-28)

No breaking changes. This release is compatible with 0.21.0 user configuration, native installs, and session data.

## 0.21.0 (2026-05-28)

No breaking changes. This release is compatible with 0.20.0 user configuration, native installs, and session data.

## 0.20.0 (2026-05-28)

No breaking changes. This release is compatible with 0.19.0 user configuration, native installs, and session data.

## 0.19.0 (2026-05-27)

No breaking changes. This release is compatible with 0.18.0 user configuration, native installs, and session data.

## 0.18.0 (2026-05-27)

No breaking changes. This release is compatible with 0.17.0 user configuration, native installs, and session data.

## 0.17.0 (2026-05-25)

No breaking changes. This release is compatible with 0.16.0 user configuration, native installs, and session data.

## 1.0.0 (2026-05-06)

Initial release — no migration needed.
