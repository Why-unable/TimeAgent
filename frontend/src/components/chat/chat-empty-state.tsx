import { Bot } from "lucide-react";

const quickActions = [
  { id: "list-schedule", label: "查询日程", prompt: "帮我查询今天的日程" },
  { id: "organize-tasks", label: "整理任务", prompt: "帮我整理一下当前的任务" },
  { id: "set-reminder", label: "设置提醒", prompt: "帮我设置一个提醒" },
  { id: "create-event", label: "创建日程", prompt: "帮我创建一个日程" },
] as const;

export type ChatQuickActionId = (typeof quickActions)[number]["id"];

/** Empty state shown at the top of a fresh conversation. */
export function ChatEmptyState({ onQuickAction }: { onQuickAction: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-10 text-center sm:py-12">
      <span className="rounded-[2rem] bg-cyan-300/10 p-6 text-cyan-300">
        <Bot size={42} />
      </span>
      <h3 className="mt-6 text-2xl font-semibold sm:text-3xl">今天需要我帮你安排什么？</h3>
      <p className="mt-3 text-base leading-7 text-slate-500 sm:mt-4 sm:text-lg sm:leading-8">
        查询日程、整理任务、设置提醒，或直接告诉我你想做什么。
      </p>
      <div
        aria-label="常用快捷操作"
        className="mt-6 grid w-full grid-cols-2 gap-3 sm:mt-8 sm:grid-cols-4"
      >
        {quickActions.map((action) => (
          <button
            key={action.id}
            type="button"
            onClick={() => onQuickAction(action.prompt)}
            className="min-h-12 rounded-2xl border border-white/10 bg-slate-900/70 px-3 py-3 text-sm font-medium text-slate-200 transition hover:border-cyan-300/30 hover:text-cyan-100"
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
