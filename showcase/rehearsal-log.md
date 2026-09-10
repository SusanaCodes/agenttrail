# Rehearsal log

Honest record of full end-to-end rehearsals of the **two-minute**
showcase. **At least two complete runs must be logged before the
showcase — and Ticket 13 is not complete until they genuinely have
been.**

Rules for this log:

- Fill an entry in **immediately after** performing the rehearsal —
  never in advance, never from memory days later.
- A rehearsal counts only if it was complete end to end: all three
  slides, both live commands, both Cmd-Tab switches, and a
  fallback-recording playback check.
- Time the run with a real timer. Target **1:50**; hard stop **2:00**.
  A run over 2:00 is a **not ready** verdict regardless of anything
  else.
- Record what actually happened, including mistakes and timing
  overruns. A logged problem is a rehearsal doing its job; an entry
  with no observations at all is a warning sign, not a good sign.
- Nothing below is pre-filled. Every `_(to be completed)_` field is
  for Susana to complete after the run. Do not fabricate dates,
  durations, results, playback checks, or witnesses.

- **This file is public.** Record no witness personal names, machine
  names, private paths, or account details — use roles ("a
  colleague") and generic descriptions ("presentation laptop").

Add further entries by copying the template at the bottom.

---

## Rehearsal 1

| Field | Record |
|---|---|
| Date and time (start) | _(to be completed)_ |
| Git commit / working-tree state (`git rev-parse --short HEAD`, `git status --short`) | _(to be completed)_ |
| Machine used (generic description, no hostname) | _(to be completed)_ |
| Total duration (target 1:50, hard stop 2:00) | _(to be completed)_ |
| v1 gate result (expect `CI GATE: PASS`, exit 0) | _(to be completed)_ |
| v2 gate result and exit status (expect `CI GATE: FAIL`, exit 1 — intentional) | _(to be completed)_ |
| Cmd-Tab switches (instant? wrong app? display issues?) | _(to be completed)_ |
| Mistakes or delays (typos, stumbles, overruns — with rough timestamps) | _(to be completed)_ |
| Corrective action taken (what will change before the next run) | _(to be completed)_ |
| Fallback video playback result (played end to end? duration ~45–50 s? from which copy?) | _(to be completed)_ |
| Final verdict: **ready / not ready** | _(to be completed)_ |
| Reviewer or witness (role only, or "none — solo run") | _(to be completed)_ |

## Rehearsal 2

| Field | Record |
|---|---|
| Date and time (start) | _(to be completed)_ |
| Git commit / working-tree state (`git rev-parse --short HEAD`, `git status --short`) | _(to be completed)_ |
| Machine used (generic description, no hostname) | _(to be completed)_ |
| Total duration (target 1:50, hard stop 2:00) | _(to be completed)_ |
| v1 gate result (expect `CI GATE: PASS`, exit 0) | _(to be completed)_ |
| v2 gate result and exit status (expect `CI GATE: FAIL`, exit 1 — intentional) | _(to be completed)_ |
| Cmd-Tab switches (instant? wrong app? display issues?) | _(to be completed)_ |
| Mistakes or delays (typos, stumbles, overruns — with rough timestamps) | _(to be completed)_ |
| Corrective action taken (what will change before the next run) | _(to be completed)_ |
| Fallback video playback result (played end to end? duration ~45–50 s? from which copy?) | _(to be completed)_ |
| Final verdict: **ready / not ready** | _(to be completed)_ |
| Reviewer or witness (role only, or "none — solo run") | _(to be completed)_ |

---

## Template for additional rehearsals

Copy this block, renumber it, and complete it after the run:

```markdown
## Rehearsal N

| Field | Record |
|---|---|
| Date and time (start) | |
| Git commit / working-tree state | |
| Machine used (generic description, no hostname) | |
| Total duration (target 1:50, hard stop 2:00) | |
| v1 gate result | |
| v2 gate result and exit status | |
| Cmd-Tab switches | |
| Mistakes or delays | |
| Corrective action taken | |
| Fallback video playback result | |
| Final verdict: ready / not ready | |
| Reviewer or witness | |
```

## Readiness criteria

The showcase is rehearsal-ready only when **all** of the following are
true:

- [ ] At least two complete end-to-end rehearsals are logged above
- [ ] The most recent rehearsal's verdict is **ready**
- [ ] The most recent rehearsal ran at or under **2:00** (target 1:50)
- [ ] The fallback recording exists, runs ~45–50 seconds, and was
      played end to end successfully in the most recent rehearsal
