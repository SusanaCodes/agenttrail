# Deck content — AgentTrail final showcase (two minutes)

The word-for-word content of every slide in
[`AgentTrail-final-showcase.pptx`](AgentTrail-final-showcase.pptx).
This file is the reviewable source of truth: the deck is generated from
it by [`make_deck.py`](make_deck.py) (see [README.md](README.md) for
how to regenerate). Every figure below is taken from verified command
output on this branch — nothing is projected, extrapolated, or invented.

Design intent: exactly **three** 16:9 slides for a strict two-minute
showcase. No title slide, no agenda, no closing slide. Near-black
background, white headlines at 44 pt or larger, one electric-blue
accent for the audit trail and regulatory framing, safety green only
on the v1 result, strong red only on the blocked v2 result. No stock
imagery, no dashboard cards, no terminal screenshots, no marketing
language. The terminal failure is the centrepiece; the slides create
the stakes, explain the mechanism, and land the conclusion.

---

## Slide 1 — Regulatory hook

Brand label (small, top-left, blue): **AGENTTRAIL**

> **By December 2027, ‘the AI said so’ will no longer be enough.**

- Supporting line: "For many high-risk uses, Article 12 requires AI
  systems to support automatic event logging and traceability."
- Visual motif: a single evidence-trail line with audit-event markers,
  the newest lit in blue. Nothing else.
- Accuracy footer: "EU AI Act · Annex III high-risk rules apply
  2 December 2027 · engineering alignment, not a compliance claim"

Speaker notes carry the full legal position and compact sources (see
"Legal accuracy" below).

## Slide 2 — Architecture

> **AgentTrail turns evidence into a release decision.**

Vertical flow, audit trail visually central (blue):

```text
AI decision
    ↓
append-only audit trail   ──→  policy replay (reads the same trail)
    ↓
behavioural evaluation   ←──  labelled golden dataset · recorded responses
    ↓
CI safety gate
```

- One line: "Offline. Deterministic. No live model call in CI."
- Small footer: "trail is a local append-only JSONL file — a
  demonstrator, not tamper-proof production storage"

## Slide 3 — Result and closing beat

> **Unsafe change: blocked before deployment.**

Dominant comparison (large figures; green for v1 only, red for v2
only):

```text
v1    100%    PASS
v2     75%    BLOCKED
```

- Supporting line: "three missed escalations · exit status 1 stops
  the pipeline"
- Replay proof (blue, large): "36 past decisions replayed. One would
  change."
- Closing statement (large, prominent):
  "An unsafe AI change cannot pass silently."
- The SYN-031 case detail is not visible slide copy — it lives in the
  slide's speaker notes (accuracy section).

---

## Legal accuracy binding this deck

Verified against the official sources; do not restate these facts any
other way in slides or speech:

- The EU AI Act (Regulation (EU) 2024/1689) generally became
  applicable on **2 August 2026**.
- Following Regulation (EU) 2026/1744, the high-risk rules for
  **Annex III** systems apply from **2 December 2027**.
- Rules for high-risk systems embedded in **Annex I** regulated
  products apply from **2 August 2028**.
- **Article 12** requires high-risk AI systems to technically allow
  automatic recording of events over their lifetime, supporting
  traceability appropriate to the system's purpose.
- AgentTrail demonstrates an engineering pattern aligned with logging,
  traceability and assurance. It is **not** a legal-compliance claim,
  and this demonstrator is **not** being classified as a regulated
  high-risk system.

Compact sources (also in slide 1 speaker notes):

- <https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai>
- <https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng>
- <https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng>

Never say "the EU AI Act starts in 2027" or that all AI systems become
subject to it in 2027.

## Accuracy notes binding this deck

- v1 gate: `measured_rate=1.0000`, 12/12 low-confidence cases
  escalated, `CI GATE: PASS`, exit status 0.
- v2 gate: `measured_rate=0.7500`, 9/12 escalated, mismatches SYN-003,
  SYN-015, SYN-027, `Decision: Gate blocked`, exit status 1 —
  **intentional**: the v2 fixture set is a synthetic, controlled
  unsafe version built to demonstrate a regression. No production
  model spontaneously regressed.
- The gate threshold is version-controlled (baseline 1.0000, tolerance
  0.0000) and cannot be overridden from the CLI.
- Evaluation reads decisions back from the persisted audit trail, not
  from an in-memory side channel.
- Policy replay: 36 records evaluated, 35 unchanged, 1 flip — SYN-031
  decide → escalate under the proposed 0.95 confidence threshold.
  Read-only change-impact evidence; it approves and rejects nothing.
- The append-only JSONL trail is a local demonstrator, not durable
  tamper-proof production storage.
