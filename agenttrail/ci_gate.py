"""CI gate: block deployment on an escalation-rate regression (Ticket 6).

Consumes the Ticket 5 evaluation verdict — golden dataset replayed
through recorded Bedrock fixtures, every decision persisted to and then
reread from the audit trail — and applies the version-controlled release
policy to it. This module never re-evaluates anything itself and never
looks at a model response directly: the only evidence it accepts is the
audit-trail-derived ``EvalResult``.

The policy lives here, in version control, and is deliberately not
overridable through environment variables, CLI flags, or workflow
inputs. Weakening it must be a reviewed code change:

    baseline low-confidence escalation rate = 1.0000
    maximum permitted regression            = 0.0000
    minimum passing rate                    = 1.0000

With only 12 labelled low-confidence cases, one missed escalation is an
8.33 percentage-point regression and must block the gate.

Everything fails closed. A routing mismatch, a measured rate below the
minimum, an empty low-confidence subset, inconsistent or non-finite
numbers, and any evaluation error all block. Exit codes: 0 the gate
passed, 1 a behavioural or rate-policy failure, 2 a configuration,
validation, or unexpected runtime error.
"""

import argparse
import math
import sys
from dataclasses import dataclass

from agenttrail.eval import EVALUATION_ERRORS, EvalMismatch, EvalResult, evaluate
from agenttrail.fixtures import DEFAULT_FIXTURE_PATH
from agenttrail.golden import DEFAULT_DATASET_PATH

# The version-controlled policy for dataset v1.0.0 (12 low-confidence
# cases, all labelled escalate). Zero tolerance is intentional: the
# subset is small enough that any regression is one whole missed
# escalation, never statistical noise.
BASELINE_LOW_CONFIDENCE_ESCALATION_RATE = 1.0
MAX_PERMITTED_REGRESSION = 0.0


class GatePolicyError(ValueError):
    """The gate could not trust its inputs or policy. Fail closed."""


# Everything the CLI maps to exit code 2: the evaluation harness's own
# fail-closed set plus the gate's input/policy validation.
GATE_ERRORS = (GatePolicyError,) + EVALUATION_ERRORS


@dataclass(frozen=True)
class GateDecision:
    """The gate's verdict on one evaluation result, ready for a CI log."""

    passed: bool
    baseline_rate: float
    measured_rate: float
    regression: float
    tolerance: float
    minimum_passing_rate: float
    low_confidence_escalated: int
    low_confidence_total: int
    failure_reasons: tuple
    mismatches: tuple


def _require(condition, message):
    # Not ``assert``: assertions disappear under ``python -O`` and this
    # validation is the safety control itself.
    if not condition:
        raise GatePolicyError(message)


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_policy(baseline_rate, tolerance):
    for name, value in (
        ("baseline_rate", baseline_rate),
        ("tolerance", tolerance),
    ):
        _require(
            isinstance(value, float) and math.isfinite(value),
            f"{name} must be a finite float, got {value!r}",
        )
    _require(
        0.0 <= baseline_rate <= 1.0,
        f"baseline_rate must be within [0.0, 1.0], got {baseline_rate!r}",
    )
    _require(
        0.0 <= tolerance <= baseline_rate,
        f"tolerance must be within [0.0, baseline_rate], got {tolerance!r}",
    )


def _validate_result(result):
    _require(
        isinstance(result, EvalResult),
        f"gate input must be an EvalResult, got {type(result).__name__}",
    )
    _require(isinstance(result.passed, bool), "passed must be a bool")
    for name in (
        "total_cases",
        "matched_cases",
        "low_confidence_total",
        "low_confidence_escalated",
    ):
        _require(
            _is_count(getattr(result, name)),
            f"{name} must be a non-negative int, got {getattr(result, name)!r}",
        )
    _require(result.total_cases >= 1, "evaluation covered no cases")
    _require(
        isinstance(result.mismatches, tuple)
        and all(isinstance(m, EvalMismatch) for m in result.mismatches),
        "mismatches must be a tuple of EvalMismatch",
    )
    _require(
        result.matched_cases >= 0
        and result.matched_cases + len(result.mismatches) == result.total_cases,
        f"inconsistent counts: matched {result.matched_cases} + "
        f"{len(result.mismatches)} mismatches != {result.total_cases} cases",
    )
    _require(
        result.passed == (not result.mismatches),
        "passed flag disagrees with the recorded mismatches",
    )
    _require(
        result.low_confidence_total >= 1,
        "low-confidence subset is empty; the escalation rate is undefined",
    )
    _require(
        result.low_confidence_total <= result.total_cases,
        f"low-confidence subset ({result.low_confidence_total}) exceeds "
        f"total cases ({result.total_cases})",
    )
    _require(
        0 <= result.low_confidence_escalated <= result.low_confidence_total,
        f"escalated count {result.low_confidence_escalated} outside "
        f"[0, {result.low_confidence_total}]",
    )
    rate = result.low_confidence_escalation_rate
    _require(
        isinstance(rate, float) and math.isfinite(rate),
        f"escalation rate must be a finite float, got {rate!r}",
    )
    _require(
        0.0 <= rate <= 1.0,
        f"escalation rate {rate!r} outside [0.0, 1.0]",
    )
    _require(
        rate == result.low_confidence_escalated / result.low_confidence_total,
        f"escalation rate {rate!r} disagrees with counts "
        f"{result.low_confidence_escalated}/{result.low_confidence_total}",
    )


def apply_policy(
    result,
    baseline_rate=BASELINE_LOW_CONFIDENCE_ESCALATION_RATE,
    tolerance=MAX_PERMITTED_REGRESSION,
):
    """Pure comparison of an EvalResult against the gate policy.

    Raises GatePolicyError when the inputs cannot be trusted; otherwise
    returns a GateDecision. The policy parameters exist only so tests
    can exercise boundaries — production callers use the defaults.
    """
    _validate_policy(baseline_rate, tolerance)
    _validate_result(result)

    minimum = baseline_rate - tolerance
    measured = result.low_confidence_escalation_rate
    reasons = []
    if result.mismatches:
        reasons.append(
            f"{len(result.mismatches)} audited routing decision(s) "
            "disagreed with the golden labels"
        )
    if measured < minimum:
        reasons.append(
            f"low-confidence escalation rate regressed from baseline "
            f"{baseline_rate:.4f} to {measured:.4f}: escalated "
            f"{result.low_confidence_escalated}/{result.low_confidence_total}"
            f", minimum passing rate {minimum:.4f} "
            f"(tolerance {tolerance:.4f})"
        )
    return GateDecision(
        passed=not reasons,
        baseline_rate=baseline_rate,
        measured_rate=measured,
        regression=max(0.0, baseline_rate - measured),
        tolerance=tolerance,
        minimum_passing_rate=minimum,
        low_confidence_escalated=result.low_confidence_escalated,
        low_confidence_total=result.low_confidence_total,
        failure_reasons=tuple(reasons),
        mismatches=result.mismatches,
    )


def format_gate_report(decision):
    """Deterministic plain-text report built only from controlled values."""
    lines = [
        f"CI GATE: {'PASS' if decision.passed else 'FAIL'}",
        f"baseline_rate={decision.baseline_rate:.4f}",
        f"measured_rate={decision.measured_rate:.4f}",
        f"regression={decision.regression:.4f}",
        f"tolerance={decision.tolerance:.4f}",
        f"low_confidence_escalated={decision.low_confidence_escalated}",
        f"low_confidence_total={decision.low_confidence_total}",
    ]
    lines.extend(f"reason: {reason}" for reason in decision.failure_reasons)
    lines.extend(
        f"mismatch: {m.case_id} expected={m.expected} audited={m.actual}"
        for m in decision.mismatches
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.ci_gate",
        description=(
            "Run the deterministic behavioural evaluation and apply the "
            "version-controlled escalation-rate policy. Offline: no AWS "
            "credentials or network access are used. The policy itself "
            "is fixed in agenttrail/ci_gate.py and cannot be overridden "
            "here."
        ),
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURE_PATH))
    args = parser.parse_args(argv)

    try:
        result = evaluate(
            dataset_path=args.dataset, fixture_path=args.fixtures
        )
        decision = apply_policy(result)
    except GATE_ERRORS as exc:
        print(f"gate error: {exc}", file=sys.stderr)
        return 2

    print(format_gate_report(decision))
    return 0 if decision.passed else 1


if __name__ == "__main__":
    sys.exit(main())
