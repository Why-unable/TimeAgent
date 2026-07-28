import { getAuthToken } from "../../api/auth-token";

export interface AgentStreamEvent<T = Record<string, unknown>> {
  id: string;
  type: string;
  data: T;
}

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const terminalEventTypes = new Set([
  "message.completed",
  "approval.required",
  "run.failed",
  "run.cancelled",
]);
const maxReconnectAttempts = 5;

export async function streamAgentRun(
  runId: string,
  onEvent: (event: AgentStreamEvent) => void,
  options: {
    cursor?: string;
    signal?: AbortSignal;
    onCursor?: (cursor: string) => void;
  } = {},
) {
  let cursor = options.cursor ?? "0";
  let reconnectAttempts = 0;
  while (true) {
    let terminal = false;
    try {
      // Native (token) auth and web (session cookie) auth are mutually
      // exclusive, mirroring api/client.ts: with a token we send the
      // Authorization header and drop cookies (the WebView is cross-origin);
      // otherwise we keep the same-origin session flow for the web client.
      const authToken = getAuthToken();
      const headers: Record<string, string> = {
        Accept: "text/event-stream",
        "Last-Event-ID": cursor,
      };
      if (authToken) headers.Authorization = `Token ${authToken}`;
      const response = await fetch(
        `${baseUrl}/api/v1/chat/runs/${runId}/events/?cursor=${encodeURIComponent(cursor)}`,
        {
          credentials: authToken ? "omit" : "same-origin",
          headers,
          signal: options.signal,
        },
      );
      if (!response.ok || !response.body) {
        throw new Error(`Agent event stream failed with status ${response.status}`);
      }

      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += value ?? "";
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const parsed = parseEvent(frame);
          if (parsed) {
            onEvent(parsed);
            if (parsed.id) {
              cursor = parsed.id;
              options.onCursor?.(cursor);
            }
            terminal ||= terminalEventTypes.has(parsed.type);
          }
        }
        if (done) break;
      }
      if (buffer.trim()) {
        const parsed = parseEvent(buffer);
        if (parsed) {
          onEvent(parsed);
          if (parsed.id) {
            cursor = parsed.id;
            options.onCursor?.(cursor);
          }
          terminal ||= terminalEventTypes.has(parsed.type);
        }
      }
    } catch (reason) {
      if (options.signal?.aborted) throw reason;
      if (reconnectAttempts >= maxReconnectAttempts) throw reason;
    }
    if (terminal) return cursor;
    if (reconnectAttempts >= maxReconnectAttempts) {
      throw new Error("Agent event stream ended before a terminal event");
    }
    reconnectAttempts += 1;
    await reconnectDelay(reconnectAttempts, options.signal);
  }
}

function reconnectDelay(attempt: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(resolve, Math.min(250 * 2 ** (attempt - 1), 2000));
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timeout);
      reject(new DOMException("The operation was aborted", "AbortError"));
    }, { once: true });
  });
}

export function parseEvent(frame: string): AgentStreamEvent | null {
  let id = "";
  let type = "message";
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    if (line.startsWith("event:")) type = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  return { id, type, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
}
