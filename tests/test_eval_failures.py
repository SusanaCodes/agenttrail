"""Fail-closed behaviour of the evaluation harness (Ticket 5).

Uses small synthetic datasets with fixtures recorded from the
deterministic fake client in support_fixtures, so routing mismatches and
broken audit trails can be produced deliberately. Nothing here touches
the committed genuine fixture set, and no test writes outside a
temporary directory.

The fake model routes on evidence_status: complete -> decide (0.95),
partial -> escalate (0.85), missing -> escalate (0.60). A synthetic case
is therefore made to mismatch by labelling it against that behaviour.
"""

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import agenttrail.eval as evalmod
from agenttrail.audit import append_audit_record, build_audit_record
from agenttrail.audit_reader import AuditTrailReadError
from agenttrail.eval import EvalError, evaluate
from agenttrail.fixtures import FixtureNotFoundError, FixtureValidationError
from agenttrail.golden import GoldenDatasetError
from support_fixtures import MODEL_ID, no_network, record_temp_fixture_set

DATASET_VERSION = "1.0.0"
REASON_CODES = {
    "complete": "EVIDENCE_COMPLETE_LOW_INCOME",
    "partial": "EVIDENCE_PARTIAL",
    "missing": "EVIDENCE_MISSING",
}


def case(number, age, income, evidence, routing, band):
    return {
        "case_id": f"SYN-{number:03d}",
        "dataset_version": DATASET_VERSION,
        "input": {
            "age_band": age,
            "income_band": income,
            "evidence_status": evidence,
        },
        "expected": {
            "routing": routing,
            "confidence_band": band,
            "reason_code": REASON_CODES[evidence],
        },
    }


# Correctly labelled: the fake model agrees with every label.
def correct_cases():
    return [
        case(1, "18-24", "low", "complete", "decide", "high"),
        case(2, "18-24", "low", "partial", "escalate", "medium"),
        case(3, "18-24", "low", "missing", "escalate", "low"),
        case(4, "25-39", "medium", "missing", "escalate", "low"),
    ]


def build_synthetic(tmp, cases):
    """Write a synthetic dataset and record matching fake fixtures."""
    tmp = Path(tmp)
    dataset_path = tmp / "golden.jsonl"
    with open(dataset_path, "w", encoding="utf-8") as f:
        for record in cases:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    fixture_path = tmp / "fixtures.jsonl"
    record_temp_fixture_set(cases, fixture_path)
    return dataset_path, fixture_path


class SyntheticEvalTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def evaluate_cases(self, cases, **kwargs):
        dataset, fixtures = build_synthetic(self.tmp_path, cases)
        return evaluate(dataset_path=dataset, fixture_path=fixtures, **kwargs)


class TestRoutingMismatches(SyntheticEvalTestCase):
    def test_all_labels_matching_passes(self):
        result = self.evaluate_cases(correct_cases())
        self.assertTrue(result.passed)
        self.assertEqual(result.total_cases, 4)
        self.assertEqual(result.matched_cases, 4)
        self.assertEqual(result.mismatches, ())

    def test_single_mismatch_fails_and_identifies_the_case(self):
        cases = correct_cases()
        # SYN-001 has complete evidence, so the model decides; label it
        # escalate to force exactly one disagreement.
        cases[0]["expected"]["routing"] = "escalate"
        result = self.evaluate_cases(cases)

        self.assertFalse(result.passed)
        self.assertEqual(result.total_cases, 4)
        self.assertEqual(result.matched_cases, 3)
        self.assertEqual(len(result.mismatches), 1)
        mismatch = result.mismatches[0]
        self.assertEqual(mismatch.case_id, "SYN-001")
        self.assertEqual(mismatch.expected, "escalate")
        self.assertEqual(mismatch.actual, "decide")

    def test_mismatch_order_follows_dataset_order(self):
        cases = correct_cases()
        cases.append(case(5, "40-64", "high", "complete", "escalate", "high"))
        cases[0]["expected"]["routing"] = "escalate"

        forward = self.evaluate_cases(cases)
        self.assertEqual(
            [m.case_id for m in forward.mismatches], ["SYN-001", "SYN-005"]
        )

        with tempfile.TemporaryDirectory() as other:
            dataset, fixtures = build_synthetic(Path(other), cases[::-1])
            reverse = evaluate(dataset_path=dataset, fixture_path=fixtures)
        self.assertEqual(
            [m.case_id for m in reverse.mismatches], ["SYN-005", "SYN-001"]
        )
        # Same verdict and counts either way; only ordering follows the file.
        self.assertEqual(forward.passed, reverse.passed)
        self.assertEqual(forward.matched_cases, reverse.matched_cases)


class TestLowConfidenceSubset(SyntheticEvalTestCase):
    def test_rate_numerator_denominator_and_value(self):
        cases = correct_cases()
        result = self.evaluate_cases(cases)
        self.assertEqual(result.low_confidence_total, 2)
        self.assertEqual(result.low_confidence_escalated, 2)
        self.assertEqual(result.low_confidence_escalation_rate, 1.0)

    def test_partial_escalation_rate_is_a_fraction(self):
        # Three low-confidence cases, one of which the model decides.
        cases = [
            case(1, "18-24", "low", "complete", "decide", "low"),
            case(2, "18-24", "low", "missing", "escalate", "low"),
            case(3, "25-39", "low", "missing", "escalate", "low"),
        ]
        result = self.evaluate_cases(cases)
        self.assertEqual(result.low_confidence_total, 3)
        self.assertEqual(result.low_confidence_escalated, 2)
        self.assertAlmostEqual(
            result.low_confidence_escalation_rate, 2 / 3, places=12
        )
        # No minimum-rate gate exists, so routing agreement still passes.
        self.assertTrue(result.passed)

    def test_empty_low_confidence_subset_fails_clearly(self):
        cases = [
            case(1, "18-24", "low", "complete", "decide", "high"),
            case(2, "18-24", "low", "partial", "escalate", "medium"),
        ]
        with self.assertRaises(EvalError) as ctx:
            self.evaluate_cases(cases)
        self.assertIn("low", str(ctx.exception))
        self.assertIn("undefined", str(ctx.exception))


class TestAuditTrailFailsClosed(SyntheticEvalTestCase):
    def evaluate_with_patched_audit(self, wrapper, cases=None):
        cases = cases or correct_cases()
        with mock.patch.object(evalmod, "decide_case_audited", wrapper):
            return self.evaluate_cases(cases)

    def test_missing_record_fails_closed(self):
        real = evalmod.decide_case_audited

        def skip_one(model_input, client, **kwargs):
            if kwargs["case_ref"] == "SYN-003":
                return {"decision": "escalate", "confidence": 0.6,
                        "rationale": "skipped"}
            return real(model_input, client, **kwargs)

        with self.assertRaises(AuditTrailReadError) as ctx:
            self.evaluate_with_patched_audit(skip_one)
        self.assertIn("missing audit records", str(ctx.exception))
        self.assertIn("SYN-003", str(ctx.exception))

    def test_duplicate_record_fails_closed(self):
        real = evalmod.decide_case_audited

        def double_write(model_input, client, **kwargs):
            result = real(model_input, client, **kwargs)
            if kwargs["case_ref"] == "SYN-002":
                append_audit_record(
                    kwargs["audit_path"],
                    build_audit_record(
                        kwargs["case_ref"], model_input, result,
                        kwargs["model_id"],
                    ),
                )
            return result

        with self.assertRaises(AuditTrailReadError) as ctx:
            self.evaluate_with_patched_audit(double_write)
        self.assertIn("duplicate audit record", str(ctx.exception))
        self.assertIn("SYN-002", str(ctx.exception))

    def test_unexpected_case_reference_fails_closed(self):
        real = evalmod.decide_case_audited

        def extra_case(model_input, client, **kwargs):
            result = real(model_input, client, **kwargs)
            if kwargs["case_ref"] == "SYN-001":
                append_audit_record(
                    kwargs["audit_path"],
                    build_audit_record(
                        "SYN-999", model_input, result, kwargs["model_id"]
                    ),
                )
            return result

        with self.assertRaises(AuditTrailReadError) as ctx:
            self.evaluate_with_patched_audit(extra_case)
        self.assertIn("unexpected audit record", str(ctx.exception))
        self.assertIn("SYN-999", str(ctx.exception))

    def test_malformed_record_fails_closed(self):
        real = evalmod.decide_case_audited

        def corrupt(model_input, client, **kwargs):
            result = real(model_input, client, **kwargs)
            if kwargs["case_ref"] == "SYN-002":
                with open(kwargs["audit_path"], "a", encoding="utf-8") as f:
                    f.write("{not valid json\n")
            return result

        with self.assertRaises(AuditTrailReadError) as ctx:
            self.evaluate_with_patched_audit(corrupt)
        self.assertIn("malformed audit record", str(ctx.exception))

    def test_record_failing_audit_validation_fails_closed(self):
        real = evalmod.decide_case_audited

        def tamper(model_input, client, **kwargs):
            result = real(model_input, client, **kwargs)
            if kwargs["case_ref"] == "SYN-002":
                record = build_audit_record(
                    "SYN-004", model_input, result, kwargs["model_id"]
                )
                record["decision"] = "approve"
                with open(kwargs["audit_path"], "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, sort_keys=True) + "\n")
            return result

        with self.assertRaises(AuditTrailReadError) as ctx:
            self.evaluate_with_patched_audit(tamper)
        self.assertIn("invalid audit record", str(ctx.exception))

    def test_existing_trail_is_never_appended_to(self):
        dataset, fixtures = build_synthetic(self.tmp_path, correct_cases())
        trail = self.tmp_path / "existing.audit.jsonl"
        trail.write_text("pre-existing content\n", encoding="utf-8")
        with self.assertRaises(EvalError) as ctx:
            evaluate(
                dataset_path=dataset, fixture_path=fixtures, audit_path=trail
            )
        self.assertIn("already exists", str(ctx.exception))
        # The user's trail is left byte-for-byte intact.
        self.assertEqual(
            trail.read_text(encoding="utf-8"), "pre-existing content\n"
        )

    def test_evaluation_trail_is_removed_when_temporary(self):
        before = set(Path(tempfile.gettempdir()).glob("agenttrail-eval-*"))
        self.evaluate_cases(correct_cases())
        after = set(Path(tempfile.gettempdir()).glob("agenttrail-eval-*"))
        self.assertEqual(after - before, set())


class TestFixturesFailClosed(SyntheticEvalTestCase):
    def test_missing_fixture_file_fails_without_network(self):
        dataset, _ = build_synthetic(self.tmp_path, correct_cases())
        absent = self.tmp_path / "absent.jsonl"
        with no_network():
            with self.assertRaises(FixtureValidationError) as ctx:
                evaluate(dataset_path=dataset, fixture_path=absent)
        self.assertIn("fixture file not found", str(ctx.exception))

    def test_uncovered_case_raises_fixture_not_found_without_network(self):
        cases = correct_cases()
        dataset, fixtures = build_synthetic(self.tmp_path, cases)
        # A case the fixture set never recorded: same file, extra line.
        extra = case(9, "65-plus", "high", "partial", "escalate", "medium")
        with open(dataset, "a", encoding="utf-8") as f:
            f.write(json.dumps(extra, sort_keys=True) + "\n")
        with no_network():
            with self.assertRaises(FixtureNotFoundError) as ctx:
                evaluate(dataset_path=dataset, fixture_path=fixtures)
        self.assertIn("no recorded fixture", str(ctx.exception))

    def test_model_id_is_derived_from_the_fixture_set(self):
        dataset, fixtures = build_synthetic(self.tmp_path, correct_cases())
        trail = self.tmp_path / "derived.audit.jsonl"
        evaluate(
            dataset_path=dataset, fixture_path=fixtures, audit_path=trail
        )
        model_ids = {
            json.loads(line)["model_id"]
            for line in trail.read_text(encoding="utf-8").splitlines()
        }
        self.assertEqual(model_ids, {MODEL_ID})


class TestDatasetFailsClosed(SyntheticEvalTestCase):
    def evaluate_dataset_text(self, text):
        dataset = self.tmp_path / "bad.jsonl"
        dataset.write_text(text, encoding="utf-8")
        _, fixtures = build_synthetic(self.tmp_path, correct_cases())
        return evaluate(dataset_path=dataset, fixture_path=fixtures)

    def test_malformed_dataset_line_fails_closed(self):
        with self.assertRaises(GoldenDatasetError) as ctx:
            self.evaluate_dataset_text("{not json\n")
        self.assertIn("malformed JSON", str(ctx.exception))

    def test_duplicate_case_id_fails_closed(self):
        duplicated = correct_cases()[:1] * 2
        text = "".join(json.dumps(c, sort_keys=True) + "\n" for c in duplicated)
        with self.assertRaises(GoldenDatasetError) as ctx:
            self.evaluate_dataset_text(text)
        self.assertIn("duplicate case_id", str(ctx.exception))

    def test_extra_input_field_is_rejected_before_any_replay(self):
        bad = correct_cases()[0]
        bad["input"]["expected_routing"] = "decide"
        with self.assertRaises(GoldenDatasetError) as ctx:
            self.evaluate_dataset_text(json.dumps(bad) + "\n")
        self.assertIn("invalid case input", str(ctx.exception))

    def test_missing_dataset_file_fails_closed(self):
        _, fixtures = build_synthetic(self.tmp_path, correct_cases())
        with self.assertRaises(GoldenDatasetError) as ctx:
            evaluate(
                dataset_path=self.tmp_path / "nope.jsonl",
                fixture_path=fixtures,
            )
        self.assertIn("golden dataset not found", str(ctx.exception))

    def test_unknown_routing_label_fails_closed(self):
        bad = correct_cases()[0]
        bad["expected"]["routing"] = "maybe"
        with self.assertRaises(GoldenDatasetError) as ctx:
            self.evaluate_dataset_text(json.dumps(bad) + "\n")
        self.assertIn("expected.routing", str(ctx.exception))


class TestCliExitCodes(SyntheticEvalTestCase):
    def run_cli(self, argv):
        stdout, stderr = StringIO(), StringIO()
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(sys, "stderr", stderr):
            code = evalmod.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def cli_args(self, cases):
        dataset, fixtures = build_synthetic(self.tmp_path, cases)
        return ["--dataset", str(dataset), "--fixtures", str(fixtures)]

    def test_passing_evaluation_exits_zero(self):
        code, out, _ = self.run_cli(self.cli_args(correct_cases()))
        self.assertEqual(code, 0)
        self.assertIn("PASS", out)

    def test_routing_mismatch_exits_one_and_prints_fail(self):
        cases = correct_cases()
        cases[0]["expected"]["routing"] = "escalate"
        code, out, _ = self.run_cli(self.cli_args(cases))
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)
        self.assertIn("mismatch: SYN-001 expected=escalate audited=decide", out)

    def test_evaluation_error_exits_two(self):
        args = self.cli_args(correct_cases())
        args[args.index("--fixtures") + 1] = str(self.tmp_path / "gone.jsonl")
        with no_network():
            code, out, err = self.run_cli(args)
        self.assertEqual(code, 2)
        self.assertIn("evaluation error", err)
        self.assertNotIn("PASS", out)


if __name__ == "__main__":
    unittest.main()
