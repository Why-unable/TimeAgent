import { ListTodo } from "lucide-react";

import { EmptyState } from "../../components/ui/primitives";

/** Empty state shown when the current filter has no tasks. */
export function TaskEmptyState() {
  return (
    <EmptyState
      className="mt-6 rounded-none border-0 px-0 py-4 text-left lg:rounded-2xl lg:border lg:border-dashed lg:border-slate-300 lg:px-5 lg:py-10 lg:text-center"
      icon={<ListTodo size={24} className="mx-0 text-slate-600 lg:mx-auto lg:size-10" />}
      title="当前分类暂无任务"
      description="用上方按钮添加一件想完成的事吧。"
    />
  );
}
