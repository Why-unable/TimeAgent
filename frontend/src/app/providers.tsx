import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ErrorBoundary } from "./error-boundary";
import { queryClient } from "./query-client";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ErrorBoundary>
  );
}

