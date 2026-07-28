import { useMutation, useQuery } from "@tanstack/react-query";

import { getCurrentUser } from "../../api/auth";
import { ApiError } from "../../api/client";
import { queryClient } from "../../app/query-client";
import { signOut } from "./session";

export const currentUserQueryKey = ["current-user"] as const;

export function useCurrentUser() {
  return useQuery({
    queryKey: currentUserQueryKey,
    queryFn: getCurrentUser,
    // 401/403 mean "not signed in" — a definitive answer, so never retry it.
    // Any other failure (network drop, timeout, 5xx) may be transient on a
    // flaky mobile connection, so retry once before surfacing an error.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        return false;
      }
      return failureCount < 1;
    },
    staleTime: 60_000,
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: signOut,
    onSuccess: () => queryClient.clear(),
  });
}
