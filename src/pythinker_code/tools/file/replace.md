Replace specific strings within a file. Prefer this over WriteFile for editing existing files.

**When to use:**
- Make a targeted edit to part of an existing text file.

**Tips:**
- Only use this tool on text files.
- Multi-line strings are supported; you can specify a single edit or a list of edits in one call.
- Unless `replace_all` is true, the old string must match **exactly once**. If it appears multiple times the edit fails — add surrounding lines until the match is unique. If it appears zero times the edit fails — re-read the file (its content may differ from what you expect) rather than guessing.
- Prefer this tool over the WriteFile tool and over Shell `sed`/`awk`.
