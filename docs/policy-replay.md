# Policy replay: what would change under a new policy (Ticket 10)

Replays historical audited cases under an explicitly versioned
alternative routing policy and reports which stored routing decisions
would change. It answers one governance question:

> What would have changed in past routing decisions if this proposed
> policy had been applied?

It is change-impact analysis only. A replay containing flips is a
**successful** run (exit 0), never a gate failure, and the report is
evidence for a human review of the proposed policy — it neither
approves nor rejects the policy, and no CI threshold is attached to the
flip rate.

## What a flip is

A flip is a case whose **replayed** routing decision — genuinely
produced by the production decision path (`agenttrail.decision.
decide_case`: recorded response, production parsing, production routing
rule) under the selected target policy — differs from the routing
decision **stored** in the historical audit record. The baseline is
always the stored audit decision; there is no side channel and no
precomputed flip flag.

## Policy v1 vs policy v2

Routing policies live in one closed registry,
`agenttrail.routing_policy.ROUTING_POLICIES`, as frozen dataclasses.
Today a routing policy determines exactly one value: the escalation
confidence threshold applied after the model response. The rule, in
both policies, is the production rule: a `decide` whose confidence is
**strictly below** the threshold escalates; **at or above** the
threshold it stands. An `escalate` is never demoted.

| Policy | Escalation confidence threshold | Status |
| ------ | ------------------------------- | ------ |
| `v1`   | 0.70 (imported from `agenttrail.decision.CONFIDENCE_THRESHOLD`, never restated) | current production behaviour |
| `v2`   | 0.95 | proposed, one documented rule change only |

`v1` behaviour is unchanged by construction: its threshold **is** the
production constant, the registry validates that equality at import,
and the replay passes the resolved threshold through `decide_case`'s
existing explicit parameter — no module-level threshold is mutated, no
version conditionals exist in the decision path, and existing callers
are untouched.

**How v2 was chosen.** The confidence distribution in the committed
genuine v1 recording (`fixtures/bedrock-converse-v1.jsonl`) is:
`decide` at 0.95 (11 cases), `decide` at 0.90 (1 case, SYN-031), and
`escalate` at 0.90 (24 cases). 0.95 is the confidence the recorded
model reports on routine complete-evidence cases, so v2 reads: *an
automated decision must carry at least routine-case confidence;
anything below it is routed to a human*. Because the reported
confidence is documented as uncalibrated, a stricter human-review bar
is a plausible cautious governance proposal — and it produces the
minimal non-zero impact (one flip), so it was demonstrably not chosen
to manufacture an impressive flip count. Unknown policy keys are
rejected before any record is read.

## Running the replay

Produce a historical trail (or use an existing one), then replay it:

```bash
mkdir -p audit  # runtime trails are git-ignored, never committed
python3 -m agenttrail.eval --audit-path audit/replay-demo.audit.jsonl

python3 -m agenttrail.policy_replay \
  --audit-path audit/replay-demo.audit.jsonl \
  --target-policy v2 \
  --legacy-baseline-policy v1
```

`--fixtures` defaults to the committed v1 recording
(`fixtures/bedrock-converse-v1.jsonl`) and `--dataset` to
`data/golden_cases.jsonl`; the target policy is always explicit.
Verified output for the trail produced by the commands above — every
count and case below is measured, not invented (only the two absolute
default-path lines are shown with a `/path/to` placeholder, since they
echo this checkout's location):

```text
audit trail:                audit/replay-demo.audit.jsonl
fixtures:                   /path/to/agenttrail/fixtures/bedrock-converse-v1.jsonl
dataset:                    /path/to/agenttrail/data/golden_cases.jsonl
AgentTrail policy replay
baseline policy:            v1
baseline provenance:        declared legacy assumption (operator-supplied, not recorded fact)
records using declaration:  36
target policy:              v2 (decide stands at confidence >= 0.95; below escalates)
records evaluated:          36
unchanged:                  35
flipped:                    1
flip rate:                  0.0278 (2.78%)
flipped cases:
- SYN-031: decide -> escalate (stored confidence 0.9000, replayed confidence 0.9000)
change-impact analysis only: this report is evidence, not an approval or rejection of the target policy
```

Interpretation: `records evaluated` is every record in the trail (an
incomplete replay fails instead of under-reporting), `flipped` counts
cases whose replayed decision differs from the stored one, and
`flip rate = flipped / evaluated`. Zero evaluated records is an error,
never a 0% success. Flipped cases are listed in ascending `case_ref`
order and the whole report is byte-for-byte identical across runs on
the same inputs — no timestamps, no randomness, no environment paths in
the report body.

Exit codes: `0` for any complete valid replay, including one with
flips; `2` for invalid arguments, unknown policies, a missing legacy
declaration, invalid or unmatched records, or fixture failures. No
partial report is emitted after a failure.

## Legacy baseline provenance is a declared assumption

Historical audit records carry `prompt_version` but **not**
`policy_version` — the audit schema is unchanged by this ticket, and
storing policy provenance on future writes is tracked separately as
**AC-25**. A prompt version identifies the prompt contract that
produced the model response; it says nothing about which routing
policy was in force afterwards, so the replay **never infers**
`policy_version` from `prompt_version` and never silently defaults it.

Records without stored policy provenance are rejected unless the
operator explicitly declares the legacy baseline with
`--legacy-baseline-policy v1`. Only `v1` is declarable, because it is
the only routing policy production has ever run; any other value fails.
Omitting the declaration exits non-zero with an actionable error. When
the declaration is used the report states, once and prominently, the
baseline policy, that its provenance is a *declared legacy assumption*
(operator-supplied, not recorded fact), and how many records depend on
it. Historical records are never modified or backfilled.

## Audit-integrity guarantee: the fixture boundary

Recorded fixtures may be reused here **only because a routing-policy
change applies after the recorded model response**: the same recorded
response is retrieved through the existing exact-fingerprint mechanism
(`ReplayBedrockClient`), re-parsed by the production extractor, and
re-routed under the target threshold. Confidence is never copied out of
the audit record and re-thresholded as a fake replay result.

A changed prompt would produce a different canonical Bedrock request
and therefore a different SHA-256 fingerprint, so a recorded v1
response can never be passed off as the answer to a v2 prompt — the
lookup misses and the replay fails closed. Replaying records made under
a different prompt works only where exact fixtures for that prompt
already exist (for example the committed synthetic v2-prompt set);
recording new fixtures is outside this feature. Fingerprint validation
is not weakened or bypassed, and there is no live fallback.

## Failure behaviour

Everything fails closed, with a non-zero exit and no partial report:

* missing, empty, malformed, or invalid audit trails (via the standard
  audit reader — the schema contract is reused, never relaxed);
* records missing required fields, duplicate case references, records
  that cannot be matched to a source case, and records whose stored
  input fields disagree with the matched source case;
* records with an unknown `prompt_version` (the recorded request cannot
  be reconstructed);
* missing, duplicate, malformed, or fingerprint-mismatched fixtures;
* a missing or unsupported legacy-baseline declaration.

No record is ever silently skipped: a partially replayed trail would
understate policy impact, so the run fails instead.

## Deterministic, offline, read-only

The replay is deterministic (same inputs, byte-identical report), fully
offline (the only model client is the fixture replayer — no live
Bedrock call, no network, no AWS credentials), and read-only over the
trail (the audit file is opened by the standard reader and its bytes
are unchanged by a replay; the tests assert this by hashing).

## Known limitations

* Only threshold-style, post-response policy changes can be replayed;
  changed-prompt replay would need separately recorded exact fixtures.
* The baseline for current records rests on the operator's declared
  legacy assumption until audit records store `policy_version` (AC-25).
* The flip report covers the cases present in the trail — it is
  historical change-impact evidence, not a forecast, an approval, or a
  statistical simulation.
