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
  } catch (error) {
    console.warn("Failed to fetch backend version:", error);
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
      } else {
        // Failed or empty fetch: clear the shared promise so a later mount
        // retries instead of reusing a permanently-failed result for the
        // rest of the session.
        serverVersionPromise = null;
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}
