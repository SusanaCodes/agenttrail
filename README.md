# AgentTrail

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
  Enforcement is currently unverified.

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
missing or invalid fixture, dataset or audit input).

### Optional verification

The full test suite runs in seconds and needs no setup. Expected: exit
`0` and output ending `OK`.

```bash
python3 -m unittest discover -s tests
```

## Scope and limitations

- A focused engineering demonstration, not a product. It is not
  production-hardened.
- Cases, rules, labels and evaluation data are synthetic. They do not
  represent real benefit policy.
- The audit trail is a local append-only JSONL file: demonstrator
  storage. It is not tamper-evident, and it is not durable production
  storage.
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
- The gate asserts one behavioural property over one recorded snapshot
  of one model. It says nothing about overall quality, fairness or
  bias, or regulatory compliance.

## Documentation

Start with the **[project manual](docs/project-manual.md)** for the
full end-to-end description, architecture, Article 12 mapping and
per-topic documentation index, and the
**[decision log](docs/decision-log.md)** for why it was built this way.
The complete demonstrated v1 and v2 output is in the
[demo scenario](docs/demo-scenario.md).

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
  issues. Private reporting is not active yet; it can only be enabled
  once the repository is public.
- **Dependencies:** the quickstart and every offline path need no
  third-party packages. Optional live recording (`boto3`), deck
  generation (`python-pptx`) and maintenance tooling (`pip-tools`,
  `pip-audit`) each install from a hash-locked `requirements-*.txt`.
  Dependabot is configured to propose weekly updates once its
  configuration is on `main`; the maintainer merges them only when the
  security and gate checks pass.

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
