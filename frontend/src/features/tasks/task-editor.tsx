import { zodResolver } from "@hookform/resolvers/zod";
import { Save } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getTaskTags, type Task } from "../../api/tasks";
import { Drawer } from "../../components/overlay/drawer";
import { toDateTimeLocalValue, toUtcISOString } from "../../utils/datetime";
import { useCreateTask, useUpdateTask } from "./hooks";

const taskFormSchema = z
  .object({
    title: z.string().trim().min(1, "请输入任务标题").max(255),
    project: z.string().max(255),
    description: z.string().max(5000),
    priority: z.enum(["low", "medium", "high", "urgent"]),
    due_at: z.string(),
    planned_start_at: z.string(),
    planned_end_at: z.string(),
    estimated_minutes: z.string().refine(
      (value) => value === "" || (Number.isInteger(Number(value)) && Number(value) > 0),
      "预计时长必须是正整数",
    ),
    buffer_before_minutes: z.string().refine(
      (value) => Number.isInteger(Number(value)) && Number(value) >= 0,
      "缓冲必须是非负整数",
    ),
    buffer_after_minutes: z.string().refine(
      (value) => Number.isInteger(Number(value)) && Number(value) >= 0,
      "缓冲必须是非负整数",
    ),
    planning_locked: z.boolean(),
    splittable: z.boolean(),
    minimum_chunk_minutes: z.string().refine(
      (value) => Number.isInteger(Number(value)) && Number(value) >= 15,
      "最小片段必须至少 15 分钟",
    ),
    tags: z.string(),
  })
  .refine(
    (values) => Boolean(values.planned_start_at) === Boolean(values.planned_end_at),
    { message: "计划开始和结束时间必须同时填写", path: ["planned_end_at"] },
  )
  .refine(
    (values) =>
      !values.planned_start_at || values.planned_end_at > values.planned_start_at,
    { message: "计划结束时间必须晚于开始时间", path: ["planned_end_at"] },
  );

type TaskForm = z.infer<typeof taskFormSchema>;

interface TaskEditorProps {
  task?: Task;
  timezone: string;
  onClose: () => void;
}

function initialValues(task: Task | undefined, timezone: string): TaskForm {
  return {
    title: task?.title ?? "",
    project: task?.project ?? "",
    description: task?.description ?? "",
    priority: task?.priority ?? "medium",
    due_at: task?.due_at ? toDateTimeLocalValue(task.due_at, timezone) : "",
    planned_start_at: task?.planned_start_at
      ? toDateTimeLocalValue(task.planned_start_at, timezone)
      : "",
    planned_end_at: task?.planned_end_at
      ? toDateTimeLocalValue(task.planned_end_at, timezone)
      : "",
    estimated_minutes: task?.estimated_minutes?.toString() ?? "",
    buffer_before_minutes: String(task?.buffer_before_minutes ?? 0),
    buffer_after_minutes: String(task?.buffer_after_minutes ?? 0),
    planning_locked: task?.planning_locked ?? false,
    splittable: task?.splittable ?? false,
    minimum_chunk_minutes: String(task?.minimum_chunk_minutes ?? 30),
    tags: task ? getTaskTags(task).join(", ") : "",
  };
}

const inputClass =
  "mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-slate-100 outline-none focus:border-cyan-300/60";

export function TaskEditor({ task, timezone, onClose }: TaskEditorProps) {
  const createMutation = useCreateTask();
  const updateMutation = useUpdateTask();
  const form = useForm<TaskForm>({
    resolver: zodResolver(taskFormSchema),
    defaultValues: initialValues(task, timezone),
  });
  const mutationError = createMutation.error ?? updateMutation.error;

  const onSubmit = form.handleSubmit((values) => {
    const input = {
      title: values.title.trim(),
      project: values.project.trim(),
      description: values.description.trim(),
      priority: values.priority,
      due_at: values.due_at ? toUtcISOString(values.due_at, timezone) : null,
      planned_start_at: values.planned_start_at
        ? toUtcISOString(values.planned_start_at, timezone)
        : null,
      planned_end_at: values.planned_end_at
        ? toUtcISOString(values.planned_end_at, timezone)
        : null,
      estimated_minutes: values.estimated_minutes ? Number(values.estimated_minutes) : null,
      buffer_before_minutes: Number(values.buffer_before_minutes),
      buffer_after_minutes: Number(values.buffer_after_minutes),
      planning_locked: values.planning_locked,
      splittable: values.splittable,
      minimum_chunk_minutes: Number(values.minimum_chunk_minutes),
      tags: values.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    };
    if (task) {
      updateMutation.mutate({ taskId: task.id, input }, { onSuccess: onClose });
    } else {
      createMutation.mutate(input, { onSuccess: onClose });
    }
  });

  return (
    <Drawer
      title={task ? "编辑任务" : "创建任务"}
      description="截止时间表示最迟完成点；计划执行时间表示预留的工作区间。"
      onClose={onClose}
    >
      <form onSubmit={onSubmit} className="space-y-5">
        <label className="block text-sm text-slate-300">
          任务标题
          <input {...form.register("title")} className={inputClass} />
          {form.formState.errors.title && (
            <span className="mt-1 block text-red-300">{form.formState.errors.title.message}</span>
          )}
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm text-slate-300">
            项目
            <input {...form.register("project")} placeholder="可选" className={inputClass} />
          </label>
          <label className="block text-sm text-slate-300">
            优先级
            <select {...form.register("priority")} className={inputClass}>
              <option value="low">低</option>
              <option value="medium">中</option>
              <option value="high">高</option>
              <option value="urgent">紧急</option>
            </select>
          </label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm text-slate-300">
            前置缓冲（分钟）
            <input type="number" min="0" max="1440" {...form.register("buffer_before_minutes")} className={inputClass} />
          </label>
          <label className="block text-sm text-slate-300">
            后置缓冲（分钟）
            <input type="number" min="0" max="1440" {...form.register("buffer_after_minutes")} className={inputClass} />
          </label>
        </div>
        <label className="flex min-h-11 items-center gap-3 border-t border-white/10 pt-4 text-sm text-slate-300">
          <input type="checkbox" {...form.register("planning_locked")} />
          锁定当前任务，不允许规划器自动移动
        </label>
        <div className="grid gap-4 border-t border-white/10 pt-4 sm:grid-cols-2">
          <label className="flex min-h-11 items-center gap-3 text-sm text-slate-300">
            <input type="checkbox" {...form.register("splittable")} />
            允许拆成多个日历工作块
          </label>
          <label className="block text-sm text-slate-300">
            最小片段（分钟）
            <input type="number" min="15" max="1440" step="15" {...form.register("minimum_chunk_minutes")} className={inputClass} />
          </label>
        </div>
        <label className="block text-sm text-slate-300">
          描述
          <textarea {...form.register("description")} rows={3} className={inputClass} />
        </label>
        <div className="rounded-2xl border border-amber-300/15 bg-amber-300/5 p-4">
          <label className="block text-sm text-amber-100">
            截止时间 due_at（{timezone}）
            <input type="datetime-local" {...form.register("due_at")} className={inputClass} />
          </label>
          <p className="mt-2 text-xs text-slate-500">表示最迟需要完成的时间，不等于计划执行时段。</p>
        </div>
        <div className="rounded-2xl border border-cyan-300/15 bg-cyan-300/5 p-4">
          <p className="text-sm text-cyan-100">计划执行时间 planned_start_at / planned_end_at</p>
          <div className="mt-1 grid gap-4 sm:grid-cols-2">
            <label className="block text-xs text-slate-400">
              计划开始（{timezone}）
              <input
                type="datetime-local"
                {...form.register("planned_start_at")}
                className={inputClass}
              />
            </label>
            <label className="block text-xs text-slate-400">
              计划结束（{timezone}）
              <input
                type="datetime-local"
                {...form.register("planned_end_at")}
                className={inputClass}
              />
            </label>
          </div>
          {form.formState.errors.planned_end_at && (
            <span className="mt-2 block text-sm text-red-300">
              {form.formState.errors.planned_end_at.message}
            </span>
          )}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm text-slate-300">
            预计时长（分钟）
            <input type="number" min="1" {...form.register("estimated_minutes")} className={inputClass} />
            {form.formState.errors.estimated_minutes && (
              <span className="mt-1 block text-red-300">
                {form.formState.errors.estimated_minutes.message}
              </span>
            )}
          </label>
          <label className="block text-sm text-slate-300">
            标签（逗号分隔）
            <input {...form.register("tags")} placeholder="工作, 报告" className={inputClass} />
          </label>
        </div>
        {mutationError && (
          <div role="alert" className="rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">
            {mutationError.message}
          </div>
        )}
        <div className="flex justify-end border-t border-white/10 pt-5">
          <button
            type="submit"
            disabled={createMutation.isPending || updateMutation.isPending}
            className="inline-flex items-center gap-2 rounded-xl bg-cyan-300 px-5 py-3 font-medium text-slate-950 disabled:opacity-50"
          >
            <Save size={18} />
            {task ? "保存修改" : "创建任务"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
