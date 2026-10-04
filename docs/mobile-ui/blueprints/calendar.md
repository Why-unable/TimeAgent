# Calendar Blueprint — Iteration 2

Status: Iteration 2 mobile implementation complete. Existing API and desktop FullCalendar behavior remain the source of truth.

## Audit evidence

- `CalendarPage` uses FullCalendar month/week/day views at every viewport. On phones, the extra view tabs expose the week layout that is 720 px wide with horizontal scrolling; vertical gestures can be captured by that nested scroll surface.
- Month cells also render event titles in a narrow grid. The existing `DayAgendaSheet` provides a readable event list and edit/cancel/create actions, but its mobile sheet needs safe-area padding, scroll containment and larger actions.
- Event API values include explicit instants; the page uses the account IANA timezone. Preserve this behavior and keep desktop controls intact.

## Mobile jobs and flow

1. Move to a month and identify/select a date.
2. Read that day’s events in a readable agenda surface.
3. Create an event or edit/cancel an existing event from the agenda.

On phones, month view is date navigation, not a compressed week/day scheduler. Do not show week/day toggles on the phone. Selecting a date or its event opens the day agenda sheet; the sheet owns the readable event title, local time, location, and actions. The existing floating create action stays reachable above bottom navigation and system insets.

Desktop retains FullCalendar Month/Week/Day controls and range list. Tablet behavior follows the existing breakpoint until separately reviewed.

## Interaction and states

- Month toolbar: previous/next month, current month label, Today. Every control is at least 44 px; primary actions are 48 px.
- Mobile month cells: keep date numbers legible, remove long event titles from cells, show a compact event indicator, and expose each date as a keyboard-operable grid cell with full local date and event count in its accessible name. Include arrow-key navigation and Enter/Space selection.
- Agenda sheet: use the shared modal `Drawer` contract, with the selected full date as its heading, focus entry/trap/restore, inert background, Escape/Android Back, semantic dimming scrim, safe-area bottom padding, `overscroll-behavior: contain`, background scroll containment, 44 px minimum secondary actions and 48 px primary create action.
- Empty: “这一天还没有日程” with a create-on-this-day action.
- Loading/error: retain a visible loading/error message; do not present an error as an empty day.
- Create/edit: keep the existing `EventEditor`, validation, linked-task option, optimistic-free API behavior, and timezone conversion.
- Conflict/API rejection: show the existing API error near the editor or agenda; do not make client-side conflict decisions.
- OAuth/sync: integration controls remain secondary and desktop-only as today.

## Acceptance

- Mobile shows the month view without week/day switching or horizontal page overflow at 320–430 CSS px; at widths up to 400 px the month surface uses the available viewport width without duplicated inset margins.
- Date/event selection opens a scrollable, readable agenda; long agenda scrolling cannot move the background or hide the footer behind Android navigation insets.
- Create, edit, cancel-confirm, ended-event read-only, empty and error states remain covered.
- Time shown for a known UTC fixture matches the configured user timezone; request serialization remains UTC.
- Event text over colored surfaces meets WCAG AA; local/external source is named in text where it matters, not indicated by color alone.
- Desktop month/week/day switching and existing schedule tests continue to pass.
- Playwright proves browser layout only. Native date picker, gesture navigation and TalkBack require a physical Android device.
