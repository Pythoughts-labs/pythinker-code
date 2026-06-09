# Pythinker Web UI (web/)

React 19 + Vite 7 + TypeScript SPA chat UI, bundled into the `pythinker-code` package. Run all
`npm` commands from this directory.

## Critical invariants

- **Do not hand-edit `web/src/lib/api/`.** It is a generated OpenAPI client (`runtime.ts`,
  `apis/`, `models/` — note the `tslint/eslint-disable` headers). To change it, edit the
  backend Pydantic models / routes under `src/pythinker_code/web/`, start the backend
  (`make web-back`, port 5494), then regenerate with `npm run generate`
  (`web/scripts/generate-api.sh` — needs Docker; it fetches `/openapi.json`, rewrites
  `web/openapi.json`, and `rm -rf src/lib/api` before regenerating).
- **Do not hand-copy build output.** `scripts/build_web.py` (`make build-web`) builds and
  syncs `web/dist` → `src/pythinker_code/web/static`. Never write ad-hoc copy/rsync scripts to
  move assets.
- **The real-time session stream is JSON-RPC over WebSocket, not REST.** Live updates flow
  through the Wire protocol (`src/hooks/wireTypes.ts`, `src/hooks/useSessionStream.ts`); the
  generated REST client is for non-streaming calls. Don't substitute polling/REST for the
  stream.

## Stack and conventions

- Build: `tsc -b && vite build`; dev: `npm run dev` (or `make web-front`). Lint/format: Biome
  (`biome check`), not ESLint/Prettier.
- Styling: Tailwind v4 + Radix UI / shadcn; compose class names with the `cn()` helper.
- State: Zustand stores; React hooks (`useSessions`, `useSessionStream`) for REST + WebSocket.
- Auth token arrives as a URL param, is stripped from the URL, persisted ~24h in
  `localStorage`, and sent as a Bearer header — never log it. Treat streamed model output as
  untrusted when rendering (XSS surface).
