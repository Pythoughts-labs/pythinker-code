Search the internet for current information — news, documentation, release notes, blog posts, papers. Returns ranked results with snippets. Results may be limited to a configured set of allowed domains.

**When to use:**
- You need information newer than your training data, or facts you cannot derive from the repository.
- You are looking for the *latest* version, release, or API of something — anchor the query to the current date rather than a year you assume from training.

**Tips:**
- Prefer specific, keyword-rich queries over questions; include the current year when recency matters (e.g. `fastmcp resources API 2026`, not `how does fastmcp work`).
- WebSearch finds pages; to read one in full, follow up with FetchURL on the most promising result.
- If results are empty or off-topic, broaden or rephrase once — do not loop on near-identical queries.

**When NOT to use:**
- For anything answerable from the working directory — read the code and docs first.
- Note: queries may be restricted to allowed domains, so a blocked search returns fewer or no results rather than an error.
