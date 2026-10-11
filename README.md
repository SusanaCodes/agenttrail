# AgentTrail

[![ci-gate on main](https://github.com/SusanaCodes/agenttrail/actions/workflows/ci-gate.yml/badge.svg?branch=main&event=push)](https://github.com/SusanaCodes/agenttrail/actions/workflows/ci-gate.yml?query=branch%3Amain)

AgentTrail detects tested routing regressions recorded in the audit
trail for the selected fixture snapshot.

It is a small, offline engineering demonstration. An agent decides or
escalates synthetic benefit cases, every decision is written to an
audit trail, and a CI gate scores that trail against labelled cases.
The picture below is the gate failing on a regression that was seeded
for the purpose.

![Output of the v2 gate command: CI GATE: FAIL, with the line "Breached safety property: escalation rate on the low-confidence set", measured value 75.0% against a required minimum of 100.0%, and exit code 1](docs/assets/ci-gate-v2-failure.png)

*Captured CLI output, rendered as an image.* The text is the verbatim
standard output of `python3 -m agenttrail.ci_gate --agent-version v2`,
captured on 8 October 2026; the
[raw capture](docs/assets/ci-gate-v2-failure.txt) is kept beside it.
The command line, the exit-code line and the red highlighting were
added when rendering; the CLI prints no colour. "Gate blocked" is the
gate's own wording for a failed gate. It is not a blocked merge or a
blocked deployment (see [Limitations](#limitations)).

The badge shows the latest `ci-gate` run for a push to `main`. Manual
runs of the seeded `v2` demonstration are excluded from it.

## The problem

Article 12 of the EU AI Act requires high-risk AI systems to
technically allow automatic recording of events so that their
operation can be traced appropriately. AgentTrail explores that
engineering problem for an AI agent: recording what it decided, on
which inputs, and under which model, prompt and policy, then using
those records to detect a tested routing regression in a CI gate. It
is a focused engineering demonstration. It does not establish legal
compliance or production readiness.

## What AgentTrail does

- An agent triages synthetic benefit cases.
- For each case it either decides automatically or escalates to a human.
- Every decision is appended to a structured, append-only audit trail.
- A behavioural evaluation replays a labelled golden dataset and scores
  what was actually written to that trail, never the model's return
  value.
- A deterministic CI gate fails when that audited routing disagrees
  with a golden label, or when the escalation rate on the labelled
  low-confidence cases falls below the version-controlled minimum.

Model responses come from recorded Amazon Bedrock fixtures matched by
request fingerprint, so evaluation and gating run offline,
deterministically and repeatably: no credentials, no network, and the
same verdict for the same code, dataset and fixture set.

## Headline demonstration

AgentTrail detects tested routing regressions recorded in the audit
trail for the selected fixture snapshot.

That sentence is the whole claim, and it has these limits:

- Fixture responses are not authenticated. The SHA-256 fingerprint
  stored with each fixture matches a request to its recorded entry. It
  is not a signature over the response, so the verdict is only as
  trustworthy as the committed fixture file.
- Merge blocking depends on GitHub repository rules requiring the
  `evaluation-gate` check. The workflow file alone does not enforce it.
  Since 11 October 2026 an active ruleset on `main` requires that
  check (see [Limitations](#limitations)); a required check does not
  prove that the job still enforces anything.

Two agent versions run through the identical pipeline against the same
36-case golden dataset and the same version-controlled policy (minimum
low-confidence escalation rate `1.0000`, tolerance `0.0000`):

| Version | Behaviour on the 12 low-confidence cases | Escalation rate | Gate |
|---|---|---|---|
| `v1` (baseline) | all 12 escalate | `1.0000` | PASS, exit `0` |
| `v2` (intentionally regressed) | 9 of 12 escalate; 3 are auto-decided | `0.7500` | FAIL, exit `1` |

`v2` is a deliberately regressed demonstration, not a deployed
production version. Its failures are deliberately seeded: an
over-confident prompt and clearly marked synthetic fixtures make three
low-confidence cases auto-decide, so that the gate's failure path can
be shown. When it fails, the gate identifies the breached property as
the escalation rate on the low-confidence set, reports the measured
shortfall, and exits non-zero rather than reporting a generic test
failure.

What is demonstrated is a failed gate. In GitHub Actions, the same
failure turns the run red and leaves the downstream
deployment-simulation job (`deployment-demo`) skipped. That job is a
no-op that deploys nothing, so a skipped simulation is not a blocked
real deployment, and no real deployment workflow exists. A red run
does not by itself stop a merge either; that is the repository-rule
dependency stated above.

### Verified figures

Each figure is a separate measurement. The gate, dataset and
policy-replay figures were last reproduced on 8 October 2026 at commit
`a558713`, with network access denied and no AWS credentials, using the
commands in the [quickstart](#ten-minute-quickstart). The unit-test
count is the current suite, re-run on 10 October 2026 after regression
tests for error-message hygiene, the redaction gate and malformed input
encodings were added; it was 345 on 8 October and 430 on 9 October.

| Figure | Result |
|---|---|
| Unit tests | 442 run, all passing, exit `0` |
| Golden cases | 36 labelled synthetic cases |
| Protected cases in the main gate | 12: the cases labelled low-confidence, which must all escalate |
| Agent `v1` | 12 of 12 protected cases escalate. Gate PASS, exit `0` |
| Agent `v2` (synthetic, seeded) | 9 of 12 protected cases escalate and 3 are auto-decided. Gate FAIL, exit `1` |
| Policy replay under routing policy `v2` | 36 stored records replayed: 35 unchanged, 1 flip (`SYN-031`, decide to escalate), exit `0` |

Two different things are called `v2`, and they are unrelated:

- **Agent version `v2`** is the seeded regression above: an
  over-confident prompt with synthetic fixtures. It is what makes the
  gate fail.
- **Routing policy `v2`** is a proposed confidence threshold of `0.95`
  in place of `0.70`. Policy replay re-routes the stored `v1` records
  under it and reports which decisions would change. It is read-only
  change-impact evidence; it approves and rejects nothing, and it is
  not part of the gate.

## Architecture

```mermaid
flowchart LR
    DATA["Golden dataset<br/>36 labelled cases"]
    FIX["Recorded fixtures<br/>offline replay"]
    HARNESS["Evaluation harness"]
    AGENT["Agent<br/>decide or escalate"]
    TRAIL[("Audit trail<br/>append-only JSONL")]
    GATE{"CI gate"}
    REPLAY["Policy replay<br/>read-only"]

    DATA -->|"cases and labels"| HARNESS
    HARNESS -->|"1. invokes per case"| AGENT
    FIX -->|"recorded response"| AGENT
    AGENT -->|"2. appends one record"| TRAIL
    TRAIL -->|"3. reopened and scored"| HARNESS
    HARNESS -->|"4. result"| GATE
    TRAIL -.->|"read separately"| REPLAY
    FIX -.->|"recorded response"| REPLAY
    DATA -.->|"source cases"| REPLAY
```

The harness invokes the agent once per golden case, discards what the
agent returns, then reopens the trail and scores only what was written
there. The CI gate runs the harness and applies a fixed policy to its
result. Policy replay is a separate command that reads an existing
trail and writes nothing. The agent is never shown the expected labels.
The [project manual](docs/project-manual.md#4-architecture) has the
full diagram.

## Ten-minute quickstart

Prerequisites: Git and Python 3 (CI pins Python 3.12). Nothing else is
needed: no third-party packages, no virtual environment, no AWS
credentials, and no network access after the clone. Run every command
from the repository root.

```bash
git clone https://github.com/SusanaCodes/agenttrail.git
cd agenttrail
```

Run the baseline v1 gate. Expected: `CI GATE: PASS`,
`measured_rate=1.0000`, `low_confidence_escalated=12`, exit `0`.

```bash
python3 -m agenttrail.ci_gate --agent-version v1
echo $?
```

Run the intentionally regressed v2 gate. Expected: `CI GATE: FAIL`,
`measured_rate=0.7500`, `low_confidence_escalated=9`, exit `1`.

```bash
python3 -m agenttrail.ci_gate --agent-version v2
echo $?
```

**Warning: v2 returning exit code `1` is expected.** It is the gate
failing as intended on the seeded regression, not a broken checkout.
Exit `2` from either command indicates a genuine execution error (a
missing, invalid or undecodable fixture, dataset or audit input).

### Optional verification

The full test suite runs in seconds and needs no setup. Expected:
`Ran 442 tests`, output ending `OK`, exit `0`.

```bash
python3 -m unittest discover -s tests
```

Policy replay needs a stored trail, so write one to a temporary path
first. Expected from the second command: `records evaluated: 36`,
`unchanged: 35`, `flipped: 1`, the line
`SYN-031: decide -> escalate`, exit `0`.

```bash
TRAIL="$(mktemp -d)/replay.audit.jsonl"
python3 -m agenttrail.eval --audit-path "$TRAIL"
python3 -m agenttrail.policy_replay --audit-path "$TRAIL" \
  --target-policy v2 --legacy-baseline-policy v1
```

Current audit records do not store `policy_version`. The
`--legacy-baseline-policy v1` option explicitly declares the baseline
as an operator-supplied assumption, not recorded policy provenance.

## Limitations

The [security assessment](docs/security-assessment.md) consolidates two
security reviews of this repository and a third, pre-publication
review. It records what has been verified and what has not: repository
enforcement was activated and proved on 11 October 2026, final
verification of each published commit is recorded on its ticket, and
it lists the implementation findings that remain open. Read it before
relying on anything here.

Two limits of the evaluation are stated in the same words wherever
they appear in the documentation.

The low-confidence override is protected by unit tests. The
fixture-backed behavioural evaluation does not exercise it, because no
recorded response falls in the sub-threshold `decide` region.

The request hash proves the replay request matches the stored request
byte for byte. It does not bind the response to that request and does
not prove that Bedrock produced the response. Fixture re-recording is a
reviewed act that the gate cannot itself authenticate.

Detail is in the [CI gate](docs/ci-gate.md#known-coverage-gap-the-low-confidence-override)
and [model fixtures](docs/model-fixtures.md#what-the-request-hash-does-and-does-not-establish)
documents. The remaining boundaries:

- **Offline fixture evaluation.** The gate scores one recorded snapshot
  of one model. It says nothing about the current live model, overall
  quality, fairness or bias.
- **Unauthenticated fixture provenance.** That the `v1` set is a
  recording is the maintainer's statement. Nothing in the repository
  verifies it, and the `v2` set is synthetic by design.
- **No tamper-evident trail.** The audit trail is a local append-only
  JSONL file: demonstrator storage. It is not tamper-evident, and it is
  not durable production storage.
- **Merge enforcement verified, with limits.** Since 11 October 2026
  the active `main-protection` ruleset (id 24875447) on `main` requires
  the `evaluation-gate`, `dependency-audit` and `secret-scan` checks
  from GitHub Actions, requires branches to be up to date, requires a
  pull request, blocks force-push and deletion, and has no bypass
  actors. A pull request without the `evaluation-gate` check was
  blocked ([pull request #16](https://github.com/SusanaCodes/agenttrail/pull/16));
  that attribution is by elimination against the effective rules,
  because GitHub's API does not name the missing check. A required
  check does not stop its own workflow logic being weakened, no
  independent human review is established (code-owner approval is
  deferred in this sole-owner repository), and there is no real
  deployment to stop. Evidence:
  [security assessment, verification record](docs/security-assessment.md#verification-record).
- **No production-readiness or compliance claim.** This is a focused
  engineering demonstration, not a product. It is not
  production-hardened and does not establish compliance with the EU AI
  Act or any other requirement.

Scope:

- Cases, rules, labels and evaluation data are synthetic. They do not
  represent real benefit policy.
- The redaction gate scans committed record data for three supported
  identifier formats (National Insurance numbers, UK postcodes and NHS
  numbers). It does not detect all personal data, and a passing scan
  does not show that none is present.
- There are no dashboards, no RAG, no vector database and no
  multi-agent orchestration.
- Record lookup displays a stored record by its ID. It does not
  re-execute or reproduce a past decision.
- Live fixture recording is separate from the offline demonstration.
  It requires `boto3`, installed from the hash-locked
  `requirements-recording.txt`, configured AWS credentials with Bedrock
  access, and makes paid live calls. Nothing in the quickstart touches
  it.

## Roadmap: Phase 2 (planned, not built)

Nothing in this section exists in the repository. Today there is one
direct Amazon Bedrock call site, a purpose-built evaluation harness and
a JSONL trail, and every offline path uses only the Python standard
library.

Phase 2 is a planned gateway that agent traffic would pass through,
instead of the agent calling the model directly:

| Planned component | Intended role | Status |
|---|---|---|
| FastAPI | Gateway endpoint that intercepts tool calls | Planned, not built |
| LiteLLM | Routing layer for model calls, with budgets and fallback | Planned, not built |
| Langfuse | Tracing over the decision path | Planned, not built |
| Inspect | Scoring the golden dataset through an evaluation framework | Planned, not built |

None of these is installed, imported or integrated, and none of the
results above depends on them. The project manual maps today's
components to
[comparable tooling](docs/project-manual.md#10-industry-tooling-equivalents)
and lists other [future work](docs/project-manual.md#13-future-improvements-phase-2).

## Documentation

Start with the **[project manual](docs/project-manual.md)** for the
full end-to-end description, architecture, Article 12 mapping and
per-topic documentation index, and the
**[decision log](docs/decision-log.md)** for why it was built this way.
The **[security assessment](docs/security-assessment.md)** (a working
assessment, not a sign-off) records the findings, risks, verification
record and remaining limits. The complete
demonstrated v1 and v2 output is in the
[demo scenario](docs/demo-scenario.md).

## Provenance

AgentTrail was built as a solo final project on a training programme,
on personal resources and accounts, with part of the build done in
allocated working hours. Ownership of the work and the right to publish
it have not been determined in writing. On 10 October 2026 the
maintainer decided to publish without such a determination, on her
understanding that the programme context permits it. That is a
maintainer decision, not a written approval from the programme or the
employer, and not an ownership determination; the
[open-code assessment](docs/open-code-assessment.md#licence-and-provenance)
records the position and the decision.

## Maintenance, security and dependencies

AgentTrail is maintained by Susana
([@SusanaCodes](https://github.com/SusanaCodes)) as a prototype, on a
best-efforts basis. Only the head of `main` is maintained.

- **Maintenance:** [maintenance and ownership](docs/maintenance.md)
  covers support scope, the next review date, dependency review,
  handover, and how the repository is marked and archived if it stops
  being maintained.
- **Security:** [SECURITY.md](SECURITY.md) gives the private reporting
  route and response targets. Do not report vulnerabilities in public
  issues. Private vulnerability reporting, secret scanning and push
  protection were enabled and read back on 11 October 2026. No test
  report has been submitted and no blocked push has been observed, so
  the triage path and the push-protection block are unexercised;
  `SECURITY.md` and the
  [open-code assessment](docs/open-code-assessment.md#evidence-update-11-october-2026)
  record the state.
- **Dependencies:** the quickstart and every offline path need no
  third-party packages. Optional live recording (`boto3`), deck
  generation (`python-pptx`) and maintenance tooling (`pip-tools`,
  `pip-audit`) each install from a hash-locked `requirements-*.txt`.
  Dependabot is configured for weekly update proposals; the maintainer
  merges them only when the security and gate checks pass.

AgentTrail uses the GDS/DSIT guidance of 14 May 2026 as its publication
checklist. Implemented controls, evidence and outstanding gaps are
documented in the [open-code assessment](docs/open-code-assessment.md).
This is the maintainer's own assessment of a prototype. It is not a
government endorsement, a certification, or a claim of legal compliance
or production readiness.

## Licence

MIT, see [LICENSE](LICENSE). The copyright line and the unresolved
provenance position behind it are recorded in the
[open-code assessment](docs/open-code-assessment.md). A
[pre-publication safety review](docs/pre-publication-safety-review.md)
was completed in September 2026 before planned public release; it is
historical evidence and does not cover later changes.
