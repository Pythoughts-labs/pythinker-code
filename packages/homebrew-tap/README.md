# Pythinker Homebrew Tap — operator notes

This directory holds the **template + generator** for the Homebrew Formula
that ships Pythinker Code to `brew install`. The actual published formula
lives in a **separate GitHub repo** (`homebrew-pythinker`) that you create
once and never hand-edit again.

After the first-time setup below, every `v*.*.*` tag push to this repo
auto-regenerates the formula and pushes it to the tap repo.

## End-user install (post-setup)

```sh
brew install TechMatrix-labs/pythinker/pythinker-code
```

Works on macOS (Intel + Apple Silicon) and Linux (x86_64 + aarch64) — same
formula, brew picks the matching native GitHub Release tarball.

Updates are manual:

```sh
brew update
brew upgrade pythinker-code
```

(Homebrew packages don't auto-update; this matches the project's docs and
matches Anthropic's published advice for Claude Code's Homebrew cask.)

## One-time setup (you do this once)

1. **Create the tap repo.** Create a new empty GitHub repo named
   `homebrew-pythinker` under your account. The `homebrew-` prefix is
   required by Homebrew; the part after the dash becomes the tap name
   (so `brew tap TechMatrix-labs/pythinker`).

   ```sh
   gh repo create TechMatrix-labs/homebrew-pythinker \
     --public \
     --description "Homebrew tap for Pythinker Code" \
     --enable-issues=false
   ```

2. **Create a fine-grained PAT** scoped to the tap repo with
   `Contents: Read and write`:
   <https://github.com/settings/personal-access-tokens/new>

3. **Add the secret to this repo.**

   ```sh
   gh secret set HOMEBREW_TAP_TOKEN --body "<the_pat>"
   ```

That's it. The next `v*.*.*` tag push to `Pythinker-Code` will:

1. Wait for native GitHub Release tarballs to be attached.
2. Render `Formula/pythinker-code.rb` from `pythinker-code.rb.tmpl` with the
   release URLs and SHA-256 digests.
3. Commit + push the formula to `TechMatrix-labs/homebrew-pythinker` on
   `main` (creating the inaugural commit on first run).
4. Brew users get the new release via `brew upgrade pythinker-code`.

## Manual fallback

If the workflow ever breaks (or the PAT expires), you can regenerate the
formula locally and push it by hand:

```sh
python packages/homebrew-tap/generate-formula.py \
  --version <version> \
  --template packages/homebrew-tap/pythinker-code.rb.tmpl \
  --output /tmp/pythinker-code.rb

# Commit /tmp/pythinker-code.rb into your homebrew-pythinker repo as
# Formula/pythinker-code.rb.
```

## Files

- `pythinker-code.rb.tmpl` — Ruby formula template (do not hand-edit).
- `generate-formula.py` — fetches native GitHub Release asset metadata and
  renders the template.
- (Workflow: `.github/workflows/homebrew-tap.yml`.)
