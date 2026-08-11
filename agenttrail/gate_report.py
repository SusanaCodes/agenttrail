"""Blocked-gate governance report for the CI safety gate (Ticket 7).

When the gate blocks, this module renders the reason as a concise,
deterministic, human-readable report naming the breached safety
property, the required minimum, the measured value, and the shortfall in
percentage points. It formats the ``GateDecision`` that
``agenttrail.ci_gate.apply_policy`` already produced — the same
structured result, configured threshold, and comparison outcome the
gate's pass/block verdict rests on. Nothing is re-evaluated or
re-compared here, and nothing here influences the verdict or exit code.

Wording is deliberate: the gate compares one measured result against the
fixed, version-controlled requirement, so the report says "required",
"measured", and "shortfall" in percentage points. It never claims a
historical regression ("before"/"after"/"dropped") — that would need a
persisted previous result, which AgentTrail does not keep.
"""

import os

# The one safety property the gate holds to a required threshold.
SAFETY_PROPERTY_LOW_CONFIDENCE_ESCALATION = (
    "escalation rate on the low-confidence set"
)

GITHUB_STEP_SUMMARY_ENV = "GITHUB_STEP_SUMMARY"


def shortfall_percentage_points(required_rate, measured_rate):
    """Absolute percentage-point gap below the requirement, never negative.

    ``max`` clamps a pass (measured at or above required) to exactly
    ``0.0`` and also normalises ``-0.0``, which ``max(0.0, -0.0)``
    resolves to positive ``0.0``. Operates on the raw rates — displayed,
    rounded percentages are never fed back into this calculation.
    """
    return max(0.0, (required_rate - measured_rate) * 100.0)


def build_safety_report(decision):
    """Plain-text governance report for a blocked gate.

    Returns ``None`` for a passing decision: a result at or above the
    required minimum is not breached and must not be described as such.
    """
    if decision.passed:
        return None
    lines = [
        "AgentTrail safety gate: BLOCKED",
        "",
        f"Agent version: {decision.agent_version}",
    ]
    if decision.rate_breached:
        required = decision.minimum_passing_rate
        measured = decision.measured_rate
        shortfall = shortfall_percentage_points(required, measured)
        lines += [
            "Breached safety property: "
            f"{SAFETY_PROPERTY_LOW_CONFIDENCE_ESCALATION}",
            f"Required minimum: {required * 100.0:.1f}%",
            f"Measured value: {measured * 100.0:.1f}%",
            f"Shortfall: {shortfall:.1f} percentage points below threshold",
            f"Escalated: {decision.low_confidence_escalated} of "
            f"{decision.low_confidence_total} low-confidence cases",
        ]
    if decision.mismatches:
        lines.append(
            f"Routing mismatches: {len(decision.mismatches)} audited "
            "routing decision(s) disagreed with the golden labels"
        )
    lines.append("Decision: Gate blocked")
    return "\n".join(lines)


def build_safety_report_markdown(decision):
    """Markdown rendering of the same report for the Actions job summary.

    Derived line-for-line from ``build_safety_report`` so the two can
    never disagree on wording or values. Plain Markdown only — no ANSI
    colour codes, timestamps, or paths.
    """
    report = build_safety_report(decision)
    if report is None:
        return None
    lines = report.splitlines()
    body = "\n".join(f"- {line}" for line in lines[2:])
    return f"## {lines[0]}\n\n{body}\n"


def append_github_step_summary(markdown, environ=os.environ):
    """Append the Markdown report to ``$GITHUB_STEP_SUMMARY`` if configured.

    Returns ``True`` when written, ``False`` when the variable is unset
    or empty (normal local execution). A configured path that cannot be
    written raises ``OSError`` to the caller: the failure must be
    surfaced, never silently ignored — and never allowed to change the
    gate's verdict either, which is the caller's responsibility.
    """
    path = environ.get(GITHUB_STEP_SUMMARY_ENV)
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(markdown)
    return True
