# AgentTrail

## The problem

Article 12 of the EU AI Act requires high-risk AI systems to
technically allow automatic recording of events so that their
operation can be traced appropriately. AgentTrail explores that
engineering problem for an AI agent: recording what it decided, on
which inputs, and under which model, prompt and policy, then using
those records to detect and block a behavioural regression in CI. It
is a focused engineering demonstration, not a claim of legal
compliance.

## What AgentTrail does

- An agent triages synthetic benefit cases.
- For each case it either decides automatically or escalates to a human.
- Every decision is appended to a structured, append-only audit trail.
- A behavioural evaluation replays a labelled golden dataset and scores
  what was actually written to that trail, never the model's return
  value.
- A deterministic CI gate blocks any change that stops low-confidence
  cases escalating.

Model responses come from recorded Amazon Bedrock fixtures matched by
request fingerprint, so evaluation and gating run offline,
deterministically and repeatably: no credentials, no network, and the
same verdict every time.

## Headline demonstration

Two agent versions run through the identical pipeline against the same
36-case golden dataset and the same version-controlled policy (minimum
low-confidence escalation rate `1.0000`, tolerance `0.0000`):

| Version | Behaviour on the 12 low-confidence cases | Escalation rate | Gate |
|---|---|---|---|
| `v1` (baseline) | all 12 escalate | `1.0000` | PASS, exit `0` |
| `v2` (intentionally regressed) | 9 of 12 escalate; 3 are auto-decided | `0.7500` | FAIL, exit `1` |

`v2` is a deliberately regressed demonstration, not a deployed
production version. Its over-confident prompt and clearly marked
synthetic fixtures exist only to prove the gate works. When it fails, the gate identifies the
breached property as the escalation rate on the low-confidence set,
reports the measured shortfall, and exits non-zero rather than
reporting a generic test failure. That non-zero exit is the
deployment-blocking behaviour being demonstrated. In GitHub Actions,
the same failure turns the run red and leaves the downstream
deployment-simulation job skipped.

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

**Warning: v2 returning exit code `1` is expected.** It is the
successful demonstration of the safety block, not a broken checkout.
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
  storage, not tamper-proof or durable production storage.
- There are no dashboards, no RAG, no vector database and no
  multi-agent orchestration.
- Record lookup displays a stored record by its ID. It does not
  re-execute or reproduce a past decision.
- Live fixture recording is separate from the offline demonstration.
  It requires `boto3`, configured AWS credentials with Bedrock access,
  and makes paid live calls. Nothing in the quickstart touches it.
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

## Licence

MIT, see [LICENSE](LICENSE). A
[pre-publication safety review](docs/pre-publication-safety-review.md)
was completed before planned public release.
