import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getCurrentUserPreference,
  updateCurrentUserPreference,
} from "../../api/preferences";

export const preferenceQueryKey = ["user-preference"] as const;

export function useCurrentUserPreference() {
  return useQuery({
    queryKey: preferenceQueryKey,
    queryFn: getCurrentUserPreference,
    retry: false,
  });
}

export function useUpdateCurrentUserPreference() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: updateCurrentUserPreference,
    onSuccess: (data) => client.setQueryData(preferenceQueryKey, data),
  });
}
