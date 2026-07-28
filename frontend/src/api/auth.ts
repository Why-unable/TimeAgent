import { clearAuthToken, setAuthToken } from "./auth-token";
import { apiRequest } from "./client";

export type CurrentUser = {
  id: number;
  email: string;
  display_name: string;
  is_email_verified: boolean;
  is_staff: boolean;
};

export type Credentials = {
  identifier: string;
  password: string;
};

type TokenLoginResponse = {
  token: string;
  user: CurrentUser;
};

export async function ensureCsrfToken() {
  return apiRequest<{ csrfToken: string }>("/api/v1/auth/csrf/");
}

export async function registerAccount(email: string, nickname: string, password: string) {
  await ensureCsrfToken();
  return apiRequest<void>("/api/v1/auth/register/", {
    method: "POST",
    body: JSON.stringify({ email, nickname, password }),
  });
}

export async function requestEmailVerification(email: string) {
  await ensureCsrfToken();
  return apiRequest<void>("/api/v1/auth/email-verification/", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function confirmEmailVerification(uid: string, token: string) {
  await ensureCsrfToken();
  return apiRequest<void>("/api/v1/auth/email-verification/confirm/", {
    method: "POST",
    body: JSON.stringify({ uid, token }),
  });
}

export async function updateNickname(nickname: string) {
  return apiRequest<CurrentUser>("/api/v1/auth/profile/", {
    method: "PATCH",
    body: JSON.stringify({ nickname }),
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

/**
 * Token login for the native app. No CSRF is needed: the endpoint clears
 * SessionAuthentication, so this is a bare credentials-for-token exchange. The
 * returned token is persisted and picked up by apiRequest on every subsequent
 * call. Used only on native; the web client keeps using loginAccount (session).
 */
export async function loginWithToken(credentials: Credentials): Promise<CurrentUser> {
  const result = await apiRequest<TokenLoginResponse>("/api/v1/auth/token/", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  await setAuthToken(result.token);
  return result.user;
}

/** Revoke the server-side token then drop the local copy (native logout). */
export async function logoutWithToken(): Promise<void> {
  try {
    await apiRequest<void>("/api/v1/auth/token/revoke/", { method: "POST" });
  } finally {
    // Always clear locally, even if the network revoke failed, so the app
    // returns to a logged-out state rather than reusing a token it can't trust.
    await clearAuthToken();
  }
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
