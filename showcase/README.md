# Final showcase package (Ticket 13)

Everything for the end-of-programme presentation of AgentTrail,
presented by Susana, within a **strict two-minute maximum**. The
working software is the centrepiece; this package frames and
demonstrates it without changing it — no application behaviour, test,
threshold, or safety control was modified for the showcase.

For current readers: the fictional benefit-style cases are the bundled
worked example of a reusable audit-and-evaluation pattern, not a real
service or benefit policy. Other workflows require adaptation; see the
[adaptation guide](../docs/adapting-agenttrail.md). The deck and its
word-for-word content remain the record of the September showcase.

The communication goal — the one thing assessors should remember:
**AgentTrail detects tested routing regressions recorded in the audit
trail for the selected fixture snapshot.** Fixture responses are not
authenticated, and merge blocking depends on GitHub repository rules
requiring the `evaluation-gate` check, which was unverified when the
showcase was given and has been required by an active ruleset on
`main` since 11 October 2026 (see
[ci-gate.md](../docs/ci-gate.md#required-branch-protection)).

There is **one** authoritative presentation path: three slides, two
live terminal commands, a ~45–50-second fallback recording. The
earlier seven-minute and five-minute variants are withdrawn.

## Contents

| File | Purpose |
|---|---|
| [AgentTrail-final-showcase.pptx](AgentTrail-final-showcase.pptx) | The three-slide 16:9 deck (hook · architecture · result) |
| [deck-content.md](deck-content.md) | Word-for-word slide content and the legal-accuracy notes — the reviewable source of truth for the deck |
| [make_deck.py](make_deck.py) | Reproducible deck generator (isolated dependency — see below) |
| [demo-script.md](demo-script.md) | Word-for-word two-minute script (target 1:50 spoken) |
| [demo-runbook.md](demo-runbook.md) | Presentation-day operations: preflight, terminal setup, live sequence, ~5-second fallback decision point |
| [rehearsal-log.md](rehearsal-log.md) | Honest log template for the two required end-to-end rehearsals |
| [fallback-recording-checklist.md](fallback-recording-checklist.md) | Checklist and exact macOS sequence for the ~45–50-second fallback recording |

Background reading for anyone reviewing the claims: the
[project manual](../docs/project-manual.md),
[demo scenario](../docs/demo-scenario.md),
[CI gate](../docs/ci-gate.md), and
[policy replay](../docs/policy-replay.md) documents.

## The demo in one paragraph

Live, offline, deterministic, in one terminal:
`python3 -m agenttrail.ci_gate --agent-version v1` passes (12/12
low-confidence cases escalated, exit 0); `--agent-version v2` — an
intentionally unsafe, controlled demonstration version with
deliberately seeded failures — fails the gate
(9/12, three mismatches, 25 percentage points below the required 100%,
exit 1, with a human-readable failure report). Policy replay is not
run live; slide 3 states its verified result — 36 historical records
replayed under the proposed policy, 35 unchanged, one flip (SYN-031,
decide → escalate). Every figure in the deck comes from verified runs.

## Legal framing (verified)

The deck's regulatory hook uses the current, accurate position: the
EU AI Act (Reg. (EU) 2024/1689) generally became applicable on
2 August 2026; following Reg. (EU) 2026/1744, the Annex III high-risk
rules apply from 2 December 2027; rules for high-risk systems embedded
in Annex I regulated products apply from 2 August 2028. Article 12
requires high-risk systems to technically allow automatic recording of
events supporting traceability. AgentTrail demonstrates an aligned
engineering pattern — not a compliance claim, and the demonstrator is
not a regulated high-risk system. Sources and exact wording:
[deck-content.md](deck-content.md).

## Regenerating the deck

The deck is generated from [deck-content.md](deck-content.md)'s
specification by [make_deck.py](make_deck.py), which needs
`python-pptx`. **This is a presentation-authoring dependency only** —
AgentTrail's offline application paths are deliberately
standard-library-only, and `python-pptx` must never be added to the
application's dependency set. Use a throwaway virtual environment and
install from the hash-locked `requirements-showcase.txt`, from the
repository root:

```bash
python3 -m venv /tmp/agenttrail-deckenv
/tmp/agenttrail-deckenv/bin/python -m pip install --require-hashes --only-binary :all: -r requirements-showcase.txt
/tmp/agenttrail-deckenv/bin/python showcase/make_deck.py
```

After any regeneration, render and inspect all three slides before
presenting (the committed deck was validated by rendering the
generated file to PDF via LibreOffice headless and visually inspecting
every slide for clipping, overlap, font substitution, and contrast).
Open it once in PowerPoint on the presentation machine as part of
preflight — see [demo-runbook.md](demo-runbook.md).

## Recordings are not committed

The fallback recording lives in `showcase/recordings/` (git-ignored)
plus a second copy per the
[fallback-recording-checklist.md](fallback-recording-checklist.md).
The repository has no binary-asset or Git LFS policy, so large media
must stay out of Git. Generated audit trails (`audit/`,
`*.audit.jsonl`) are likewise never committed.

## Honest status

- [x] Three-slide deck, two-minute script, runbook, rehearsal
      template, and recording checklist written; deck rendering
      visually verified (LibreOffice PDF render, all three slides)
- [ ] **Rehearsal 1** performed, timed at or under 2:00, and logged in
      [rehearsal-log.md](rehearsal-log.md) — Susana
- [ ] **Rehearsal 2** performed, timed, and logged — Susana
- [ ] **Fallback recording** (~45–50 s, v1-green / v2-red) made,
      verified end to end, checksummed, second copy stored — Susana

Ticket 13 is **not complete** until all three unchecked items are
genuinely done. The templates existing is not the same as the
rehearsals and recording existing.
