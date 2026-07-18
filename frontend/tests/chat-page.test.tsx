import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "../src/pages/chat-page";

const conversation = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "",
  created_at: "2026-07-17T08:00:00Z",
  updated_at: "2026-07-17T08:00:00Z",
};

const run = {
  id: "22222222-2222-4222-8222-222222222222",
  conversation_id: conversation.id,
  operation_id: "33333333-3333-4333-8333-333333333333",
  request_id: "request-1",
  status: "pending",
  input_message: "今天有什么安排？",
  final_response: "",
  error: "",
  started_at: "2026-07-17T08:00:00Z",
  completed_at: "2026-07-17T08:00:01Z",
  created_at: "2026-07-17T08:00:00Z",
};

function renderChatPage() {
  return render(
    <MemoryRouter initialEntries={["/chat"]}>
      <Routes>
        <Route path="/chat/:conversationId?" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates a conversation and renders tool lifecycle plus final answer", async () => {
    const stream = [
      'id: 1\nevent: agent.started\ndata: {"run_id":"run-1"}\n\n',
      'id: 2\nevent: tool.started\ndata: {"tool_call_id":"tool-1","tool_name":"list_events"}\n\n',
      'id: 3\nevent: tool.completed\ndata: {"tool_call_id":"tool-1","tool_name":"list_events"}\n\n',
      'id: 4\nevent: message.delta\ndata: {"content":"你今天"}\n\n',
      'id: 5\nevent: message.delta\ndata: {"content":"没有安排。"}\n\n',
      'id: 6\nevent: message.completed\ndata: {"content":"你今天没有安排。"}\n\n',
    ].join("");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/conversations/") && method === "GET") {
        return new Response(JSON.stringify([]));
      }
      if (url.endsWith("/conversations/") && method === "POST") {
        return new Response(JSON.stringify(conversation), { status: 201 });
      }
      if (url.endsWith("/messages/")) {
        return new Response(JSON.stringify(run), { status: 202 });
      }
      if (url.endsWith(`/conversations/${conversation.id}/`)) {
        return new Response(JSON.stringify({ ...conversation, title: run.input_message, runs: [run] }));
      }
      if (url.includes(`/runs/${run.id}/events/`)) {
        expect(init?.headers).toEqual(expect.objectContaining({ "Last-Event-ID": "0" }));
        return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChatPage();
    await userEvent.type(screen.getByLabelText("消息"), "今天有什么安排？");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("你今天没有安排。")).toBeInTheDocument();
    expect(screen.getByText("list_events")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes(`/runs/${run.id}/events/?cursor=0`))).toBe(true);
  });

  it("shows a run failure returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith("/conversations/") && (init?.method ?? "GET") === "GET") {
          return new Response(JSON.stringify([]));
        }
        return new Response(JSON.stringify({ detail: "模型暂不可用" }), { status: 503 });
      }),
    );
    renderChatPage();

    await userEvent.type(screen.getByLabelText("消息"), "你好");
    await userEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("模型暂不可用");
  });
});
