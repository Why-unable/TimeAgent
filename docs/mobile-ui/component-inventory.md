# Mobile Component Inventory

| Component | Purpose / when to use | Avoid | State and size | Accessibility | Surface type |
|---|---|---|---|---|---|
| MobileHeader | Page identity/date and one contextual action | Repeating desktop toolbar | 48–64 px content; title/body roles | semantic heading; action named | none |
| BottomNavigation | Four persistent top-level destinations | Feature lists or route-specific controls | Fixed; every item at least 48 px target | labeled `nav`; `aria-current` | subtle surface |
| SectionHeader | Name a content group and optional count | Decorative card title | 17/24 title; count secondary | heading level follows document | none |
| MobileSectionHeader | Align a section title with one short count or action | Stacking icon, description, badge, border, and background | 17/24 title; compact trailing metadata | semantic heading; named action | none |
| ListRow | Navigate/select one entity | Multi-action dense dashboard row | min-height 48 px | full row focus, clear accessible name | divider-list |
| TaskRow | Show task title, time and one primary action | Icon-only required action | >= 48 px controls | action names include task title | divider-list |
| ScheduleRow | Show event title/time; route to detail | Full Calendar replacement | compact two-line row | time uses `time` where possible | divider-list |
| PrimaryButton | One main action per local region | Accent color on every button | min-height 48 px | visible label, busy/disabled state | none |
| IconButton | Secondary compact action | Unlabeled critical action | >= 44 px, preferably 48 px | explicit `aria-label` | none |
| Chip | Lightweight optional prompt/filter | Primary transaction | min-height 44 px; scroll row | button semantics and focus | none |
| StatusBadge | Draft/applied/error/completion state | Color-only state | compact readable text | state expressed in text | none |
| MobileBottomSheet | Focused mobile edit/selection | Long unrelated settings list | full/partial height; safe area | title, focus enter/trap/restore, Back/Escape | modal surface |
| Drawer | Me or conversation-history navigation | Primary in-flow content | width bounded by viewport | close action, focus management | modal surface |
| EmptyState | Explain next step when no data | Permanent marketing landing | one primary CTA | concise live/error semantics | none |
| InlineAlert | Actionable warning/error near affected object | Large dashboard warning card | content-driven; >= 14 px text | `role=status/alert` as appropriate | subtle surface |
| ExecutionCard | Distinguish the current action | One card around every section | one prominent surface max per viewport | title, time, action order | focus card |
| HarvestSheet | Optional reflection after saved completion | Blocking the completion itself | focused sheet; concise choices | focus and status return after save | modal surface |

Existing React counterparts are reused where appropriate (`MobileNavigation`, `Drawer`, `TodayExecutionSurface`, `CompletionHarvest`). New shared primitives require demonstrated reuse and accessibility coverage.

## Iteration 2 additions

| Component | Purpose / when to use | Avoid | State and size | Accessibility | Surface type |
|---|---|---|---|---|
| MobileMonthCalendar | Phone date navigation; selecting a date opens the agenda | Replacing desktop FullCalendar or showing dense event titles in month cells | Six-week grid; compact event marker; month navigation | Grid roles, full date names, arrow-key movement, Enter/Space selection, visible focus | subtle surface |
| ScheduleHubPage | Mobile overview for one selected date and tasks without planned starts | Recalculating availability, conflicts or approval state | Seven-date grid; section-level loading/errors; single filled Planning CTA | Named previous/next/current-week controls; selected date exposed beyond color | divider-list |
| DayAgendaSheet | Read and act on one date's events | Hiding CRUD errors or duplicating EventEditor rules | Shared modal Drawer; safe-area footer; scroll-contained agenda | Focus management, Escape/native Back, named actions and semantic heading | modal surface |
| MobileTaskActions | Keep one main execution action and progressively disclose secondary actions | Showing every icon action on every task row | Main execution + completion; More actions disclosure | Task-specific labels, pressed states, 44–48 px targets, focus recovery | none |

## Iteration 3 patterns using the shared Drawer

| Pattern | Purpose / when to use | Avoid | State and size | Accessibility | Surface type |
|---|---|---|---|---|
| PlanningEditSheet | Edit a placed, unlocked, single-segment plan item with local start time and duration | Making drag the only edit path or duplicating feasibility rules | Shared Drawer; 15-minute step buttons; draft remains explicit | Task-specific title, timezone in labels, validation/conflict/status text stays visible in the sheet | modal surface |
| ReminderCreateSheet | Enter one reminder without leaving the list context | Keeping the full create form expanded above the list | Shared Drawer; local time and optional association | Labeled fields, field errors, safe-area and focus lifecycle | modal surface |
| ApprovalFilterSheet | Select one proposal status on narrow screens | Persistent row of six filters | Shared Drawer; selected value exposed in text and pressed state | Named options and focus restoration | modal surface |
| MemoryConfirmSheet | Confirm forgetting or clearing derived memory | Browser-native confirmation or unclear destructive consequence | Shared Drawer; explicit return and confirm actions | Consequence text, keyboard focus, accessible button names | modal surface |

## V2 visual hierarchy additions

| Component | Purpose / when to use | Avoid | State and size | Accessibility | Surface type |
|---|---|---|---|---|---|
| ReminderStatusGroup | Group failed, pending, recent and cancelled reminders | Wrapping each reminder in its own card | Section heading/count plus divider rows | Ordered `h2` group headings, `h3` reminder titles, text status | divider-list |
| ApprovalDecisionSurface | Review one independent high-risk ActionProposal | Nested change/details/editor cards | One restrained amber decision surface; details and batch fields use dividers | Action names include the proposal object where available | subtle surface (decision) |
| ApprovalChangePreview | Compare a proposed change with current values | A separate bordered surface inside the decision | Compact labeled values and divider rows | User timezone labels and full readable values | divider-list |
| ApprovalBatchEditorGroup | Edit fields belonging to one batch item | A background/bordered fieldset around every item | Plain field group separated by a 1 px divider; controls keep their input boundary | Visible field labels and group legend | none (input controls only) |

Surface values: `none` means typography/spacing only; `divider-list` means sibling rows or section separators; `subtle surface` signals a low-emphasis state; `focus card` marks the current execution object; `modal surface` marks an overlay or focused form. Every retained bordered surface should explain its semantic role.
