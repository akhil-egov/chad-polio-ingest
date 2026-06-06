# Triage Labels — chad-polio-ingest

These five labels encode workflow state.

| Role | Label string | Meaning |
|------|-------------|---------|
| Needs evaluation | `needs-triage` | Maintainer has not yet assessed this issue |
| Waiting on reporter | `needs-info` | Blocked — need more detail from the person who filed it |
| Agent-ready | `ready-for-agent` | Fully specified; an AFK agent can implement with no human context |
| Human-ready | `ready-for-human` | Needs human judgement or context to implement |
| Won't fix | `wontfix` | Will not be actioned — close with this label and a comment explaining why |

## Rules

- An issue starts with `needs-triage`.
- Only one workflow label at a time — remove the previous before applying the next.
- `ready-for-agent` requires: clear acceptance criteria, no open questions, all referenced ES fields/indices confirmed in live data.
- `wontfix` must always have a closing comment.
