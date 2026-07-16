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

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const requestId = crypto.randomUUID();

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Request-ID": requestId,
        ...init.headers,
      },
      signal: init.signal ?? controller.signal,
    });

    if (!response.ok) {
      throw new ApiError(
        `Request failed with status ${response.status}`,
        response.status,
        response.headers.get("X-Request-ID") ?? requestId,
      );
    }

    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

