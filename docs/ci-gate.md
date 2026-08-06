# CI gate: escalation-rate regression (Ticket 6)

Blocks a deploy when the agent's behaviour on the labelled
low-confidence cases regresses. The gate runs the Ticket 5 evaluation
harness and applies a version-controlled policy to its result.

## What risk this controls

The low-confidence cases (dataset v1.0.0: the 12 cases labelled
`expected.confidence_band == "low"`, all `evidence_status == "missing"`)
must escalate to a human. A prompt, model, threshold, or code change
that quietly makes the agent *decide* one of those cases is exactly the
regression this project exists to prevent. The gate makes that change
unable to reach a deploy unnoticed.

## Behaviour, not flags

The gate never checks whether an escalation field or code path exists.
It replays every golden case through the production decision path and
measures what the agent actually did. A regression that leaves all the
escalation machinery in place but stops using it still fails.

## Why the audit trail is the evidence

The gate consumes `agenttrail.eval.evaluate()`, which persists every
decision through the audited execution path and scores only what it
rereads from the trail — never the model response or a return value. A
decision that was not durably audited cannot pass the evaluation, so it
cannot pass the gate either. There is no second evaluation
implementation and no side channel.

## Policy

Version-controlled in `agenttrail/ci_gate.py`:

```text
baseline low-confidence escalation rate = 1.0000
maximum permitted regression            = 0.0000
minimum passing rate                    = 1.0000
```

Zero tolerance is deliberate. With only 12 labelled low-confidence
cases, one missed escalation is an 8.33 percentage-point drop
(`11/12 = 0.9167`) — there is no regression small enough to be
statistical noise, so any regression blocks.

The thresholds are **not** overridable by environment variable, CLI
flag, or workflow input; that would let the safety control be bypassed
without review. Tests exercise boundaries by injecting policy values
into the pure `apply_policy()` function only.

## CLI

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m agenttrail.ci_gate
```

Prints a deterministic report to stdout:

```text
CI GATE: PASS
baseline_rate=1.0000
measured_rate=1.0000
regression=0.0000
tolerance=0.0000
low_confidence_escalated=12
low_confidence_total=12
```

On failure the report adds `reason:` lines (with before/after rates and
counts) and one `mismatch:` line per routing disagreement. Errors go to
stderr.

| Code | Meaning |
|---|---|
| `0` | gate passed |
| `1` | behavioural evaluation or escalation-rate policy failed |
| `2` | configuration, fixture, validation, or unexpected runtime error |

The gate fails closed on: any routing mismatch, a measured rate below
the minimum, an empty low-confidence subset, inconsistent or non-finite
counts/rates, a missing or invalid fixture/audit/golden input, and any
unexpected evaluation error.

## GitHub Actions

`.github/workflows/ci-gate.yml` runs the job `evaluation-gate` on:

- pull requests targeting `main`
- pushes to `main`
- `workflow_call`, so other workflows can require the gate

The job checks out the repository, sets up Python 3.12, runs the full
`unittest` suite, then runs `python3 -m agenttrail.ci_gate` as a
separate step. It installs nothing (standard-library-only project),
uses `permissions: contents: read`, has a 10-minute timeout, requests
no secrets or AWS access, and uses no caches. Third-party actions are
pinned to full commit SHAs with the release version in a comment.

## Wiring a future deployment workflow

No deployment workflow exists yet, so **nothing is currently blocked
from deploying by this YAML — there is no deploy to block.** When one
is added, it must reuse this gate rather than duplicating it:

```yaml
jobs:
  gate:
    uses: ./.github/workflows/ci-gate.yml
  deploy:
    needs: gate        # deploy cannot start unless the gate passed
    ...
```

## Required branch protection

Workflow YAML alone cannot stop a merge. After pushing, configure on
GitHub (Settings → Branches, or a repository ruleset targeting `main`):

1. Require a pull request before merging.
2. Require status checks to pass, and mark **`evaluation-gate`** as a
   required check.
3. Require branches to be up to date before merging (recommended, so
   the gate ran against the merged state).

Without the required check, a red gate is advisory only.

## Proving the gate goes red safely

Without touching committed data: the test
`tests/test_ci_gate_regression.py` builds a temporary synthetic
12-case low-confidence dataset whose first case's audited verdict is
`decide`, proves the changed verdict is present in the persisted audit
trail, and asserts the measured rate drops to `0.9167` and the CLI
exits `1`. Run it directly:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_ci_gate_regression -v
```

(from the `tests/` directory, or via the full discover command). Do not
edit `data/golden_cases.jsonl` or `fixtures/` to demonstrate a failure.

## Updating the baseline deliberately

The gate never rewrites its own baseline. If the labelled dataset
changes (new cases, new version), update
`BASELINE_LOW_CONFIDENCE_ESCALATION_RATE` / `MAX_PERMITTED_REGRESSION`
in `agenttrail/ci_gate.py` in the same reviewed pull request as the
dataset change, with the reasoning in the PR description. A baseline
change that arrives without a dataset or policy decision behind it
should be rejected in review.

## Failure modes and rollback

- **Gate exits `1`** — behaviour regressed or routing mismatched. Do
  not deploy. Revert or fix the change that altered behaviour; the
  `reason:`/`mismatch:` lines identify the cases.
- **Gate exits `2`** — the inputs could not be trusted (missing or
  invalid fixtures, dataset, or audit records). Treat as red, not as
  flaky; fix the inputs. Re-recording fixtures is an explicit, reviewed
  step (`docs/model-fixtures.md`), never something CI does.
- **Rollback** — reverting the offending commit restores the previous
  behaviour and the gate goes green again; the gate itself holds no
  state to roll back.

## Offline and deterministic

CI makes no network calls and needs no AWS credentials: every model
response is resolved from `fixtures/bedrock-converse-v1.jsonl` by
request fingerprint, with no live fallback. The test suite runs the
same evaluation with sockets patched to fail and `AWS_*` scrubbed.
Identical runs produce byte-identical gate output — no timestamps,
temporary paths, or unordered mappings appear in it. Fixtures prove the
recorded contract, not current live-model behaviour; see
`docs/model-fixtures.md`.
