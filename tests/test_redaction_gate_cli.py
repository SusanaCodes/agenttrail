"""CLI contract for the Ticket 8 redaction gate.

Proves the documented exit codes (0 clean, 1 finding, 2 operational
error), the headline acceptance case (clean record exits 0; the same
record with a planted synthetic NI number exits 1), that the committed
record data passes offline, and that no output channel ever reproduces
a detected value. Identifiers here are synthetic test inputs only.
"""

import json
import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import agenttrail.redaction_gate as gatemod
from support_fixtures import no_aws_credentials, no_network

NI = "AB 12 34 56 C"

CLEAN_RECORD = {
    "age_band": "18-24",
    "case_ref": "SYN-001",
    "confidence": 0.95,
    "decision": "decide",
    "evidence_status": "complete",
    "income_band": "low",
    "model_id": "amazon.nova-lite-v1:0",
    "prompt_version": "1.0.0",
    "timestamp": "2026-08-06T17:01:19Z",
}


def run_cli(argv):
    stdout, stderr = StringIO(), StringIO()
    with mock.patch.object(sys, "stdout", stdout), \
            mock.patch.object(sys, "stderr", stderr):
        code = gatemod.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def write_trail(tmp, extra=None, name="records.jsonl"):
    record = dict(CLEAN_RECORD)
    if extra:
        record.update(extra)
    path = Path(tmp) / name
    path.write_text(json.dumps(record, sort_keys=True) + "\n")
    return path


class TestCommittedDataPasses(unittest.TestCase):
    def test_default_targets_pass_offline(self):
        with no_aws_credentials(os.environ), no_network():
            code, out, err = run_cli([])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertTrue(out.startswith("REDACTION GATE: PASS\n"))
        self.assertIn("scanned_files=2", out)
        self.assertIn("findings=0", out)

    def test_output_is_byte_identical_across_runs(self):
        runs = [run_cli([]) for _ in range(3)]
        self.assertEqual(len({out for _, out, _ in runs}), 1)
        self.assertEqual({code for code, _, _ in runs}, {0})


class TestAcceptance(unittest.TestCase):
    def test_clean_record_exits_zero_then_planted_ni_exits_one(self):
        with TemporaryDirectory() as tmp:
            clean = write_trail(tmp)
            code, out, err = run_cli([str(clean)])
            self.assertEqual(code, 0)
            self.assertEqual(err, "")
            self.assertTrue(out.startswith("REDACTION GATE: PASS\n"))

            planted = write_trail(
                tmp, extra={"meta": {"note": NI}}, name="planted.jsonl"
            )
            code, out, err = run_cli([str(planted)])
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("REDACTION GATE: FAIL\n"))
        self.assertIn(
            f"finding: {planted}:1: national_insurance_number: [REDACTED]",
            out,
        )
        for channel in (out, err):
            self.assertNotIn(NI, channel)
            self.assertNotIn("AB123456C", channel)
            self.assertNotIn("123456", channel)

    def test_postcode_and_nhs_number_each_exit_one(self):
        for extra, category in (
            ({"note": "M1 1AE"}, "uk_postcode"),
            ({"note": "943 476 5919"}, "nhs_number"),
            ({"note": "ab 12 34 56 c"}, "national_insurance_number"),
        ):
            with self.subTest(category=category), \
                    TemporaryDirectory() as tmp:
                path = write_trail(tmp, extra=extra)
                code, out, err = run_cli([str(path)])
                self.assertEqual(code, 1)
                self.assertIn(f": {category}: [REDACTED]", out)
                self.assertNotIn(extra["note"], out)
                self.assertNotIn(extra["note"], err)

    def test_multiple_findings_reported_in_deterministic_order(self):
        with TemporaryDirectory() as tmp:
            b = write_trail(tmp, extra={"n": "9434765919"}, name="b.jsonl")
            a = write_trail(
                tmp, extra={"n": f"SW1A 1AA {NI}"}, name="a.jsonl"
            )
            first = run_cli([str(b), str(a)])
            second = run_cli([str(b), str(a)])
        self.assertEqual(first, second)
        code, out, _ = first
        self.assertEqual(code, 1)
        finding_lines = [
            line for line in out.splitlines()
            if line.startswith("finding: ")
        ]
        self.assertEqual(
            finding_lines,
            [
                f"finding: {a}:1: national_insurance_number: [REDACTED]",
                f"finding: {a}:1: uk_postcode: [REDACTED]",
                f"finding: {b}:1: nhs_number: [REDACTED]",
            ],
        )


class TestOperationalErrors(unittest.TestCase):
    def test_missing_target_exits_two_not_zero(self):
        code, out, err = run_cli(["/nonexistent/records.jsonl"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("REDACTION GATE: ERROR", err)
        self.assertNotIn("PASS", err)

    def test_one_missing_target_among_good_ones_still_exits_two(self):
        with TemporaryDirectory() as tmp:
            good = write_trail(tmp)
            code, out, err = run_cli(
                [str(good), str(Path(tmp) / "absent.jsonl")]
            )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("REDACTION GATE: ERROR", err)

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_unreadable_target_exits_two(self):
        with TemporaryDirectory() as tmp:
            path = write_trail(tmp)
            path.chmod(0o000)
            try:
                code, out, err = run_cli([str(path)])
            finally:
                path.chmod(0o600)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("REDACTION GATE: ERROR", err)


if __name__ == "__main__":
    unittest.main()
