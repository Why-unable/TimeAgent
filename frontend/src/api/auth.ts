import { apiRequest } from "./client";

export type CurrentUser = {
  id: number;
  email: string;
  display_name: string;
  is_staff: boolean;
};

export type Credentials = {
  identifier: string;
  password: string;
};

export async function ensureCsrfToken() {
  return apiRequest<{ csrfToken: string }>("/api/v1/auth/csrf/");
}

export async function registerAccount(email: string, password: string) {
  await ensureCsrfToken();
  return apiRequest<CurrentUser>("/api/v1/auth/register/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function loginAccount(credentials: Credentials) {
  await ensureCsrfToken();
  return apiRequest<CurrentUser>("/api/v1/auth/login/", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function getCurrentUser() {
  return apiRequest<CurrentUser>("/api/v1/auth/me/");
}

export async function logoutAccount() {
  await ensureCsrfToken();
  return apiRequest<void>("/api/v1/auth/logout/", { method: "POST" });
}

export async function requestPasswordReset(email: string) {
  await ensureCsrfToken();
  return apiRequest<void>("/api/v1/auth/password-reset/", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function confirmPasswordReset(uid: string, token: string, password: string) {
  await ensureCsrfToken();
  return apiRequest<void>("/api/v1/auth/password-reset/confirm/", {
    method: "POST",
    body: JSON.stringify({ uid, token, password }),
  });
}
