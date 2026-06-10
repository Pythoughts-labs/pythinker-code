import { useEffect, useState } from "react";
import { apiClient } from "@/lib/apiClient";
import { pythinkerCliVersion } from "@/lib/version";

// The build-time constant goes stale when the CLI is upgraded without a
// frontend rebuild, so prefer the version the running backend reports.
let cachedServerVersion: string | null = null;
let serverVersionPromise: Promise<string | null> | null = null;

async function fetchServerVersion(): Promise<string | null> {
  try {
    const config = await apiClient.config.getGlobalConfigApiConfigGet();
    return config.version || null;
  } catch {
    return null;
  }
}

export function usePythinkerVersion(): string {
  const [version, setVersion] = useState(
    cachedServerVersion ?? pythinkerCliVersion,
  );

  useEffect(() => {
    if (cachedServerVersion) {
      return;
    }
    let cancelled = false;
    serverVersionPromise ??= fetchServerVersion();
    serverVersionPromise.then((serverVersion) => {
      if (serverVersion) {
        cachedServerVersion = serverVersion;
        if (!cancelled) {
          setVersion(serverVersion);
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}
