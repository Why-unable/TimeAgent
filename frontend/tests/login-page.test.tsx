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

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><LoginPage /></MemoryRouter>);
}

describe("LoginPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    navigate.mockReset();
  });

  it("registers from the login page and asks the user to verify email", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: false, registration_enabled: true }));
      }
      if (url.endsWith("/api/v1/auth/csrf/")) return new Response(JSON.stringify({ csrfToken: "token" }));
      if (url.endsWith("/api/v1/auth/register/") && init?.method === "POST") {
        return new Response(JSON.stringify({ detail: "Verification email sent" }), { status: 202 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    await userEvent.click(await screen.findByRole("tab", { name: "注册" }));
    await userEvent.type(screen.getByLabelText("邮箱"), "owner@example.test");
    await userEvent.type(screen.getByLabelText("昵称"), "Owner");
    await userEvent.type(screen.getByLabelText("密码"), "strong password 123");
    await userEvent.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByText("验证链接已发送至邮箱。请完成验证后再登录。")).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("returns to login with a clear instruction after email verification", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: false, registration_enabled: true }));
      }
      if (url.endsWith("/api/v1/auth/csrf/")) return new Response(JSON.stringify({ csrfToken: "token" }));
      if (url.endsWith("/api/v1/auth/email-verification/confirm/") && init?.method === "POST") {
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));

    renderAt("/login?verify_uid=uid&verify_token=token");

    await screen.findByRole("heading", { name: "验证邮箱" });
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/login", expect.objectContaining({ replace: true })),
    );
  });

  it("moves an already registered address back to login instead of leaving a dead-end error", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: false, registration_enabled: true }));
      }
      if (url.endsWith("/api/v1/auth/csrf/")) return new Response(JSON.stringify({ csrfToken: "token" }));
      if (url.endsWith("/api/v1/auth/register/") && init?.method === "POST") {
        return new Response(JSON.stringify({ detail: "An account with this email already exists" }), { status: 400 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    await userEvent.click(await screen.findByRole("tab", { name: "注册" }));
    await userEvent.type(screen.getByLabelText("邮箱"), "owner@example.test");
    await userEvent.type(screen.getByLabelText("昵称"), "Owner");
    await userEvent.type(screen.getByLabelText("密码"), "strong password 123");
    await userEvent.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByText("该邮箱已经注册并可直接登录。请输入密码后登录。")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "登录" })).toHaveAttribute("aria-selected", "true");
  });

  it("enters an isolated guest workspace without email registration", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: true, registration_enabled: true }));
      }
      if (url.endsWith("/api/v1/auth/csrf/")) {
        return new Response(JSON.stringify({ csrfToken: "token" }));
      }
      if (url.endsWith("/api/v1/auth/guest/") && init?.method === "POST") {
        return new Response(JSON.stringify({
          id: 42,
          email: "",
          display_name: "游客",
          is_email_verified: false,
          is_staff: false,
          is_guest: true,
          guest_expires_at: "2026-08-11T06:00:00Z",
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    await userEvent.click(await screen.findByRole("button", { name: "游客体验（无需注册）" }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/today", { replace: true }));
  });

  it("hides guest access when disabled and keeps the enabled registration path visible", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: false, registration_enabled: true }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    expect(await screen.findByRole("tab", { name: "注册" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "游客体验（无需注册）" })).not.toBeInTheDocument();
  });

  it("shows only guest access when backend registration is disabled", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: true, registration_enabled: false }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    expect(await screen.findByRole("button", { name: "游客体验（无需注册）" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "注册" })).not.toBeInTheDocument();
  });

  it("offers a retry and keeps registration available when account options cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderLoginPage();

    expect(await screen.findByText("暂时无法确认注册状态；游客体验已隐藏。你仍可登录或尝试注册。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "游客体验（无需注册）" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "注册" })).toBeInTheDocument();
  });

  it("restores focus to the login panel after the account-options retry succeeds", async () => {
    let requests = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        requests += 1;
        return requests === 1
          ? new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 })
          : new Response(JSON.stringify({ guest_access_enabled: false, registration_enabled: true }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const user = userEvent.setup();
    renderLoginPage();

    await user.click(await screen.findByRole("button", { name: "重试" }));

    expect(await screen.findByText("账号选项已重新读取。")).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveFocus();
  });

  it("shows the backend's Chinese registration-disabled message", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 });
      }
      if (url.endsWith("/api/v1/auth/csrf/")) return new Response(JSON.stringify({ csrfToken: "token" }));
      if (url.endsWith("/api/v1/auth/register/") && init?.method === "POST") {
        return new Response(JSON.stringify({ detail: "当前暂不开放注册。" }), { status: 403 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const user = userEvent.setup();
    renderLoginPage();

    await user.click(await screen.findByRole("tab", { name: "注册" }));
    await user.type(screen.getByLabelText("邮箱"), "trial@example.test");
    await user.type(screen.getByLabelText("昵称"), "Trial");
    await user.type(screen.getByLabelText("密码"), "strong password 123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("当前暂不开放注册。");
  });

  it("moves focus and selection through account tabs with arrow keys", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/options/")) {
        return new Response(JSON.stringify({ guest_access_enabled: false, registration_enabled: true }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const user = userEvent.setup();
    renderLoginPage();

    const loginTab = await screen.findByRole("tab", { name: "登录" });
    const registerTab = screen.getByRole("tab", { name: "注册" });
    loginTab.focus();
    await user.keyboard("{ArrowRight}");

    expect(registerTab).toHaveFocus();
    expect(registerTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "创建账号" })).toBeInTheDocument();
  });
});
