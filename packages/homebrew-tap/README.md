# Pythinker Homebrew Tap — operator notes

This directory holds the **template + generator** for the Homebrew Formula
that ships Pythinker Code to `brew install`. The actual published formula
lives in a **separate GitHub repo** (`homebrew-pythinker`) that you create
once and never hand-edit again.

After the first-time setup below, every `v*.*.*` tag push to this repo
auto-regenerates the formula and pushes it to the tap repo.

## End-user install (post-setup)

```sh
brew install mohamed-elkholy95/pythinker/pythinker-code
```

Works on macOS (Intel + Apple Silicon) and Linux (x86_64 + aarch64) — same
formula, brew picks the right Python.

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
   (so `brew tap mohamed-elkholy95/pythinker`).

   ```sh
   gh repo create mohamed-elkholy95/homebrew-pythinker \
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

1. Wait for `pythinker-code <version>` to land on PyPI.
2. Install it into a fresh venv and run `homebrew-pypi-poet` to enumerate
   every transitive dep with PyPI URL + SHA-256.
3. Render `Formula/pythinker-code.rb` from `pythinker-code.rb.tmpl`.
4. Commit + push the formula to `mohamed-elkholy95/homebrew-pythinker` on
   `main` (creating the inaugural commit on first run).
5. Brew users get the new release via `brew upgrade pythinker-code`.

## Manual fallback

If the workflow ever breaks (or the PAT expires), you can regenerate the
formula locally and push it by hand:

```sh
python -m venv /tmp/poet-env
source /tmp/poet-env/bin/activate
pip install pythinker-code==<version> homebrew-pypi-poet

python packages/homebrew-tap/generate-formula.py \
  --version <version> \
  --template packages/homebrew-tap/pythinker-code.rb.tmpl \
  --output /tmp/pythinker-code.rb

# Commit /tmp/pythinker-code.rb into your homebrew-pythinker repo as
# Formula/pythinker-code.rb.
```

## Files

- `pythinker-code.rb.tmpl` — Ruby formula template (do not hand-edit).
- `generate-formula.py` — fetches the PyPI sdist metadata + runs
  `homebrew-pypi-poet` + renders the template.
- (Workflow: `.github/workflows/homebrew-tap.yml`.)
