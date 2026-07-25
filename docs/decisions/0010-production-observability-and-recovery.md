# 0010: Production Observability and Recovery

## Status

Accepted

## Decision

- Correlate every Django HTTP response with `X-Request-ID` and emit a compact
  JSON completion log without query strings, cookies, credentials, request
  bodies, or user content.
- Use `django-prometheus` for the standard Django `/metrics` endpoint.
  The endpoint is scraped only across Docker's internal network; Nginx denies
  public access to it.
- Provide Prometheus as an opt-in Compose overlay with two baseline alerts:
  unavailable Django target and HTTP 5xx responses.
- Use explicit, host-run PowerShell scripts for PostgreSQL custom-format backup
  and deliberately confirmed restore. Backups are ignored by Git.

## Consequences

The default runtime remains a small monolith. Operators can enable monitoring
without exposing its UI publicly, and can practice restoration against a
non-production Compose project before treating a backup policy as complete.
