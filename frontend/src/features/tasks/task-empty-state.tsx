import { ListTodo } from "lucide-react";

import { EmptyState } from "../../components/ui/primitives";

/** Empty state shown when the current filter has no tasks. */
export function TaskEmptyState() {
  return (
    <EmptyState
      className="mt-6 border-white/10"
      icon={<ListTodo size={42} className="mx-auto text-slate-600" />}
      title="当前分类暂无任务"
      description="用上方按钮添加一件想完成的事吧。"
    />
  );
}
