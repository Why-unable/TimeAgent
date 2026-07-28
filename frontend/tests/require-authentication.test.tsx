import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/api/client";
import { RequireAuthentication } from "../src/features/accounts/require-authentication";
import { useCurrentUser } from "../src/features/accounts/hooks";

vi.mock("../src/features/accounts/hooks", () => ({
  useCurrentUser: vi.fn(),
}));

const mockedUseCurrentUser = vi.mocked(useCurrentUser);

type CurrentUserState = ReturnType<typeof useCurrentUser>;

function stubUser(state: Partial<CurrentUserState>) {
  mockedUseCurrentUser.mockReturnValue({
    isPending: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
    ...state,
  } as unknown as CurrentUserState);
}

function renderGuarded() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/today"]}>
        <Routes>
          <Route element={<RequireAuthentication />}>
            <Route path="/today" element={<p>受保护内容</p>} />
          </Route>
          <Route path="/login" element={<p>登录页</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireAuthentication", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the protected route when authenticated", () => {
    stubUser({ isError: false });
    renderGuarded();
    expect(screen.getByText("受保护内容")).toBeInTheDocument();
  });

  it.each([401, 403])("redirects to login on a %i", (status) => {
    stubUser({ isError: true, error: new ApiError("unauthenticated", status) });
    renderGuarded();
    expect(screen.getByText("登录页")).toBeInTheDocument();
  });

  it("shows a retry surface for non-401 errors instead of logging out", () => {
    stubUser({ isError: true, error: new ApiError("server error", 500) });
    renderGuarded();
    expect(screen.getByText("暂时无法验证登录状态")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.queryByText("登录页")).not.toBeInTheDocument();
  });

  it("treats a network failure without a status as retryable", () => {
    stubUser({ isError: true, error: new TypeError("Failed to fetch") });
    renderGuarded();
    expect(screen.getByText("暂时无法验证登录状态")).toBeInTheDocument();
    expect(screen.queryByText("登录页")).not.toBeInTheDocument();
  });
});
