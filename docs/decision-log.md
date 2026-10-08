# AgentTrail decision log

Durable architectural and product decisions, with the alternatives that
were rejected and why. Identifiers are stable: a superseded decision
keeps its number and gains a status note. Dates are taken from the Git
history of the commit that landed the decision; where the repository
holds no evidence for a decision's original date or motivation, the
entry says so plainly.

| ID | Decision | Status | Date |
|---|---|---|---|
| [ADR-001](#adr-001--deliberately-narrow-showcase-scope) | Deliberately narrow showcase scope | Accepted | 2026-07-24 (project start) |
| [ADR-002](#adr-002--forced-structured-tool-call-never-model-free-text) | Forced structured tool call, never model free text | Accepted | 2026-07-26 |
| [ADR-003](#adr-003--pii-minimised-by-construction) | PII minimised by construction | Accepted | 2026-07-28 (backstop 2026-08-07) |
| [ADR-004](#adr-004--append-only-jsonl-audit-trail-with-stated-limitations) | Append-only JSONL audit trail with stated limitations | Accepted | 2026-07-28 |
| [ADR-005](#adr-005--recorded-fixtures-instead-of-live-model-calls-in-ci) | Recorded fixtures instead of live model calls in CI | Accepted | 2026-08-06 |
| [ADR-006](#adr-006--behavioural-assertion-over-a-labelled-dataset) | Behavioural assertion over a labelled dataset | Accepted | 2026-08-06 |
| [ADR-007](#adr-007--the-evaluation-verdict-comes-from-the-reopened-audit-trail) | The evaluation verdict comes from the reopened audit trail | Accepted | 2026-08-06 |
| [ADR-008](#adr-008--one-headline-gate-before-additional-gates) | One headline gate before additional gates | Accepted | Phase 1 sequencing (Tickets 5–8) |
| [ADR-009](#adr-009--version-controlled-non-overridable-gate-policy) | Version-controlled, non-overridable gate policy | Accepted | 2026-08-06 |
| [ADR-010](#adr-010--github-actions-instead-of-gitlab-ci) | GitHub Actions instead of GitLab CI | Accepted | 2026-08-06 |
| [ADR-011](#adr-011--synthetic-clearly-marked-fixtures-for-the-unsafe-demo-version) | Synthetic, clearly-marked fixtures for the unsafe demo version | Accepted | 2026-08-11 |
| [ADR-012](#adr-012--record-lookup-not-execution-replay) | Record lookup, not execution replay | Accepted | 2026-08-12 |
| [ADR-013](#adr-013--policy-provenance-is-never-inferred) | Policy provenance is never inferred | Accepted | 2026-08-13 |

---

## ADR-001 — Deliberately narrow showcase scope

**Status:** Accepted. **Date:** 2026-07-24 (repository initialisation;
scope held throughout Phase 1).

**Context.** A portfolio/programme showcase must demonstrate a safety
claim an assessor can verify. Breadth (dashboards, retrieval, multiple
agents) competes directly with the depth needed to make one claim
inspectable end to end.

**Chosen approach.** Deliver one complete, connected safety pipeline:
labelled golden dataset, one decide-or-escalate decision path,
append-only audit trail, deterministic evaluation, a CI gate whose
verdict repository rules can require, and a staged demonstration in
which the gate fails on a deliberately seeded unsafe change.

**Alternatives rejected (deferred, not forgotten).** Dashboards; RAG;
vector databases; multi-agent orchestration; MCP gateway integration.
The gateway inversion is the designed Phase 2 step (identified in the
programme plan as AC-17 to AC-24; those definitions are not recorded in
this repository — see the [project manual, section 13](project-manual.md#13-future-improvements-phase-2)).

**Rationale.** One control performing a meaningful, verifiable job
provides stronger evidence than several incomplete controls. Every
additional subsystem would dilute review attention and expand the
surface that must be proven safe.

**Consequences and trade-offs.** The demonstration is narrow: one
decision path, one behavioural property, synthetic data. In exchange,
every claim in the documentation is backed by runnable, deterministic
evidence.

**Implementation evidence.** The whole repository; the Phase 1 ticket
sequence in the Git history (2026-07-24 → 2026-08-13); absence of any
dashboard/RAG/vector/multi-agent/MCP code.

## ADR-002 — Forced structured tool call, never model free text

**Status:** Accepted. **Date:** 2026-07-26 (commit "Add Bedrock
decide-or-escalate call").

**Context.** The agent's output must be validatable, auditable, and
free of uncontrolled text that could carry hallucinated reasoning or
sensitive content into records.

**Chosen approach.** One Bedrock Converse call per case with
`toolChoice` forcing the `submit_decision` tool. The tool schema is
closed: `decision` (enum), `confidence` (bounded number),
`rationale_template` (enum). The response is strictly validated —
exactly one content block, only the expected tool, no extra fields, and
the template must agree with the decision. The rationale text is
rendered locally from the allow-listed template using validated case
fields.

**Alternatives rejected.** Free-text prompting with output parsing
(fragile; free text can be logged and audited, but it is harder to
validate mechanically, harder to constrain, less suitable as structured
safety evidence, and can carry uncontrolled or sensitive content into
the system);
storing the model's own rationale text (uncontrolled content in
records); multiple tool options (widens the surface without a need).

**Rationale.** A closed contract makes every model interaction
mechanically checkable, keeps records enum-and-pattern constrained, and
makes the request canonically serialisable — the property fixture
fingerprinting (ADR-005) later depends on.

**Consequences and trade-offs.** The rationale is a template rendering,
not an explanation of the model's actual reasoning — a deliberate
limitation stated in the audit documentation. The model-reported
confidence is uncalibrated and documented as such.

**Implementation evidence.**
[`agenttrail/decision.py`](../agenttrail/decision.py) (`TOOL_CONFIG`,
`_extract_tool_input`, `RATIONALE_TEMPLATES`);
[`tests/test_decision.py`](../tests/test_decision.py).

## ADR-003 — PII minimised by construction

**Status:** Accepted. **Date:** input schema 2026-07-25, audit
allow-list 2026-07-28, regex backstop 2026-08-07.

**Context.** Decision records about people are exactly where personal
data leaks into logs. Detection-based controls act after sensitive data
already exists in the pipeline.

**Chosen approach.** A hierarchy: (1) structured allow-listed fields
only — three enumerated inputs, synthetic `SYN-NNN` case references, a
closed audit record shape with `additionalProperties: false`; (2)
rationales rendered locally from allow-listed templates and revalidated
on read (see ADR-002); (3) a deterministic regex scan of committed
structured JSONL data for three UK identifier formats (National
Insurance numbers, UK postcodes, NHS numbers) as a backstop, reporting
findings without ever printing the matched value.

**Alternatives rejected.** Storing unrestricted model prose (reopens
the leak the schema closes); general NER as the primary control
(unnecessary dependency and complexity, probabilistic behaviour in a
control that must be deterministic, false-positive and false-negative
risk, and a poor fit for a narrowly structured schema with no free
text to read).

**Rationale.** Reduce sensitive data before detection is ever needed,
and keep the control that remains deterministic and reviewable.

**Consequences and trade-offs.** The backstop's scope is exactly three
identifier formats — documented as such, never as universal PII
detection. Synthetic data means the showcase demonstrates the mechanism,
not real-data governance (a stated Phase 2 concern).

**Implementation evidence.**
[`data/golden_cases.schema.json`](../data/golden_cases.schema.json);
[`agenttrail/audit.py`](../agenttrail/audit.py) (allow-list, rationale
revalidation);
[`agenttrail/redaction_gate.py`](../agenttrail/redaction_gate.py);
[`tests/test_redaction_gate.py`](../tests/test_redaction_gate.py);
[redaction-gate.md](redaction-gate.md).

## ADR-004 — Append-only JSONL audit trail with stated limitations

**Status:** Accepted. **Date:** 2026-07-28 (commit "Add append-only
structured audit trail").

**Context.** Every audited decision needs a persisted structured record
that later evaluation can trust, without introducing a database
dependency into a showcase whose offline paths are deliberately
standard-library-only.

**Chosen approach.** One validated JSON object per line, appended with
a single `O_APPEND` write; deterministic encoding (sorted keys, compact
separators, ASCII-only); files created `0o600`; the writer exposes
append-only behaviour with no rewrite, truncate, or delete API, and the
separate readers
([`agenttrail/audit_reader.py`](../agenttrail/audit_reader.py)) never
mutate the trail; a failed append means the decision is not returned.
The documentation states what is not guaranteed:
not transactional, not exactly-once, no fsync, no tamper evidence,
`O_APPEND` atomicity assumed only for local POSIX filesystems.

**Alternatives rejected.** A database (durability and querying, at the
cost of the offline paths' standard-library-only property — deferred to
Phase 2); claiming
tamper evidence or exactly-once semantics the implementation does not
have.

**Rationale.** JSONL keeps the trail human-readable, line-oriented, and
straightforward to inspect and stream with the standard-library reader,
and the honest-limits documentation
keeps the record-keeping claim proportionate to the implementation.

**Consequences and trade-offs.** Records can be lost on OS crash or
power failure; nothing detects post-hoc modification of a trail file.
Both are documented and listed as Phase 2 work.

**Implementation evidence.**
[`agenttrail/audit.py`](../agenttrail/audit.py) (module docstring and
`append_audit_record`);
[`agenttrail/audit_reader.py`](../agenttrail/audit_reader.py);
[`tests/test_audit.py`](../tests/test_audit.py);
[audit-trail.md](audit-trail.md).

## ADR-005 — Recorded fixtures instead of live model calls in CI

**Status:** Accepted. **Date:** 2026-08-06 (commit "Add deterministic
Bedrock fixture recording and replay").

**Context.** The CI gate must give the same verdict for the same change
on every run. Live Bedrock calls are probabilistic, paid,
credential-bearing, and network-dependent.

**Chosen approach.** Record one genuine Bedrock response per golden
case in a single explicit, human-run session
(`python3 -m agenttrail.record_fixtures`), commit the captured
request/response pairs, and replay them by SHA-256 fingerprint of the
complete canonicalised Converse request. Replay
(`ReplayBedrockClient`) never imports the AWS SDK, holds no live
client, and raises `FixtureNotFoundError` on any unrecorded request.

**Alternatives rejected.** Live Bedrock calls in evaluation or CI
(flaky, paid, credential-bearing); silent live fallback on a fixture
miss (would quietly reintroduce all of the above); record-on-miss
(would let an unreviewed model response become the new baseline);
relying on `temperature: 0.0` and seeds instead of recording (reduces
variance but guarantees nothing across model revisions or serving
infrastructure).

**Rationale.** A probabilistic or network-dependent gate becomes
flaky, and a flaky gate trains operators to rerun and ignore it — which
is worse than having no trusted gate at all.

**Consequences and trade-offs.** Fixtures are a snapshot: they hold
one recorded contract, say nothing about current live-model behaviour,
are not authenticated, and go stale
when the prompt, tool schema, model, or dataset changes.
The request hash proves the replay request matches the stored request
byte for byte. It does not bind the response to that request and does
not prove that Bedrock produced the response. Fixture re-recording is a
reviewed act that the gate cannot itself authenticate.
Replay consistency and drift detection are planned as
[AC-32](https://thesreflow.atlassian.net/browse/AC-32), which has not
shipped; authenticating response provenance is a separate deferred
control. Contract
changes fail loudly as fingerprint misses; silent model-revision drift
does not, so periodic deliberate live evaluation remains necessary.
Re-recording changes the behavioural evidence evaluation relies on and
should therefore be reviewed; `--overwrite` forces an explicit
replacement choice and prevents accidental replacement, while
repository review remains a separate process control.

**Implementation evidence.**
[`agenttrail/fixtures.py`](../agenttrail/fixtures.py);
[`agenttrail/record_fixtures.py`](../agenttrail/record_fixtures.py);
[`tests/test_fixture_replay.py`](../tests/test_fixture_replay.py)
(sockets patched to fail, `boto3` asserted absent);
[model-fixtures.md](model-fixtures.md).

## ADR-006 — Behavioural assertion over a labelled dataset

**Status:** Accepted. **Date:** 2026-08-06 (commit "Add behavioural
routing evaluation against golden labels").

**Context.** The safety claim is "low-confidence cases escalate to a
human". A check must measure that behaviour, not the existence of the
machinery meant to produce it.

**Chosen approach.** Replay all 36 labelled golden cases through the
production decision path and compare each **recorded** routing decision
with its expected label, computing the low-confidence escalation rate
over the labelled subset.

**Alternatives rejected.** Checking only whether an escalation flag or
field was emitted: that tests plumbing and becomes tautological — a
regression that leaves the escalation machinery in place but stops
using it would still pass.

**Rationale.** The gate must assert the behavioural safety property
itself. Labels make the expectation explicit, reviewable, and versioned
(dataset v1.0.0, distribution pinned by tests).

**Consequences and trade-offs.** The assertion is only as good as the
labels; label changes are ground-truth changes and require versioning
and review. The property covers 36 synthetic cases, not the open input
space.

**Implementation evidence.**
[`agenttrail/eval.py`](../agenttrail/eval.py);
[`agenttrail/golden.py`](../agenttrail/golden.py);
[`data/golden_cases.jsonl`](../data/golden_cases.jsonl);
[`tests/test_eval.py`](../tests/test_eval.py);
[evaluation.md](evaluation.md).

## ADR-007 — The evaluation verdict comes from the reopened audit trail

**Status:** Accepted. **Date:** 2026-08-06 (same commit as ADR-006).

**Context.** With an audit trail and an evaluation both in place, the
evaluation could score the decision function's return values and treat
the trail as a write-only log. That would make the record decorative.

**Chosen approach.** The harness runs every case through
`decide_case_audited`, **discards the return values**, reopens the
persisted trail after all writes are closed, validates every record,
requires exactly one record per case (matched by `case_ref`, never line
position), and scores only what was successfully written and reread
from the trail.

**Alternatives rejected.** Scoring return values (a decision absent
from the persisted trail could pass evaluation); tolerating missing or duplicate
records (a silently dropped record would let an unaudited decision
pass).

**Rationale.** This is what makes the trail the architectural hinge:
the gate's evidence is the record, so record-keeping failures are
safety failures. A dedicated test checks the property — it
patches the audited call to return the opposite decision for every case
while still writing truthful records, and the evaluation still passes.

**Consequences and trade-offs.** Evaluation is slightly slower (write
then reread) and any trail-integrity problem fails the whole run — by
design.

**Implementation evidence.**
[`agenttrail/eval.py`](../agenttrail/eval.py) (module docstring,
`_run_and_score`);
[`agenttrail/audit_reader.py`](../agenttrail/audit_reader.py)
(`index_records_by_case`);
[`tests/test_eval.py`](../tests/test_eval.py);
[evaluation.md](evaluation.md) ("Why the verdict comes from the audit
trail").

## ADR-008 — One headline gate before additional gates

**Status:** Accepted. **Date:** Phase 1 sequencing decision; visible in
the ticket order (evaluation 2026-08-06 → gate 2026-08-06 → failure
report 2026-08-07 → redaction backstop 2026-08-07 → demonstration
2026-08-11). No single commit records this decision; the evidence is
the sequence itself.

**Context.** Several safety gates were conceivable (behavioural,
fixture-integrity, privacy, cost). Building them in parallel risked
finishing none of them properly.

**Chosen approach.** Finish one behavioural gate end to end — dataset,
decision path, trail, evaluation, policy, CI enforcement, failure
report, and a demonstration that it genuinely blocks — before starting
any additional gate. The redaction gate was then added as a narrow,
complete backstop, not a second partially-built headline control.

**Alternatives rejected.** Three partially implemented safety gates.

**Rationale.** One control performing a meaningful job end to end
provides stronger evidence than several incomplete controls; an
unproven gate is indistinguishable from a decorative one.

**Consequences and trade-offs.** Other worthwhile properties
(over-escalation, fixture integrity as an independent workflow gate)
remain future work, listed in the
[project manual, section 13](project-manual.md#13-future-improvements-phase-2).

**Implementation evidence.** Git history order; the completed chain in
[`agenttrail/ci_gate.py`](../agenttrail/ci_gate.py),
[`agenttrail/gate_report.py`](../agenttrail/gate_report.py),
[`.github/workflows/ci-gate.yml`](../.github/workflows/ci-gate.yml),
and [demo-scenario.md](demo-scenario.md).

## ADR-009 — Version-controlled, non-overridable gate policy

**Status:** Accepted. **Date:** 2026-08-06 (commit "Add deterministic
escalation regression CI gate").

**Context.** A safety threshold that can be adjusted through an
environment variable, CLI flag, or workflow input can be weakened
without review, precisely under delivery pressure.

**Chosen approach.** The policy — baseline 1.0000, tolerance 0.0000 —
lives as constants in [`agenttrail/ci_gate.py`](../agenttrail/ci_gate.py)
and no interface overrides those thresholds (the CLI does accept
`--dataset` and `--fixtures` paths, which change the evidence the
thresholds are applied to, not the thresholds). Tests exercise
boundary values only by injecting parameters into the pure
`apply_policy()` function. Weakening or changing the policy requires a
version-controlled source change — it cannot be made through an
environment variable, CLI flag, or workflow input — which is then
subject to the repository's configured review and branch-protection
controls; the constants alone do not prove that a person reviewed any
given change. Such a change is expected to arrive in the same pull
request as the dataset or policy decision that justifies it.

**Alternatives rejected.** Configurable thresholds (bypassable without
review); a non-zero tolerance (with 12 low-confidence cases, any
regression is one whole missed escalation, never noise).

**Rationale.** The gate is the safety control; its parameters must have
the same review protection as the code.

**Consequences and trade-offs.** Legitimate policy changes are slower
(they must land as source changes under the repository's review
controls) — accepted as the point of the design.

**Implementation evidence.**
[`agenttrail/ci_gate.py`](../agenttrail/ci_gate.py)
(`BASELINE_LOW_CONFIDENCE_ESCALATION_RATE`, `MAX_PERMITTED_REGRESSION`,
module docstring); [`tests/test_ci_gate.py`](../tests/test_ci_gate.py);
[ci-gate.md](ci-gate.md).

## ADR-010 — GitHub Actions instead of GitLab CI

**Status:** Accepted. **Date:** the gate landed on GitHub Actions
2026-08-06/07 (gate and manual-trigger commits).

**Context.** The CI gate was originally planned for GitLab CI. The only
in-repository trace of that plan is the historical note in
[evaluation.md](evaluation.md), written while the gate did not yet
exist; the repository holds no other record of the original platform
choice or the date the switch was decided — this entry says so rather
than reconstructing a fuller story.

**Chosen approach.** Deliver the gate as a GitHub Actions workflow
([`.github/workflows/ci-gate.yml`](../.github/workflows/ci-gate.yml)):
push/PR/`workflow_call` triggers plus a manual `workflow_dispatch` with
the closed v1/v2 choice, and a `deployment-demo` job gated by `needs:`.

**Alternatives rejected for this showcase.** Retaining GitLab CI solely
because it was the original platform.

**Rationale.** Assessor and programme-rubric alignment: the rubric
favoured GitHub Actions, and the repository is hosted on GitHub, so the
demo runs where assessors review it. The orchestration platform
changed; the gate's safety property — deterministic, fail-closed
behavioural evaluation of the recorded trail under a version-controlled
policy — did not, and does not depend on the platform. GitLab CI could
host the same gate; neither platform is inherently safer.

**Consequences and trade-offs.** Platform-specific touches (the
`GITHUB_STEP_SUMMARY` job summary, `workflow_dispatch` inputs, branch
protection via required status checks) would need re-mapping if the
project ever moved again; all safety logic lives in the Python CLI, so
the workflow stays thin.

**Implementation evidence.**
[`.github/workflows/ci-gate.yml`](../.github/workflows/ci-gate.yml);
[`agenttrail/gate_report.py`](../agenttrail/gate_report.py)
(`append_github_step_summary`); the historical GitLab note in
[evaluation.md](evaluation.md); [ci-gate.md](ci-gate.md).

## ADR-011 — Synthetic, clearly-marked fixtures for the unsafe demo version

**Status:** Accepted. **Date:** 2026-08-11 (commit "Add v1/v2 demo
scenario proving the CI gate blocks unsafe changes").

**Context.** Proving the gate blocks requires an agent version that
genuinely misbehaves. Recording one live would mean paying to run an
intentionally unsafe prompt and hoping the model misbehaves on the
right cases — an unreliable and unnecessary dependency for a staged
demonstration.

**Chosen approach.** Register an explicitly unsafe `v2` agent version
(over-confident prompt, `2.0.0`) and generate its fixture set
synthetically and offline (`agenttrail.demo_fixtures`): three
low-confidence cases return a confident `decide` (0.92, above the 0.70
threshold); all other cases mirror the genuine v1 recording. Provenance
is marked three ways — `synthetic` in the file name,
`tooluse_synthetic_demo_` tool-use IDs, and a fixed synthesis
`recorded_at`. The set passes the full production fixture contract, is
generated through the production request path and response extractor,
and is byte-for-byte reproducible (asserted by
[`tests/test_demo_scenario.py`](../tests/test_demo_scenario.py)).
Nothing selects v2 implicitly.

**Alternatives rejected.** Recording v2 live (cost, non-determinism, no
guarantee of the demonstrative failure); editing the genuine v1
recording or golden labels to force a failure (would corrupt the
project's ground truth); presenting synthetic data as a live capture
(dishonest provenance).

**Rationale.** The demonstration must exercise the real pipeline — real
requests, real parsing, real trail, real gate — while being honest that
the misbehaving responses are staged.

**Consequences and trade-offs.** The v2 regression demonstrates the
gate's mechanics, not observed live-model misbehaviour; the
documentation states this wherever v2 is mentioned.

**Implementation evidence.**
[`agenttrail/versions.py`](../agenttrail/versions.py);
[`agenttrail/demo_fixtures.py`](../agenttrail/demo_fixtures.py);
[`fixtures/bedrock-converse-v2-synthetic.jsonl`](../fixtures/bedrock-converse-v2-synthetic.jsonl);
[demo-scenario.md](demo-scenario.md).

## ADR-012 — Record lookup, not execution replay

**Status:** Accepted. **Date:** 2026-08-12 (commit "Add stored decision
record lookup").

**Context.** Auditors need to retrieve the evidence for one specific
decision. It is tempting to present such a view as "replaying" the
decision, which would overstate what it does.

**Chosen approach.** `agenttrail.record_view` retrieves and renders one
**already-stored** audit record by its random UUIDv4 `decision_id`. It
invokes no model, regenerates nothing, never modifies the trail, and
renders only the approved audit fields (a record carrying any
unexpected field is refused entirely). Its output states explicitly:
"lookup of an existing record; no model call".

**Alternatives rejected.** Claiming to rerun or reproduce the
historical model execution: without the original execution context and
a replay contract for it, presenting lookup as deterministic execution
replay would be a false determinism claim.

**Rationale.** Lookup provides traceability — what was decided, on what
inputs, by which model and prompt, when — which is the actual audit
need. The word "replay" is reserved for the fixture and policy replay
mechanisms, which have a defined contract.

**Consequences and trade-offs.** Each mechanism answers a distinct
question: record lookup answers what was stored for one historical
audited decision; deterministic evaluation answers how the committed
recorded snapshot behaves against the golden dataset; policy replay
answers how historical audited cases would route under a target policy
using the exact recorded responses. None of them answers what the
current live model would do — that requires a separately governed live
invocation or a new fixture-recording and review exercise. The record
view will not pretend to answer any question beyond its own.

**Implementation evidence.**
[`agenttrail/record_view.py`](../agenttrail/record_view.py) (module
docstring and CLI description);
[`tests/test_record_view.py`](../tests/test_record_view.py);
[record-view.md](record-view.md).

## ADR-013 — Policy provenance is never inferred

**Status:** Accepted. **Date:** 2026-08-13 (commit "feat: add
deterministic policy replay").

**Context.** Policy replay compares stored decisions against a proposed
routing policy, which requires knowing which policy produced each
stored decision. Historical records carry `prompt_version` but no
`policy_version`.

**Chosen approach.** Records without stored policy provenance are
rejected unless the operator passes `--legacy-baseline-policy v1` — an
explicit declaration, restricted to `v1` because it is the only
legacy-baseline value the current implementation permits (AgentTrail is
a demonstrator; historical records store no `policy_version`, so the
baseline must be declared by the operator rather than read from the
records). The report states prominently that the
baseline is a *declared legacy assumption (operator-supplied, not
recorded fact)* and counts the records that depend on it. Storing
`policy_version` on future records is tracked as AC-25 — the only
acceptance-criterion identifier recorded in the repository.

**Alternatives rejected.** Inferring the policy from `prompt_version`
(a prompt version identifies the prompt contract, not the routing
policy in force after the response); silently defaulting to `v1`
(would present an assumption as fact); backfilling `policy_version`
into historical records (would rewrite the append-only trail).

**Rationale.** Replay output is governance evidence; an assumption
buried in a default would contaminate it. Making the assumption
explicit, restricted, and prominently labelled keeps the report honest.

**Consequences and trade-offs.** One extra required flag for current
trails, with an actionable error message when omitted — friction spent
directly on evidential integrity.

**Implementation evidence.**
[`agenttrail/policy_replay.py`](../agenttrail/policy_replay.py)
(`_validate_provenance`);
[`agenttrail/routing_policy.py`](../agenttrail/routing_policy.py)
(`LEGACY_BASELINE_POLICY_KEY`);
[`tests/test_policy_replay.py`](../tests/test_policy_replay.py);
[policy-replay.md](policy-replay.md).
