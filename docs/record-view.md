# Record view: look up a stored decision record by ID

**Module:** `agenttrail.record_view` — **Ticket 11**

The record view is the human-readable evidence view over the append-only
audit trail (docs/audit-trail.md). Given a decision ID, it finds the one
stored record that carries that ID and prints it with stable labels for
an auditor, investigator, or governance reviewer.

## What it does — and does not — do

It **reads** an already-stored decision record. It does **not**:

* invoke the agent, Bedrock, or any network service;
* regenerate or reproduce the historical decision (it is a lookup of
  stored evidence, not a replay);
* modify, rewrite, or delete anything in the trail;
* accept or display free text, raw prompts, raw model responses, or
  personal identifiers.

## Command

```
python3 -m agenttrail.record_view --trail <path> --decision-id <id>
```

Example:

```
python3 -m agenttrail.record_view \
    --trail audit/decisions.audit.jsonl \
    --decision-id 2f6b8c1a-9d3e-4f7a-8b2c-1d4e5f6a7b8c
```

## Fields displayed

Exactly the approved audit fields, in fixed sections:

* **Identity** — decision ID, case reference
* **Structured inputs** — age band, income band, evidence status
* **Outcome** — decision, confidence (printed as `0.0000`–`1.0000` on a
  0.0–1.0 scale; uncalibrated), rationale (allow-listed template
  rendering)
* **Provenance** — model ID, prompt version, timestamp (UTC)

## Decision IDs

Every record written since Ticket 11 carries a `decision_id`: a random
canonical lowercase UUIDv4 generated once when the record is built. It
is never derived from case data, never a line number, and never
regenerated during lookup. `case_ref` is a case reference, not a
decision ID — the CLI rejects one passed as the other.

## Legacy records

Records written before `decision_id` existed remain valid trail members.
A lookup skips them — they can never match an ID, falsely or otherwise —
and if the renderer is given one directly it labels the ID as
`(not recorded; record predates decision IDs)` rather than inventing a
value. Historical records are never rewritten to add IDs; the trail is
append-only.

## Success and failure behaviour

On success the readable record is written to stdout, prefixed with a
note that this is a lookup of an existing record with no model call.
Failures print one concise line to stderr (no tracebacks for expected
operator errors) and exit non-zero.

| Exit code | Meaning |
|---|---|
| 0 | record found and rendered |
| 1 | no stored record carries the given decision ID |
| 2 | the trail cannot serve as evidence (missing/unreadable file, malformed JSONL, blank line, invalid record, duplicate decision IDs) or the decision-ID argument is not a valid identifier |

Failure is always explicit: duplicate IDs are reported rather than one
record being silently chosen, and corrupt JSONL is reported as
corruption, never as "record not found".

## Allow-listed rendering boundary

The view renders only the approved audit fields above; it never dumps a
raw object or every field found in a JSON line. A record carrying any
unexpected field (for example a planted `raw_user_input`) fails audit
validation and the lookup refuses to render the record at all — the
field name is reported, its value is not. This view does **not**
independently detect or redact arbitrary PII; the safety property is
narrower: only approved, already-structured fields can ever reach the
output. The schema allow-list (docs/audit-trail.md) and the redaction
gate (docs/redaction-gate.md) remain the primary and backstop privacy
controls.

## Audit, investigation, and governance use

Because the view reads only the persisted trail, what it shows is the
evidence itself: the structured inputs the decision was made on, the
recorded outcome and confidence, and the exact model ID, prompt version,
and time — enough to answer "what did the system decide, on what basis,
with which model and prompt, and when" without re-running anything.
