import type { D1Database, ExecutionContext } from "@cloudflare/workers-types";
import { badgeJson, installsJson } from "./badge";
import { incrementCount, readCount } from "./counter";
import { isInstallUserAgent } from "./ua";

export interface Env {
  DB: D1Database;
}

const INSTALL_PATHS = new Set(["/install.sh", "/install.ps1"]);

function json(body: unknown, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json; charset=utf-8", ...extraHeaders },
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/api/installs") {
      const n = await safeRead(env);
      return json(installsJson(n), { "access-control-allow-origin": "*" });
    }

    if (path === "/api/installs/badge") {
      const n = await safeRead(env);
      return json(badgeJson(n), { "cache-control": "public, max-age=300" });
    }

    if (INSTALL_PATHS.has(path)) {
      // Fetch the script from the apex. Cloudflare routes a same-zone
      // subrequest straight to the origin (routes can't be the target of a
      // same-zone fetch), so this does NOT recurse into this Worker. cacheTtl
      // lets the edge cache the script to keep origin load low.
      const origin = `https://pythinker.com${path}${url.search}`;
      const init: RequestInit =
        request.method === "GET"
          ? { method: "GET", headers: request.headers, cf: { cacheEverything: true, cacheTtl: 300 } }
          : { method: request.method, headers: request.headers };
      let res: Response;
      try {
        res = await fetch(origin, init);
      } catch {
        // Origin and its CDN cache are both unavailable. Fail open: never let
        // the Worker throw (that would surface a 1101 error page to curl|bash).
        // Return a harmless shellscript that exits non-zero; do not count.
        return new Response("# install temporarily unavailable\nexit 1\n", {
          status: 503,
          headers: { "content-type": "text/x-shellscript; charset=utf-8" },
        });
      }

      const eligible =
        request.method === "GET" &&
        res.status === 200 &&
        isInstallUserAgent(request.headers.get("user-agent"));

      if (eligible) {
        // Scheduled without awaiting; may continue after the response returns.
        ctx.waitUntil(incrementCount(env.DB).catch(() => {}));
      }
      return res;
    }

    return new Response("Not found", { status: 404 });
  },
};

async function safeRead(env: Env): Promise<number | null> {
  try {
    return await readCount(env.DB);
  } catch {
    return null;
  }
}
