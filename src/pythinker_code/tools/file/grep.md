A powerful search tool based on ripgrep.

**When to use:**
- Find where a specific symbol, string, or pattern appears across the codebase.

**Tips:**
- ALWAYS use the Grep tool instead of running `grep` or `rg` via the Shell tool.
- Use ripgrep pattern syntax, not grep syntax. E.g. escape braces like `\\{` to search for `{`.
- Hidden files (dotfiles like `.gitlab-ci.yml`, `.eslintrc.json`) are always searched. To also search files excluded by `.gitignore` (e.g. `node_modules`, build outputs), set `include_ignored` to `true`. Sensitive files (such as `.env`) are still skipped for safety, even when `include_ignored` is `true`.

**Scope the search so results fit your context:**
- Narrow with `path`, a `glob`, or a file `type` rather than scanning the whole repo for a common token.
- For "does this exist / where" questions, start with `output_mode="files_with_matches"` to get just the file list, then read the promising files.
- Use `head_limit` to cap matches. A broad pattern — a bare common word, or searching under `node_modules`/`.venv`/`dist` — can return enormous output that floods your context; narrow it first.

**When to escalate:**
- For open-ended investigation that will clearly need more than ~3 searches across many files, delegate to a read-only `explore` subagent (via `Agent`/`RunAgents`) instead of running many Grep calls yourself, to keep your own context clean.
