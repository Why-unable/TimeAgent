import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "../src/pages/chat-page";

vi.mock("../src/features/preferences/hooks", () => ({
  useCurrentUserPreference: () => ({ data: { timezone: "Asia/Shanghai" } }),
}));

const conversation = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "",
  kind: "chat",
  created_at: "2026-07-17T08:00:00Z",
  updated_at: "2026-07-17T08:00:00Z",
};

const run = {
  id: "22222222-2222-4222-8222-222222222222",
  conversation_id: conversation.id,
  operation_id: "33333333-3333-4333-8333-333333333333",
  request_id: "request-1",
  trigger_type: "user_message",
  trigger_payload: {},
  synthetic_input: false,
  status: "pending",
  input_message: "今天有什么安排？",
  final_response: "",
  error: "",
  started_at: "2026-07-17T08:00:00Z",
  completed_at: "2026-07-17T08:00:01Z",
  created_at: "2026-07-17T08:00:00Z",
};

function renderChatPage(initialEntry = "/chat") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
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
      if (url.endsWith("/api/v1/action-proposals/")) {
        return new Response(JSON.stringify([]));
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

  it("renders persisted user and assistant message times in the user timezone", async () => {
    const completedRun = {
      ...run,
      status: "completed",
      final_response: "你今天下午三点有项目会议。",
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/conversations/")) {
        return new Response(JSON.stringify([conversation]));
      }
      if (url.endsWith(`/conversations/${conversation.id}/`)) {
        return new Response(JSON.stringify({ ...conversation, runs: [completedRun] }));
      }
      if (url.endsWith("/api/v1/action-proposals/")) {
        return new Response(JSON.stringify([]));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    const view = renderChatPage(`/chat/${conversation.id}`);

    expect(await screen.findByText(completedRun.final_response)).toBeInTheDocument();
    const timestamps = Array.from(view.container.querySelectorAll("time"));
    expect(timestamps).toHaveLength(2);
    expect(timestamps[0]).toHaveAttribute("datetime", completedRun.created_at);
    expect(timestamps[1]).toHaveAttribute("datetime", completedRun.completed_at);
    expect(timestamps.every((timestamp) => timestamp.textContent?.includes("16:00"))).toBe(true);
  });

  it("separates chat, manual briefing, and scheduled briefing history", async () => {
    const conversations = [
      { ...conversation, title: "普通聊天", kind: "chat" },
      { ...conversation, id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", title: "手动晨间简报", kind: "manual_briefing" },
      { ...conversation, id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", title: "自动晨间简报", kind: "scheduled_briefing" },
    ];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/conversations/")) {
        return new Response(JSON.stringify(conversations));
      }
      if (url.endsWith("/api/v1/action-proposals/")) {
        return new Response(JSON.stringify([]));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderChatPage();

    expect(await screen.findByRole("button", { name: "普通聊天" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "手动晨间简报" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "手动简报" }));
    expect(await screen.findByRole("button", { name: "手动晨间简报" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "自动晨间简报" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "自动简报" }));
    expect(await screen.findByRole("button", { name: "自动晨间简报" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "普通聊天" })).not.toBeInTheDocument();
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

  it("resumes SSE from the approval cursor and renders the final reply", async () => {
    const proposal = {
      id: "44444444-4444-4444-8444-444444444444",
      conversation_id: conversation.id,
      agent_run_id: run.id,
      original_request: "明天下午三点创建项目评审日程",
      explanation: "创建正式日程会占用你的日历时间，需要确认后执行。",
      action_type: "create_event",
      action_payload: {
        title: "项目评审",
        start_at: "2026-07-20T07:00:00Z",
        end_at: "2026-07-20T08:00:00Z",
        timezone: "Asia/Shanghai",
      },
      original_payload: {},
      display_context: { allowed_decisions: ["approve", "edit", "reject"] },
      risk_level: "high",
      status: "awaiting_approval",
      requires_approval: true,
      version: 1,
      expires_at: "2026-07-20T08:00:00Z",
      decided_at: null,
      approved_at: null,
      resumed_at: null,
      executed_at: null,
      decision_reason: "",
      execution_result: null,
      error: "",
      created_at: "2026-07-19T08:00:00Z",
      updated_at: "2026-07-19T08:00:00Z",
    };
    const initialStream = [
      `id: 1\nevent: agent.started\ndata: {"run_id":"${run.id}"}\n\n`,
      'id: 2\nevent: message.delta\ndata: {"content":"没有冲突。"}\n\n',
      `id: 3\nevent: approval.required\ndata: {"proposal_id":"${proposal.id}"}\n\n`,
    ].join("");
    const resumedStream = [
      `id: 4\nevent: agent.resumed\ndata: {"run_id":"${run.id}"}\n\n`,
      'id: 5\nevent: tool.started\ndata: {"tool_call_id":"create-1","tool_name":"create_event"}\n\n',
      'id: 6\nevent: tool.completed\ndata: {"tool_call_id":"create-1","tool_name":"create_event"}\n\n',
      'id: 7\nevent: message.delta\ndata: {"content":"日程已创建。"}\n\n',
      'id: 8\nevent: message.completed\ndata: {"content":"日程已创建。"}\n\n',
    ].join("");
    const streamCursors: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/conversations/") && method === "GET") {
        return new Response(JSON.stringify([conversation]));
      }
      if (url.endsWith(`/conversations/${conversation.id}/`)) {
        return new Response(JSON.stringify({ ...conversation, runs: [run] }));
      }
      if (url.endsWith("/api/v1/action-proposals/")) {
        return new Response(JSON.stringify([proposal]));
      }
      if (url.endsWith(`/api/v1/action-proposals/${proposal.id}/`)) {
        return new Response(JSON.stringify(proposal));
      }
      if (url.endsWith(`/api/v1/action-proposals/${proposal.id}/approve/`)) {
        return new Response(JSON.stringify({
          proposal: { ...proposal, status: "approved", version: 2 },
          resume_queued: true,
        }), { status: 202 });
      }
      if (url.includes(`/runs/${run.id}/events/`)) {
        const cursor = new URL(url, "http://localhost").searchParams.get("cursor") ?? "";
        streamCursors.push(cursor);
        return new Response(cursor === "3" ? resumedStream : initialStream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChatPage(`/chat/${conversation.id}`);
    const approve = await screen.findByRole("button", { name: "批准" });
    await userEvent.click(approve);

    expect(await screen.findByText("日程已创建。")).toBeInTheDocument();
    expect(streamCursors).toEqual(["0", "3"]);
  });
});
