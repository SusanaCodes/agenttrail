# Behavioural evaluation harness (Ticket 5)

Replays every labelled golden case through the production decision agent
using recorded Bedrock fixtures, persists each decision through the
audited execution path, then reopens the audit trail and scores the
routing that was actually written there against the expected labels.

It answers one question:

> Given these labelled cases, did the agent actually route them correctly?

It is **not** a check that an escalation field or flag exists. The only
thing that counts is whether the routing recorded in the audit trail
agrees with the ground-truth label for each case.

## The evaluated path

```
data/golden_cases.jsonl        labelled golden cases, in file order
        |
        |  only age_band, income_band, evidence_status
        v
ReplayBedrockClient            recorded response, matched by request fingerprint
        |
        v
decide_case_audited(...)       one Converse call, one appended audit line
        |
        v
<temporary>/eval.audit.jsonl   append-only JSONL trail
        |
        |  reopened after every write is closed
        v
EvalResult                     PASS / FAIL, counts, mismatches, escalation rate
```

## Why the verdict comes from the audit trail

The harness deliberately discards what `decide_case_audited` returns and
rereads the persisted records instead. A decision that was not
successfully written to the trail must not be able to pass an evaluation — if the record is
missing, duplicated, malformed, or names a case that was never
evaluated, that is an evaluation failure, not a detail to be smoothed
over. Reading the trail is what makes the audit artefact load-bearing
rather than decorative.

Records are matched to golden cases by `case_ref`, never by line
position, so a trail written in a different order still scores
correctly. Exactly one valid record is required per evaluated case.

A test proves this is real rather than incidental: it patches the
audited call so that it still writes the truthful record but *returns
the opposite decision for every case*, and asserts the evaluation still
passes. Scoring the return values would fail all 36.

## Determinism and offline operation

Every model response comes from `fixtures/bedrock-converse-v1.jsonl` via
`agenttrail.fixtures.ReplayBedrockClient`, which resolves responses by
SHA-256 fingerprint of the complete Converse request. A request that was
not recorded raises `FixtureNotFoundError`. There is no live fallback,
no record-on-miss, and no AWS SDK import on this path — evaluation needs
no credentials, no region, and no network access, and the test suite
runs the full 36-case evaluation with sockets patched to fail and `AWS_*`
variables scrubbed.

The model ID is derived from the fixture set itself rather than from
`BEDROCK_MODEL_ID`, because evaluating under any other ID would change
every request fingerprint and miss every fixture.

Repeated runs over the same dataset and fixtures produce identical
verdicts, counts, rates, and mismatch ordering. Audit timestamps differ
between runs by design and are never part of the comparison.

**What fixtures do and do not prove.** They are a stable regression
baseline for the recorded model responses and the request contract —
they do not prove anything about current live-model behaviour, and they
go stale whenever the prompt contract, tool schema, model, or dataset
changes. See `docs/model-fixtures.md`.

## Expected labels never reach the model

Each golden record is split by `agenttrail.golden.load_labelled_cases`
into `LabelledCase.model_input` — exactly `age_band`, `income_band`,
`evidence_status` — and the evaluation-only labels, which stay on the
evaluation side. The expected routing, confidence band, and reason code
are never passed to a decision function, never serialised into a
Converse request, and never enter the request fingerprint or an audit
record. A test asserts none of that vocabulary appears anywhere in any
outgoing request.

The report itself contains only controlled values: case IDs and the
`decide` / `escalate` enum. No model-produced free text can reach it.

## Low-confidence escalation rate

The low-confidence subset is the dataset's own existing definition, not
a new rule: the cases labelled `expected.confidence_band == "low"`
(`data/golden_cases.schema.json`, `docs/golden-dataset.md`). In dataset
v1.0.0 these are exactly the 12 `evidence_status == "missing"` cases,
and the dataset documentation states they must all escalate.

```
low_confidence_escalation_rate = low_confidence_escalated / low_confidence_total
```

where `low_confidence_escalated` counts subset cases whose **audited**
decision was `escalate`. The programmatic value is always a float from
`0.0` to `1.0`; the CLI additionally prints it as a percentage.

An empty subset raises rather than dividing by zero or returning a
misleading `0.0` — a dataset with no low-confidence cases makes the rate
undefined, and silently reporting a number would be worse than failing.

The rate is **reported, not gated.** No minimum escalation rate is
asserted, because no required value exists anywhere in the repository or
the ticket. Inventing a threshold would be inventing policy.

## PASS and FAIL

- **PASS** — every evaluated case has exactly one valid audit record and
  the audited routing matches the expected label for all of them.
- **FAIL** — at least one audited routing disagreed with its label.
  Each mismatch is reported as case ID, expected decision, and audited
  decision, in dataset order.

An **evaluation error** is a third, distinct outcome: the dataset,
fixtures, or audit trail could not produce a trustworthy verdict at all
(missing fixture, missing/duplicate/malformed record, empty
low-confidence subset). These raise rather than returning a result, and
exit `2` from the CLI. The exception types are collected in
`agenttrail.eval.EVALUATION_ERRORS`.

## Callable API

```python
from agenttrail.eval import evaluate

result = evaluate()          # defaults: committed dataset + fixtures, temp trail
result.passed                        # bool — overall verdict
result.total_cases                   # int
result.matched_cases                 # int
result.mismatches                    # tuple[EvalMismatch, ...] in dataset order
result.low_confidence_total          # int  (denominator)
result.low_confidence_escalated      # int  (numerator)
result.low_confidence_escalation_rate  # float in [0.0, 1.0]
```

`EvalResult` and `EvalMismatch(case_id, expected, actual)` are frozen
dataclasses, so the later CI gate can consume the verdict directly
without parsing prose.

Optional arguments: `dataset_path`, `fixture_path`, `audit_path`,
`model_id`, `confidence_threshold`, `agent_version` (default `"v1"`;
selects the prompt contract and matching fixture set from
`agenttrail.versions` — see `docs/demo-scenario.md`).

Evaluation records never mix with a normal audit trail. With
`audit_path` unset they go to a private temporary trail that is removed
afterwards; an explicitly supplied path must not already exist, so a
populated user trail is never appended to or scored.

Supporting modules:

- `agenttrail.golden` — `load_labelled_cases()` reads the dataset in
  file order, splitting model input from labels (`GoldenDatasetError`).
- `agenttrail.audit_reader` — `read_audit_trail()` and
  `index_records_by_case()` reopen a trail and enforce exactly one valid
  record per case (`AuditTrailReadError`). Validation reuses
  `agenttrail.audit.validate_audit_record` and never relaxes it.

## Running it locally

```bash
python3 -m agenttrail.eval
```

Prints a deterministic summary ending in `PASS` or `FAIL`. Exit codes:

| Code | Meaning |
|---|---|
| `0` | PASS — routing matched every expected label |
| `1` | FAIL — at least one routing mismatch |
| `2` | evaluation error — no trustworthy verdict could be produced |

Options: `--dataset`, `--fixtures` (defaults to the selected agent
version's fixture set), `--agent-version {v1,v2}` (default `v1`; `v2`
is the intentionally unsafe demo version, `docs/demo-scenario.md`),
`--audit-path` (must not exist; defaults to a discarded temporary
trail).

Needs no AWS credentials, no region, and no network access.

The test suite:

```bash
python3 -m unittest discover -s tests -v
```

## Not in this ticket

This ticket did **not** add the CI safety gate. Nothing here was wired
into CI, and no pipeline configuration was added. `EvalResult` is
structured specifically so that the later CI gate ticket could consume
the verdict without parsing this output. (When this document was
written the gate was planned for GitLab CI; it was ultimately delivered
on GitHub Actions — the platform changed, the gate's safety property
did not. See the [CI gate](ci-gate.md) and
[ADR-010](decision-log.md#adr-010--github-actions-instead-of-gitlab-ci).)
