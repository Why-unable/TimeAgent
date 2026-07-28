// Unified login/logout that picks the right auth mechanism per platform:
// native (Capacitor WebView, cross-origin) uses token auth; web uses the
// existing same-origin session + CSRF flow. Callers don't need to know which.

import {
  type Credentials,
  type CurrentUser,
  loginAccount,
  loginWithToken,
  logoutAccount,
  logoutWithToken,
} from "../../api/auth";
import { isNativePlatform } from "../../platform";

export async function signIn(credentials: Credentials): Promise<CurrentUser> {
  return isNativePlatform() ? loginWithToken(credentials) : loginAccount(credentials);
}

export async function signOut(): Promise<void> {
  if (isNativePlatform()) {
    await logoutWithToken();
    return;
  }
  await logoutAccount();
}
