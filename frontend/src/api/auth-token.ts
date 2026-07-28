// Auth token storage for the native (Capacitor) client.
//
// The web build authenticates with same-origin session cookies (ADR-0009) and
// never sets a token, so this module is inert there. The native Android build
// runs from a cross-origin WebView where cookies are unreliable, so it logs in
// via /api/v1/auth/token/ and sends the token in the Authorization header.
//
// Storage is pluggable: the browser/test default uses localStorage but browser
// authentication never writes a token. Native bootstrap replaces it with an
// Android Keystore-backed store before hydration. We keep an in-memory copy so
// apiRequest can read it synchronously without awaiting storage on every call.

export interface TokenStore {
  load(): Promise<string | null>;
  save(token: string): Promise<void>;
  clear(): Promise<void>;
}

const STORAGE_KEY = "time-agent.auth-token";

const localStorageStore: TokenStore = {
  async load() {
    try {
      return globalThis.localStorage?.getItem(STORAGE_KEY) ?? null;
    } catch {
      return null;
    }
  },
  async save(token: string) {
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, token);
    } catch {
      // Storage may be unavailable (private mode); the in-memory copy still works.
    }
  },
  async clear() {
    try {
      globalThis.localStorage?.removeItem(STORAGE_KEY);
    } catch {
      // Ignore — clearing the in-memory copy is what matters for auth state.
    }
  },
};

let store: TokenStore = localStorageStore;
let cachedToken: string | null = null;

/** Replace the backing store (Android Keystore-backed storage on native). */
export function setTokenStore(next: TokenStore): void {
  store = next;
}

/** Restore the browser store and clear memory; intended for test isolation. */
export function resetTokenStore(): void {
  store = localStorageStore;
  cachedToken = null;
}

/** Synchronous read for apiRequest; reflects the last loaded/saved value. */
export function getAuthToken(): string | null {
  return cachedToken;
}

/** Hydrate the in-memory token from persistent storage (call once at boot). */
export async function loadAuthToken(): Promise<string | null> {
  cachedToken = await store.load();
  return cachedToken;
}

export async function setAuthToken(token: string): Promise<void> {
  cachedToken = token;
  await store.save(token);
}

export async function clearAuthToken(): Promise<void> {
  cachedToken = null;
  await store.clear();
}
