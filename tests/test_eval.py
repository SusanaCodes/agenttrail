"""Behavioural evaluation over the real golden dataset (Ticket 5).

Exercises the whole boundary — golden dataset -> fixture replay ->
audited decision -> persisted trail -> verdict — against the committed
genuine fixture set, offline and without AWS credentials.

Failure paths (missing/duplicate/malformed records, fixture misses,
empty low-confidence subsets) live in tests/test_eval_failures.py.
"""

import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from io import StringIO
from pathlib import Path
from unittest import mock

import agenttrail.eval as evalmod
from agenttrail.eval import EvalResult, evaluate, format_report
from agenttrail.fixtures import DEFAULT_FIXTURE_PATH, ReplayBedrockClient
from agenttrail.golden import (
    DEFAULT_DATASET_PATH,
    LOW_CONFIDENCE_BAND,
    load_labelled_cases,
)
from support_fixtures import no_aws_credentials, no_network

FIXTURES_RECORDED = DEFAULT_FIXTURE_PATH.is_file()
SKIP_REASON = (
    f"{DEFAULT_FIXTURE_PATH} not recorded yet — genuine Bedrock fixtures "
    "require the explicit approved run of "
    "python3 -m agenttrail.record_fixtures"
)

# Evaluation-only vocabulary that must never reach the model.
LABEL_MARKERS = ("expected", "routing", "confidence_band", "reason_code",
                 "EVIDENCE_COMPLETE", "EVIDENCE_PARTIAL", "EVIDENCE_MISSING")


def trail_lines(path):
    """Read a persisted audit trail without leaving the file open."""
    return Path(path).read_text(encoding="utf-8").splitlines()


def dataset_expectations():
    """Read the golden labels independently of the evaluation module."""
    total = low_total = 0
    with open(DEFAULT_DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            total += 1
            if record["expected"]["confidence_band"] == LOW_CONFIDENCE_BAND:
                low_total += 1
    return total, low_total


class CapturingReplayClient:
    """Records every Converse request while replaying it for real."""

    def __init__(self, fixture_path):
        self._inner = ReplayBedrockClient(fixture_path)
        self.requests = []

    def converse(self, **request):
        self.requests.append(deepcopy(request))
        return self._inner.converse(**request)


@unittest.skipUnless(FIXTURES_RECORDED, SKIP_REASON)
class TestGoldenEvaluation(unittest.TestCase):
    def test_full_dataset_passes_offline_without_credentials(self):
        total, low_total = dataset_expectations()
        with no_aws_credentials(os.environ), no_network():
            result = evaluate()
        self.assertTrue(result.passed)
        self.assertEqual(result.total_cases, total)
        self.assertEqual(result.matched_cases, total)
        self.assertEqual(result.mismatches, ())
        self.assertEqual(result.low_confidence_total, low_total)

    def test_replay_path_never_imports_boto3(self):
        with no_network():
            evaluate()
        self.assertNotIn("boto3", sys.modules)

    def test_low_confidence_rate_is_numerically_correct(self):
        _, low_total = dataset_expectations()
        result = evaluate()
        self.assertEqual(result.low_confidence_total, low_total)
        self.assertLessEqual(result.low_confidence_escalated, low_total)
        self.assertEqual(
            result.low_confidence_escalation_rate,
            result.low_confidence_escalated / low_total,
        )
        self.assertIsInstance(result.low_confidence_escalation_rate, float)
        self.assertGreaterEqual(result.low_confidence_escalation_rate, 0.0)
        self.assertLessEqual(result.low_confidence_escalation_rate, 1.0)

    def test_low_confidence_subset_matches_the_dataset_definition(self):
        # The subset is the dataset's own confidence_band == "low" label,
        # cross-checked here against the persisted audit decisions.
        cases = load_labelled_cases()
        low_ids = {
            c.case_id for c in cases
            if c.confidence_band == LOW_CONFIDENCE_BAND
        }
        with tempfile.TemporaryDirectory() as tmp:
            trail = Path(tmp) / "eval.audit.jsonl"
            result = evaluate(audit_path=trail)
            records = [json.loads(line) for line in trail_lines(trail)]
        escalated = sum(
            1 for r in records
            if r["case_ref"] in low_ids and r["decision"] == "escalate"
        )
        self.assertEqual(result.low_confidence_total, len(low_ids))
        self.assertEqual(result.low_confidence_escalated, escalated)

    def test_every_case_goes_through_the_audited_path(self):
        cases = load_labelled_cases()
        calls = []
        real = evalmod.decide_case_audited

        def counting(case, client, **kwargs):
            calls.append(kwargs["case_ref"])
            return real(case, client, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            trail = Path(tmp) / "eval.audit.jsonl"
            with mock.patch.object(evalmod, "decide_case_audited", counting):
                evaluate(audit_path=trail)
            lines = trail_lines(trail)

        self.assertEqual(calls, [c.case_id for c in cases])
        self.assertEqual(len(lines), len(cases))
        refs = sorted(json.loads(line)["case_ref"] for line in lines)
        self.assertEqual(refs, sorted(c.case_id for c in cases))

    def test_verdict_comes_from_the_trail_not_the_return_value(self):
        # The audited call still writes the truthful record, but returns
        # the opposite decision for every case. Scoring the return value
        # would mismatch all 36; scoring the persisted record must pass.
        real = evalmod.decide_case_audited
        returned = {}

        def lying(case, client, **kwargs):
            truth = real(case, client, **kwargs)
            lie = dict(truth)
            lie["decision"] = (
                "escalate" if truth["decision"] == "decide" else "decide"
            )
            returned[kwargs["case_ref"]] = lie
            return lie

        with tempfile.TemporaryDirectory() as tmp:
            trail = Path(tmp) / "eval.audit.jsonl"
            with mock.patch.object(evalmod, "decide_case_audited", lying):
                result = evaluate(audit_path=trail)
            persisted = {
                r["case_ref"]: r["decision"]
                for r in (json.loads(line) for line in trail_lines(trail))
            }

        # The two sources genuinely disagree for every case, so this test
        # cannot pass by accident if the verdict were read from returns.
        self.assertEqual(len(persisted), result.total_cases)
        for case_ref, decision in persisted.items():
            self.assertNotEqual(returned[case_ref]["decision"], decision)

        self.assertTrue(result.passed)
        self.assertEqual(result.mismatches, ())
        self.assertEqual(result.matched_cases, result.total_cases)

    def test_repeated_runs_produce_identical_results(self):
        first = evaluate()
        second = evaluate()
        self.assertEqual(first, second)
        self.assertIsInstance(first, EvalResult)
        # Timestamps differ between runs and must not leak into the result.
        self.assertNotIn("timestamp", first.__dict__)

    def test_expected_labels_never_enter_the_bedrock_request(self):
        created = []

        def factory(fixture_path):
            client = CapturingReplayClient(fixture_path)
            created.append(client)
            return client

        with mock.patch.object(evalmod, "ReplayBedrockClient", factory):
            result = evaluate()

        self.assertEqual(len(created), 1)
        requests = created[0].requests
        self.assertEqual(len(requests), result.total_cases)
        for request in requests:
            payload = json.loads(request["messages"][0]["content"][0]["text"])
            self.assertEqual(
                set(payload),
                {"age_band", "income_band", "evidence_status"},
                "only the three permitted input fields may be sent",
            )
            serialised = json.dumps(request, sort_keys=True)
            for marker in LABEL_MARKERS:
                self.assertNotIn(
                    marker, serialised,
                    f"evaluation metadata {marker!r} leaked into the request",
                )

    def test_dataset_order_is_preserved(self):
        cases = load_labelled_cases()
        with open(DEFAULT_DATASET_PATH, encoding="utf-8") as f:
            file_order = [json.loads(line)["case_id"] for line in f]
        self.assertEqual([c.case_id for c in cases], file_order)

    def test_model_input_excludes_evaluation_fields(self):
        for case in load_labelled_cases():
            self.assertEqual(
                set(case.model_input),
                {"age_band", "income_band", "evidence_status"},
            )


@unittest.skipUnless(FIXTURES_RECORDED, SKIP_REASON)
class TestEvalReporting(unittest.TestCase):
    def test_report_is_deterministic_and_free_of_model_text(self):
        result = evaluate()
        first = format_report(result)
        self.assertEqual(first, format_report(result))
        self.assertIn("PASS", first)
        self.assertNotIn("rationale", first)
        self.assertNotIn("Decided:", first)
        self.assertNotIn("Escalated:", first)

    def test_result_is_immutable(self):
        result = evaluate()
        with self.assertRaises(Exception):
            result.passed = False
        self.assertIsInstance(result.mismatches, tuple)


@unittest.skipUnless(FIXTURES_RECORDED, SKIP_REASON)
class TestEvalCli(unittest.TestCase):
    def run_cli(self, argv):
        stdout = StringIO()
        with mock.patch.object(sys, "stdout", stdout):
            code = evalmod.main(argv)
        return code, stdout.getvalue()

    def test_cli_exits_zero_and_prints_pass(self):
        with no_aws_credentials(os.environ), no_network():
            code, output = self.run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("PASS", output)
        self.assertNotIn("FAIL", output)
        self.assertIn("low-confidence esc. rate:", output)

    def test_cli_writes_an_explicit_audit_trail(self):
        cases = load_labelled_cases()
        with tempfile.TemporaryDirectory() as tmp:
            trail = Path(tmp) / "cli.audit.jsonl"
            code, _ = self.run_cli(["--audit-path", str(trail)])
            lines = trail_lines(trail)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), len(cases))

    def test_cli_reports_the_recorded_model(self):
        _, output = self.run_cli([])
        self.assertIn("amazon.nova-lite-v1:0", output)


if __name__ == "__main__":
    unittest.main()
