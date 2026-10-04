const quickActions = [
  { id: "list-schedule", label: "看今天安排", prompt: "帮我查询今天的日程" },
  { id: "organize-tasks", label: "整理任务", prompt: "帮我整理一下当前的任务" },
  { id: "set-reminder", label: "设置提醒", prompt: "帮我设置一个提醒" },
  { id: "create-event", label: "新建日程", prompt: "帮我创建一个日程" },
] as const;

export type ChatQuickActionId = (typeof quickActions)[number]["id"];

/** Empty state shown at the top of a fresh conversation. */
export function ChatEmptyState({ onQuickAction }: { onQuickAction: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-start px-1 py-5 text-left lg:items-center lg:px-4 lg:py-10 lg:text-center">
      <h3 className="text-lg font-semibold text-slate-900 lg:text-2xl">今天想先处理哪件事？</h3>
      <p className="mt-1 text-sm text-slate-600 lg:mt-3 lg:text-base">
        直接输入目标，或选一个常用问题。
      </p>
      <div
        role="group"
        aria-label="常用快捷操作"
        className="mt-3 flex w-full gap-2 overflow-x-auto pb-1 lg:mt-6 lg:flex-wrap lg:justify-center lg:overflow-visible"
      >
        {quickActions.map((action) => (
          <button
            key={action.id}
            type="button"
            onClick={() => onQuickAction(action.prompt)}
            className="min-h-11 shrink-0 rounded-full border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 transition hover:border-teal-600 hover:bg-teal-50 hover:text-teal-800"
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
