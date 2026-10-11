# Adapting AgentTrail to another workflow

AgentTrail demonstrates a reusable engineering pattern: record an
agent's decision, evaluate the persisted record against labelled
expectations, and apply a version-controlled gate to that evaluation.

The bundled fictional benefit-style cases are one worked example.
They are not a real service or benefit policy, and they do not define
the only possible use of the pattern. For example, the pattern could
be adapted to support-ticket triage or recommendations about which
operational changes need human review. Neither adaptation is shipped
in this repository.

## What can be reused

- Evaluate what was actually persisted, rather than trusting a return
  value or checking that a routing flag exists.
- Use labelled cases to define expected behaviour and protect important
  subsets explicitly.
- Replay fixtures deterministically so a given code, dataset and
  fixture set produce a repeatable verdict without live model calls.
- Version the decision contract, evaluation data and gate policy so
  changes can be reviewed together.
- Keep proposed-policy replay separate from acceptance: a report of
  changed decisions supports review but does not approve a policy.

These are design choices that can carry into another workflow. The
existing implementation is not a universal agent adapter: its schemas,
prompts, rationale templates, routing vocabulary and evaluation metrics
are specific to the worked example. Changing a dataset file alone is
not enough.

## What needs to change

| Area | Current example | Adaptation work |
|---|---|---|
| Inputs and labels | Three enumerated case fields and `decide`/`escalate` labels in the [golden dataset](golden-dataset.md) | Define the new input and output contract, representative labelled cases and important failure cases. Update the schema and validation. |
| Agent decision | Prompt, forced tool response, parser and allow-listed rationale templates in [decision.py](../agenttrail/decision.py) and [versions.py](../agenttrail/versions.py) | Implement the workflow's decision logic and safe output handling. Review thresholds and bump contract versions when their meaning changes. |
| Stored evidence | Case fields, identifiers and enums in the [audit schema](../data/audit_record.schema.json), [writer](../agenttrail/audit.py) and [reader](../agenttrail/audit_reader.py) | Define the minimum evidence needed, update field allow-lists and validation together, and decide how existing records will be handled. Review storage and access requirements. |
| Evaluation | Exact routing labels and protected low-confidence cases in [eval.py](../agenttrail/eval.py) | Define how the persisted decisions are scored and which failures should block a change. Check missing, duplicate and malformed evidence as well as incorrect decisions. |
| Gate policy | Escalation-rate baseline and tolerance in [ci_gate.py](../agenttrail/ci_gate.py) | Choose workflow-specific metrics and thresholds. Test an acceptable version and a deliberately regressed version. Retain accurate non-zero exit codes. |
| Model integration and fixtures | Bedrock Converse request contract, fingerprints and registered fixture sets in [model-fixtures.md](model-fixtures.md) | For a new provider, implement a compatible client or change the client contract. Update fixture recording and replay together; review new fixtures when prompts, tools or requests change. |
| Policy replay | Confidence-threshold routing policies in [policy-replay.md](policy-replay.md) | If change-impact analysis is needed, define the new policy semantics and replay path. Keep it separate from gate acceptance. |
| Tests, privacy and CI | Example-specific assertions, redaction checks and required repository checks | Replace assertions with ones for the new contract, review sensitive-data handling, and verify that CI failures actually block the intended action. |

## A practical adaptation sequence

1. Specify the decision being evaluated, its allowed outcomes and when
   human review is required. Create labelled examples, including cases
   where an incorrect automatic decision would matter.
2. Update input validation, decision logic and audit schemas together.
   Preserve an explicit field allow-list; do not start serialising
   arbitrary inputs or model text into the trail.
3. Update evaluation and gate policy to express the new expectations.
   Test that missing or invalid audit evidence cannot produce a passing
   verdict.
4. Review or record fixtures for the new request contract. A changed
   prompt or tool schema changes the request fingerprint; do not disable
   replay validation to make old fixtures fit.
5. Run the tests and evaluation on the adapted workflow. Include a
   deliberate regression to confirm the gate catches the property you
   intend to protect, and verify repository enforcement separately.

## What adaptation does not establish

A fixture-backed verdict covers the chosen cases and recorded responses.
It does not establish live-model performance, fairness, compliance or
production readiness. The current fixtures are not authenticated, and
the local append-only trail is not tamper-evident. Those limits require
separate design and verification for a new use.

The example's model-reported confidence is uncalibrated. Its thresholds
are not general probabilities of correctness and should not be copied
as a safety measure for another workflow without suitable evidence.

The current behavioural gate also does not exercise the low-confidence
override; see the [known coverage gap](ci-gate.md#known-coverage-gap-the-low-confidence-override).
Reuse should start from explicit requirements and tests for the new
workflow, rather than treating the demo's passing result as assurance
for a different application.
