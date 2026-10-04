# Android WebView Requirements

The installed client remains React + Vite + Capacitor + Android WebView. Do not replace it with React Native, Flutter or Compose in this initiative.

## Viewport and safe area

- Verify viewport meta configuration in `frontend/index.html`, Capacitor configuration in `frontend/capacitor.config.ts`, and Android manifest/window flags before altering edge-to-edge behavior.
- Fixed bottom navigation, composer, floating actions and sheets account for `env(safe-area-inset-*)`.
- The viewport declares `viewport-fit=cover` so WebView safe-area inset values are available. This is a CSS capability check only; physical Android 15/16 edge-to-edge and gesture/three-button navigation must still be checked on device.
- Keep body/page scrolling distinct from internal drawers, sheets and chat message scrolling.

## Keyboard

- Use `window.visualViewport` when available; handle resize and scroll and remove listeners on unmount.
- Keep the focused input, last relevant message and submit/cancel button visible while Android IME is open.
- Hide or inert the bottom navigation while the composer keyboard is active; preserve enough scroll padding to reach the last message.
- Do not assume desktop Enter-to-submit on touch keyboards; keep a visible send button and preserve composition input.

## Android Back and browser history

- First close the topmost sheet/drawer/modal. Otherwise use normal Router/browser history navigation; at the home destination allow the system default behavior.
- Do not register a global back handler that steals web history. If Capacitor App API is used, document and test listener lifecycle and remove it on unmount.

## Evidence boundary

Playwright mobile viewport tests validate browser layout and interactions only. Physical APK install, TalkBack, IME resize/pan, system bars, navigation gestures, notification deep links and native Back must be marked `NOT EXECUTED` without a connected Android device.
