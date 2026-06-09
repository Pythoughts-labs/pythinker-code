Write content to a file, creating it or overwriting/appending to an existing one.

**When to use:**
- Create a genuinely new file, or fully replace a file whose entire contents you are rewriting.

**When NOT to use:**
- To change part of an existing file, prefer StrReplaceFile — it is safer (exact-match) and avoids accidentally dropping content you did not mean to touch. Never blindly recreate a large existing file from memory with WriteFile.
- Do not proactively create documentation (`README`, `*.md`) unless the user asked for it.

**Tips:**
- When `mode` is not specified, it defaults to `overwrite`. Always write with caution.
- When the content to write is too long (e.g. > 100 lines), use this tool multiple times instead of a single call: `overwrite` mode for the first write, then `append` mode for the rest.
