List the resources and prompt templates published by connected MCP servers.

Use this to discover readable resources (documents, database views, files exposed
over MCP) and prompt templates before reading one with ReadMcpResource. Pass
`server` to scope to a single server, or omit it to see everything.

When to use:
- The user references an MCP server's data ("read the schema from the db server").
- You need to know what a connected MCP server exposes beyond its tools.

When NOT to use:
- To call an MCP tool — those are already in your toolset; call them directly.
- For local files — use ReadFile/Grep instead.

This is read-only and always available.
