import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "../src/pages/chat-page";

vi.mock("../src/features/preferences/hooks", () => ({
  useCurrentUserPreference: () => ({ data: { timezone: "Asia/Shanghai" } }),
}));

vi.mock("../src/features/today/hooks", () => ({
  useTodaySummary: () => ({
    data: {
      events: [],
      planned_tasks: [],
      due_tasks: [],
      overdue_tasks: [],
      pending_reminders: [],
      conflicts: [],
    },
  }),
}));

vi.mock("../src/features/tasks/hooks", () => ({
  useTasks: () => ({ data: [{ id: "task-a", title: "论文修改" }] }),
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
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/chat/:conversationId?" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ChatPage", () => {
  it("prefills an ordinary prompt without sending it", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/conversations/")) return new Response(JSON.stringify([]));
      if (String(input).endsWith("/preferences/me/")) return new Response(JSON.stringify({ timezone: "Asia/Shanghai" }));
      return new Response(JSON.stringify([]));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderChatPage("/chat?prompt=帮我安排今天的任务");
    expect(await screen.findByLabelText("消息")).toHaveValue("帮我安排今天的任务");
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/messages/"))).toBe(false);
  });

  it("sends an explicitly launched insight prompt once and keeps normal prompts editable", async () => {
    const createdConversation = { ...conversation, id: "55555555-5555-4555-8555-555555555555" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/conversations/") && method === "GET") return new Response(JSON.stringify([]));
      if (url.endsWith("/conversations/") && method === "POST") {
        return new Response(JSON.stringify(createdConversation));
      }
      if (url.endsWith("/messages/") && method === "POST") {
        return new Response(JSON.stringify({ ...run, conversation_id: createdConversation.id }));
      }
      if (url.endsWith(`/conversations/${createdConversation.id}/`)) {
        return new Response(JSON.stringify({ ...createdConversation, runs: [] }));
      }
      if (url.endsWith("/action-proposals/")) return new Response(JSON.stringify([]));
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChatPage("/chat?insight_id=insight-1&insight_title=容量风险&auto_send=1");

    await waitFor(() => {
      const messageCall = fetchMock.mock.calls.find(([input, init]) =>
        String(input).endsWith("/messages/") && init?.method === "POST",
      );
      expect(messageCall).toBeDefined();
      expect(JSON.parse(String(messageCall?.[1]?.body)).message)
        .toBe("请基于洞察“容量风险”分析影响并给出可执行选项。洞察 ID：insight-1");
    });
    expect(fetchMock.mock.calls.filter(([input, init]) =>
      String(input).endsWith("/messages/") && init?.method === "POST",
    )).toHaveLength(1);
  });

  it("renders a persisted schedule plan artifact in conversation history", async () => {
    const planId = "66666666-6666-4666-8666-666666666666";
    const completedRun = {
      ...run,
      status: "completed",
      final_response: "已经安排好了。",
      artifacts: [{ artifact_type: "schedule_plan", artifact_id: planId, version: 1 }],
    };
    const latestRun = {
      ...run,
      id: "88888888-8888-4888-8888-888888888888",
      operation_id: "99999999-9999-4999-8999-999999999999",
      request_id: "request-2",
      status: "completed",
      input_message: "请继续调整这个草案",
      final_response: "已打开计划调整。",
      created_at: "2026-07-17T09:00:00Z",
      artifacts: [{ artifact_type: "schedule_plan", artifact_id: planId, version: 1 }],
    };
    const plan = {
      id: planId,
      strategy: "plan_tasks_only",
      items: [{
        task_id: "task-a",
        state: "placed",
        start_at: "2026-07-17T01:00:00Z",
        end_at: "2026-07-17T02:00:00Z",
        segment_index: 1,
        segment_count: 1,
      }],
      constraints_snapshot: {},
      decision_profile_snapshot: {},
      status: "draft",
      version: 1,
      created_at: "2026-07-17T00:00:00Z",
      updated_at: "2026-07-17T00:00:00Z",
      expires_at: "2026-07-18T00:00:00Z",
      applied_at: null,
      abandoned_at: null,
      invalidated_at: null,
      invalidation_reason: "",
    };
    const agentInteraction = {
      id: "77777777-7777-4777-8777-777777777771",
      conversation_id: conversation.id,
      agent_run_id: latestRun.id,
      plan_id: planId,
      plan_version: 1,
      task_id: null,
      type: "priority_ranking",
      payload: { plan_id: planId },
      allowed_actions: ["reorder", "dismiss"],
      status: "pending",
      expires_at: "2026-07-18T00:00:00Z",
      version: 1,
      created_at: "2026-07-17T00:00:00Z",
      updated_at: "2026-07-17T00:00:00Z",
      resolved_at: null,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/conversations/")) return new Response(JSON.stringify([conversation]));
      if (url.endsWith(`/conversations/${conversation.id}/`)) {
        return new Response(JSON.stringify({ ...conversation, runs: [completedRun, latestRun] }));
      }
      if (url.endsWith("/action-proposals/")) return new Response(JSON.stringify([]));
      if (url.endsWith(`/planning/plans/${planId}/`)) return new Response(JSON.stringify(plan));
      if (url.includes(`/api/v1/interactions/?plan_id=${planId}`)) {
        return new Response(JSON.stringify([agentInteraction]));
      }
      if (url.endsWith("/api/v1/interactions/") && method === "POST") {
        const request = JSON.parse(String(init?.body)) as Record<string, string>;
        return new Response(JSON.stringify({
          id: request.type === "priority_ranking"
            ? "77777777-7777-4777-8777-777777777771"
            : "77777777-7777-4777-8777-777777777772",
          conversation_id: conversation.id,
          agent_run_id: run.id,
          plan_id: planId,
          plan_version: 1,
          task_id: null,
          type: request.type,
          payload: { plan_id: planId },
          allowed_actions: ["edit", "reorder", "dismiss"],
          status: "pending",
          expires_at: "2026-07-18T00:00:00Z",
          version: 1,
          created_at: "2026-07-17T00:00:00Z",
          updated_at: "2026-07-17T00:00:00Z",
          resolved_at: null,
        }));
      }
      if (url.endsWith("/api/v1/interactions/telemetry/")) return new Response(null, { status: 202 });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderChatPage(`/chat/${conversation.id}`);

    expect(await screen.findByRole("region", { name: "Agent 计划预览" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "在计划页打开" })).toHaveAttribute("href", `/planning?plan_id=${planId}`);
    expect(screen.getByText("论文修改")).toBeInTheDocument();
    expect(screen.getByText("计划草案")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "本次计划优先顺序" })).toBeInTheDocument();
    expect(await screen.findByText(/助理已准备好“调整本次任务顺序”交互/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "可编辑计划时间线" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).endsWith("/api/v1/interactions/") && init?.method === "POST",
    )).toBe(false);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not auto-focus the composer on mount", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/conversations/")) {
        return new Response(JSON.stringify([]));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderChatPage();
    const composer = await screen.findByLabelText("消息");
    expect(document.activeElement).not.toBe(composer);
  });

  it("quick action populates the composer with a preset prompt", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/conversations/")) {
        return new Response(JSON.stringify([]));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderChatPage();
    const empty = await screen.findByRole("heading", { name: "今天需要我帮你安排什么？" });
    expect(empty).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "今日上下文" })).toHaveTextContent("0 个日程");
    await userEvent.click(screen.getByRole("button", { name: "查询日程" }));
    const composer = screen.getByLabelText("消息") as HTMLTextAreaElement;
    expect(composer.value).toContain("查询");
  });

  it("creates a conversation and renders tool lifecycle plus final answer", async () => {
    const stream = [
      'id: 1\nevent: agent.started\ndata: {"run_id":"run-1"}\n\n',
      'id: 2\nevent: tool.started\ndata: {"tool_call_id":"tool-1","tool_name":"list_events"}\n\n',
      'id: 3\nevent: tool.completed\ndata: {"tool_call_id":"tool-1","tool_name":"list_events"}\n\n',
      'id: 4\nevent: tool.started\ndata: {"tool_call_id":"tool-2","tool_name":"list_tasks"}\n\n',
      'id: 5\nevent: tool.completed\ndata: {"tool_call_id":"tool-2","tool_name":"list_tasks"}\n\n',
      'id: 6\nevent: message.delta\ndata: {"content":"你今天"}\n\n',
      'id: 7\nevent: message.delta\ndata: {"content":"没有安排。"}\n\n',
      'id: 8\nevent: message.completed\ndata: {"content":"你今天没有安排。"}\n\n',
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
    expect(screen.getByText("list_tasks")).toBeInTheDocument();
    expect(screen.getAllByLabelText("执行详情")).toHaveLength(1);
    expect(screen.getAllByText("已完成")).toHaveLength(2);
    const toolPanel = screen.getByLabelText("执行详情");
    expect(toolPanel.querySelector("details")?.open).toBe(false);
    const assistantAnswer = screen.getByText("你今天没有安排。");
    expect(
      toolPanel.compareDocumentPosition(assistantAnswer)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
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

  it("shows a recoverable message instead of a raw API error", async () => {
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

    expect(await screen.findByRole("alert")).toHaveTextContent("消息没有发送成功，请检查连接后重试。");
    expect(screen.queryByText("模型暂不可用")).not.toBeInTheDocument();
  });

  it("does not show Android WebView's fetch error when leaving an active run", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/conversations/")) {
        return Promise.resolve(new Response(JSON.stringify([conversation])));
      }
      if (url.endsWith(`/conversations/${conversation.id}/`)) {
        return Promise.resolve(new Response(JSON.stringify({ ...conversation, runs: [run] })));
      }
      if (url.endsWith("/api/v1/action-proposals/")) {
        return Promise.resolve(new Response(JSON.stringify([])));
      }
      if (url.includes(`/runs/${run.id}/events/`)) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new Error("The user aborted a request."));
          }, { once: true });
        });
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    }));

    renderChatPage(`/chat/${conversation.id}`);
    await screen.findByText(run.input_message);
    await userEvent.click(screen.getAllByRole("button", { name: "新建聊天" })[0]);

    expect(await screen.findByRole("heading", { name: "今天需要我帮你安排什么？" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("The user aborted a request.")).not.toBeInTheDocument();
  });

  it("shows a persisted failure reason and request reference with readable colors", async () => {
    const failedRun = {
      ...run,
      status: "failed",
      error: "模型服务响应超时，请检查网络后重试。",
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/conversations/")) return new Response(JSON.stringify([conversation]));
      if (url.endsWith(`/conversations/${conversation.id}/`)) {
        return new Response(JSON.stringify({ ...conversation, runs: [failedRun] }));
      }
      if (url.endsWith("/api/v1/action-proposals/")) return new Response(JSON.stringify([]));
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderChatPage(`/chat/${conversation.id}`);
    const notice = await screen.findByText("这次没有完成请求。请重试；如果问题持续，请稍后再试。");
    expect(notice).not.toHaveTextContent("request-1");
    expect(notice).not.toHaveTextContent("模型服务响应超时");
    expect(notice).toHaveClass("bg-red-50", "text-red-900");
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
    const approve = await screen.findByRole("button", { name: "确认并应用" });
    await userEvent.click(approve);

    expect(await screen.findByText("日程已创建。")).toBeInTheDocument();
    expect(streamCursors).toEqual(["0", "3"]);
  });
});
