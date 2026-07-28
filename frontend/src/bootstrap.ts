// App bootstrap that must complete before the first render/API call.
//
// Its main job today is hydrating the persisted auth token into memory so
// apiRequest attaches Authorization from the very first request (native app).
// The Capacitor bootstrap (native only) is loaded lazily to keep it out of the
// web bundle and out of tests.

import { loadAuthToken } from "./api/auth-token";
import { isNativePlatform } from "./platform";

export async function bootstrap(): Promise<void> {
  if (isNativePlatform()) {
    // Loaded lazily: the module imports Capacitor plugins that only exist in
    // the native runtime, so the web build never pulls them in.
    const native = await import("./native/bootstrap");
    await native.configureNative();
    await loadAuthToken();
    // Token hydration must precede reminder reconciliation, but network sync
    // must not hold the first UI render hostage on a slow mobile connection.
    void native.startNativeServices();
    return;
  }
  // Web uses the localStorage-backed store, which normally remains empty
  // because browser authentication uses the session cookie.
  await loadAuthToken();
}
