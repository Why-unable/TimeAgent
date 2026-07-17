import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  completeTask,
  createTask,
  listTasks,
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
