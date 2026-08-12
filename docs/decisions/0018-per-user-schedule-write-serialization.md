# 0018: Per-user schedule write serialization

## Status

Accepted.

## Context

Calendar events, tasks and reminders are separate business entities, but their write paths overlap. Event and planned-task changes deterministically synchronize reminder rows, all schedule facts reference the same user, and event conflict checks must remain atomic with the final write. LangGraph may execute multiple tool calls from one model response concurrently, while separate HTTP requests and Celery jobs can also write for the same user.

Using the `auth_user` row as the schedule mutex creates unnecessary interaction with PostgreSQL foreign-key locks. A concurrent event write and custom reminder write can therefore acquire locks in different orders and form a deadlock even though their requested records are distinct.

## Decision

- Every Application Service transaction that changes a user's events, tasks, reminders, recurring series, derived reminders or an applied schedule plan acquires the same transaction-scoped PostgreSQL advisory lock before locking or writing business rows.
- The lock key is partitioned by user. Different users continue to write concurrently; reads, model calls and external-provider calls do not acquire this lock.
- The lock is acquired only inside `transaction.atomic()` and is released automatically when the transaction commits or rolls back.
- SQLite uses a `select_for_update()` fallback for local tests. PostgreSQL remains the production authority and supplies the real concurrency guarantee.
- Optimistic version checks, idempotency keys and entity-level `select_for_update()` locks remain in place. The advisory lock coordinates lock ordering; it does not replace those invariants.

## Consequences

- Same-user schedule writes are serialized, preventing deadlocks and stale conflict checks across Agent, API and Celery entry points.
- Different users and all read-only tools retain normal concurrency.
- A schedule write transaction must not perform model or external network calls while holding the lock.
