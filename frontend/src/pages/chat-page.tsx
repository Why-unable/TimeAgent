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
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  cancelAgentRun,
  createConversation,
  getConversation,
  listConversations,
  sendChatMessage,
  type AgentRun,
  type Conversation,
} from "../api/chat";
import { getSchedulePlan, type SchedulePlan } from "../api/planning";
import {
  decideActionProposal,
  getActionProposal,
  listActionProposals,
  type ActionProposal,
} from "../api/action-proposals";
import { ApprovalCard } from "../components/approvals/approval-card";
import { ChatEmptyState } from "../components/chat/chat-empty-state";
import { Drawer } from "../components/overlay/drawer";
import { MarkdownMessage } from "../components/chat/markdown-message";
import { PlanPreview, type PlanPreviewItem } from "../components/planning/plan-preview";
import type { TodaySummary } from "../api/today";
import { streamAgentRun, type AgentStreamEvent } from "../features/agent-runs/sse-client";
import { useTodaySummary } from "../features/today/hooks";
import { useCurrentUserPreference } from "../features/preferences/hooks";
import { useTasks } from "../features/tasks/hooks";
import { formatInUserTimezone, formatTimeInUserTimezone, getLocalDateKey } from "../utils/datetime";

type ChatEntry =
  | { id: string; kind: "user" | "assistant"; content: string; timestamp: string }
  | { id: string; kind: "notice"; content: string; tone: "error" | "muted" }
  | {
      id: string;
      kind: "schedule_plan";
      planId: string;
      version: number;
      conversationId?: string;
      agentRunId?: string;
      agentRunActive?: boolean;
      plan?: SchedulePlan;
      state: "loading" | "loaded" | "failed";
    }
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

const toolActivities: Record<string, string> = {
  list_events: "正在读取你的日程…",
  list_tasks: "正在读取你的任务…",
  get_planning_context: "正在检查可用时间…",
  propose_schedule_plan: "正在安排任务…",
  request_plan_interaction: "正在准备计划交互…",
  validate_schedule_plan: "正在检查计划…",
  apply_schedule_plan: "正在更新计划…",
  create_event: "正在准备日程变更…",
  create_reminder: "正在准备提醒…",
  get_temporal_insights: "正在检查时间风险…",
};

function toolActivityLabel(tool: ToolEntry) {
  return toolActivities[tool.name] ?? "正在处理你的请求…";
}

function ToolActivityPanel({ tools }: { tools: ToolEntry[] }) {
  const allCompleted = tools.length > 0 && tools.every((tool) => tool.status === "completed");
  const hasFailure = tools.some((tool) => tool.status === "failed");
  return (
    <section aria-label="执行详情" className="w-full rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm">
      <details>
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs font-semibold text-slate-700">
          <LoaderCircle className={!allCompleted && !hasFailure ? "animate-spin text-teal-600" : "text-teal-700"} size={14} />
          <span className="flex-1" aria-live="polite">{hasFailure ? "有一步没有完成" : allCompleted ? "已处理你的请求" : toolActivityLabel(tools.find((tool) => tool.status === "running") ?? tools[tools.length - 1])}</span>
          <span className="font-normal text-slate-500">查看详情</span>
          <span className={hasFailure ? "text-red-600" : allCompleted ? "text-teal-700" : "text-amber-700"}>
            {hasFailure ? "需要重试" : allCompleted ? "完成" : "处理中"}
          </span>
        </summary>
        <div className="max-h-28 overflow-y-auto divide-y divide-slate-100 border-t border-slate-200">
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
      </details>
    </section>
  );
}

function TodayContextSummary({ data }: { data: TodaySummary }) {
  const taskCount = data.planned_tasks.length + data.due_tasks.length + data.overdue_tasks.length;
  return (
    <section aria-label="今日上下文" className="mx-auto mb-4 flex max-w-3xl flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2.5 text-xs text-slate-600">
      <span className="font-semibold text-teal-800">今日上下文</span>
      <span>{data.events.length} 个日程</span>
      <span>{taskCount} 个任务</span>
      <span>{data.pending_reminders.length} 个提醒</span>
      <span className={data.conflicts.length > 0 ? "font-medium text-red-700" : "text-teal-700"}>
        {data.conflicts.length > 0 ? `${data.conflicts.length} 个冲突` : "暂无冲突"}
      </span>
    </section>
  );
}

function SchedulePlanArtifactCard({
  entry,
  timezone,
  onRetry,
  onPlanChange,
  conversationId,
  agentRunId,
  agentRunActive,
}: {
  entry: Extract<ChatEntry, { kind: "schedule_plan" }>;
  timezone: string;
  onRetry: () => void;
  onPlanChange: (plan: SchedulePlan) => void;
  conversationId?: string;
  agentRunId?: string;
  agentRunActive?: boolean;
}) {
  const tasks = useTasks();
  const taskTitles = useMemo(
    () => new Map((tasks.data ?? []).map((task) => [task.id, task.title])),
    [tasks.data],
  );
  const planItems = (Array.isArray(entry.plan?.items) ? entry.plan.items : []) as Array<
    PlanPreviewItem & { kind?: string }
  >;
  const visibleItems = planItems.filter((item) => item.kind !== "plan_evidence");
  const statusLabel: Record<string, string> = {
    draft: "计划草案",
    applied: "已应用",
    superseded: "已替换",
    abandoned: "已放弃",
    invalidated: "需要重新检查",
  };

  return (
    <section aria-label="Agent 计划预览" className="w-full rounded-xl border border-cyan-200/20 bg-slate-950/70 p-4 shadow-sm lg:mx-auto lg:max-w-3xl">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-cyan-100">计划预览</h3>
          {entry.plan && <p className="mt-1 text-xs text-slate-400">{statusLabel[String(entry.plan.status)] ?? "计划"}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {entry.state === "loaded" && entry.plan && (
            <Link
              to={`/planning?plan_id=${encodeURIComponent(entry.planId)}`}
              className="inline-flex min-h-11 items-center rounded-lg border border-cyan-200/20 px-3 text-xs font-medium text-cyan-100 hover:bg-cyan-100/5"
            >
              在计划页打开
            </Link>
          )}
          {entry.state === "failed" && <button type="button" onClick={onRetry} className="min-h-11 rounded-lg border border-white/15 px-3 text-xs text-slate-200 hover:bg-white/5">重试加载</button>}
        </div>
      </header>
      {entry.state === "loading" && <p role="status" className="mt-3 text-sm text-slate-400">正在加载计划…</p>}
      {entry.state === "failed" && <p role="alert" className="mt-3 text-sm text-amber-200">暂时无法加载这份计划。你可以重试，或继续在对话里调整。</p>}
      {entry.state === "loaded" && entry.plan && (
        <>
          <PlanPreview
            items={visibleItems}
            taskTitles={taskTitles}
            timezone={timezone}
            plan={entry.plan}
            onPlanChange={onPlanChange}
            conversationId={conversationId}
            agentRunId={agentRunId}
            agentRunActive={agentRunActive}
          />
          <p className="mt-3 border-t border-white/10 pt-3 text-xs leading-5 text-slate-400">可以直接拖动或输入时间调整草案，也可以继续告诉助理如何调整；正式应用前会按确认流程检查。</p>
        </>
      )}
    </section>
  );
}

function entriesFromRuns(runs: Array<AgentRun & { artifacts: Array<{
  artifact_type: string;
  artifact_id: string;
  version: number;
}> }>, conversationId?: string): ChatEntry[] {
  const entries = runs.flatMap((run) => {
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
      entries.push({
        id: `notice-${run.id}`,
        kind: "notice",
        content: "这次没有完成请求。请重试；如果问题持续，请稍后再试。",
        tone: "error",
      });
    } else if (run.status === "cancelled") {
      entries.push({ id: `notice-${run.id}`, kind: "notice", content: "这次运行已取消。", tone: "muted" });
    }
    for (const artifact of run.artifacts ?? []) {
      if (artifact.artifact_type !== "schedule_plan") continue;
      entries.push({
        id: `plan-artifact-${artifact.artifact_id}`,
        kind: "schedule_plan",
        planId: artifact.artifact_id,
        version: artifact.version,
        conversationId,
        agentRunId: run.id,
        agentRunActive: ACTIVE_RUN_STATUSES.has(run.status),
        state: "loading",
      });
    }
    return entries;
  });
  const uniqueEntries: ChatEntry[] = [];
  const planEntryIndexes = new Map<string, number>();
  for (const entry of entries) {
    if (entry.kind !== "schedule_plan") {
      uniqueEntries.push(entry);
      continue;
    }
    const index = planEntryIndexes.get(entry.planId);
    if (index === undefined) {
      planEntryIndexes.set(entry.planId, uniqueEntries.length);
      uniqueEntries.push(entry);
      continue;
    }
    const previous = uniqueEntries[index];
    if (previous.kind === "schedule_plan") {
      uniqueEntries[index] = {
        ...previous,
        version: Math.max(previous.version, entry.version),
        conversationId: entry.conversationId ?? previous.conversationId,
        agentRunId: entry.agentRunId,
        agentRunActive: entry.agentRunActive,
        state: "loading",
      };
    }
  }
  return uniqueEntries;
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
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const preference = useCurrentUserPreference();
  const todaySummary = useTodaySummary();
  const timezone = preference.data?.timezone
    ?? import.meta.env.VITE_DEFAULT_TIMEZONE
    ?? "Asia/Shanghai";
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [autoSendIntent, setAutoSendIntent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyKind, setHistoryKind] = useState<ConversationKind>("chat");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const runCursors = useRef(new Map<string, string>());
  const messagesEnd = useRef<HTMLDivElement | null>(null);
  const messageViewport = useRef<HTMLDivElement | null>(null);
  const shouldFollowLatest = useRef(true);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const composer = useRef<HTMLFormElement | null>(null);
  const autoSendStarted = useRef(false);
  const [composerOffset, setComposerOffset] = useState(0);
  const [keyboardResizesViewport, setKeyboardResizesViewport] = useState(false);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  useEffect(() => {
    const prompt = searchParams.get("prompt");
    const insightTitle = searchParams.get("insight_title");
    const insightId = searchParams.get("insight_id");
    const intent = prompt
      ?? (insightId && insightTitle
        ? `请基于洞察“${insightTitle}”分析影响并给出可执行选项。洞察 ID：${insightId}`
        : null);
    if (conversationId || !intent) return;

    setMessage((current) => current.trim() ? current : intent);
    if (searchParams.get("auto_send") === "1") {
      setAutoSendIntent(intent);
    }
    setSearchParams({}, { replace: true });
  }, [conversationId, searchParams, setSearchParams]);

  // Keep the composer above the software keyboard by tracking visualViewport.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let unobscuredHeight = vv.height;
    const handler = () => {
      const isComposerFocused = document.activeElement === textarea.current;
      const currentHeight = vv.height;
      if (!isComposerFocused) {
        unobscuredHeight = currentHeight;
        setComposerOffset(0);
        setKeyboardResizesViewport(false);
        return;
      }

      const coveredHeight = window.innerHeight - currentHeight - vv.offsetTop;
      const resizedHeight = unobscuredHeight - currentHeight;
      const resizesViewport = resizedHeight > 160 && coveredHeight <= 24;
      setKeyboardResizesViewport(resizesViewport);
      setComposerOffset(!resizesViewport && coveredHeight > 24 ? coveredHeight : 0);
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
    } catch {
      setError("暂时无法加载历史对话，请重试。");
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

  const loadPlanArtifact = useCallback(async (
    planId: string,
    minimumVersion = 1,
    agentRunId?: string,
    agentRunActive = false,
  ) => {
    const entryId = `plan-artifact-${planId}`;
    setEntries((current) => {
      const exists = current.some((entry) => entry.kind === "schedule_plan" && entry.planId === planId);
      if (!exists) {
        return [...current, {
          id: entryId,
          kind: "schedule_plan",
          planId,
          version: minimumVersion,
          conversationId,
          agentRunId,
          agentRunActive,
          state: "loading",
        }];
      }
      return current.map((entry) => entry.kind === "schedule_plan" && entry.planId === planId
        ? { ...entry, version: Math.max(entry.version, minimumVersion), conversationId: entry.conversationId ?? conversationId, agentRunId: agentRunId ?? entry.agentRunId, agentRunActive: agentRunId === undefined ? entry.agentRunActive || agentRunActive : agentRunActive, state: "loading" }
        : entry);
    });

    try {
      const plan = await getSchedulePlan(planId);
      const planVersion = plan.version ?? minimumVersion;
      setEntries((current) => current.map((entry) => {
        if (entry.kind !== "schedule_plan" || entry.planId !== planId) return entry;
        if (planVersion < entry.version) {
          return { ...entry, state: "failed" };
        }
        return { ...entry, version: planVersion, plan, state: "loaded" };
      }));
    } catch {
      setEntries((current) => current.map((entry) => entry.kind === "schedule_plan" && entry.planId === planId
        ? { ...entry, state: "failed" }
        : entry));
    }
  }, [conversationId]);

  const applyEvent = useCallback((activeRunId: string, event: AgentStreamEvent) => {
    const callId = String(event.data.tool_call_id ?? event.id);
    const toolName = String(event.data.tool_name ?? "tool");
    const assistantId = `assistant-${activeRunId}`;
    const eventTimestamp = typeof event.data.event_created_at === "string"
      ? event.data.event_created_at
      : new Date().toISOString();
    if (event.type === "artifact.available") {
      const artifactId = String(event.data.artifact_id ?? "");
      const artifactType = String(event.data.artifact_type ?? "");
      const version = Number(event.data.version);
      if (artifactType === "schedule_plan" && artifactId && Number.isInteger(version) && version > 0) {
        void loadPlanArtifact(artifactId, version, activeRunId, true);
      }
    } else if (event.type === "tool.started") {
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
        }).catch(() => {
          setError("暂时无法加载这项待确认操作，请重试。");
        });
      }
    } else if (event.type === "run.failed") {
      setError("这次没有完成请求。你可以重试；如果问题持续，请稍后再试。");
    } else if (event.type === "run.cancelled") {
      setError("Agent 运行已取消");
    }
  }, [loadPlanArtifact]);

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
    } catch {
      // Android WebView may reject an aborted fetch with a plain Error such as
      // "The user aborted a request." instead of a DOMException/AbortError.
      // The signal is the authoritative indication that this stream was
      // intentionally stopped (for example, while changing conversations).
      if (!abortController.signal.aborted) {
        setError("实时回复中断了。请重试，或稍后回到这段对话查看结果。");
      }
    } finally {
      if (!abortController.signal.aborted) {
        setEntries((current) => current.map((entry) => entry.kind === "schedule_plan" && entry.agentRunId === activeRunId
          ? { ...entry, agentRunActive: false }
          : entry));
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
        const historyEntries = entriesFromRuns(conversation.runs, conversation.id);
        setEntries([...historyEntries, ...approvalEntries]);
        for (const entry of historyEntries) {
          if (entry.kind === "schedule_plan") {
            void loadPlanArtifact(entry.planId, entry.version, entry.agentRunId);
          }
        }
        const activeRun = [...conversation.runs].reverse().find((run) => ACTIVE_RUN_STATUSES.has(run.status));
        if (activeRun) {
          const streamController = new AbortController();
          controller.current = streamController;
          void consumeRun(activeRun.id, streamController);
        }
      })
      .catch(() => {
        if (loadController.signal.aborted) return;
        setError("暂时无法加载这段对话，请重试。");
      })
      .finally(() => {
        if (!loadController.signal.aborted) setLoadingHistory(false);
      });

    return () => {
      loadController.abort();
      controller.current?.abort();
    };
  }, [consumeRun, conversationId, loadPlanArtifact]);

  useEffect(() => {
    if (shouldFollowLatest.current) {
      messagesEnd.current?.scrollIntoView?.({ behavior: "auto" });
      setShowJumpToLatest(false);
    } else if (busy) {
      setShowJumpToLatest(true);
    }
  }, [entries, busy]);

  useEffect(() => {
    setHistoryOpen(false);
  }, [conversationId]);

  const handleMessageScroll = () => {
    const viewport = messageViewport.current;
    if (!viewport) return;
    const distanceToBottom = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
    const isNearBottom = distanceToBottom <= 96;
    shouldFollowLatest.current = isNearBottom;
    if (isNearBottom) setShowJumpToLatest(false);
    else if (busy) setShowJumpToLatest(true);
  };

  const jumpToLatest = () => {
    shouldFollowLatest.current = true;
    setShowJumpToLatest(false);
    messagesEnd.current?.scrollIntoView?.({ behavior: "auto" });
  };

  const groups = useMemo(
    () => groupConversations(conversations.filter((item) => item.kind === historyKind)),
    [conversations, historyKind],
  );
  const activeConversation = conversations.find((conversation) => conversation.id === conversationId);

  useEffect(() => {
    if (activeConversation) setHistoryKind(activeConversation.kind);
  }, [activeConversation]);

  const sendMessage = useCallback(async (draft: string) => {
    const content = draft.trim();
    if (!content || busy) return;
    shouldFollowLatest.current = true;
    setShowJumpToLatest(false);
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
        setMessage(content);
        setError("消息没有发送成功，请检查连接后重试。");
      }
    }
  }, [busy, consumeRun, conversationId, navigate, refreshConversations]);

  useEffect(() => {
    if (!autoSendIntent || autoSendStarted.current) return;
    autoSendStarted.current = true;
    setAutoSendIntent(null);
    void sendMessage(autoSendIntent);
  }, [autoSendIntent, sendMessage]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void sendMessage(message);
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
    <div className="flex min-h-[45dvh] max-h-[68dvh] flex-col lg:h-full lg:min-h-0 lg:max-h-none">
      <div className="hidden items-center gap-2 border-b border-slate-200 p-3 lg:flex">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-700"><History size={16} /> 对话历史</p>
      </div>
      <div className="p-3">
        <button type="button" onClick={startNewChat} className="mobile-on-brand flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-3 text-sm font-semibold text-white transition hover:bg-teal-800">
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
            aria-pressed={historyKind === kind}
            className={`min-h-11 rounded-lg px-2 text-xs font-medium ${historyKind === kind ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-100"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <nav aria-label="对话历史列表" className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loadingConversations && <p className="px-3 py-4 text-xs text-slate-500">正在加载历史对话…</p>}
        {!loadingConversations && groups.length === 0 && <p className="px-3 py-4 text-xs leading-5 text-slate-500">此分类下还没有会话。</p>}
        {groups.map((group) => (
          <div key={group.label} className="mt-3 first:mt-0">
            <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-slate-600">{group.label}</p>
            <div className="space-y-1">
              {group.conversations.map((conversation) => (
                <button
                  type="button"
                  key={conversation.id}
                  onClick={() => navigate(`/chat/${conversation.id}`)}
                  aria-current={conversation.id === conversationId ? "page" : undefined}
                  className={`group flex min-h-11 w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${conversation.id === conversationId ? "bg-teal-50 text-teal-800" : "text-slate-700 hover:bg-slate-100"}`}
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
    <section className={`-mx-4 flex ${keyboardResizesViewport ? "h-[calc(100dvh-2rem)]" : "h-[calc(100dvh-8.25rem)]"} min-h-0 overflow-hidden bg-transparent lg:mx-auto lg:h-[calc(100vh-7rem)] lg:min-h-[32rem] lg:max-w-7xl lg:rounded-2xl lg:border lg:border-slate-200 lg:bg-white/70`}>
      <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-slate-50 lg:block">{historyPanel}</aside>
      {historyOpen && (
        <Drawer title="对话历史" onClose={() => setHistoryOpen(false)}>
          {historyPanel}
        </Drawer>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-14 items-center gap-3 border-b border-slate-200 px-4 py-2.5 sm:px-6 lg:px-4">
          <button type="button" onClick={() => setHistoryOpen(true)} aria-label="打开对话历史" aria-haspopup="dialog" className="grid min-h-12 min-w-12 place-items-center rounded-xl text-slate-700 hover:bg-slate-100 lg:hidden"><Menu size={22} /></button>
          <Bot className="shrink-0 text-teal-700" size={23} aria-hidden="true" />
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900">{activeConversation?.title || "Time Steward"}</h2>
            <p className="text-xs text-slate-600">{activeConversation?.kind === "manual_briefing" ? "用户手动简报" : activeConversation?.kind === "scheduled_briefing" ? "自动简报" : "私人时间助理"}</p>
          </div>
          {conversationId && <button type="button" onClick={startNewChat} className="ml-auto hidden min-h-11 items-center gap-2 rounded-lg border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50 sm:flex"><Plus size={15} /> 新建聊天</button>}
        </header>

        <div className="relative min-h-0 flex-1">
        <div ref={messageViewport} onScroll={handleMessageScroll} className="h-full space-y-5 overflow-y-auto px-4 py-5 sm:px-8 lg:px-4">
          {loadingHistory && <p className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500"><LoaderCircle className="animate-spin" size={16} /> 正在加载对话…</p>}
          {!loadingHistory && entries.length === 0 && (
            <>
              {todaySummary.data && <div className="hidden lg:block"><TodayContextSummary data={todaySummary.data} /></div>}
              <ChatEmptyState onQuickAction={handleQuickAction} />
            </>
          )}
          {entries.map((entry) => {
            if (entry.kind === "approval") {
              return (
                <div key={entry.id} className="w-full lg:mx-auto lg:max-w-3xl">
                  <ApprovalCard
                    proposal={entry.proposal}
                    timezone={timezone}
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
            if (entry.kind === "schedule_plan") {
              return (
                <SchedulePlanArtifactCard
                  key={entry.id}
                  entry={entry}
                  timezone={timezone}
                  onRetry={() => void loadPlanArtifact(entry.planId, entry.version, entry.agentRunId)}
                  onPlanChange={(updatedPlan) => setEntries((current) => current.map((candidate) =>
                    candidate.kind === "schedule_plan" && candidate.planId === updatedPlan.id
                    ? { ...candidate, plan: updatedPlan, version: updatedPlan.version ?? candidate.version, state: "loaded" }
                      : candidate,
                  ))}
                  conversationId={entry.conversationId}
                  agentRunId={entry.agentRunId}
                  agentRunActive={entry.agentRunActive}
                />
              );
            }
            if (entry.kind === "notice") {
              return <p key={entry.id} className={`w-full rounded-xl border px-4 py-3 text-sm font-medium leading-6 lg:mx-auto lg:max-w-xl ${entry.tone === "error" ? "border-red-300 bg-red-50 text-red-900" : "border-slate-200 bg-slate-50 text-slate-700"}`}>{entry.content}</p>;
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
                    <p className="whitespace-pre-wrap rounded-2xl bg-teal-50 px-4 py-3 text-base leading-6 text-slate-900">{entry.content}</p>
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
                    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 lg:px-4 lg:py-3">
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
          {busy && <p role="status" className="mx-auto flex max-w-3xl items-center gap-2 text-sm text-slate-600"><LoaderCircle className="animate-spin" size={16} /> Time Steward 正在处理…</p>}
          {error && <p role="alert" className="mx-auto max-w-3xl rounded-xl border border-red-300 bg-red-50 p-3 text-sm font-medium leading-6 text-red-900 shadow-sm">{error}</p>}
          <div ref={messagesEnd} />
        </div>
        {showJumpToLatest && (
          <button type="button" onClick={jumpToLatest} className="absolute bottom-2 left-1/2 z-10 min-h-11 -translate-x-1/2 rounded-full border border-slate-300 bg-white px-4 text-sm font-medium text-teal-800 shadow-sm">
            回到最新消息
          </button>
        )}
        </div>

        <form
          ref={composer}
          onSubmit={submit}
          style={{ transform: composerOffset ? `translateY(-${composerOffset}px)` : undefined }}
          className="border-t border-slate-200 bg-white/95 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 transition-transform sm:p-4 lg:p-3"
        >
          <div className="mx-3 flex max-w-none items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-teal-700 sm:mx-auto sm:max-w-3xl sm:p-3">
            <label className="sr-only" htmlFor="chat-message">消息</label>
            <textarea ref={textarea} id="chat-message" rows={1} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={handleComposerKeyDown} disabled={busy || loadingHistory} placeholder="输入你的时间管理请求…" className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-2.5 py-2.5 text-base text-slate-900 outline-none placeholder:text-slate-600 disabled:opacity-60" />
            {busy ? (
              <button type="button" onClick={cancel} aria-label="停止运行" className="grid size-12 shrink-0 place-items-center rounded-xl bg-red-50 text-red-800"><CircleStop size={21} /></button>
            ) : (
              <button type="submit" aria-label="发送消息" disabled={!message.trim() || loadingHistory} className="mobile-on-brand grid size-12 shrink-0 place-items-center rounded-xl bg-teal-700 text-white disabled:opacity-40"><Send size={21} /></button>
            )}
          </div>
        </form>
      </div>
    </section>
  );
}
