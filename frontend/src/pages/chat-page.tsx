import {
  Bot,
  ChevronRight,
  CircleStop,
  History,
  LoaderCircle,
  Menu,
  MessageSquare,
  Newspaper,
  Plus,
  Send,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  cancelAgentRun,
  createConversation,
  getConversation,
  listConversations,
  sendChatMessage,
  type AgentRun,
  type Conversation,
} from "../api/chat";
import {
  decideActionProposal,
  getActionProposal,
  listActionProposals,
  type ActionProposal,
} from "../api/action-proposals";
import { ApprovalCard } from "../components/approvals/approval-card";
import { ChatEmptyState } from "../components/chat/chat-empty-state";
import { MarkdownMessage } from "../components/chat/markdown-message";
import { streamAgentRun, type AgentStreamEvent } from "../features/agent-runs/sse-client";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { formatInUserTimezone, formatTimeInUserTimezone, getLocalDateKey } from "../utils/datetime";

type ChatEntry =
  | { id: string; kind: "user" | "assistant"; content: string; timestamp: string }
  | { id: string; kind: "notice"; content: string; tone: "error" | "muted" }
  | {
      id: string;
      kind: "tool";
      runId: string;
      name: string;
      status: "running" | "completed" | "failed";
    }
  | { id: string; kind: "approval"; proposal: ActionProposal };

type ConversationGroup = { label: string; conversations: Conversation[] };
type ConversationKind = Conversation["kind"];
type ToolEntry = Extract<ChatEntry, { kind: "tool" }>;

const ACTIVE_RUN_STATUSES = new Set(["pending", "running"]);

function ToolActivityPanel({ tools }: { tools: ToolEntry[] }) {
  return (
    <section
      aria-label="工具调用记录"
      className="max-h-28 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm"
    >
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700">
        <Wrench size={14} />
        <span className="flex-1">工具调用</span>
        <span className="font-normal text-slate-500">{tools.length} 项</span>
      </header>
      <div className="divide-y divide-slate-100">
        {tools.map((tool) => (
          <div key={tool.id} className="flex items-center gap-2 px-3 py-2 text-xs">
            {tool.status === "running" ? (
              <LoaderCircle className="shrink-0 animate-spin text-teal-600" size={14} />
            ) : (
              <Wrench className="shrink-0 text-slate-500" size={14} />
            )}
            <span className="min-w-0 flex-1 truncate font-medium text-slate-800">
              {tool.name}
            </span>
            <span
              className={
                tool.status === "failed"
                  ? "text-red-600"
                  : tool.status === "completed"
                    ? "text-teal-700"
                    : "text-amber-700"
              }
            >
              {tool.status === "running"
                ? "执行中"
                : tool.status === "completed"
                  ? "已完成"
                  : "失败"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function entriesFromRuns(runs: AgentRun[]): ChatEntry[] {
  return runs.flatMap((run) => {
    const entries: ChatEntry[] = run.synthetic_input
      ? [{ id: `trigger-${run.id}`, kind: "notice", content: run.input_message, tone: "muted" }]
      : [{ id: `user-${run.id}`, kind: "user", content: run.input_message, timestamp: run.created_at }];
    if (run.final_response) {
      entries.push({
        id: `assistant-${run.id}`,
        kind: "assistant",
        content: run.final_response,
        timestamp: run.completed_at ?? run.created_at,
      });
    } else if (run.status === "failed") {
      entries.push({ id: `notice-${run.id}`, kind: "notice", content: "这次回复生成失败。", tone: "error" });
    } else if (run.status === "cancelled") {
      entries.push({ id: `notice-${run.id}`, kind: "notice", content: "这次运行已取消。", tone: "muted" });
    }
    return entries;
  });
}

function formatChatTimestamp(value: string, timezone: string, now = new Date()): string {
  if (getLocalDateKey(value, timezone) === getLocalDateKey(now, timezone)) {
    return formatTimeInUserTimezone(value, timezone);
  }
  return formatInUserTimezone(value, timezone);
}

function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const sevenDaysAgo = startOfToday - 6 * 24 * 60 * 60 * 1000;
  const groups: ConversationGroup[] = [
    { label: "今天", conversations: [] },
    { label: "最近 7 天", conversations: [] },
    { label: "更早", conversations: [] },
  ];
  for (const conversation of conversations) {
    const updatedAt = new Date(conversation.updated_at).getTime();
    const group = updatedAt >= startOfToday ? groups[0] : updatedAt >= sevenDaysAgo ? groups[1] : groups[2];
    group.conversations.push(conversation);
  }
  return groups.filter((group) => group.conversations.length > 0);
}

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const preference = useCurrentUserPreference();
  const timezone = preference.data?.timezone
    ?? import.meta.env.VITE_DEFAULT_TIMEZONE
    ?? "Asia/Shanghai";
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyKind, setHistoryKind] = useState<ConversationKind>("chat");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const runCursors = useRef(new Map<string, string>());
  const messagesEnd = useRef<HTMLDivElement | null>(null);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const composer = useRef<HTMLFormElement | null>(null);
  const [composerOffset, setComposerOffset] = useState(0);

  // Keep the composer above the software keyboard by tracking visualViewport.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const handler = () => {
      const delta = window.innerHeight - vv.height - vv.offsetTop;
      setComposerOffset(delta > 24 ? delta : 0);
    };
    vv.addEventListener("resize", handler);
    vv.addEventListener("scroll", handler);
    handler();
    return () => {
      vv.removeEventListener("resize", handler);
      vv.removeEventListener("scroll", handler);
    };
  }, []);

  const handleQuickAction = useCallback((prompt: string) => {
    setMessage((current) => (current.trim() ? current : prompt));
    // Focus is intentional here because the user just tapped a button.
    textarea.current?.focus();
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载历史对话");
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  const refreshApprovalEntries = useCallback(async (activeRunId: string) => {
    const proposals = (await listActionProposals()).filter(
      (proposal) => proposal.agent_run_id === activeRunId,
    );
    const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
    setEntries((current) => current.map((entry) =>
      entry.kind === "approval" && byId.has(entry.proposal.id)
        ? { ...entry, proposal: byId.get(entry.proposal.id)! }
        : entry,
    ));
  }, []);

  const applyEvent = useCallback((activeRunId: string, event: AgentStreamEvent) => {
    const callId = String(event.data.tool_call_id ?? event.id);
    const toolName = String(event.data.tool_name ?? "tool");
    const assistantId = `assistant-${activeRunId}`;
    const eventTimestamp = typeof event.data.event_created_at === "string"
      ? event.data.event_created_at
      : new Date().toISOString();
    if (event.type === "tool.started") {
      setEntries((current) => current.some((entry) => entry.kind === "tool" && entry.id === callId)
        ? current
        : [...current, {
          id: callId,
          kind: "tool",
          runId: activeRunId,
          name: toolName,
          status: "running",
        }]);
    } else if (event.type === "tool.completed" || event.type === "tool.failed") {
      setEntries((current) => current.map((entry) =>
        entry.kind === "tool" && entry.id === callId
          ? { ...entry, status: event.type === "tool.completed" ? "completed" : "failed" }
          : entry,
      ));
    } else if (event.type === "briefing.section.started") {
      const section = String(event.data.section ?? "section");
      const id = `briefing-section-${activeRunId}-${section}`;
      setEntries((current) => current.some((entry) => entry.kind === "tool" && entry.id === id)
        ? current
        : [...current, {
          id,
          kind: "tool",
          runId: activeRunId,
          name: `简报 · ${section === "calendar" ? "日程" : "任务"}`,
          status: "running",
        }]);
    } else if (event.type === "briefing.section.completed") {
      const section = String(event.data.section ?? "section");
      const id = `briefing-section-${activeRunId}-${section}`;
      setEntries((current) => current.map((entry) => entry.kind === "tool" && entry.id === id
        ? { ...entry, status: event.data.status === "completed" ? "completed" : "failed" }
        : entry));
    } else if (event.type === "message.delta") {
      const delta = String(event.data.content ?? "");
      setEntries((current) => {
        const exists = current.some((entry) => entry.kind === "assistant" && entry.id === assistantId);
        if (!exists) {
          return [...current, {
            id: assistantId,
            kind: "assistant",
            content: delta,
            timestamp: eventTimestamp,
          }];
        }
        return current.map((entry) => entry.kind === "assistant" && entry.id === assistantId
          ? { ...entry, content: entry.content + delta }
          : entry);
      });
    } else if (event.type === "message.completed") {
      const content = String(event.data.content ?? "");
      setEntries((current) => {
        const exists = current.some((entry) => entry.kind === "assistant" && entry.id === assistantId);
        if (!exists) {
          return [...current, {
            id: assistantId,
            kind: "assistant",
            content,
            timestamp: eventTimestamp,
          }];
        }
        return current.map((entry) => entry.kind === "assistant" && entry.id === assistantId
          ? { ...entry, content, timestamp: eventTimestamp }
          : entry);
      });
    } else if (event.type === "approval.required") {
      const proposalId = String(event.data.proposal_id ?? "");
      if (proposalId) {
        void getActionProposal(proposalId).then((proposal) => {
          setEntries((current) => current.some(
            (entry) => entry.kind === "approval" && entry.proposal.id === proposal.id,
          ) ? current : [...current, { id: `approval-${proposal.id}`, kind: "approval", proposal }]);
        }).catch((reason) => {
          setError(reason instanceof Error ? reason.message : "无法加载审批操作");
        });
      }
    } else if (event.type === "run.failed") {
      setError(String(event.data.error ?? "Agent 运行失败"));
    } else if (event.type === "run.cancelled") {
      setError("Agent 运行已取消");
    }
  }, []);

  const consumeRun = useCallback(async (activeRunId: string, abortController: AbortController) => {
    setRunId(activeRunId);
    setBusy(true);
    try {
      await streamAgentRun(activeRunId, (event) => applyEvent(activeRunId, event), {
        cursor: runCursors.current.get(activeRunId) ?? "0",
        signal: abortController.signal,
        onCursor: (cursor) => runCursors.current.set(activeRunId, cursor),
      });
      await refreshApprovalEntries(activeRunId);
      void refreshConversations();
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(reason instanceof Error ? reason.message : "实时回复连接中断");
      }
    } finally {
      if (!abortController.signal.aborted) {
        setBusy(false);
        setRunId(null);
        controller.current = null;
      }
    }
  }, [applyEvent, refreshApprovalEntries, refreshConversations]);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    controller.current?.abort();
    controller.current = null;
    setRunId(null);
    setBusy(false);
    setError("");
    setHistoryOpen(false);

    if (!conversationId) {
      setEntries([]);
      setLoadingHistory(false);
      return;
    }

    const loadController = new AbortController();
    setLoadingHistory(true);
    void Promise.all([getConversation(conversationId), listActionProposals()])
      .then(([conversation, proposals]) => {
        if (loadController.signal.aborted) return;
        const approvalEntries: ChatEntry[] = proposals
          .filter((proposal) => proposal.conversation_id === conversation.id)
          .map((proposal) => ({ id: `approval-${proposal.id}`, kind: "approval", proposal }));
        setEntries([...entriesFromRuns(conversation.runs), ...approvalEntries]);
        const activeRun = [...conversation.runs].reverse().find((run) => ACTIVE_RUN_STATUSES.has(run.status));
        if (activeRun) {
          const streamController = new AbortController();
          controller.current = streamController;
          void consumeRun(activeRun.id, streamController);
        }
      })
      .catch((reason) => {
        if (loadController.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "无法加载这段对话");
      })
      .finally(() => {
        if (!loadController.signal.aborted) setLoadingHistory(false);
      });

    return () => {
      loadController.abort();
      controller.current?.abort();
    };
  }, [consumeRun, conversationId]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView?.({ behavior: entries.length > 2 ? "smooth" : "auto" });
  }, [entries, busy]);

  const groups = useMemo(
    () => groupConversations(conversations.filter((item) => item.kind === historyKind)),
    [conversations, historyKind],
  );
  const activeConversation = conversations.find((conversation) => conversation.id === conversationId);

  useEffect(() => {
    if (activeConversation) setHistoryKind(activeConversation.kind);
  }, [activeConversation]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const content = message.trim();
    if (!content || busy) return;
    setMessage("");
    setError("");
    setBusy(true);
    try {
      const conversation = conversationId ? null : await createConversation();
      const activeConversationId = conversationId ?? conversation?.id;
      if (!activeConversationId) throw new Error("无法创建会话");
      const run = await sendChatMessage(activeConversationId, content);

      if (!conversationId) {
        navigate(`/chat/${activeConversationId}`);
        void refreshConversations();
        return;
      }

      setEntries((current) => [
        ...current,
        { id: `user-${run.id}`, kind: "user", content, timestamp: run.created_at },
      ]);
      const streamController = new AbortController();
      controller.current = streamController;
      await consumeRun(run.id, streamController);
    } catch (reason) {
      setBusy(false);
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(reason instanceof Error ? reason.message : "发送失败");
      }
    }
  };

  const cancel = async () => {
    controller.current?.abort();
    if (runId) await cancelAgentRun(runId).catch(() => undefined);
    setError("Agent 运行已取消");
    setBusy(false);
    setRunId(null);
  };

  const handleProposalDecision = async (
    proposal: ActionProposal,
    decision: "approve" | "edit" | "reject",
    options?: { actionPayload?: Record<string, unknown>; reason?: string },
  ) => {
    setError("");
    const response = await decideActionProposal(proposal, decision, options);
    setEntries((current) => current.map((entry) =>
      entry.kind === "approval" && entry.proposal.id === proposal.id
        ? { ...entry, proposal: response.proposal }
        : entry,
    ));
    if (response.resume_queued) {
      const streamController = new AbortController();
      controller.current = streamController;
      await consumeRun(proposal.agent_run_id, streamController);
    }
    return response;
  };

  const startNewChat = () => {
    if (busy) controller.current?.abort();
    navigate("/chat");
    setHistoryKind("chat");
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // On touch devices the software keyboard has no practical Shift+Enter
    // affordance. Keep Return as a newline and use the visible send button.
    if (navigator.maxTouchPoints > 0) return;
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const historyPanel = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 p-3">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-200"><History size={16} /> 对话历史</p>
        <button type="button" onClick={() => setHistoryOpen(false)} aria-label="关闭对话历史" className="rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-white lg:hidden"><X size={18} /></button>
      </div>
      <div className="p-3">
        <button type="button" onClick={startNewChat} className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-3 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-200">
          <Plus size={17} /> 新建聊天
        </button>
      </div>
      <div className="grid grid-cols-3 gap-1 px-3 pb-2" aria-label="会话类型">
        {([
          ["chat", "聊天"],
          ["manual_briefing", "手动简报"],
          ["scheduled_briefing", "自动简报"],
        ] as const).map(([kind, label]) => (
          <button
            type="button"
            key={kind}
            onClick={() => setHistoryKind(kind)}
            className={`rounded-lg px-2 py-2 text-[11px] ${historyKind === kind ? "bg-cyan-400/15 text-cyan-200" : "text-slate-500 hover:bg-white/5"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <nav aria-label="对话历史" className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loadingConversations && <p className="px-3 py-4 text-xs text-slate-500">正在加载历史对话…</p>}
        {!loadingConversations && groups.length === 0 && <p className="px-3 py-4 text-xs leading-5 text-slate-500">此分类下还没有会话。</p>}
        {groups.map((group) => (
          <div key={group.label} className="mt-3 first:mt-0">
            <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-slate-500">{group.label}</p>
            <div className="space-y-1">
              {group.conversations.map((conversation) => (
                <button
                  type="button"
                  key={conversation.id}
                  onClick={() => navigate(`/chat/${conversation.id}`)}
                  aria-current={conversation.id === conversationId ? "page" : undefined}
                  className={`group flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition ${conversation.id === conversationId ? "bg-cyan-400/10 text-cyan-100" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}
                >
                  {conversation.kind === "chat" ? <MessageSquare size={15} className="shrink-0 opacity-60" /> : <Newspaper size={15} className="shrink-0 opacity-60" />}
                  <span className="min-w-0 flex-1 truncate">{conversation.title || "新对话"}</span>
                  {conversation.id === conversationId && <ChevronRight size={14} className="shrink-0 text-cyan-300" />}
                </button>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );

  return (
    <section className="-mx-5 flex h-[calc(100dvh-8.25rem)] min-h-[32rem] overflow-hidden bg-transparent lg:mx-auto lg:h-[calc(100vh-7rem)] lg:max-w-7xl lg:rounded-2xl lg:border lg:border-white/10 lg:bg-slate-900/40">
      <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-slate-950/40 lg:block">{historyPanel}</aside>
      {historyOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button type="button" aria-label="关闭对话历史" onClick={() => setHistoryOpen(false)} className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm" />
          <aside className="relative h-full w-[min(20rem,85vw)] border-r border-white/10 bg-slate-950 shadow-2xl">{historyPanel}</aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-white/10 px-4 py-3 sm:px-6 lg:px-4">
          <button type="button" onClick={() => setHistoryOpen(true)} aria-label="打开对话历史" className="rounded-2xl bg-white/5 p-3 text-slate-300 hover:bg-white/10 hover:text-white lg:hidden"><Menu size={24} /></button>
          <Bot className="shrink-0 text-cyan-300" size={27} />
          <div className="min-w-0">
            <h2 className="truncate text-xl font-semibold text-slate-100">{activeConversation?.title || "智能时间助理"}</h2>
            <p className="mt-0.5 text-base text-slate-500">{activeConversation?.kind === "manual_briefing" ? "用户手动简报" : activeConversation?.kind === "scheduled_briefing" ? "自动简报" : "Time Steward"}</p>
          </div>
          {conversationId && <button type="button" onClick={startNewChat} className="ml-auto hidden items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 sm:flex"><Plus size={15} /> 新建聊天</button>}
        </header>

        <div aria-live="polite" aria-busy={loadingHistory || busy} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5 sm:px-8 lg:px-4">
          {loadingHistory && <p className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500"><LoaderCircle className="animate-spin" size={16} /> 正在加载对话…</p>}
          {!loadingHistory && entries.length === 0 && (
            <ChatEmptyState onQuickAction={handleQuickAction} />
          )}
          {entries.map((entry) => {
            if (entry.kind === "approval") {
              return (
                <div key={entry.id} className="w-full lg:mx-auto lg:max-w-3xl">
                  <ApprovalCard
                    proposal={entry.proposal}
                    busy={busy}
                    onDecision={(decision, options) => handleProposalDecision(
                      entry.proposal,
                      decision,
                      options,
                    )}
                  />
                </div>
              );
            }
            if (entry.kind === "tool") {
              const runTools = entries.filter(
                (candidate): candidate is ToolEntry =>
                  candidate.kind === "tool" && candidate.runId === entry.runId,
              );
              const assistantExists = entries.some(
                (candidate) =>
                  candidate.kind === "assistant"
                  && candidate.id === `assistant-${entry.runId}`,
              );
              if (assistantExists || runTools[0]?.id !== entry.id) {
                return null;
              }
              return (
                <div key={entry.id} className="w-full lg:mx-auto lg:max-w-3xl">
                  <ToolActivityPanel tools={runTools} />
                </div>
              );
            }
            if (entry.kind === "notice") {
              return <p key={entry.id} className={`w-full rounded-xl border px-4 py-3 text-sm lg:mx-auto lg:max-w-xl ${entry.tone === "error" ? "border-red-400/30 bg-red-400/10 text-red-100" : "border-white/10 bg-white/5 text-slate-400"}`}>{entry.content}</p>;
            }
            const assistantRunId = entry.kind === "assistant"
              ? entry.id.replace(/^assistant-/, "")
              : "";
            const runTools = assistantRunId
              ? entries.filter(
                (candidate): candidate is ToolEntry =>
                  candidate.kind === "tool" && candidate.runId === assistantRunId,
              )
              : [];
            return (
              <div key={entry.id} className="w-full space-y-2 lg:mx-auto lg:max-w-3xl">
                {entry.kind === "assistant" && runTools.length > 0 && (
                  <ToolActivityPanel tools={runTools} />
                )}
                <article className={`flex w-full gap-3 ${entry.kind === "user" ? "justify-end" : "justify-start"}`}>
                {entry.kind === "assistant" && <Bot className="mt-2 shrink-0 text-cyan-300" size={18} />}
                {entry.kind === "user" ? (
                  <div className="max-w-[88%] sm:max-w-[85%]">
                    <p className="whitespace-pre-wrap rounded-2xl bg-cyan-400/15 px-4 py-3 text-base leading-6 text-cyan-50">{entry.content}</p>
                    <time
                      dateTime={entry.timestamp}
                      title={formatInUserTimezone(entry.timestamp, timezone)}
                      className="mt-1.5 block pr-1 text-right text-[11px] text-slate-600"
                    >
                      {formatChatTimestamp(entry.timestamp, timezone)}
                    </time>
                  </div>
                ) : (
                  <div className="min-w-0 flex-1 lg:max-w-[85%]">
                    <div className="rounded-2xl bg-white/5 px-4 py-3 lg:px-4 lg:py-3">
                      <MarkdownMessage content={entry.content} />
                    </div>
                    <time
                      dateTime={entry.timestamp}
                      title={formatInUserTimezone(entry.timestamp, timezone)}
                      className="mt-1.5 block pl-1 text-[11px] text-slate-600"
                    >
                      {formatChatTimestamp(entry.timestamp, timezone)}
                    </time>
                  </div>
                )}
                {entry.kind === "user" && <UserRound className="mt-2 shrink-0 text-slate-400" size={18} />}
                </article>
              </div>
            );
          })}
          {busy && <p className="mx-auto flex max-w-3xl items-center gap-2 text-sm text-slate-400"><LoaderCircle className="animate-spin" size={16} /> Time Steward 正在处理…</p>}
          {error && <p role="alert" className="mx-auto max-w-3xl rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-100">{error}</p>}
          <div ref={messagesEnd} />
        </div>

        <form
          ref={composer}
          onSubmit={submit}
          style={{ transform: composerOffset ? `translateY(-${composerOffset}px)` : undefined }}
          className="border-t border-white/10 bg-slate-950/95 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 transition-transform sm:p-4 lg:p-3"
        >
          <div className="mx-4 flex max-w-none items-end gap-2 rounded-3xl border border-white/10 bg-slate-900 p-3 shadow-xl focus-within:border-cyan-300/40 sm:mx-auto sm:max-w-3xl">
            <label className="sr-only" htmlFor="chat-message">消息</label>
            <textarea ref={textarea} id="chat-message" rows={1} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={handleComposerKeyDown} disabled={busy || loadingHistory} placeholder="输入你的时间管理请求…" className="max-h-40 min-h-14 flex-1 resize-none bg-transparent px-3 py-3 text-lg outline-none disabled:opacity-60" />
            {busy ? (
              <button type="button" onClick={cancel} aria-label="停止运行" className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-red-400/15 text-red-200"><CircleStop size={24} /></button>
            ) : (
              <button type="submit" aria-label="发送消息" disabled={!message.trim() || loadingHistory} className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-cyan-300 text-slate-950 disabled:opacity-40"><Send size={24} /></button>
            )}
          </div>
        </form>
      </div>
    </section>
  );
}
