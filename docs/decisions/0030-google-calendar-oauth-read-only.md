# ADR 0030: Google Calendar OAuth read-only boundary

- Status: accepted
- Date: 2026-08-24
- Extends: ADR 0023

## Context

The Phase A calendar slice can read ICS feeds, but it cannot authenticate to Google, safely refresh access, or distinguish the same Provider event ID across accounts/calendars. A real Provider must not put OAuth tokens in `CalendarSyncConnection`, logs, browser-visible configuration, or model context.

## Decision

- Add account/calendar identity fields to external `CalendarEvent` mirrors and make the external uniqueness boundary `user + provider + account + calendar + event`. Existing external rows are backfilled from a unique matching connection when possible and otherwise receive an explicit legacy identity.
- Public event create/update APIs no longer accept Provider `source` or external identity fields. Only `CalendarSyncService` writes external mirrors.
- Persist one encrypted `CalendarOAuthCredential` per user/provider/account. Encrypt the structured token payload with Fernet using `CALENDAR_OAUTH_FERNET_KEY`; store expiry/scopes separately for lifecycle decisions, never expose encrypted or plaintext payloads through serializers.
- Persist only a SHA-256 digest of each random OAuth state. The state is user-bound, expires, and is consumed transactionally once. Callback replay fails closed.
- Implement a read-only `GoogleCalendarProvider` over the existing Provider Protocol. It supports bounded CalendarList and Events pagination, all-day/timed events, deletion tombstones and incremental sync tokens. HTTP 410 resets once to a full ranged sync; authentication, rate-limit and temporary failures become sanitized domain errors.
- OAuth callback selects the primary calendar for the first vertical slice. Additional calendar selection, webhooks and all external writes remain out of scope.
- The browser receives only a Google authorization URL and final connection status. Client IDs, client secrets, encryption keys, access/refresh tokens and authorization codes remain backend-only.

## Alternatives

- Store tokens on every calendar connection: rejected because one account credential may serve several calendars and rotation would duplicate secrets.
- Encrypt with `DJANGO_SECRET_KEY`: rejected because credential key rotation must be independent of Django signing/session rotation.
- Use Google SDK objects throughout the domain: rejected to keep Provider tests transport-injected and the service boundary replaceable.
- Prefix `external_id` with calendar text: rejected because it hides a missing data dimension, risks length/collision problems and makes migrations harder to reason about.

## Consequences

This adds a security-sensitive persistence boundary and an encryption-key deployment requirement. Losing the Fernet key makes stored credentials unreadable, so operations must back it up and rotate through an explicit re-encryption procedure. State is consumed before the authorization code is exchanged; a transient exchange or CalendarList failure therefore requires the user to start a new OAuth flow. This deliberately favors one-time replay protection over callback retry convenience. The implementation proves deterministic contract behavior with fake transports; Google sandbox consent, revocation, quota and long-running sync remain external acceptance gates and cannot be claimed from unit tests.

## Migration and rollback

- Before migration, external event uniqueness is `user + source + external_id`; no OAuth credential/state tables exist.
- Migration adds account/calendar identity, backfills from exactly one matching connection, and assigns an explicit `legacy:<source>` identity when ownership is ambiguous. It then replaces the unique/check constraints and creates encrypted credential/state tables.
- After migration, public Event serializers reject Provider identity writes and only `CalendarSyncService` maintains mirrors.
- Code rollback should first disable Google connections and preserve the current database backup. Reversing the schema migration drops encrypted credentials and requires user re-authorization; it also removes account/calendar dimensions, so it must not run while duplicate Provider IDs exist across calendars.
- Key rotation does not require a schema migration: deploy the new primary key plus old keys, run `rotate_calendar_oauth_credentials`, verify access, then remove old keys.
