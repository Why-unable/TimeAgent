// Runtime platform detection. Kept dependency-free so the web build and tests
// never import Capacitor. The Capacitor bootstrap (native only) can call
// markNative() to make this authoritative; absent that, we sniff the global
// Capacitor bridge that the native runtime injects into the WebView.

let nativeOverride: boolean | null = null;

/** Called by the Capacitor bootstrap on native startup. */
export function markNative(value: boolean): void {
  nativeOverride = value;
}

export function isNativePlatform(): boolean {
  if (nativeOverride !== null) return nativeOverride;
  const bridge = (globalThis as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return typeof bridge?.isNativePlatform === "function" ? bridge.isNativePlatform() : false;
}
