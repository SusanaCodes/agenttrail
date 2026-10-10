"""Redaction gate: decoded-JSON scanning (AC-37).

A supported identifier written with JSON ``\\uXXXX`` escapes is restored
by any JSON parser but is invisible to a scan of the raw line text. The
gate therefore also scans the decoded keys and string values of every
line that is valid JSON, each string on its own.

Every identifier here is a synthetic test input, written to temporary
files only. Nothing reads or writes the committed record data.
"""

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import agenttrail.redaction_gate as gatemod
from agenttrail.redaction_gate import scan_file, scan_line

NI = "AB 12 34 56 C"
NI_COMPACT = "AB123456C"
NHS = "999 999 0002"
POSTCODE = "SW1A 1AA"

# Decodes to ordinary text; present only to prove decoded content is
# not reproduced in any output.
DECODED_ONLY_TEXT = "zzdecodedonlytext"

IDENTIFIERS = {
    "national_insurance_number": NI,
    "nhs_number": NHS,
    "uk_postcode": POSTCODE,
}


def escaped(text):
    """Every character as a JSON \\uXXXX escape."""
    return "".join(f"\\u{ord(ch):04x}" for ch in text)


def run_cli(argv):
    stdout, stderr = StringIO(), StringIO()
    with mock.patch.object(sys, "stdout", stdout), \
            mock.patch.object(sys, "stderr", stderr):
        code = gatemod.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def write_lines(tmp, lines, name="records.jsonl"):
    path = Path(tmp) / name
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


class TestEscapedIdentifiersAreDetected(unittest.TestCase):
    def assert_hidden_from_raw_text(self, line, identifier):
        # Guards each case: the raw line really does not contain the
        # identifier, and a JSON parser really does restore it.
        self.assertNotIn(identifier, line)
        self.assertIn(identifier, json.dumps(json.loads(line)))

    def test_fully_escaped_value_is_detected_for_each_category(self):
        for category, identifier in IDENTIFIERS.items():
            line = '{"note": "%s"}' % escaped(identifier)
            self.assert_hidden_from_raw_text(line, identifier)
            self.assertEqual(scan_line(line), (category,), category)

    def test_partially_escaped_value_is_detected(self):
        line = '{"note": "%s123456C"}' % escaped("AB")
        self.assert_hidden_from_raw_text(line, NI_COMPACT)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_escaped_separators_are_decoded_before_matching(self):
        line = '{"note": "AB\\u002012\\u002034\\u002056\\u0020C"}'
        self.assert_hidden_from_raw_text(line, NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_escaped_key_is_detected(self):
        line = '{"%s": "x"}' % escaped(NI)
        self.assert_hidden_from_raw_text(line, NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_escaped_value_in_nested_object_is_detected(self):
        line = '{"a": {"b": {"c": "%s"}}}' % escaped(NHS)
        self.assert_hidden_from_raw_text(line, NHS)
        self.assertEqual(scan_line(line), ("nhs_number",))

    def test_escaped_value_in_array_is_detected(self):
        line = '{"a": ["x", "%s", 3]}' % escaped(POSTCODE)
        self.assert_hidden_from_raw_text(line, POSTCODE)
        self.assertEqual(scan_line(line), ("uk_postcode",))

    def test_escaped_value_in_array_of_objects_is_detected(self):
        line = '[{"k": [{"deep": "%s"}]}]' % escaped(NI)
        self.assert_hidden_from_raw_text(line, NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_escaped_nested_key_is_detected(self):
        line = '{"a": [{"%s": 1}]}' % escaped(NHS)
        self.assert_hidden_from_raw_text(line, NHS)
        self.assertEqual(scan_line(line), ("nhs_number",))

    def test_top_level_string_line_is_detected(self):
        line = '"%s"' % escaped(NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_value_under_a_repeated_key_is_still_scanned(self):
        # A parser keeps only the last of two equal keys. The scan must
        # still see the first one's value.
        line = '{"note": "%s", "note": "clean"}' % escaped(NI)
        self.assertNotIn(NI, json.dumps(json.loads(line)))
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_several_escaped_categories_on_one_line_sorted(self):
        line = '{"a": "%s", "b": ["%s"], "%s": 0}' % (
            escaped(POSTCODE), escaped(NHS), escaped(NI),
        )
        self.assertEqual(
            scan_line(line),
            ("national_insurance_number", "nhs_number", "uk_postcode"),
        )


class TestFieldsAreNotJoined(unittest.TestCase):
    def test_identifier_split_across_fields_is_not_assembled(self):
        for line in (
            '{"a": "AB12", "b": "3456C"}',
            '{"a": "AB 12 34", "b": "56 C"}',
            '["943", "476", "5919"]',
            '{"a": ["SW1A", "1AA"]}',
            '{"AB12": "3456C"}',
        ):
            self.assertEqual(scan_line(line), (), line)

    def test_escaped_fragments_in_separate_fields_are_not_assembled(self):
        line = '{"a": "%s", "b": "%s"}' % (escaped("AB12"), escaped("3456C"))
        self.assertEqual(scan_line(line), ())


class TestNoDuplicateFindings(unittest.TestCase):
    def test_plain_identifier_is_reported_once_per_line(self):
        # Visible to both the raw scan and the decoded scan.
        line = json.dumps({"note": NI})
        self.assertEqual(scan_line(line), ("national_insurance_number",))
        with TemporaryDirectory() as tmp:
            findings = scan_file(write_lines(tmp, [line]))
        self.assertEqual(
            [(f.line_number, f.category) for f in findings],
            [(1, "national_insurance_number")],
        )

    def test_raw_and_escaped_copies_on_one_line_are_one_finding(self):
        line = '{"plain": "%s", "hidden": "%s"}' % (NI, escaped(NI))
        with TemporaryDirectory() as tmp:
            findings = scan_file(write_lines(tmp, [line]))
        self.assertEqual(len(findings), 1)


class TestCleanEscapedJsonStaysClean(unittest.TestCase):
    def test_escaped_ordinary_text_has_no_findings(self):
        for line in (
            '{"note": "%s"}' % escaped("clean value"),
            '{"%s": "%s"}' % (escaped("case_ref"), escaped("SYN-001")),
            '{"model_id": "%s"}' % escaped("amazon.nova-lite-v1:0"),
            '{"timestamp": "%s"}' % escaped("2026-08-06T17:01:19Z"),
            '{"a": ["%s", {"b": "%s"}]}' % (
                escaped("18-24"), escaped("complete"),
            ),
        ):
            self.assertEqual(scan_line(line), (), line)

    def test_escaped_token_embedded_in_longer_token_is_not_matched(self):
        # Same rule as the raw scan: no match inside a longer token.
        line = '{"id": "%s"}' % escaped("tooluse_AB123456Cxyz")
        self.assertEqual(scan_line(line), ())

    def test_clean_escaped_file_exits_zero(self):
        lines = [
            '{"note": "%s", "n": 1}' % escaped("nothing to see"),
            '{"a": {"b": ["%s"]}}' % escaped("still clean"),
        ]
        with TemporaryDirectory() as tmp:
            code, out, err = run_cli([str(write_lines(tmp, lines))])
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("REDACTION GATE: PASS\n"))
        self.assertIn("findings=0", out)


class TestOutputNeverCarriesDecodedContent(unittest.TestCase):
    def test_cli_reports_location_and_category_only(self):
        lines = [
            '{"clean": true}',
            '{"%s": "%s", "list": ["%s", {"%s": "%s"}]}' % (
                escaped(DECODED_ONLY_TEXT), escaped(NI),
                escaped(NHS), escaped(POSTCODE), escaped(DECODED_ONLY_TEXT),
            ),
        ]
        with TemporaryDirectory() as tmp:
            path = write_lines(tmp, lines)
            code, out, err = run_cli([str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertTrue(out.startswith("REDACTION GATE: FAIL\n"))
        self.assertIn("findings=3", out)
        for category in IDENTIFIERS:
            self.assertIn(f"finding: {path}:2: {category}: [REDACTED]", out)
        # The temporary path is the only caller-supplied text in the
        # report; set it aside so its random name cannot collide.
        body = out.replace(str(path), "<path>")
        for hidden in (
            NI, NI_COMPACT, NHS, POSTCODE, DECODED_ONLY_TEXT,
            "123456", "5919", "SW1A",
        ):
            self.assertNotIn(hidden, body)
        # The escaped spelling is file content too and is not echoed.
        self.assertNotIn("\\u", body)

    def test_finding_objects_carry_no_decoded_content(self):
        line = '{"%s": "%s"}' % (escaped(DECODED_ONLY_TEXT), escaped(NI))
        with TemporaryDirectory() as tmp:
            findings = scan_file(write_lines(tmp, [line]))
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            set(vars(findings[0])), {"path", "line_number", "category"}
        )
        rendered = repr(findings)
        self.assertNotIn(NI, rendered)
        self.assertNotIn(DECODED_ONLY_TEXT, rendered)


class TestMalformedInputBehaviourIsPreserved(unittest.TestCase):
    def test_non_json_line_is_still_scanned_as_raw_text(self):
        self.assertEqual(
            scan_line(f"plain log line mentioning {NI}"),
            ("national_insurance_number",),
        )

    def test_malformed_json_lines_do_not_raise(self):
        for line in ("", "   ", "{not json", '{"a": "%s"' % escaped(NI)):
            self.assertEqual(scan_line(line), (), repr(line))

    def test_malformed_file_exit_codes_are_unchanged(self):
        with TemporaryDirectory() as tmp:
            clean = write_lines(tmp, ["{not json", "", "also not json"])
            code, out, _ = run_cli([str(clean)])
            self.assertEqual(code, 0)
            self.assertIn("findings=0", out)

            planted = write_lines(
                tmp, ["{not json", f"free text {NI}"], name="planted.jsonl"
            )
            code, out, _ = run_cli([str(planted)])
        self.assertEqual(code, 1)
        self.assertIn(
            f"finding: {planted}:2: national_insurance_number: [REDACTED]",
            out,
        )
        self.assertNotIn(NI, out)


class TestUndecodableValidJsonFailsClosed(unittest.TestCase):
    def test_line_the_parser_cannot_decode_is_an_error_not_a_pass(self):
        # Valid JSON that the standard parser gives up on. Scanning only
        # its raw text would let an escaped identifier through, so the
        # scan reports that it could not be completed.
        depth = 200_000
        line = "[" * depth + '"%s"' % escaped(NI) + "]" * depth
        with TemporaryDirectory() as tmp:
            path = write_lines(tmp, ['{"clean": true}', line])
            code, out, err = run_cli([str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("REDACTION GATE: ERROR", err)
        self.assertIn(f"{path}:2", err)
        self.assertNotIn(NI, err)
        self.assertNotIn("\\u", err)

    def test_number_the_parser_refuses_is_an_error_not_a_pass(self):
        # A valid JSON number too long for the parser to convert.
        line = '{"n": %s, "note": "%s"}' % ("9" * 6000, escaped(NI))
        with TemporaryDirectory() as tmp:
            path = write_lines(tmp, [line])
            code, out, err = run_cli([str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("REDACTION GATE: ERROR", err)
        self.assertIn(f"{path}:1", err)
        self.assertNotIn(NI, err)
        self.assertNotIn("9999", err.replace(str(path), "<path>"))


if __name__ == "__main__":
    unittest.main()
