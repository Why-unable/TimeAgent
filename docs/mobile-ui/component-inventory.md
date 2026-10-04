# Mobile Component Inventory

| Component | Purpose / when to use | Avoid | State and size | Accessibility |
|---|---|---|---|---|
| MobileHeader | Page identity/date and one contextual action | Repeating desktop toolbar | 48–64 px content; title/body roles | semantic heading; action named |
| BottomNavigation | Four persistent top-level destinations | Feature lists or route-specific controls | Fixed; every item at least 48 px target | labeled `nav`; `aria-current` |
| SectionHeader | Name a content group and optional count | Decorative card title | 17/24 title; count secondary | heading level follows document |
| ListRow | Navigate/select one entity | Multi-action dense dashboard row | min-height 48 px | full row focus, clear accessible name |
| TaskRow | Show task title, time and one primary action | Icon-only required action | >= 48 px controls | action names include task title |
| ScheduleRow | Show event title/time; route to detail | Full Calendar replacement | compact two-line row | time uses `time` where possible |
| PrimaryButton | One main action per local region | Accent color on every button | min-height 48 px | visible label, busy/disabled state |
| IconButton | Secondary compact action | Unlabeled critical action | >= 44 px, preferably 48 px | explicit `aria-label` |
| Chip | Lightweight optional prompt/filter | Primary transaction | min-height 44 px; scroll row | button semantics and focus |
| StatusBadge | Draft/applied/error/completion state | Color-only state | compact readable text | state expressed in text |
| MobileBottomSheet | Focused mobile edit/selection | Long unrelated settings list | full/partial height; safe area | title, focus enter/trap/restore, Back/Escape |
| Drawer | Me or conversation-history navigation | Primary in-flow content | width bounded by viewport | close action, focus management |
| EmptyState | Explain next step when no data | Permanent marketing landing | one primary CTA | concise live/error semantics |
| InlineAlert | Actionable warning/error near affected object | Large dashboard warning card | content-driven; >= 14 px text | `role=status/alert` as appropriate |
| ExecutionCard | Distinguish the current action | One card around every section | one prominent surface max per viewport | title, time, action order |
| HarvestSheet | Optional reflection after saved completion | Blocking the completion itself | focused sheet; concise choices | focus and status return after save |

Existing React counterparts are reused where appropriate (`MobileNavigation`, `Drawer`, `TodayExecutionSurface`, `CompletionHarvest`). New shared primitives require demonstrated reuse and accessibility coverage.

## Iteration 2 additions

| Component | Purpose / when to use | Avoid | State and size | Accessibility |
|---|---|---|---|---|
| MobileMonthCalendar | Phone date navigation; selecting a date opens the agenda | Replacing desktop FullCalendar or showing dense event titles in month cells | Six-week grid; compact event marker; month navigation | Grid roles, full date names, arrow-key movement, Enter/Space selection, visible focus |
| ScheduleHubPage | Mobile overview for one selected date and tasks without planned starts | Recalculating availability, conflicts or approval state | Seven-day rail; section-level loading/errors; single filled Planning CTA | Named previous/next/current-week controls; selected date exposed beyond color |
| DayAgendaSheet | Read and act on one date's events | Hiding CRUD errors or duplicating EventEditor rules | Shared modal Drawer; safe-area footer; scroll-contained agenda | Focus management, Escape/native Back, named actions and semantic heading |
| MobileTaskActions | Keep one main execution action and progressively disclose secondary actions | Showing every icon action on every task row | Main execution + completion; More actions disclosure | Task-specific labels, pressed states, 44–48 px targets, focus recovery |

## Iteration 3 patterns using the shared Drawer

| Pattern | Purpose / when to use | Avoid | State and size | Accessibility |
|---|---|---|---|---|
| PlanningEditSheet | Edit a placed, unlocked, single-segment plan item with local start time and duration | Making drag the only edit path or duplicating feasibility rules | Shared Drawer; 15-minute step buttons; draft remains explicit | Task-specific title, timezone in labels, validation/conflict/status text stays visible in the sheet |
| ReminderCreateSheet | Enter one reminder without leaving the list context | Keeping the full create form expanded above the list | Shared Drawer; local time and optional association | Labeled fields, field errors, safe-area and focus lifecycle |
| ApprovalFilterSheet | Select one proposal status on narrow screens | Persistent row of six filters | Shared Drawer; selected value exposed in text and pressed state | Named options and focus restoration |
| MemoryConfirmSheet | Confirm forgetting or clearing derived memory | Browser-native confirmation or unclear destructive consequence | Shared Drawer; explicit return and confirm actions | Consequence text, keyboard focus, accessible button names |
