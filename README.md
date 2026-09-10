# AgentTrail

A complete, deliberately narrow demonstration of an **auditable AI
decision path with a deterministic CI safety gate**. An agent triages
synthetic benefit cases — deciding automatically or escalating to a
human — and every decision is appended to a structured, append-only
audit trail. A behavioural evaluation replays a labelled golden dataset
through recorded Amazon Bedrock responses, scores what was actually
written to the trail, and a CI gate blocks any change that stops
low-confidence cases escalating.

All evaluation and gating is offline and deterministic: no AWS
credentials and no network. The offline evaluation, tests, safety
gates, demo replay, policy replay and record-lookup paths use only the
Python standard library; live fixture recording additionally requires
`boto3`. The cases and rules are synthetic evaluation data, not real
benefit policy.

## Quick start

From a clean checkout (Python 3; CI pins 3.12):

```bash
python3 -m unittest discover -s tests    # full test suite
python3 -m agenttrail.ci_gate            # safety gate: PASS, exit 0
python3 -m agenttrail.ci_gate --agent-version v2   # intentionally unsafe demo:
                                                   # FAIL, exit 1 — that block IS the demo
```

## Documentation

Start with the **[project manual](docs/project-manual.md)** — overview,
end-to-end flow, worked example, architecture, runbook — and the
**[decision log](docs/decision-log.md)** for why it was built this way.

Per-topic references:

| Topic | Document |
|---|---|
| Golden dataset (36 labelled synthetic cases) | [docs/golden-dataset.md](docs/golden-dataset.md) |
| Append-only audit trail | [docs/audit-trail.md](docs/audit-trail.md) |
| Recorded Bedrock fixtures and replay | [docs/model-fixtures.md](docs/model-fixtures.md) |
| Behavioural evaluation harness | [docs/evaluation.md](docs/evaluation.md) |
| CI safety gate and failure report | [docs/ci-gate.md](docs/ci-gate.md) |
| Redaction gate (structured-identifier backstop) | [docs/redaction-gate.md](docs/redaction-gate.md) |
| Demo scenario: v1 green, v2 red | [docs/demo-scenario.md](docs/demo-scenario.md) |
| Policy replay (implemented — what would change under a proposed policy) | [docs/policy-replay.md](docs/policy-replay.md) |
| Record lookup (stored-record view, not replay) | [docs/record-view.md](docs/record-view.md) |

## Licence

MIT — see [LICENSE](LICENSE). The pre-publication safety review that
preceded making this repository public is recorded in
[docs/pre-publication-safety-review.md](docs/pre-publication-safety-review.md).
