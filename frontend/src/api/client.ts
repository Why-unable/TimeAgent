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

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const timeoutMs = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 5000);

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
  const requestId = crypto.randomUUID();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", requestId);

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const csrfToken = getCookie("csrftoken");
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(init.method?.toUpperCase() ?? "GET")) {
    headers.set("X-CSRFToken", decodeURIComponent(csrfToken));
  }

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "same-origin",
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
