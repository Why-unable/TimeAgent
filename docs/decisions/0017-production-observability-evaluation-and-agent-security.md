# 0017: Production observability, evaluation, and Agent security

## Status

Accepted; supersedes the limited dashboard scope of ADR 0010 while retaining its request-ID and backup decisions.

## Decision

- Prometheus is the SLI and alert-rule source. Labels are deliberately bounded: status, trigger type, tool name, channel and risk level; never user ID, conversation ID or request ID.
- Grafana is provisioned from version-controlled data sources and dashboards. Alertmanager receives Prometheus alerts. PostgreSQL, Redis and Celery use dedicated exporters.
- JSON application logs remain free of request bodies and secrets. Grafana Alloy reads Docker logs into Loki; `request_id` is the correlation key for an individual failure.
- Business SLIs are collected from PostgreSQL at scrape time so they are available regardless of whether Django or a Celery worker performed the transition.
- Every Time Steward and Briefing Agent model call writes a bounded `LLMCallAudit` record through an Application Service. The record contains provider-reported or explicitly marked estimated token counts, duration, component/model/status, request correlation identifiers, and the token count/ratio of the injected long-term-memory block. It never stores prompts, responses, tool arguments, user identifiers, API credentials, or private reasoning.
- Reverse-geocoding provider/result/latency, LLM input/output/total tokens, per-call token quantiles, memory-token quantiles and memory/input ratios are exposed as bounded-label Prometheus series and provisioned Grafana panels. Per-request inspection uses sanitized Loki logs rather than Prometheus labels.
- Alertmanager configuration is rendered at deployment time from the existing SMTP environment into a mode-`0600` Docker volume. SMTP credentials are not committed to the repository, and alert recipients can be separated from application email with `ALERTMANAGER_EMAIL_TO`.
- Agent evaluation uses versioned fixtures and writes immutable-schema reports containing dataset/prompt hashes, model identity, per-case tool precision/recall, forbidden actions, response leakage checks and latency. Evaluation writes remain inside a rolled-back transaction.
- A real-provider evaluation run is a mandatory release gate together with static checks, tests, Django checks and migration drift checks. Provider unavailability or missing credentials fails closed; a mock-model run is suitable only for development tests and cannot approve a release.
- LangSmith tracing/evaluation is optional because production traces may contain personal data. Enabling it requires an explicit data-processing decision, retention policy and sampling policy.
- Prompt injection is mitigated by capability restriction, Application Service authorization, HITL, deterministic output validation, explicit untrusted-data boundaries and security regression cases. Keyword detection is telemetry only and never an authorization decision.

## Service objectives

- Public readiness availability: 99.9% monthly.
- HTTP 5xx ratio: below 1% over 30 minutes; page at 5% over 10 minutes.
- Interactive API p95: below 2 seconds, excluding streamed Agent completion.
- Agent run success ratio: at least 95% over 24 hours.
- No Agent run remains pending/running for more than 10 minutes.
- At least 99% of successful model calls expose provider-reported token usage; estimated usage is visible but does not satisfy this objective.
- Time Steward long-term memory should remain below 35% of input tokens at p95 over 24 hours.
- No forbidden tool invocation or system-prompt/credential leakage in the release evaluation suite.
