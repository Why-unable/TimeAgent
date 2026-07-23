import { useMutation, useQuery } from "@tanstack/react-query";

import { getCurrentUser, logoutAccount } from "../../api/auth";
import { queryClient } from "../../app/query-client";

export const currentUserQueryKey = ["current-user"] as const;

export function useCurrentUser() {
  return useQuery({
    queryKey: currentUserQueryKey,
    queryFn: getCurrentUser,
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: logoutAccount,
    onSuccess: () => queryClient.clear(),
  });
}
