# Mobile Accessibility

- Core actions are keyboard/touch accessible and have at least 44 × 44 CSS px targets; prefer 48 px on Android.
- Text/background contrast targets WCAG 2.2 AA: 4.5:1 for normal text, 3:1 for large text and meaningful UI boundaries.
- Focus is visible and unobscured. After a modal closes, restore focus to its opener; when a committed action creates a follow-up interaction, move focus to its heading/status intentionally.
- Sheets/drawers have an accessible title, close action, focus entry/trap/restore, Escape support, and Android Back integration where native Capacitor is active.
- Navigation uses landmarks, meaningful labels, `aria-current`, and a visible active state that is not color-only.
- Live run/completion/error states use restrained live regions; do not mark the entire conversation as one noisy live region if streaming causes repeated announcements.
- Inputs keep visible labels or accessible names; browser autofill, virtual keyboard and text zoom must remain usable.
- Layout supports 200% text zoom and reflow at 320 CSS px without hiding core actions or requiring horizontal page scrolling.
- Respect reduced-motion preferences. No hover-only action.
- Playwright/RTL automation is not a substitute for TalkBack or physical-device evaluation; report that device testing is `NOT EXECUTED` when no device is available.
