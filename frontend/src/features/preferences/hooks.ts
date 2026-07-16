import { useQuery } from "@tanstack/react-query";

import { getCurrentUserPreference } from "../../api/preferences";

export const preferenceQueryKey = ["user-preference"] as const;

export function useCurrentUserPreference() {
  return useQuery({
    queryKey: preferenceQueryKey,
    queryFn: getCurrentUserPreference,
    retry: false,
  });
}

