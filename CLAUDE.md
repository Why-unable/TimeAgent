# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project shape

Time Agent is a time-centric personal task manager. It is a Django + React monorepo with a Time Steward LangGraph agent, a deterministic Briefing workflow, and a Capacitor Android shell that reuses the Vite bundle. The canonical Chinese README ([README.md](README.md)) and rules ([AGENTS.md](AGENTS.md)) take precedence over anything here; the roadmap phases live in [ROADMAP.md](ROADMAP.md) and detailed specs in [PROJECT_SPEC.md](PROJECT_SPEC.md) / [FRONTEND_SPEC.md](FRONTEND_SPEC.md). The repo is currently at Phase 10.

## Commands

Backend deps use `uv` (Python 3.12); frontend uses `npm` with a checked-in `package-lock.json`. Never introduce `pip freeze` output or replace npm with another manager.

Common recipes ([Makefile](Makefile)):

- `make up` / `make down` — full Compose stack.
- `make backend-test` → `cd backend && uv run pytest` (pytest-django, `config.settings.test`).
- `make frontend-test` → `cd frontend && npm test` (Vitest run mode; `npm run test:watch` for watch).
- `make lint` → Ruff + mypy (strict) + ESLint.
- `make check` → Django `check` + pytest + Ruff + mypy + Vitest + `vite build`. Run this before finishing anything non-trivial.
- `make migrate` / `make migrations` — apply migrations / assert none are pending.
- `make api-schema` → regenerate [backend/openapi.json](backend/openapi.json). `make frontend-api` chains it and regenerates [frontend/src/api/generated/schema.d.ts](frontend/src/api/generated/schema.d.ts). **Any API change requires re-running `make frontend-api` and committing both files**; the generated schema is never hand-edited.

Single test / narrower runs:

- Backend one test: `cd backend && uv run pytest tests/test_events.py::test_name`. Test discovery is rooted at `backend/tests/` per [backend/pyproject.toml](backend/pyproject.toml).
- Frontend one file: `cd frontend && npm test -- src/features/tasks/foo.test.tsx` (or `npx vitest run <path>`).
- Playwright: `cd frontend && npx playwright install chromium` once, then `npm run test:e2e`.
- Real SMTP / Web Push tests are opt-in behind `RUN_LIVE_NOTIFICATION_TESTS=1` (see [backend/tests/test_notifications_live.py](backend/tests/test_notifications_live.py)).
- Agent tool-trajectory eval (calls real models, writes are rolled back): `cd backend && uv run python manage.py evaluate_time_steward [--model claude|deepseek]`.
- Config sanity for the agent: `cd backend && uv run python manage.py check_agent_config`.
- External weather/news probes: `cd backend && uv run python manage.py check_external_providers --weather-location 上海 --topic Python`.

### Local production and Android release facts

- On the current host, this checkout at `/home/hyj/Project/TimeAgent` is also the live Compose deployment. The production services are started with `docker-compose.yml` plus `docker-compose.prod.yml`; do not assume a separate remote server or require SSH before checking the local Docker daemon.
- Nginx mounts the host `releases/` directory read-only at `/var/www/time-agent-releases`. Android update metadata comes from the host `.env` `ANDROID_UPDATE_*` values and is loaded by Django, so an APK release requires both publishing the file and recreating Django (plus verifying Nginx can read the file).
- The current production signing lineage (including version `1.1.7`) uses `/home/hyj/.android/debug.keystore`, alias `androiddebugkey`, with the conventional Android debug-keystore credentials. Its SHA-256 certificate fingerprint is `e7fb9f63eff74b44c3ec32dafdcb2c726ff2d031c5c7614f70dda486916a783e`. Despite the filename, this exact file is the compatibility-critical production signer: do not delete, regenerate, or replace it when publishing an in-place update.
- Before every Android release, compare the candidate APK signer to the previous published APK with Android SDK `apksigner`; matching the path or alias alone is insufficient. Then increment both `versionCode` and `versionName` in `frontend/android/app/build.gradle`, build with `VITE_API_BASE_URL=https://steward.uresofa.me`, publish the APK, update `.env`, recreate the relevant containers, and verify the manifest/hash. The complete commands and safety notes are in [docs/android-build-and-verify.md](docs/android-build-and-verify.md).

Local dev without Docker: `docker compose up -d postgres redis`, then `cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py setup_langgraph && uv run python manage.py runserver`; run Celery worker + beat in separate terminals; run `cd frontend && npm install && npm run dev` (Vite proxies `/api` and `/health` to `:8000`).

Windows PowerShell users can substitute `npm.cmd` when `npm.ps1` is blocked by execution policy.

## Runtime architecture (backend)

Django settings split into `base` / `development` / `test` / `production` under [backend/config/settings/](backend/config/settings/); `pytest` and `manage.py check` both use `config.settings.test`. URL root is [backend/config/urls.py](backend/config/urls.py) and everything mounts under `/api/v1/`. Celery lives in [backend/config/celery.py](backend/config/celery.py). All datetimes are stored in UTC; user-facing formatting resolves through IANA timezones via helpers in [backend/common/time.py](backend/common/time.py) and [backend/common/clock.py](backend/common/clock.py) — never call `datetime.now()` directly in business code.

Every app in [backend/apps/](backend/apps/) follows the same shape: `models.py` (domain) → `services.py` (application service, does all writes) → `views.py` + `serializers.py` (DRF). The hard rule from [AGENTS.md](AGENTS.md) is **Tool → Application Service → Domain/Repository → ORM**. Views and Agent tools never touch the ORM directly, and Serializers never persist — writes always go through the service. Optimistic locking (events use `expected_version`) and idempotency keys (reminders, notifications) live in the service layer.

Key apps and how they compose:

- `preferences`, `accounts` — user + auth + IANA timezone. Auth is same-origin Django Session for the web PWA and DRF `Token` for the Capacitor Android shell (mutually exclusive; see [frontend/src/api/client.ts](frontend/src/api/client.ts) and ADR 0014). The token path skips CSRF and cookies entirely. Optional public demos create isolated expiring guest users with server-enforced quotas and disabled memory/external notification capabilities (ADR 0020).
- `events`, `tasks`, `reminders`, `today`, `planning` — core domain. Events are actual time occupation with a version; tasks are work with optional planned start/end that spawn deterministic 7d/3d/1d/30m relative reminders; events spawn 1d/2h/30m reminders. `TaskExecutionSignal` records explicit started/paused/resumed/completed/skipped evidence through its Application Service and is the source for later plan/actual calibration. Conflict detection uses half-open intervals; free-time search combines working hours + events + planned tasks.
- `reminders` dispatch — Celery Beat scans due reminders idempotently and hands them to notification providers. **No LLM ever runs in the reminder path.**
- `agents` — the Time Steward. Built with LangChain `create_agent()` ([backend/apps/agents/agents/time_steward.py](backend/apps/agents/agents/time_steward.py)) plus middleware and a `ToolRuntime` context ([backend/apps/agents/context.py](backend/apps/agents/context.py), [backend/apps/agents/tools/](backend/apps/agents/tools/)). LangGraph outer graph ([backend/apps/agents/outer_graph.py](backend/apps/agents/outer_graph.py)) only handles routing, handoff, interrupt/resume and deterministic workflows — it does not re-implement the inner agent loop. Non-secret config is [backend/config/agent.example.yaml](backend/config/agent.example.yaml) (copy to `agent.yaml`, point `TIME_AGENT_CONFIG_PATH` at it); Pydantic-validated at startup, cached, so agent config changes require restarting Django+Celery. Supported providers are only `openai_compatible` and `anthropic`.
- `action_proposals` — HITL boundary. High-risk tools return an `ActionProposal` and pause the run via LangChain `HumanInTheLoopMiddleware` + LangGraph `interrupt`; approval resumes the same thread with `Command(resume=...)`. `create_event` supports approve / edit-then-approve / reject; the `cancel_*` tools only support approve / reject. `ACTION_PROPOSAL_TTL_SECONDS` (default 24 h) governs expiry — Celery Beat rejects expired proposals, never auto-approves.
- `conversations` — chat + AgentRun persistence, SSE event stream, and cancellation. Chat pages talk to `/api/v1/chat/...`; the Time Steward can hand off to the Briefing workflow via `Command.PARENT`.
- `briefings` — deterministic parallel-Section workflow with a short-lived read-only Briefing Agent (weather + news + schedule tools). Structured output via LangChain `create_agent(response_format=...)`; DeepSeek uses `thinking: {type: disabled}` so ToolStrategy can commit the final report. Config also lives in [backend/config/agent.yaml](backend/config/agent.yaml) (`agent.briefing_model`).
- `external_data` — providers for weather (Open-Meteo) and news (curated RSS/Atom feeds in [backend/config/providers.yaml](backend/config/providers.yaml), path overridable via `TIME_AGENT_PROVIDER_CONFIG_PATH`). Users set locations and topics on `/settings/time`; the backend maps aliases → canonical topics → allowed feeds. Weather preferences preserve administrative representative coordinates and user-authorized device GPS independently, and briefing sources label their coordinate role (ADR 0019). Provider config changes need a Django + Celery restart.
- `notifications` — `NotificationDelivery` state machine, stable idempotency keys, Celery async delivery with bounded retries, and a provider registry for Console / Django Email / Web Push. VAPID private key is server-only; the public key is exposed through an authenticated endpoint. Per-channel results for reminders and briefings are audited independently.
- `time_memory` — deterministic long-term Time Steward profile derived from PostgreSQL schedule facts and stored as rebuildable LangGraph Store data. Generation/injection, reset and exclusions are user-controlled; Briefing never consumes this profile (ADR 0015).
- `app_updates` — authenticated Android release-manifest API. Native code verifies HTTPS, size, SHA-256, package ID, version monotonicity and signing certificate before handing installation to Android; Django never serves APK bodies (ADR 0016).
- `observability` — bounded-label business/LLM metrics, sanitized `LLMCallAudit` persistence and runtime Alertmanager configuration. Prometheus/Grafana/Alertmanager/Loki/Alloy and exporters are optional local-only production overlays (ADR 0017).
- `integrations` — external calendar Provider Protocol, Pydantic DTOs, capabilities, `CalendarSyncConnection`, read-only Provider-driven sync and connection status API (`/api/v1/integrations/calendar/connections/`). ICS and Google Calendar read-only Providers are implemented; Google uses hashed one-time OAuth state, independently encrypted/rotatable credentials, bounded pagination/incremental tokens and account/calendar-scoped event identity. Bounded Celery polling is implemented. Microsoft OAuth, webhooks and external write-back are not implemented; live Google sandbox verification remains an external gate.
- `insights` — deterministic `TemporalInsight` detector/inbox for deadline risk, with evidence, deduplication, expiry and user disposition; it does not call LLM or send notifications directly.

## Runtime architecture (frontend)

React 19 + Vite + React Router + TanStack Query + Zustand + Tailwind + FullCalendar. Feature code lives under [frontend/src/features/](frontend/src/features/) (`accounts`, `agent-runs`, `approvals`, `briefings`, `events`, `notifications`, `onboarding`, `preferences`, `reminders`, `tasks`, `today`, `workspace`); each feature owns its API module, components, hooks, and tests. Routing is centralized in [frontend/src/app/router.tsx](frontend/src/app/router.tsx), providers/query-client in [frontend/src/app/](frontend/src/app/), the global error boundary in [frontend/src/app/error-boundary.tsx](frontend/src/app/error-boundary.tsx). Time-memory controls are at `/settings/time-memory`; native self-update settings are at `/settings/app`.

All HTTP goes through [frontend/src/api/client.ts](frontend/src/api/client.ts) — do not scatter `fetch()`. The client picks native token auth (Authorization: Token …, `credentials: "omit"`) when [frontend/src/api/auth-token.ts](frontend/src/api/auth-token.ts) has a value, otherwise the same-origin session + CSRF path. It also sends `X-Request-ID` on every call, which is the correlator surfaced by the JSON backend logs and Nginx.

Platform split: [frontend/src/platform.ts](frontend/src/platform.ts) is a dependency-free `isNativePlatform()` probe so the web build never imports Capacitor. Capacitor-only wiring (local notifications, secure token storage, deep links) lives in [frontend/src/native/](frontend/src/native/) and is loaded lazily from [frontend/src/bootstrap.ts](frontend/src/bootstrap.ts). The Android shell is under [frontend/android/](frontend/android/); see [docs/android-build-and-verify.md](docs/android-build-and-verify.md) and ADR 0014. Web push and PWA registration live in [frontend/src/pwa.ts](frontend/src/pwa.ts).

The frontend must not re-derive backend rules (conflicts, permissions, state machines, idempotency, risk classification). Read state from the server, present it, and let the API reject.

## Contract, docs, and decision log

- OpenAPI contract: [backend/openapi.json](backend/openapi.json) → generated TS at [frontend/src/api/generated/schema.d.ts](frontend/src/api/generated/schema.d.ts). Regenerate both after any API surface change.
- Deep-dive docs: [docs/architecture/](docs/architecture/) (phase writeups, agent config, calendar/task/reminder state machines, today summary, planning, time foundation).
- Decisions of record: [docs/decisions/](docs/decisions/) — every new agent, persistence boundary, or deployment topology change needs its own ADR (see AGENTS.md rule 25).
- 中文开发指南: [开发指南01.md](开发指南01.md) is the canonical phase-by-phase roadmap the team follows.

## Non-obvious rules ([AGENTS.md](AGENTS.md))

- PostgreSQL is the sole authority for business truth. Memory, chat history, and caches are not substitutes.
- Never inject the model's implicit clock into relative-time reasoning — always pass an explicit current time.
- The Time Steward must be built via LangChain `create_agent()`; the outer LangGraph does routing/handoff/interrupt/deterministic workflows only.
- Reminders dispatch through deterministic Celery, never through an LLM. Scheduled briefings enter the Briefing workflow directly and skip the Time Steward.
- High-risk writes require an `ActionProposal` + HITL approval; never bypass the policy layer.
- No API keys, tokens, session cookies, personal data, or model private reasoning in logs, memory, or `VITE_*` env vars (Vite variables ship to browsers).
- Do not add speculative abstractions (empty interfaces, fake agents) or scope creep (multi-agent, microservices, vector DB, complex RBAC) at this phase.
- Do not modify files outside the current task's scope, and never silently delete existing behavior.
