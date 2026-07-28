import { ListTodo } from "lucide-react";

/** Empty state shown when the current filter has no tasks. */
export function TaskEmptyState() {
  return (
    <div className="mt-8 rounded-[var(--mobile-card-radius)] border border-dashed border-white/10 p-8 text-center sm:p-12">
      <ListTodo size={52} className="mx-auto text-slate-600" />
      <p className="mt-5 text-xl font-semibold text-slate-300 sm:text-[22px]">当前分类暂无任务</p>
      <p className="mt-3 text-base text-slate-500">用上方按钮添加一件想完成的事吧。</p>
    </div>
  );
}
