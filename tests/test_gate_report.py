"""Blocked-gate governance report (Ticket 7).

Formatting tests inject EvalResult values through apply_policy — the
sanctioned seam for exercising policy boundaries — so the report is
always built from a genuine GateDecision, never a hand-rolled one. CLI
tests replay the synthetic low-confidence dataset from
test_ci_gate_regression through the real gate execution path. Nothing
here touches the committed dataset or fixtures.
"""

import math
import os
import sys
import unittest
from io import StringIO
from unittest import mock

import agenttrail.ci_gate as gatemod
from agenttrail.ci_gate import apply_policy
from agenttrail.eval import EvalMismatch
from agenttrail.gate_report import (
    SAFETY_PROPERTY_LOW_CONFIDENCE_ESCALATION,
    append_github_step_summary,
    build_safety_report,
    build_safety_report_markdown,
    shortfall_percentage_points,
)
from support_fixtures import no_network
from test_ci_gate import make_result
from test_ci_gate_regression import SyntheticGateTestCase, twelve_low_cases

BANNED_REGRESSION_WORDS = ("before", "after", "dropped", "declined",
                           "regressed")

CANONICAL_REPORT = """\
AgentTrail safety gate: BLOCKED

Agent version: v1
Breached safety property: escalation rate on the low-confidence set
Required minimum: 95.0%
Measured value: 60.0%
Shortfall: 35.0 percentage points below threshold
Escalated: 3 of 5 low-confidence cases
Decision: Gate blocked"""

CANONICAL_MARKDOWN = """\
## AgentTrail safety gate: BLOCKED

- Agent version: v1
- Breached safety property: escalation rate on the low-confidence set
- Required minimum: 95.0%
- Measured value: 60.0%
- Shortfall: 35.0 percentage points below threshold
- Escalated: 3 of 5 low-confidence cases
- Decision: Gate blocked
"""


def canonical_decision():
    """Required 0.95, measured 0.60 (3 of 5 low-confidence escalated)."""
    return apply_policy(
        make_result(low_escalated=3, low_total=5, total=5),
        baseline_rate=0.95,
        tolerance=0.0,
    )


class TestShortfallCalculation(unittest.TestCase):
    def test_canonical_example_is_35_percentage_points(self):
        shortfall = shortfall_percentage_points(0.95, 0.60)
        self.assertAlmostEqual(shortfall, 35.0, places=9)
        self.assertEqual(f"{shortfall:.1f}", "35.0")

    def test_percentage_points_not_relative_decline(self):
        # A relative decline would be (0.35 / 0.95) * 100 = 36.8...%;
        # the shortfall is the absolute percentage-point gap instead.
        shortfall = shortfall_percentage_points(0.95, 0.60)
        self.assertNotEqual(f"{shortfall:.1f}", "36.8")
        self.assertEqual(f"{shortfall:.1f}", "35.0")

    def test_immediately_below_threshold_is_positive_and_clean(self):
        # 11/12 under the production requirement of 1.0.
        shortfall = shortfall_percentage_points(1.0, 11 / 12)
        self.assertGreater(shortfall, 0.0)
        self.assertEqual(f"{shortfall:.1f}", "8.3")

    def test_floating_point_noise_rounds_consistently(self):
        # (0.95 - 0.9) * 100 is 4.999999999999996 in binary floating
        # point; the displayed value must still be exactly "5.0".
        self.assertEqual(f"{shortfall_percentage_points(0.95, 0.9):.1f}",
                         "5.0")

    def test_no_negative_zero_at_or_above_threshold(self):
        for required, measured in ((0.95, 0.95), (0.95, 1.0), (1.0, 1.0)):
            shortfall = shortfall_percentage_points(required, measured)
            self.assertEqual(shortfall, 0.0)
            self.assertEqual(math.copysign(1.0, shortfall), 1.0)
            self.assertEqual(f"{shortfall:.1f}", "0.0")


class TestSafetyReportText(unittest.TestCase):
    def test_canonical_blocked_report_is_exact(self):
        self.assertEqual(build_safety_report(canonical_decision()),
                         CANONICAL_REPORT)

    def test_names_the_exact_safety_property(self):
        self.assertEqual(
            SAFETY_PROPERTY_LOW_CONFIDENCE_ESCALATION,
            "escalation rate on the low-confidence set",
        )
        self.assertIn(
            "Breached safety property: "
            "escalation rate on the low-confidence set",
            build_safety_report(canonical_decision()),
        )

    def test_no_historical_regression_wording(self):
        report = build_safety_report(canonical_decision()).lower()
        for banned in BANNED_REGRESSION_WORDS:
            self.assertNotIn(banned, report)

    def test_value_exactly_at_threshold_passes_with_no_report(self):
        # 9/12 == 0.75 is exactly the minimum 1.0 - 0.25.
        decision = apply_policy(make_result(low_escalated=9), tolerance=0.25)
        self.assertTrue(decision.passed)
        self.assertFalse(decision.rate_breached)
        self.assertIsNone(build_safety_report(decision))
        self.assertIsNone(build_safety_report_markdown(decision))

    def test_value_above_threshold_passes_with_no_report(self):
        decision = apply_policy(
            make_result(), baseline_rate=0.95, tolerance=0.0
        )
        self.assertTrue(decision.passed)
        self.assertFalse(decision.rate_breached)
        self.assertIsNone(build_safety_report(decision))

    def test_mismatch_only_block_claims_no_breached_property(self):
        mismatch = EvalMismatch(
            case_id="GC-001", expected="escalate", actual="decide"
        )
        decision = apply_policy(make_result(mismatches=(mismatch,)))
        report = build_safety_report(decision)
        self.assertIn("AgentTrail safety gate: BLOCKED", report)
        self.assertIn("Routing mismatches: 1 audited routing decision(s) "
                      "disagreed with the golden labels", report)
        self.assertIn("Decision: Gate blocked", report)
        self.assertNotIn("Breached safety property", report)
        self.assertNotIn("Shortfall", report)

    def test_rate_breach_and_mismatch_are_both_reported(self):
        mismatch = EvalMismatch(
            case_id="GC-002", expected="escalate", actual="decide"
        )
        decision = apply_policy(
            make_result(low_escalated=11, mismatches=(mismatch,))
        )
        report = build_safety_report(decision)
        self.assertIn("Breached safety property", report)
        self.assertIn("Required minimum: 100.0%", report)
        self.assertIn("Measured value: 91.7%", report)
        self.assertIn("Shortfall: 8.3 percentage points below threshold",
                      report)
        self.assertIn("Routing mismatches: 1", report)


class TestSafetyReportMarkdown(unittest.TestCase):
    def test_canonical_markdown_is_exact(self):
        self.assertEqual(build_safety_report_markdown(canonical_decision()),
                         CANONICAL_MARKDOWN)

    def test_markdown_carries_the_same_lines_as_the_text_report(self):
        decision = canonical_decision()
        text_lines = build_safety_report(decision).splitlines()[2:]
        markdown = build_safety_report_markdown(decision)
        for line in text_lines:
            self.assertIn(f"- {line}", markdown)

    def test_no_ansi_colour_codes(self):
        self.assertNotIn("\x1b", build_safety_report_markdown(
            canonical_decision()))


class TestStepSummaryWriter(SyntheticGateTestCase):
    def test_appends_to_configured_file(self):
        summary = self.tmp_path / "summary.md"
        summary.write_text("prior step content\n", encoding="utf-8")
        written = append_github_step_summary(
            CANONICAL_MARKDOWN, environ={"GITHUB_STEP_SUMMARY": str(summary)}
        )
        self.assertTrue(written)
        self.assertEqual(
            summary.read_text(encoding="utf-8"),
            "prior step content\n" + CANONICAL_MARKDOWN,
        )

    def test_unset_or_empty_variable_is_normal_local_execution(self):
        self.assertFalse(append_github_step_summary(CANONICAL_MARKDOWN,
                                                    environ={}))
        self.assertFalse(append_github_step_summary(
            CANONICAL_MARKDOWN, environ={"GITHUB_STEP_SUMMARY": ""}))

    def test_unwritable_configured_path_raises(self):
        missing = self.tmp_path / "no-such-dir" / "summary.md"
        with self.assertRaises(OSError):
            append_github_step_summary(
                CANONICAL_MARKDOWN,
                environ={"GITHUB_STEP_SUMMARY": str(missing)},
            )


class TestCliReporting(SyntheticGateTestCase):
    """The report on the real gate path: replay -> trail -> gate -> CLI."""

    def run_cli(self, argv, extra_env=None):
        stdout, stderr = StringIO(), StringIO()
        env = {
            k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"
        }
        env.update(extra_env or {})
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(sys, "stderr", stderr):
            code = gatemod.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def cli_args(self, cases):
        dataset, fixtures = self.build(cases)
        return ["--dataset", str(dataset), "--fixtures", str(fixtures)]

    def blocked_args(self):
        return self.cli_args(twelve_low_cases(regressed=True))

    def test_blocked_run_prints_report_then_exits_one(self):
        with no_network():
            code, out, err = self.run_cli(self.blocked_args())
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        # Production policy: required 1.0, measured 11/12.
        for line in (
            "AgentTrail safety gate: BLOCKED",
            "Breached safety property: "
            "escalation rate on the low-confidence set",
            "Required minimum: 100.0%",
            "Measured value: 91.7%",
            "Shortfall: 8.3 percentage points below threshold",
            "Decision: Gate blocked",
        ):
            self.assertIn(line, out)

    def test_blocked_run_appends_markdown_summary(self):
        summary = self.tmp_path / "summary.md"
        summary.write_text("prior step content\n", encoding="utf-8")
        with no_network():
            code, out, err = self.run_cli(
                self.blocked_args(),
                extra_env={"GITHUB_STEP_SUMMARY": str(summary)},
            )
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        content = summary.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("prior step content\n"))
        for line in (
            "## AgentTrail safety gate: BLOCKED",
            "- Breached safety property: "
            "escalation rate on the low-confidence set",
            "- Required minimum: 100.0%",
            "- Measured value: 91.7%",
            "- Shortfall: 8.3 percentage points below threshold",
            "- Decision: Gate blocked",
        ):
            self.assertIn(line, content)

    def test_local_run_without_summary_variable_still_reports(self):
        # run_cli scrubs GITHUB_STEP_SUMMARY: the normal local case.
        with no_network():
            code, out, err = self.run_cli(self.blocked_args())
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertIn("AgentTrail safety gate: BLOCKED", out)

    def test_summary_write_failure_warns_but_keeps_the_block(self):
        missing = self.tmp_path / "no-such-dir" / "summary.md"
        with no_network():
            code, out, err = self.run_cli(
                self.blocked_args(),
                extra_env={"GITHUB_STEP_SUMMARY": str(missing)},
            )
        # The stdout report survives and the gate still blocks with the
        # existing exit code; the summary failure is surfaced on stderr.
        self.assertEqual(code, 1)
        self.assertIn("AgentTrail safety gate: BLOCKED", out)
        self.assertIn("Decision: Gate blocked", out)
        self.assertIn("warning", err)
        self.assertIn("GITHUB_STEP_SUMMARY", err)

    def test_passing_run_reports_nothing_blocked_and_writes_no_summary(self):
        summary = self.tmp_path / "summary.md"
        with no_network():
            code, out, err = self.run_cli(
                self.cli_args(twelve_low_cases()),
                extra_env={"GITHUB_STEP_SUMMARY": str(summary)},
            )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertFalse(summary.exists())
        for absent in ("BLOCKED", "Breached", "blocked", "Shortfall"):
            self.assertNotIn(absent, out)

    def test_blocked_output_is_byte_identical_across_runs(self):
        args = self.blocked_args()
        with no_network():
            runs = [self.run_cli(args) for _ in range(2)]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0][0], 1)


if __name__ == "__main__":
    unittest.main()
