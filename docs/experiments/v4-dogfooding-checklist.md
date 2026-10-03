# V4 One-Workday Dogfooding Checklist

Use one real user and one ordinary workday. Do not collect task names, private calendar details, email, chat transcripts, credentials, or screenshots that expose personal information. Record short sanitized identifiers such as `task-A`, behavior, and time bucket only.

## Before starting

- [ ] Confirm staging or the intended non-production account and current date/timezone.
- [ ] Choose 3–6 ordinary, non-sensitive tasks the user already intends to do.
- [ ] Do not seed a scripted “happy path” after the user begins; let the user work normally.
- [ ] Explain that feedback is about observed behavior, not a satisfaction score.
- [ ] Record start/end time only if the participant agrees and the observer can time consistently; otherwise mark decision time `unmeasured`.

## Observe the day

| Moment | Record these behaviors |
| --- | --- |
| First open | Why the user opened TimeAgent, first visible page, time to first action if timed reliably |
| Morning Brief | Opened/ignored, what was confusing, whether they switched to Calendar or another briefing source |
| Today | Which items they acted on; whether Now/Next/Later matched their expectation; any duplicate or stale item |
| Plan | Whether they typed a request or used a structured control; repeated context; clarifications; what they expected Apply to do |
| Execution | Start/complete action, interruption, error, recovery, whether the UI interrupted focused work |
| Completion Harvest | Chosen/ skipped feedback, reason, whether the card felt useful or obstructive |
| Replan/conflict | Trigger, Chat vs ConflictResolver choice, number of page hops, re-entry of known facts, approval understanding |
| Day Closing | Whether selection was understood, whether unselected work felt safe, draft recovery after navigating away/reload |
| Tool switching | Exact moment they returned to another Calendar/Todo tool and the action they did there |
| End of day | What was still unclear or cumbersome; do not ask only “Are you satisfied?” |

## Sanitized event log

| Time bucket | Page/feature | User action | Confusion or friction | Recovery / alternate tool | Severity |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## Count only observable outcomes

Capture page transitions, text submissions, structured UI actions, Agent turns, tool calls, clarifications, approvals, errors, and recoveries. Keep correctness and final state ahead of speed. Mark clicks/decision time `unmeasured` if there is no reliable counter/timer. Store no exact private prompt, title, schedule, email, or transcript.

At the end, summarize the most costly three observed frictions and link each to a sanitized event-log row. Do not convert one participant's preference into a population claim.
