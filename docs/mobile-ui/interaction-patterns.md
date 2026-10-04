# Mobile Interaction Patterns

## Navigation

Use one persistent four-destination bottom bar. Route-specific controls remain subordinate to the active destination. The Me drawer uses labeled sections and single-line rows; avoid a second grid of large feature cards.

## Lists and execution

Use rows for related objects. A task row exposes one primary action; secondary actions go behind a clear text action or detail route. A focused execution surface may highlight one current/next item, followed by a short Next list and collapsed Later content.

## Sheets and drawers

Use one shared overlay primitive for focused selection/editing. It must expose a title, have an explicit close control, support Escape/Android Back, restore focus, and keep content inside safe areas. Do not open a sheet for trivial navigation when a route is clearer.

## Completion and planning

Task completion remains immediate and saved before optional harvest feedback. Feedback never gates the completion action. Plan edits remain drafts; approval and apply use existing ActionProposal + HITL behavior. Show retry/review when safe; do not make browser-only schedule decisions.

## Chat

Open directly into a conversation. On an empty conversation, keep a compact prompt and horizontally scrollable suggestion chips; the composer remains visually anchored to the bottom and visible above the software keyboard. While a run is active, preserve cancellation and progress affordances.

## Motion and haptics

Honor `prefers-reduced-motion`. Use motion only to explain state changes. No haptics dependency is added in V1; if introduced later, first record a design decision and limit vibration to completion/reorder/important confirmation.
