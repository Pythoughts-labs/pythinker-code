import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ErrorBoundary } from "./components/error-boundary";
import { consumeAuthTokenFromUrl, setAuthToken } from "./lib/auth";
import { pythinkerBrand } from "./lib/brand";

const DYNAMIC_IMPORT_ERROR_PATTERNS: string[] = [
  "Failed to fetch dynamically imported module",
  "Importing a module script failed",
  "Failed to load module script",
  "ChunkLoadError",
];

const isDynamicImportFailure = (error: Error): boolean =>
  DYNAMIC_IMPORT_ERROR_PATTERNS.some((pattern) =>
    error.message.includes(pattern),
  );

const DYNAMIC_IMPORT_RELOAD_KEY = "pythinker:dynamic-import-reload";

const shouldReloadAfterDynamicImportFailure = (): boolean =>
  sessionStorage.getItem(DYNAMIC_IMPORT_RELOAD_KEY) !== "1";

const markDynamicImportReloaded = (): void => {
  sessionStorage.setItem(DYNAMIC_IMPORT_RELOAD_KEY, "1");
};

const setupDynamicImportRecovery = (): void => {
  // Internal UI ships with frequent breaking changes, so if a stale tab hits
  // missing hashed assets we prefer a single automatic refresh to align to
  // the latest build. The session guard avoids infinite reload loops when the
  // failure is due to transient network issues instead of a version mismatch.
  window.addEventListener("vite:preloadError", () => {
    if (shouldReloadAfterDynamicImportFailure()) {
      markDynamicImportReloaded();
      window.location.reload();
    }
  });

  window.addEventListener(
    "unhandledrejection",
    (event: PromiseRejectionEvent) => {
      const { reason } = event;
      if (reason instanceof Error && isDynamicImportFailure(reason)) {
        event.preventDefault();
        if (shouldReloadAfterDynamicImportFailure()) {
          markDynamicImportReloaded();
          window.location.reload();
        }
      }
    },
  );
};

setupDynamicImportRecovery();
// Store the URL token BEFORE React mounts. Doing this in a component effect is
// too late: data-fetching mount effects fire first and would send a stale
// localStorage token from a previous server run, yielding 401s on first load.
const urlToken = consumeAuthTokenFromUrl();
if (urlToken) {
  setAuthToken(urlToken);
}
document.title = pythinkerBrand.appTitle;
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
