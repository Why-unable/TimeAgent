import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  completeTask,
  createTask,
  listTasks,
  recordTaskExecutionSignal,
  getTaskExecutionSummary,
  type CreateTask,
  type UpdateTask,
  updateTask,
} from "../../api/tasks";

export const taskQueryKey = ["tasks"] as const;

export function useTasks() {
  return useQuery({ queryKey: taskQueryKey, queryFn: () => listTasks(), retry: false });
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateTask) => createTask(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taskQueryKey }),
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, input }: { taskId: string; input: UpdateTask }) =>
      updateTask(taskId, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taskQueryKey }),
  });
}

export function useCompleteTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: completeTask,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: taskQueryKey }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
      ]);
    },
  });
}

export function useRecordTaskExecutionSignal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      taskId,
      signalType,
    }: {
      taskId: string;
      signalType: "started" | "paused" | "resumed" | "skipped";
    }) => recordTaskExecutionSignal(taskId, signalType),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: taskQueryKey }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["task-execution-summary"] }),
      ]);
    },
  });
}

export function useTaskExecutionSummary(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task-execution-summary", taskId],
    queryFn: () => getTaskExecutionSummary(taskId as string),
    enabled: Boolean(taskId),
    retry: false,
  });
}
