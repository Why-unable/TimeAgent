export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

import { getAuthToken } from "./auth-token";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const timeoutMs = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 5000);

function createRequestId(): string {
  const cryptography = globalThis.crypto;
  if (typeof cryptography?.randomUUID === "function") {
    return cryptography.randomUUID();
  }
  if (typeof cryptography?.getRandomValues === "function") {
    const bytes = cryptography.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }
  return `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getCookie(name: string): string | undefined {
  return document.cookie
    .split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const requestId = createRequestId();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", requestId);

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Native (token) auth and web (session cookie) auth are mutually exclusive.
  // When a token is present we send it in the Authorization header and skip
  // cookies + CSRF entirely, since the native WebView is cross-origin. Otherwise
  // we preserve the existing same-origin session + CSRF flow unchanged.
  const authToken = getAuthToken();
  if (authToken) {
    headers.set("Authorization", `Token ${authToken}`);
  } else {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(init.method?.toUpperCase() ?? "GET")) {
      headers.set("X-CSRFToken", decodeURIComponent(csrfToken));
    }
  }

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: authToken ? "omit" : "same-origin",
      headers,
      signal: init.signal ?? controller.signal,
    });

    if (!response.ok) {
      let message = `Request failed with status ${response.status}`;
      try {
        const body = (await response.clone().json()) as Record<string, unknown>;
        if (typeof body.detail === "string") {
          message = body.detail;
        } else {
          const firstMessage = Object.values(body).flat().find((value) => typeof value === "string");
          if (typeof firstMessage === "string") message = firstMessage;
        }
      } catch {
        // The status-based fallback remains useful for non-JSON responses.
      }
      throw new ApiError(
        message,
        response.status,
        response.headers.get("X-Request-ID") ?? requestId,
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}
