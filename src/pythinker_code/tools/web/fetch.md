Fetch a web page from a URL and extract its main text content.

**When to use:**
- Read the full content of a specific, known URL (a doc page, a changelog, an issue, or a result returned by WebSearch).

**Tips:**
- Use WebSearch first when you do not already have the exact URL, then FetchURL the best result.
- Prefer the most specific/canonical URL (a doc page over a site root) so the extracted text stays on topic.

**When NOT to use / failure modes:**
- Requests may be restricted to a configured set of allowed domains; fetching a disallowed host — including via an HTTP redirect — returns an error rather than content. If you hit this, surface the blocked host to the user instead of retrying the same URL.
- Do not guess or construct URLs. Only fetch URLs the user gave you, that appear in local files, or that WebSearch returned.
