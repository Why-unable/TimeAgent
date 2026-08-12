export const ONBOARDING_VERSION = 1;
export const ONBOARDING_START_EVENT = "time-agent:onboarding:start";

function storageKey(userId: number): string {
  return `time-agent:onboarding:${userId}:v${ONBOARDING_VERSION}`;
}

export function hasCompletedOnboarding(userId: number): boolean {
  try {
    return globalThis.localStorage?.getItem(storageKey(userId)) === "completed";
  } catch {
    return false;
  }
}

export function markOnboardingCompleted(userId: number): void {
  try {
    globalThis.localStorage?.setItem(storageKey(userId), "completed");
  } catch {
    return;
  }
}

export function resetOnboarding(userId: number): void {
  try {
    globalThis.localStorage?.removeItem(storageKey(userId));
  } catch {
    return;
  }
}

export function requestOnboardingStart(): void {
  globalThis.dispatchEvent?.(new Event(ONBOARDING_START_EVENT));
}
