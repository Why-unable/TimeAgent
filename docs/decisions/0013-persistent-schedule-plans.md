# ADR 0013: Persistent schedule plans

`SchedulePlan` is a PostgreSQL-backed, versioned planning proposal. Creating a plan is read-only with
respect to calendar and task business facts: it stores task IDs, expected task versions, proposed UTC slots,
and the selected application strategy.

`apply_schedule_plan` is the only transition that changes business facts. It is a high-risk HITL tool and
executes in one transaction. Before writing, it locks the plan and target tasks, checks that the plan remains
a draft and that every task still has the recorded version. The `plan_tasks_only` strategy writes task planned
ranges; `create_linked_event_blocks` delegates to `EventService`, so final event conflict validation and
reminder synchronization remain authoritative.

Plans are not LangGraph state, memory, or chat text. They are durable approval artifacts and become `applied`
exactly once; a stale or previously applied plan cannot be replayed.
