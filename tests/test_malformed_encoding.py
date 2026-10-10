"""Malformed input encodings fail closed with the documented exit code (AC-38).

A trail, fixture file or dataset that is not valid UTF-8 cannot serve as
evidence. Each loader must translate the decoding failure into its own
typed malformed-input error, so that every CLI maps it to exit ``2``:
``record_view`` must not report it as "no record found" (exit ``1``),
and ``ci_gate`` and ``eval`` must not report it as a behavioural failure
(exit ``1``). The error names the file only; the decoder's own message,
which quotes the offending bytes, must not be echoed or chained.

Every input here is synthetic and lives in a temporary directory.
Invalid bytes are planted at both the start and the end of each file,
because the text layer surfaces them at different points of the read.
"""

import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import agenttrail.ci_gate as gatemod
import agenttrail.eval as evalmod
import agenttrail.policy_replay as replaymod
from agenttrail.audit_reader import AuditTrailReadError, read_audit_trail
from agenttrail.eval import evaluate
from agenttrail.fixtures import FixtureValidationError, load_fixtures
from agenttrail.golden import GoldenDatasetError, load_labelled_cases
from support_fixtures import no_network
from test_eval_failures import build_synthetic, correct_cases
from test_record_view import ABSENT_ID, DECISION_ID_1, record_one, run_cli
from test_record_view import write_trail as write_records

# A byte sequence that no UTF-8 decoder accepts.
INVALID_BYTES = b"\xff\xfe"
# How the decoder's own message would render those bytes, and the
# exception name itself: neither may reach an error message or output.
ECHO_MARKERS = ("\\xff", "\\xfe", "UnicodeDecodeError", "Traceback")


def corrupt(path, where):
    """Return a copy of ``path`` with invalid bytes at the start or end."""
    data = Path(path).read_bytes()
    bad = Path(path).with_name(f"{Path(path).stem}-bad-{where}{Path(path).suffix}")
    if where == "start":
        bad.write_bytes(INVALID_BYTES + data)
    else:
        bad.write_bytes(data + INVALID_BYTES + b"\n")
    return bad


def _capture(main, argv):
    stdout, stderr = StringIO(), StringIO()
    scrubbed = {
        k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"
    }
    with no_network(), \
            mock.patch.dict(os.environ, scrubbed, clear=True), \
            mock.patch.object(sys, "stdout", stdout), \
            mock.patch.object(sys, "stderr", stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class MalformedEncodingTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)

    def assert_clean(self, exc, text=""):
        message = str(exc)
        for marker in ECHO_MARKERS:
            self.assertNotIn(marker, message)
            self.assertNotIn(marker, text)
        # The decoder's exception, whose message quotes the bytes, must
        # not travel with the typed error either.
        self.assertIsNone(exc.__cause__)
        self.assertTrue(exc.__suppress_context__)


class TestLoadersFailClosed(MalformedEncodingTestCase):
    def test_audit_reader_raises_typed_error(self):
        trail = write_records(self.tmp_path, [record_one()])
        for where in ("start", "end"):
            with self.assertRaises(AuditTrailReadError, msg=where) as ctx:
                read_audit_trail(corrupt(trail, where))
            self.assert_clean(ctx.exception)
            self.assertIn("not valid UTF-8", str(ctx.exception))

    def test_fixture_loader_raises_typed_error(self):
        _, fixtures = build_synthetic(self.tmp_path, correct_cases())
        for where in ("start", "end"):
            with self.assertRaises(FixtureValidationError, msg=where) as ctx:
                load_fixtures(corrupt(fixtures, where))
            self.assert_clean(ctx.exception)
            self.assertIn("not valid UTF-8", str(ctx.exception))

    def test_golden_loader_raises_typed_error(self):
        dataset, _ = build_synthetic(self.tmp_path, correct_cases())
        for where in ("start", "end"):
            with self.assertRaises(GoldenDatasetError, msg=where) as ctx:
                load_labelled_cases(corrupt(dataset, where))
            self.assert_clean(ctx.exception)
            self.assertIn("not valid UTF-8", str(ctx.exception))

    def test_unmodified_inputs_still_load(self):
        # Guards the tests above: only the planted bytes make them fail.
        dataset, fixtures = build_synthetic(self.tmp_path, correct_cases())
        trail = write_records(self.tmp_path, [record_one()])
        self.assertEqual(len(load_labelled_cases(dataset)), 4)
        self.assertEqual(len(load_fixtures(fixtures)), 4)
        self.assertEqual(read_audit_trail(trail), [record_one()])


class TestRecordViewExitCodes(MalformedEncodingTestCase):
    def test_malformed_trail_exits_two_not_one(self):
        trail = write_records(self.tmp_path, [record_one()])
        for where in ("start", "end"):
            code, out, err = run_cli(
                ["--trail", str(corrupt(trail, where)),
                 "--decision-id", DECISION_ID_1]
            )
            self.assertEqual(code, 2, where)
            self.assertEqual(out, "")
            self.assertIn("record view error", err)
            self.assertNotIn("no audit record found", err)
            for marker in ECHO_MARKERS:
                self.assertNotIn(marker, err)

    def test_absent_id_in_a_valid_trail_still_exits_one(self):
        # The malformed-input and not-found outcomes stay distinct.
        trail = write_records(self.tmp_path, [record_one()])
        code, _, err = run_cli(
            ["--trail", str(trail), "--decision-id", ABSENT_ID]
        )
        self.assertEqual(code, 1)
        self.assertIn("no audit record found", err)


class TestEvaluationExitCodes(MalformedEncodingTestCase):
    def setUp(self):
        super().setUp()
        self.dataset, self.fixtures = build_synthetic(
            self.tmp_path, correct_cases()
        )

    def assert_exit_two(self, main, argv, prefix, label):
        code, out, err = _capture(main, argv)
        self.assertEqual(code, 2, label)
        self.assertEqual(out, "", label)
        self.assertIn(prefix, err, label)
        for marker in ECHO_MARKERS:
            self.assertNotIn(marker, err, label)

    def test_unmodified_inputs_pass(self):
        # Guards the tests below: only the planted bytes make them fail.
        code, out, err = _capture(
            gatemod.main,
            ["--dataset", str(self.dataset), "--fixtures", str(self.fixtures)],
        )
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("CI GATE: PASS\n"))

    def test_ci_gate_malformed_fixtures_exit_two(self):
        for where in ("start", "end"):
            self.assert_exit_two(
                gatemod.main,
                ["--dataset", str(self.dataset),
                 "--fixtures", str(corrupt(self.fixtures, where))],
                "gate error", f"fixtures {where}",
            )

    def test_ci_gate_malformed_dataset_exits_two(self):
        for where in ("start", "end"):
            self.assert_exit_two(
                gatemod.main,
                ["--dataset", str(corrupt(self.dataset, where)),
                 "--fixtures", str(self.fixtures)],
                "gate error", f"dataset {where}",
            )

    def test_eval_malformed_fixtures_and_dataset_exit_two(self):
        for where in ("start", "end"):
            self.assert_exit_two(
                evalmod.main,
                ["--dataset", str(self.dataset),
                 "--fixtures", str(corrupt(self.fixtures, where))],
                "evaluation error", f"fixtures {where}",
            )
            self.assert_exit_two(
                evalmod.main,
                ["--dataset", str(corrupt(self.dataset, where)),
                 "--fixtures", str(self.fixtures)],
                "evaluation error", f"dataset {where}",
            )

    def test_policy_replay_malformed_trail_exits_two(self):
        trail = self.tmp_path / "trail.jsonl"
        evaluate(
            dataset_path=self.dataset,
            fixture_path=self.fixtures,
            audit_path=trail,
        )
        for where in ("start", "end"):
            self.assert_exit_two(
                replaymod.main,
                ["--audit-path", str(corrupt(trail, where)),
                 "--fixtures", str(self.fixtures),
                 "--dataset", str(self.dataset),
                 "--target-policy", "v2",
                 "--legacy-baseline-policy", "v1"],
                "policy replay error", f"trail {where}",
            )


if __name__ == "__main__":
    unittest.main()
