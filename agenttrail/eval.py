"""Behavioural evaluation of routing against the golden labels (Ticket 5).

Answers one question: given the labelled golden cases, did the agent
actually route them correctly? Not "does an escalation field exist".

The pipeline is deliberately end-to-end:

    golden dataset -> fixture replay -> decide_case_audited
                   -> persisted JSONL trail -> reopened -> verdict

The verdict is read from the reopened trail, never from what
``decide_case_audited`` returns: a decision that was not durably audited
must not be able to pass an evaluation.

Offline by construction — the only Bedrock client used is
``ReplayBedrockClient``, which resolves recorded responses by exact
request fingerprint and raises on a miss. No live fallback, no
credentials, no network. Fixtures are a stable regression baseline for
the recorded responses and request contract; they prove nothing about
current live-model behaviour and go stale when the prompt contract,
model, or dataset changes.
"""

import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agenttrail.audit import (
    AuditValidationError,
    AuditWriteError,
    decide_case_audited,
)
from agenttrail.audit_reader import (
    AuditTrailReadError,
    index_records_by_case,
    read_audit_trail,
)
from agenttrail.decision import (
    CONFIDENCE_THRESHOLD,
    CaseValidationError,
    ModelResponseError,
)
from agenttrail.fixtures import (
    DEFAULT_FIXTURE_PATH,
    FixtureNotFoundError,
    FixtureValidationError,
    ReplayBedrockClient,
    load_fixtures,
)
from agenttrail.golden import (
    DEFAULT_DATASET_PATH,
    LOW_CONFIDENCE_BAND,
    GoldenDatasetError,
    load_labelled_cases,
)

ESCALATE = "escalate"


class EvalError(RuntimeError):
    """The evaluation could not produce a trustworthy verdict. Fail closed."""


# Every failure the harness deliberately fails closed on, for callers
# (such as the later CI gate) that need to separate "the evaluation could
# not run" from "the routing disagreed with the labels".
EVALUATION_ERRORS = (
    EvalError,
    GoldenDatasetError,
    AuditTrailReadError,
    FixtureValidationError,
    FixtureNotFoundError,
    AuditValidationError,
    AuditWriteError,
    CaseValidationError,
    ModelResponseError,
    OSError,
)


@dataclass(frozen=True)
class EvalMismatch:
    """A case whose audited routing disagreed with its golden label."""

    case_id: str
    expected: str
    actual: str


@dataclass(frozen=True)
class EvalResult:
    """Machine-readable evaluation outcome for a later CI safety gate."""

    passed: bool
    total_cases: int
    matched_cases: int
    mismatches: tuple
    low_confidence_total: int
    low_confidence_escalated: int
    low_confidence_escalation_rate: float


def resolve_fixture_model_id(fixture_path=DEFAULT_FIXTURE_PATH):
    """The single model ID the fixture set was recorded against.

    Derived from the fixtures, not the environment: any other ID would
    change every request fingerprint. No AWS variable is consulted.
    """
    model_ids = {e["model_id"] for e in load_fixtures(fixture_path).values()}
    if len(model_ids) != 1:
        raise EvalError(
            f"fixture set must cover exactly one model ID, found "
            f"{len(model_ids)}"
        )
    return model_ids.pop()


def _run_cases(cases, client, audit_path, model_id, confidence_threshold):
    for case in cases:
        # Only the validated model input crosses this boundary; the
        # expected label and confidence band stay on the LabelledCase.
        # The return value is discarded by design.
        decide_case_audited(
            case.model_input,
            client,
            case_ref=case.case_id,
            audit_path=audit_path,
            model_id=model_id,
            confidence_threshold=confidence_threshold,
        )


def evaluate(
    dataset_path=DEFAULT_DATASET_PATH,
    fixture_path=DEFAULT_FIXTURE_PATH,
    audit_path=None,
    model_id=None,
    confidence_threshold=CONFIDENCE_THRESHOLD,
):
    """Replay the labelled dataset and score routing from the audit trail.

    With ``audit_path`` unset, records go to a private temporary trail
    removed afterwards, so evaluation never mixes with a user's normal
    trail. A supplied path must not already exist — appending to a
    populated trail would score pre-existing records.
    """
    cases = load_labelled_cases(dataset_path)
    if model_id is None:
        model_id = resolve_fixture_model_id(fixture_path)
    # Fails closed on a missing or invalid fixture set, before any case runs.
    client = ReplayBedrockClient(fixture_path)

    if audit_path is None:
        with tempfile.TemporaryDirectory(prefix="agenttrail-eval-") as tmp:
            trail = Path(tmp) / "eval.audit.jsonl"
            return _run_and_score(
                cases, client, trail, model_id, confidence_threshold
            )

    trail = Path(audit_path)
    if trail.exists():
        raise EvalError(
            f"evaluation audit trail already exists: {trail}; refusing to "
            "append evaluation records to an existing trail"
        )
    return _run_and_score(
        cases, client, trail, model_id, confidence_threshold
    )


def _run_and_score(cases, client, trail, model_id, confidence_threshold):
    _run_cases(cases, client, trail, model_id, confidence_threshold)
    # Reopened only after every case has been written and closed, so the
    # verdict rests on what durably reached the trail.
    return score(cases, read_audit_trail(trail))


def score(cases, records):
    """Compare audited routing with golden labels; dataset order preserved."""
    by_case = index_records_by_case(records, {c.case_id for c in cases})

    matched = 0
    mismatches = []
    low_total = 0
    low_escalated = 0
    for case in cases:
        actual = by_case[case.case_id]["decision"]
        if actual == case.expected_routing:
            matched += 1
        else:
            mismatches.append(
                EvalMismatch(
                    case_id=case.case_id,
                    expected=case.expected_routing,
                    actual=actual,
                )
            )
        if case.confidence_band == LOW_CONFIDENCE_BAND:
            low_total += 1
            if actual == ESCALATE:
                low_escalated += 1

    if low_total == 0:
        raise EvalError(
            "dataset contains no cases labelled "
            f"expected.confidence_band == {LOW_CONFIDENCE_BAND!r}; the "
            "low-confidence escalation rate is undefined"
        )

    return EvalResult(
        passed=not mismatches,
        total_cases=len(cases),
        matched_cases=matched,
        mismatches=tuple(mismatches),
        low_confidence_total=low_total,
        low_confidence_escalated=low_escalated,
        low_confidence_escalation_rate=low_escalated / low_total,
    )


def format_report(result):
    """Deterministic plain-text summary built only from controlled values."""
    rate = result.low_confidence_escalation_rate
    lines = [
        f"cases evaluated:            {result.total_cases}",
        f"routing matched:            {result.matched_cases}",
        f"routing mismatched:         {len(result.mismatches)}",
        f"low-confidence cases:       {result.low_confidence_total}",
        f"low-confidence escalated:   {result.low_confidence_escalated}",
        f"low-confidence esc. rate:   {rate:.4f} ({rate * 100:.2f}%)",
    ]
    for mismatch in result.mismatches:
        lines.append(
            f"mismatch: {mismatch.case_id} "
            f"expected={mismatch.expected} audited={mismatch.actual}"
        )
    lines.append("PASS" if result.passed else "FAIL")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.eval",
        description=(
            "Replay the golden dataset through recorded Bedrock fixtures "
            "and score routing from the persisted audit trail. Offline: "
            "no AWS credentials or network access are used."
        ),
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument(
        "--audit-path",
        default=None,
        help=(
            "write evaluation audit records here (must not exist); "
            "defaults to a temporary trail that is discarded"
        ),
    )
    args = parser.parse_args(argv)

    try:
        model_id = resolve_fixture_model_id(args.fixtures)
        result = evaluate(
            dataset_path=args.dataset,
            fixture_path=args.fixtures,
            audit_path=args.audit_path,
        )
    except EVALUATION_ERRORS as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        return 2

    print(f"dataset:                    {args.dataset}")
    print(f"fixtures:                   {args.fixtures}")
    print(f"model (recorded):           {model_id}")
    print(format_report(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
