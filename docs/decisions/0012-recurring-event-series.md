# ADR 0012: Finite recurring event series

Recurring calendar commitments are represented by an `EventSeries` aggregate and linked, materialized
`CalendarEvent` occurrences. A series must have either an end date or an occurrence count, is capped at
366 occurrences / days, and is created or changed only through the Event application service.

This preserves a durable rule, allows all/future scope operations, and keeps each occurrence visible to the
normal calendar, conflict detection, reminder scheduler, audit log, and HITL approval flow. We deliberately
do not support infinite recurrence in the first version.
