# Mobile Design Tokens

The current product uses a light mobile palette in `frontend/src/styles/index.css`. These semantic values formalize the existing visual direction; component-specific Tailwind colors should not override them without a documented state reason.

## Spacing

| Token | Value | Use |
|---|---:|---|
| `space-1` | 4 px | icon/text gap |
| `space-2` | 8 px | compact control internals |
| `space-3` | 12 px | row and chip spacing |
| `space-4` | 16 px | narrow-phone gutter (<= 360 px) / section gap |
| page gutter | 20 px by default; 16 px at <= 360 px | mobile shell spacing |
| `space-5` | 20 px | major section separation |
| `space-6` | 24 px | feature surface padding |
| `space-8` | 32 px | page group separation |

### Mobile rhythm roles

| Role | Value | Use |
|---|---:|---|
| Page gutter | 16–20 px | outer content edge |
| Section gap | 24 px | separate sibling content groups |
| Row gap | 12 px | list row content and compact recommendations |
| Inline gap | 8 px | icon/label and related inline metadata |
| Control gap | 8 px | adjacent chips and buttons |
| Divider | 1 px | section and list boundaries; do not add a card border as well |

Use the spacing scale `4 / 8 / 12 / 16 / 20 / 24 / 32 px` for page gutter, section gap, row gap, inline gap, and control gap roles. The role-specific values live in `frontend/src/styles/index.css`; prefer the role token or an existing scale step over an arbitrary one-off margin.

## Radius

| Token | Value | Use |
|---|---:|---|
| `radius-control` | 10–12 px | buttons, inputs, chips |
| `radius-row` | 12 px | selected/interactive row surface |
| `radius-surface` | 16 px | independent semantic content surface |
| `radius-feature` | 16–20 px | one prominent execution or feedback surface |
| `radius-sheet` | 24 px top corners | modal bottom sheet |

Do not use a large radius by default on every section.

Ordinary sections and divider lists have no radius. A Surface must represent focus, input, decision, warning, or modal state. Avoid nested content Surfaces by default.

## Typography

| Role | Size / line height | Use |
|---|---|---|
| Display | 30/36 px | rare single hero only |
| Page title | 24/32 px | page identity |
| Section title | 17/24 px | content group |
| Body | 16/24 px | core content and actions |
| Secondary | 14/20 px | supporting facts |
| Caption | 12/16 px | metadata; never essential instructions alone |
| Button | 14–16 px, medium/semibold | concise verb-first labels |

## Color and surfaces

| Token | Value | Use |
|---|---|---|
| Page background | `#F4F7FB` | mobile app canvas |
| Surface | `#FFFFFF` | cards/sheets requiring separation |
| Muted surface | `#EDF3FA` | selected navigation and secondary controls |
| Primary text | `#172033` | headings and body |
| Secondary text | `#475569` | supporting text |
| Muted text | `#64748B` | metadata with adequate contrast |
| Border | `#CBD5E1` | control/surface boundary |
| Primary teal | `#0F766E` | primary action/selection/current state |
| Cyan accent | `#0891B2` | secondary product accent only |
| Danger | `#B91C1C` | destructive/error |
| Warning | `#92400E` | warning text; pair with light amber surface |
| Success | `#047857` | success text/current completion |

Avoid pale text on pale surfaces and using color alone to communicate state.

## Touch, border and elevation

- Minimum interactive target: 44 × 44 CSS px; primary Android targets: 48 × 48 px.
- Divider: 1 px neutral border; use before adding a container.
- Elevation: only to express overlay ordering (sheet/drawer). Inline content uses border or whitespace, not shadow stacks.
- Fixed navigation includes `env(safe-area-inset-bottom)` and a stable content clearance token.
