"""CI-gate policy and CLI behaviour (Ticket 6).

Pure-policy tests inject EvalResult values straight into apply_policy,
which is the sanctioned seam for exercising boundaries. The committed-
baseline and CLI tests run the full golden-dataset replay offline with
sockets patched to fail. Behavioural-regression coverage — a changed
low-confidence verdict flowing through the audit trail and blocking the
gate — lives in tests/test_ci_gate_regression.py.
"""

import dataclasses
import math
import os
import sys
import unittest
from io import StringIO
from unittest import mock

import agenttrail.ci_gate as gatemod
from agenttrail.ci_gate import (
    BASELINE_LOW_CONFIDENCE_ESCALATION_RATE,
    MAX_PERMITTED_REGRESSION,
    GatePolicyError,
    apply_policy,
    format_gate_report,
)
from agenttrail.eval import EvalMismatch, EvalResult, evaluate
from agenttrail.fixtures import DEFAULT_FIXTURE_PATH
from support_fixtures import no_aws_credentials, no_network

FIXTURES_RECORDED = DEFAULT_FIXTURE_PATH.is_file()
SKIP_REASON = (
    f"{DEFAULT_FIXTURE_PATH} not recorded yet — genuine Bedrock fixtures "
    "require the explicit approved run of "
    "python3 -m agenttrail.record_fixtures"
)


def make_result(low_escalated=12, low_total=12, mismatches=(), total=36):
    """A consistent EvalResult with the given low-confidence outcome."""
    return EvalResult(
        passed=not mismatches,
        total_cases=total,
        matched_cases=total - len(mismatches),
        mismatches=tuple(mismatches),
        low_confidence_total=low_total,
        low_confidence_escalated=low_escalated,
        low_confidence_escalation_rate=low_escalated / low_total,
    )


class TestProductionPolicyValues(unittest.TestCase):
    def test_policy_constants_match_the_versioned_policy(self):
        self.assertEqual(BASELINE_LOW_CONFIDENCE_ESCALATION_RATE, 1.0)
        self.assertEqual(MAX_PERMITTED_REGRESSION, 0.0)

    def test_cli_offers_no_threshold_override(self):
        for flag in ("--baseline-rate=0.0", "--tolerance=1.0",
                     "--minimum-passing-rate=0.0"):
            with self.assertRaises(SystemExit):
                with mock.patch.object(sys, "stderr", StringIO()):
                    gatemod.main([flag])


class TestPurePolicy(unittest.TestCase):
    def test_perfect_result_passes(self):
        decision = apply_policy(make_result())
        self.assertTrue(decision.passed)
        self.assertEqual(decision.measured_rate, 1.0)
        self.assertEqual(decision.regression, 0.0)
        self.assertEqual(decision.failure_reasons, ())

    def test_one_of_twelve_missing_fails_under_production_policy(self):
        decision = apply_policy(make_result(low_escalated=11))
        self.assertFalse(decision.passed)
        self.assertAlmostEqual(decision.measured_rate, 0.9167, places=4)
        self.assertAlmostEqual(decision.regression, 1 / 12, places=12)
        self.assertIn("11/12", decision.failure_reasons[0])

    def test_rate_exactly_at_the_boundary_passes(self):
        # 9/12 == 0.75 is exactly the minimum 1.0 - 0.25.
        decision = apply_policy(
            make_result(low_escalated=9), tolerance=0.25
        )
        self.assertTrue(decision.passed)
        self.assertEqual(decision.measured_rate, 0.75)

    def test_rate_below_the_boundary_fails(self):
        decision = apply_policy(
            make_result(low_escalated=8), tolerance=0.25
        )
        self.assertFalse(decision.passed)
        self.assertIn("regressed", decision.failure_reasons[0])

    def test_mismatch_fails_even_with_perfect_rate(self):
        mismatch = EvalMismatch(
            case_id="GC-001", expected="escalate", actual="decide"
        )
        decision = apply_policy(make_result(mismatches=(mismatch,)))
        self.assertFalse(decision.passed)
        self.assertEqual(decision.measured_rate, 1.0)
        self.assertIn("disagreed", decision.failure_reasons[0])
        self.assertEqual(decision.mismatches, (mismatch,))

    def test_empty_low_confidence_subset_fails_closed(self):
        result = dataclasses.replace(
            make_result(),
            low_confidence_total=0,
            low_confidence_escalated=0,
            low_confidence_escalation_rate=0.0,
        )
        with self.assertRaises(GatePolicyError) as ctx:
            apply_policy(result)
        self.assertIn("empty", str(ctx.exception))

    def test_inconsistent_counts_fail_closed(self):
        bad_results = [
            dataclasses.replace(make_result(), low_confidence_escalated=13),
            dataclasses.replace(make_result(), low_confidence_escalated=-1),
            dataclasses.replace(make_result(), low_confidence_total=40),
            dataclasses.replace(make_result(), matched_cases=35),
            dataclasses.replace(make_result(), total_cases=0),
            dataclasses.replace(make_result(), low_confidence_escalated="12"),
        ]
        for result in bad_results:
            with self.assertRaises(GatePolicyError):
                apply_policy(result)

    def test_rate_disagreeing_with_counts_fails_closed(self):
        result = dataclasses.replace(
            make_result(low_escalated=11), low_confidence_escalation_rate=1.0
        )
        with self.assertRaises(GatePolicyError) as ctx:
            apply_policy(result)
        self.assertIn("disagrees with counts", str(ctx.exception))

    def test_non_finite_rates_fail_closed(self):
        for bad in (math.nan, math.inf, -math.inf):
            result = dataclasses.replace(
                make_result(), low_confidence_escalation_rate=bad
            )
            with self.assertRaises(GatePolicyError):
                apply_policy(result)

    def test_invalid_policy_values_fail_closed(self):
        for baseline, tolerance in (
            (math.nan, 0.0), (1.5, 0.0), (-0.1, 0.0),
            (1.0, -0.1), (1.0, 1.5), (0.5, 0.6), (1.0, math.nan),
        ):
            with self.assertRaises(GatePolicyError):
                apply_policy(
                    make_result(), baseline_rate=baseline, tolerance=tolerance
                )

    def test_passed_flag_disagreeing_with_mismatches_fails_closed(self):
        mismatch = EvalMismatch(
            case_id="GC-001", expected="escalate", actual="decide"
        )
        lying = dataclasses.replace(
            make_result(mismatches=(mismatch,), total=36),
            passed=True,
        )
        with self.assertRaises(GatePolicyError):
            apply_policy(lying)

    def test_decision_is_immutable(self):
        decision = apply_policy(make_result())
        with self.assertRaises(Exception):
            decision.passed = False

    def test_report_contains_every_required_field(self):
        report = format_gate_report(apply_policy(make_result()))
        self.assertEqual(report.splitlines()[0], "CI GATE: PASS")
        for line in (
            "baseline_rate=1.0000", "measured_rate=1.0000",
            "regression=0.0000", "tolerance=0.0000",
            "low_confidence_escalated=12", "low_confidence_total=12",
        ):
            self.assertIn(line, report)


@unittest.skipUnless(FIXTURES_RECORDED, SKIP_REASON)
class TestGateOnCommittedBaseline(unittest.TestCase):
    def test_current_baseline_passes_offline(self):
        with no_aws_credentials(os.environ), no_network():
            decision = apply_policy(evaluate())
        self.assertTrue(decision.passed)
        self.assertEqual(decision.measured_rate, 1.0)
        self.assertEqual(decision.low_confidence_escalated, 12)
        self.assertEqual(decision.low_confidence_total, 12)
        self.assertEqual(decision.regression, 0.0)


@unittest.skipUnless(FIXTURES_RECORDED, SKIP_REASON)
class TestCli(unittest.TestCase):
    def run_cli(self, argv):
        stdout, stderr = StringIO(), StringIO()
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(sys, "stderr", stderr):
            code = gatemod.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_success_exits_zero_without_credentials_or_network(self):
        with no_aws_credentials(os.environ), no_network():
            code, out, err = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertTrue(out.startswith("CI GATE: PASS\n"))
        self.assertIn("measured_rate=1.0000", out)
        self.assertIn("low_confidence_escalated=12", out)

    def test_output_is_byte_identical_across_runs(self):
        runs = [self.run_cli([]) for _ in range(3)]
        self.assertEqual(len({out for _, out, _ in runs}), 1)
        self.assertEqual({code for code, _, _ in runs}, {0})

    def test_missing_fixture_file_exits_two(self):
        with no_network():
            code, out, err = self.run_cli(
                ["--fixtures", "/nonexistent/fixtures.jsonl"]
            )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("gate error", err)


if __name__ == "__main__":
    unittest.main()
