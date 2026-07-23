import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "../src/pages/login-page";

const navigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

function renderLoginPage() {
  return render(<MemoryRouter initialEntries={["/login"]}><LoginPage /></MemoryRouter>);
}

describe("LoginPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    navigate.mockReset();
  });

  it("registers from the login page and continues into the app", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/csrf/")) return new Response(JSON.stringify({ csrfToken: "token" }));
      if (url.endsWith("/api/v1/auth/register/") && init?.method === "POST") {
        return new Response(JSON.stringify({ id: 1, email: "owner@example.test", display_name: "owner@example.test", is_staff: false }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    await userEvent.click(screen.getByRole("tab", { name: "注册" }));
    await userEvent.type(screen.getByLabelText("邮箱"), "owner@example.test");
    await userEvent.type(screen.getByLabelText("密码"), "strong password 123");
    await userEvent.click(screen.getByRole("button", { name: "创建账号" }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/today", { replace: true }));
  });
});
