"""Behavioural regression coverage for the CI gate (Ticket 6).

Builds a synthetic 12-case low-confidence dataset around the
deterministic fake model from support_fixtures (complete -> decide,
partial/missing -> escalate), so a genuinely changed low-confidence
verdict flows through the real path — fixture replay -> audited
decision -> persisted trail -> EvalResult -> gate — and blocks it.
Nothing here touches the committed dataset or fixtures; all test data
lives in temporary directories with automatic cleanup.

Dataset-building helpers are shared with tests/test_eval_failures.py.
"""

import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import agenttrail.ci_gate as gatemod
from agenttrail.ci_gate import apply_policy
from agenttrail.eval import evaluate
from support_fixtures import no_network
from test_eval_failures import build_synthetic, case, correct_cases

AGE_BANDS = ("18-24", "25-39", "40-64", "65-plus")
INCOME_BANDS = ("low", "medium", "high")


def twelve_low_cases(regressed=False):
    """Twelve distinct-input low-confidence cases, all expected to escalate.

    With ``regressed=True`` the first case's evidence becomes complete,
    which the fake model decides on with high confidence. Its label is
    routing=decide so the evaluation itself stays mismatch-free — the
    only signal left is the audited escalation rate dropping to 11/12,
    which is exactly what the gate must catch.
    """
    combos = [(age, income) for age in AGE_BANDS for income in INCOME_BANDS]
    cases = [
        case(n, age, income, "missing", "escalate", "low")
        for n, (age, income) in enumerate(combos, start=1)
    ]
    if regressed:
        cases[0] = case(1, "18-24", "low", "complete", "decide", "low")
    return cases


class SyntheticGateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def build(self, cases):
        return build_synthetic(self.tmp_path, cases)


class TestBehaviouralRegression(SyntheticGateTestCase):
    def test_healthy_low_confidence_dataset_passes_the_gate(self):
        dataset, fixtures = self.build(twelve_low_cases())
        with no_network():
            result = evaluate(dataset_path=dataset, fixture_path=fixtures)
        decision = apply_policy(result)
        self.assertTrue(decision.passed)
        self.assertEqual(decision.low_confidence_escalated, 12)
        self.assertEqual(decision.measured_rate, 1.0)

    def test_changed_verdict_reaches_the_trail_and_blocks_the_gate(self):
        dataset, fixtures = self.build(twelve_low_cases(regressed=True))
        trail = self.tmp_path / "gate.audit.jsonl"
        with no_network():
            result = evaluate(
                dataset_path=dataset, fixture_path=fixtures, audit_path=trail
            )

        # The changed verdict genuinely reached the persisted trail.
        records = {
            r["case_ref"]: r["decision"]
            for r in map(
                json.loads, trail.read_text(encoding="utf-8").splitlines()
            )
        }
        self.assertEqual(records["SYN-001"], "decide")
        self.assertEqual(
            sum(1 for d in records.values() if d == "escalate"), 11
        )

        # It lowered the measured rate without any routing mismatch...
        self.assertTrue(result.passed)
        self.assertEqual(result.low_confidence_escalated, 11)
        self.assertEqual(result.low_confidence_total, 12)
        self.assertAlmostEqual(
            result.low_confidence_escalation_rate, 11 / 12, places=12
        )

        # ...and the gate is the control that turns that into a block.
        decision = apply_policy(result)
        self.assertFalse(decision.passed)
        self.assertAlmostEqual(decision.regression, 1 / 12, places=12)
        self.assertIn("11/12", decision.failure_reasons[0])

    def test_routing_mismatch_blocks_even_when_every_low_case_escalates(self):
        cases = twelve_low_cases()
        # Complete evidence makes the fake model decide; labelling it
        # escalate/high creates a mismatch outside the low subset.
        cases.append(case(13, "18-24", "low", "complete", "escalate", "high"))
        dataset, fixtures = self.build(cases)
        with no_network():
            result = evaluate(dataset_path=dataset, fixture_path=fixtures)
        self.assertEqual(result.low_confidence_escalation_rate, 1.0)
        decision = apply_policy(result)
        self.assertFalse(decision.passed)
        self.assertEqual(len(decision.mismatches), 1)
        self.assertEqual(decision.mismatches[0].case_id, "SYN-013")


class TestCliRegression(SyntheticGateTestCase):
    def run_cli(self, argv):
        stdout, stderr = StringIO(), StringIO()
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(sys, "stderr", stderr):
            code = gatemod.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def cli_args(self, cases):
        dataset, fixtures = self.build(cases)
        return ["--dataset", str(dataset), "--fixtures", str(fixtures)]

    def test_regression_exits_one_with_before_and_after_numbers(self):
        with no_network():
            code, out, err = self.run_cli(
                self.cli_args(twelve_low_cases(regressed=True))
            )
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertTrue(out.startswith("CI GATE: FAIL\n"))
        for line in (
            "baseline_rate=1.0000", "measured_rate=0.9167",
            "regression=0.0833", "tolerance=0.0000",
            "low_confidence_escalated=11", "low_confidence_total=12",
        ):
            self.assertIn(line, out)

    def test_failing_output_is_byte_identical_across_runs(self):
        args = self.cli_args(twelve_low_cases(regressed=True))
        with no_network():
            runs = [self.run_cli(args) for _ in range(2)]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0][0], 1)

    def test_mismatch_is_reported_and_exits_one(self):
        cases = twelve_low_cases()
        cases.append(case(13, "18-24", "low", "complete", "escalate", "high"))
        with no_network():
            code, out, _ = self.run_cli(self.cli_args(cases))
        self.assertEqual(code, 1)
        self.assertIn(
            "mismatch: SYN-013 expected=escalate audited=decide", out
        )

    def test_empty_low_confidence_subset_exits_two(self):
        # Only high/medium-band cases: the rate is undefined, not 0 or 1.
        with no_network():
            code, out, err = self.run_cli(self.cli_args(correct_cases()[:2]))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("gate error", err)
        self.assertIn("undefined", err)

    def test_environment_variables_cannot_weaken_the_gate(self):
        args = self.cli_args(twelve_low_cases(regressed=True))
        permissive = {
            "AGENTTRAIL_BASELINE_RATE": "0.0",
            "AGENTTRAIL_TOLERANCE": "1.0",
            "CI_GATE_MINIMUM_PASSING_RATE": "0.0",
        }
        with mock.patch.dict(os.environ, permissive), no_network():
            code, out, _ = self.run_cli(args)
        self.assertEqual(code, 1)
        self.assertIn("CI GATE: FAIL", out)


if __name__ == "__main__":
    unittest.main()
