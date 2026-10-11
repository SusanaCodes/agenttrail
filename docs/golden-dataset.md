# AgentTrail golden dataset

**Dataset version: 1.0.0** — `data/golden_cases.jsonl` (36 cases)

## This is synthetic evaluation data

This dataset belongs to AgentTrail's bundled fictional case-review
example. Its fields and labels are specific to that example, not a
universal decision schema. Other workflows need their own labelled
cases and evaluation properties; see
[Adapting AgentTrail](adapting-agenttrail.md).

Every case, label, and rule in this dataset is **synthetic evaluation data
invented for testing AgentTrail's routing behaviour. It does not represent,
approximate, or implement real UK benefit policy** and must never be used as
guidance for real benefit decisions.

Applicant inputs are restricted to three enumerated fields. There are no
free-text applicant fields, names, addresses, dates of birth, National
Insurance numbers, or any other real or real-looking PII, and the schema
(`data/golden_cases.schema.json`) forbids adding any.

## Record structure

One JSON object per line:

```json
{
  "case_id": "SYN-001",
  "dataset_version": "1.0.0",
  "input":    {"age_band": "18-24", "income_band": "low", "evidence_status": "complete"},
  "expected": {"routing": "decide", "confidence_band": "high", "reason_code": "EVIDENCE_COMPLETE_LOW_INCOME"}
}
```

Every string is constrained by an approved enum, the case ID pattern
(`^SYN-[0-9]{3}$`), or the version pattern (`^[0-9]+\.[0-9]+\.[0-9]+$`).
No null, blank, or unconstrained values are permitted anywhere.

## Enum definitions

| Field | Allowed values |
|---|---|
| `input.age_band` | `18-24`, `25-39`, `40-64`, `65-plus` |
| `input.income_band` | `low`, `medium`, `high` |
| `input.evidence_status` | `complete`, `partial`, `missing` |
| `expected.routing` | `decide`, `escalate` |
| `expected.confidence_band` | `high`, `medium`, `low` |
| `expected.reason_code` | `EVIDENCE_COMPLETE_LOW_INCOME`, `EVIDENCE_COMPLETE_MEDIUM_INCOME`, `EVIDENCE_COMPLETE_HIGH_INCOME`, `EVIDENCE_PARTIAL`, `EVIDENCE_MISSING` |

## Labelling rules (synthetic policy v1.0.0)

Labels are a pure, deterministic function of `input`; first match wins:

| # | Condition | `routing` | `confidence_band` | `reason_code` |
|---|---|---|---|---|
| R1 | `evidence_status == missing` | `escalate` | `low` | `EVIDENCE_MISSING` |
| R2 | `evidence_status == partial` | `escalate` | `medium` | `EVIDENCE_PARTIAL` |
| R3 | `evidence_status == complete` and `income_band == low` | `decide` | `high` | `EVIDENCE_COMPLETE_LOW_INCOME` |
| R4 | `evidence_status == complete` and `income_band == medium` | `decide` | `high` | `EVIDENCE_COMPLETE_MEDIUM_INCOME` |
| R5 | `evidence_status == complete` and `income_band == high` | `decide` | `high` | `EVIDENCE_COMPLETE_HIGH_INCOME` |

Design constraints, enforced by tests:

- **`age_band` is routing-inert.** Age is recorded but never consulted; the
  age-invariance test asserts identical labels across all four age bands for
  each `(income_band, evidence_status)` combination.
- **`income_band` is routing-inert in v1.0.0.** It differentiates `decide`
  reason codes only.
- **Low confidence always escalates.** `low` confidence occurs only when
  evidence is missing; without the required evidence the system cannot make a
  safe automated decision, so it must hand off to a human reviewer.

## Coverage and expected distribution

The dataset is the **full Cartesian product** of the three input enums
(4 × 3 × 3 = 36); every combination appears exactly once. Cases are ordered
age → income → evidence and numbered `SYN-001` … `SYN-036`.

| Dimension | Counts |
|---|---|
| Routing | `decide` 12, `escalate` 24 (escalation rate 66.7%) |
| Confidence | `high` 12, `medium` 12, `low` 12 |
| Reason codes | `EVIDENCE_MISSING` 12, `EVIDENCE_PARTIAL` 12, each `EVIDENCE_COMPLETE_*_INCOME` 4 |
| Low-confidence subset | 12 cases (`evidence_status == missing`), 100% `escalate` |

## Reuse by the future audit-trail schema

Audit records produced by the future audit-trail implementation must reuse
this vocabulary verbatim:

- The applicant snapshot must appear under an `input` object with exactly the
  field names `age_band`, `income_band`, `evidence_status` and the same enums.
- Decisions must use the same `routing` (`decide` / `escalate`),
  `confidence_band` (`high` / `medium` / `low`), and `reason_code` enums.
- Audit records should reference `case_id` and `dataset_version` when a case
  is scored against this ground truth, so every evaluation is traceable to
  the exact dataset version used.

## Versioning ground-truth changes

The labels in this dataset are the project's ground truth. Any change must be
reviewed, and in the same change must:

1. Bump `dataset_version` (semantic versioning: patch for corrections that do
   not change labels, minor for added cases or enum values, major for changed
   labelling rules or removed/relabelled cases) — in every record, in the
   schema description if affected, and in this document.
2. Update the locked distribution constants in
   `tests/test_golden_dataset.py` and the tables above.
3. State in the change description which rule(s) changed and why.

Tests pin the exact case count and category distribution, so an unreviewed
edit to the dataset fails CI-style checks by design.

## Running the acceptance tests

```bash
python3 -m unittest discover -s tests -v
```

Standard library only; no external dependencies.
