// Registers the app service worker for offline shell + Web Push.
// Kept idempotent: calling register("/sw.js") repeatedly returns the same
// active registration, so the push flow can safely await it too.

export async function registerServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  // Dev server serves modules via Vite; the SW ships as a static /public file
  // and is meaningful only against the built app, so register it in prod builds.
  if (import.meta.env.DEV) return;
  try {
    await navigator.serviceWorker.register("/sw.js?v=3");
  } catch {
    // Registration failure must never block app startup.
  }
}
