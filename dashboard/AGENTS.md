# Pythinker Dashboard UI (dashboard/)

React 19 + Vite + TypeScript session-tracing visualizer, bundled into the `pythinker-code`
package. It is a read-only viewer of Wire events, context messages, agent state, and subagent
activity. Run all `npm` commands from this directory.

## Critical invariants

- **`dashboard/src/lib/api.ts` is hand-written, not generated** (unlike `web/`, which has a generated
  client). Keep its types (`WireEvent`, `ContextMessage`, `SessionInfo`, `SubagentInfo`) in
  sync by hand with the dashboard backend (`src/pythinker_code/dashboard/`) and the Wire protocol
  (`src/pythinker_code/wire/`) whenever either changes. There is no codegen step here.
- **Do not hand-copy build output.** `scripts/build_dashboard.py` builds and syncs `dashboard/dist` →
  `src/pythinker_code/dashboard/static`. No ad-hoc copy/rsync scripts.
- **Read-only data plane.** It consumes `/api/dashboard/*` from the dashboard backend (port 5495) with a
  Bearer token taken from a URL query param; `cache.ts` dedupes in-flight requests. Do not add
  write/mutation calls here — mutations belong to the web UI / backend, not the visualizer.

## Stack and conventions

- Build: `tsc -b && vite build`; dev: `npm run dev` (or `make dashboard-front`). Backend:
  `make dashboard-back` (port 5495).
- Styling: Tailwind + Radix UI / shadcn; `react-virtuoso` for efficient large-session lists.
- Feature panels live under `src/features/` (`wire-viewer`, `context-viewer`, `agents-panel`,
  `state-viewer`, `sessions-explorer`).
