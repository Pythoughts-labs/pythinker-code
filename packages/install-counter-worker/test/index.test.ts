import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";

type Stmt = { run: () => Promise<void>; first: () => Promise<{ n: number } | null> };

function makeEnv(opts: { n?: number; throwOnWrite?: boolean } = {}) {
  const run = vi.fn(async () => {
    if (opts.throwOnWrite) throw new Error("D1 down");
  });
  const first = vi.fn(async () => ({ n: opts.n ?? 0 }));
  const prepare = vi.fn((_sql: string): Stmt => ({ run, first }));
  return { env: { DB: { prepare }, DL_HOST: "dl.pythinker.com" } as any, run, prepare };
}

function ctx() {
  const promises: Promise<unknown>[] = [];
  return { waitUntil: (p: Promise<unknown>) => promises.push(p), _promises: promises } as any;
}

const ORIGIN_BODY = "#!/bin/sh\necho install\n";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(ORIGIN_BODY, { status: 200 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("worker router", () => {
  it("increments for a curl UA on a 200 install fetch and serves the script", async () => {
    const { env, run } = makeEnv();
    const c = ctx();
    const res = await worker.fetch(
      new Request("https://pythinker.com/install.sh", { headers: { "user-agent": "curl/8.5.0" } }),
      env,
      c,
    );
    await Promise.all(c._promises);
    expect(res.status).toBe(200);
    expect(await res.text()).toBe(ORIGIN_BODY);
    expect(run).toHaveBeenCalledTimes(1);
    // subrequest hit DL_HOST, never the proxied route (loopback guard)
    expect((fetch as any).mock.calls[0][0]).toContain("dl.pythinker.com/install.sh");
  });

  it("does NOT increment for a browser UA", async () => {
    const { env, run } = makeEnv();
    const c = ctx();
    await worker.fetch(
      new Request("https://pythinker.com/install.sh", { headers: { "user-agent": "Mozilla/5.0 Chrome/124" } }),
      env,
      c,
    );
    await Promise.all(c._promises);
    expect(run).not.toHaveBeenCalled();
  });

  it("does NOT increment when origin returns non-200", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 502 })));
    const { env, run } = makeEnv();
    const c = ctx();
    const res = await worker.fetch(
      new Request("https://pythinker.com/install.sh", { headers: { "user-agent": "curl/8" } }),
      env,
      c,
    );
    await Promise.all(c._promises);
    expect(res.status).toBe(502);
    expect(run).not.toHaveBeenCalled();
  });

  it("does NOT increment for a non-GET method", async () => {
    const { env, run } = makeEnv();
    const c = ctx();
    await worker.fetch(
      new Request("https://pythinker.com/install.sh", { method: "HEAD", headers: { "user-agent": "curl/8" } }),
      env,
      c,
    );
    await Promise.all(c._promises);
    expect(run).not.toHaveBeenCalled();
  });

  it("is fail-open: a D1 write error still serves the script", async () => {
    const { env } = makeEnv({ throwOnWrite: true });
    const c = ctx();
    const res = await worker.fetch(
      new Request("https://pythinker.com/install.sh", { headers: { "user-agent": "curl/8" } }),
      env,
      c,
    );
    await Promise.all(c._promises); // must not reject
    expect(res.status).toBe(200);
    expect(await res.text()).toBe(ORIGIN_BODY);
  });

  it("/api/installs returns JSON with CORS", async () => {
    const { env } = makeEnv({ n: 12345 });
    const res = await worker.fetch(new Request("https://pythinker.com/api/installs"), env, ctx());
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    expect(await res.json()).toEqual({ installs: 12345 });
  });

  it("/api/installs/badge returns shields-endpoint JSON", async () => {
    const { env } = makeEnv({ n: 12345 });
    const res = await worker.fetch(new Request("https://pythinker.com/api/installs/badge"), env, ctx());
    expect(await res.json()).toEqual({
      schemaVersion: 1,
      label: "installs",
      message: "12,345",
      color: "blue",
    });
  });
});
