"""Scanner-level tests for the Ticket 8 redaction gate.

All identifiers used here are synthetic test inputs (the ticket's
planted NI value, a checksum-valid NHS-shaped number in the 999 range
reserved for testing, and well-known public postcodes). No real
person's data appears. CLI contract and exit-code coverage lives in
tests/test_redaction_gate_cli.py.
"""

import dataclasses
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agenttrail.redaction_gate import (
    RedactionScanError,
    format_report,
    scan_file,
    scan_line,
    scan_paths,
)

NI = "AB 12 34 56 C"
NHS = "999 999 0002"
POSTCODE = "SW1A 1AA"

# Shaped like a real audit record; content is irrelevant to the scanner,
# which reads raw line text.
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


def record_line(extra=None):
    record = dict(CLEAN_RECORD)
    if extra:
        record.update(extra)
    return json.dumps(record, sort_keys=True)


class TestScanLine(unittest.TestCase):
    def test_clean_audit_record_line_has_no_findings(self):
        self.assertEqual(scan_line(record_line()), ())

    def test_ni_number_conventional_presentations_detected(self):
        for value in (
            "AB123456C",
            "AB 12 34 56 C",
            "AB-12-34-56-C",
            "AB 123456 C",
            "ab123456c",
            "ab 12 34 56 c",
        ):
            with self.subTest(value=value):
                self.assertIn(
                    "national_insurance_number", scan_line(value)
                )

    def test_non_issuable_or_malformed_ni_shapes_not_detected(self):
        for value in (
            "DA123456C",   # first prefix letter D is never issued
            "AO123456C",   # second prefix letter O is never issued
            "BG123456C",   # invalid prefix pair
            "AB123456E",   # suffix must be A-D
            "AB12345C",    # five digits
            "XAB123456C",  # embedded in a longer token
            "AB123456C7",  # embedded in a longer token
        ):
            with self.subTest(value=value):
                self.assertEqual(scan_line(value), ())

    def test_postcode_common_shapes_detected(self):
        for value in (
            "SW1A 1AA", "sw1a1aa", "M1 1AE", "m11ae",
            "B33 8TH", "EC1A 1BB", "CR2 6XH", "DN55 1PT",
        ):
            with self.subTest(value=value):
                self.assertIn("uk_postcode", scan_line(value))

    def test_existing_record_vocabulary_is_not_a_postcode(self):
        for value in (
            "SYN-001",
            "1.0.0",
            "amazon.nova-lite-v1:0",
            "tooluse_3MS6YbsHtRfm8ogHndHD5r",
            "2026-08-06T17:01:19Z",
            "DECIDED_EVIDENCE_FOR_INCOME",
        ):
            with self.subTest(value=value):
                self.assertEqual(scan_line(value), ())

    def test_nhs_number_grouped_and_ungrouped_detected(self):
        for value in ("9999990002", "999 999 0002", "999-999-0002"):
            with self.subTest(value=value):
                self.assertIn("nhs_number", scan_line(value))

    def test_nhs_number_without_checksum_still_detected(self):
        # Deliberate design: shape-only matching, no modulus-11 check.
        # 1234567890 fails the checksum but is still a finding.
        self.assertIn("nhs_number", scan_line("1234567890"))

    def test_wrong_length_or_embedded_digit_runs_not_nhs(self):
        for value in (
            "999999000",             # nine digits
            "99999900020",           # eleven digits
            "a9999990002b",          # inside an alphanumeric token
            "sha_9999990002_suffix",  # underscore-delimited token
        ):
            with self.subTest(value=value):
                self.assertEqual(scan_line(value), ())

    def test_multiple_categories_on_one_line_sorted(self):
        line = f"{POSTCODE} {NI} {NHS}"
        self.assertEqual(
            scan_line(line),
            ("national_insurance_number", "nhs_number", "uk_postcode"),
        )


class TestScanFileAndPaths(unittest.TestCase):
    def write(self, tmp, name, lines):
        path = Path(tmp) / name
        path.write_text("".join(line + "\n" for line in lines))
        return path

    def test_identifier_in_nested_unexpected_field_detected(self):
        with TemporaryDirectory() as tmp:
            path = self.write(
                tmp,
                "records.jsonl",
                [
                    record_line(),
                    record_line({"meta": {"note": NI}}),
                ],
            )
            findings = scan_file(path)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line_number, 2)
        self.assertEqual(findings[0].category, "national_insurance_number")

    def test_findings_sorted_by_path_line_category_and_stable(self):
        with TemporaryDirectory() as tmp:
            b = self.write(
                tmp, "b.jsonl", [record_line({"x": NHS}), record_line()]
            )
            a = self.write(
                tmp,
                "a.jsonl",
                [record_line(), record_line({"x": f"{POSTCODE} {NI}"})],
            )
            first, targets = scan_paths([b, a])
            second, _ = scan_paths([b, a])
        self.assertEqual(first, second)
        self.assertEqual(targets, (str(a), str(b)))
        self.assertEqual(
            [(f.path, f.line_number, f.category) for f in first],
            [
                (str(a), 2, "national_insurance_number"),
                (str(a), 2, "uk_postcode"),
                (str(b), 1, "nhs_number"),
            ],
        )

    def test_missing_target_raises_instead_of_passing(self):
        with self.assertRaises(RedactionScanError):
            scan_file("/nonexistent/records.jsonl")

    def test_directory_target_raises(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(RedactionScanError):
                scan_file(tmp)

    def test_empty_target_list_raises(self):
        with self.assertRaises(RedactionScanError):
            scan_paths([])

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_unreadable_target_raises(self):
        with TemporaryDirectory() as tmp:
            path = self.write(tmp, "records.jsonl", [record_line()])
            path.chmod(0o000)
            try:
                with self.assertRaises(RedactionScanError):
                    scan_file(path)
            finally:
                path.chmod(0o600)


class TestFindingsNeverCarryTheValue(unittest.TestCase):
    def test_finding_has_no_field_for_matched_text(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_text(record_line({"x": NI}) + "\n")
            (finding,) = scan_file(path)
        field_names = {f.name for f in dataclasses.fields(finding)}
        self.assertEqual(field_names, {"path", "line_number", "category"})

    def test_report_redacts_and_never_contains_the_identifiers(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_text(
                record_line({"x": NI, "y": NHS, "z": POSTCODE}) + "\n"
            )
            findings, targets = scan_paths([path])
            report = format_report(findings, targets)
        self.assertTrue(report.startswith("REDACTION GATE: FAIL\n"))
        self.assertIn(
            f"finding: {path}:1: national_insurance_number: [REDACTED]",
            report,
        )
        for secret in (NI, NHS, POSTCODE, "AB123456C", "9999990002"):
            self.assertNotIn(secret, report)

    def test_pass_report_shape(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"
            path.write_text(record_line() + "\n")
            findings, targets = scan_paths([path])
            report = format_report(findings, targets)
        self.assertEqual(
            report.splitlines(),
            [
                "REDACTION GATE: PASS",
                "scanned_files=1",
                "findings=0",
                f"target: {path}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
