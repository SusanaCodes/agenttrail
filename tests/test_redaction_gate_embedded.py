"""Redaction gate: JSON documents stored inside string fields (AC-37).

The Bedrock fixtures keep the case fields as JSON text inside the string
``request.messages[].content[].text``. Decoding the line restores that
text, but an identifier written with ``\\uXXXX`` escapes inside it is
only restored by parsing the text as JSON in turn. The gate therefore
also decodes every decoded string that is itself a valid JSON document,
layer by layer, and scans the keys and string values it finds.

Every identifier here is a synthetic test input, written to temporary
files only. One test reads a committed fixture line as a template;
nothing writes to the committed record data.
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
from agenttrail.versions import AGENT_VERSIONS

NI = "AB 12 34 56 C"
NI_COMPACT = "AB123456C"
NHS = "999 999 0002"
POSTCODE = "SW1A 1AA"

# Decodes to ordinary text; present only to prove decoded content is
# not reproduced in any output.
DECODED_ONLY_TEXT = "zzembeddedonlytext"


def escaped(text):
    """Every character as a JSON \\uXXXX escape."""
    return "".join(f"\\u{ord(ch):04x}" for ch in text)


def fixture_line(text):
    """A fixture-shaped line whose message text field holds ``text``."""
    return json.dumps(
        {
            "request": {
                "messages": [{"role": "user", "content": [{"text": text}]}]
            }
        }
    )


def fixture_text(line):
    return json.loads(line)["request"]["messages"][0]["content"][0]["text"]


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


class EmbeddedCase(unittest.TestCase):
    def assert_hidden_until_inner_decode(self, line, identifier):
        # Guards each detection case: the identifier is absent from the
        # raw line and from the decoded text field, and parsing that
        # text field as JSON restores it.
        text = fixture_text(line)
        self.assertNotIn(identifier, line)
        self.assertNotIn(identifier, text)
        self.assertIn(identifier, json.dumps(json.loads(text)))


class TestEscapedIdentifierInFixtureTextField(EmbeddedCase):
    def check(self, category, identifier):
        line = fixture_line('{"case_note": "%s"}' % escaped(identifier))
        self.assert_hidden_until_inner_decode(line, identifier)
        self.assertEqual(scan_line(line), (category,))

    def test_escaped_ni_number_in_text_field_is_detected(self):
        self.check("national_insurance_number", NI)

    def test_escaped_postcode_in_text_field_is_detected(self):
        self.check("uk_postcode", POSTCODE)

    def test_escaped_nhs_number_in_text_field_is_detected(self):
        self.check("nhs_number", NHS)

    def test_committed_fixture_line_with_replaced_text_is_detected(self):
        # The real fixture representation: a committed line, with only
        # its text field replaced in memory.
        fixture_path = AGENT_VERSIONS["v1"].fixture_path
        with open(fixture_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        content = entry["request"]["messages"][0]["content"][0]
        self.assertIsInstance(json.loads(content["text"]), dict)
        self.assertEqual(scan_line(json.dumps(entry)), ())
        content["text"] = '{"age_band": "%s"}' % escaped(NI)
        line = json.dumps(entry)
        self.assertNotIn(NI, line)
        self.assertEqual(scan_line(line), ("national_insurance_number",))


class TestEmbeddedDocumentIsTraversed(EmbeddedCase):
    def test_escaped_embedded_key_is_detected(self):
        line = fixture_line('{"%s": "x"}' % escaped(NI))
        self.assert_hidden_until_inner_decode(line, NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_escaped_value_in_nested_embedded_objects_is_detected(self):
        line = fixture_line('{"a": {"b": {"c": "%s"}}}' % escaped(NHS))
        self.assert_hidden_until_inner_decode(line, NHS)
        self.assertEqual(scan_line(line), ("nhs_number",))

    def test_escaped_value_in_embedded_arrays_is_detected(self):
        line = fixture_line('[1, ["x", [{"k": ["%s"]}]]]' % escaped(POSTCODE))
        self.assert_hidden_until_inner_decode(line, POSTCODE)
        self.assertEqual(scan_line(line), ("uk_postcode",))

    def test_escaped_nested_embedded_key_is_detected(self):
        line = fixture_line('{"a": [{"%s": 1}]}' % escaped(NHS))
        self.assert_hidden_until_inner_decode(line, NHS)
        self.assertEqual(scan_line(line), ("nhs_number",))

    def test_embedded_document_that_is_a_bare_string_is_detected(self):
        line = fixture_line('"%s"' % escaped(NI))
        self.assert_hidden_until_inner_decode(line, NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_embedded_document_with_surrounding_whitespace_is_detected(self):
        line = fixture_line(' \n {"note": "%s"}\n' % escaped(NI))
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_embedded_document_in_an_outer_key_is_detected(self):
        line = json.dumps({'{"note": "%s"}' % escaped(NI): 1})
        self.assertNotIn(NI, line)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_embedded_document_outside_the_fixture_path_is_detected(self):
        line = json.dumps({"a": [{"b": '["%s"]' % escaped(POSTCODE)}]})
        self.assertNotIn(POSTCODE, line)
        self.assertEqual(scan_line(line), ("uk_postcode",))

    def test_value_under_a_repeated_embedded_key_is_still_scanned(self):
        # A parser keeps only the last of two equal keys. The scan must
        # still see the first one's value, at this layer too.
        line = fixture_line('{"note": "%s", "note": "clean"}' % escaped(NI))
        self.assertNotIn(NI, json.dumps(json.loads(fixture_text(line))))
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_several_embedded_categories_on_one_line_sorted(self):
        line = fixture_line(
            '{"a": "%s", "b": ["%s"], "%s": 0}'
            % (escaped(POSTCODE), escaped(NHS), escaped(NI))
        )
        self.assertEqual(
            scan_line(line),
            ("national_insurance_number", "nhs_number", "uk_postcode"),
        )


class TestFurtherEmbeddedLayers(EmbeddedCase):
    def test_document_embedded_in_an_embedded_document_is_detected(self):
        innermost = '{"note": "%s"}' % escaped(NI)
        middle = json.dumps({"payload": innermost})
        line = fixture_line(middle)
        self.assertNotIn(NI, json.dumps(json.loads(fixture_text(line))))
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_repeated_key_in_a_further_layer_is_still_scanned(self):
        innermost = '{"k": "%s", "k": "clean"}' % escaped(NHS)
        line = fixture_line(json.dumps([innermost]))
        self.assertEqual(scan_line(line), ("nhs_number",))

    def test_many_string_layers_are_unwrapped_and_the_scan_returns(self):
        text = '{"note": "%s"}' % escaped(POSTCODE)
        for _ in range(8):
            text = json.dumps(text)
        self.assertEqual(scan_line(fixture_line(text)), ("uk_postcode",))

    def test_many_clean_string_layers_have_no_findings(self):
        text = '{"note": "clean"}'
        for _ in range(8):
            text = json.dumps(text)
        self.assertEqual(scan_line(fixture_line(text)), ())


class TestCleanAndNonJsonStringsAreUnaffected(unittest.TestCase):
    def test_clean_embedded_json_has_no_findings(self):
        for text in (
            '{"age_band": "18-24", "evidence_status": "complete"}',
            '{"%s": ["%s"]}' % (escaped("case_ref"), escaped("SYN-001")),
            '{"id": "%s"}' % escaped("tooluse_AB123456Cxyz"),
            "[]",
            "{}",
            '""',
            "null",
            "true",
            "12",
            "1e3",
        ):
            self.assertEqual(scan_line(fixture_line(text)), (), text)

    def test_ordinary_prose_has_no_findings(self):
        for text in (
            "Assess this case and choose a routing decision.",
            'She said "hello" and left. {braces} [brackets]',
            "",
            "   ",
        ):
            self.assertEqual(scan_line(fixture_line(text)), (), text)

    def test_identifier_in_ordinary_prose_is_still_detected(self):
        line = fixture_line(f"Applicant quoted {NI} on the phone.")
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_malformed_json_like_strings_have_no_findings(self):
        for text in (
            '{"note": "clean"',
            "{'note': 'clean'}",
            '{"note": "clean"} trailing',
            '[1, 2,]',
            '{"a": }',
            '"unterminated',
            "{not json",
        ):
            self.assertEqual(scan_line(fixture_line(text)), (), text)

    def test_identifier_in_malformed_json_like_string_is_still_detected(self):
        line = fixture_line('{"note": "%s"' % NI)
        self.assertEqual(scan_line(line), ("national_insurance_number",))

    def test_escapes_in_a_malformed_string_are_not_interpreted(self):
        # Only the JSON parser decodes escapes. A string it rejects is
        # scanned as the text it is, with no unescaping of our own.
        line = fixture_line('{"note": "%s"' % escaped(NI))
        self.assertEqual(scan_line(line), ())

    def test_escape_shaped_prose_is_not_interpreted(self):
        line = fixture_line("see %s for details" % escaped(NI))
        self.assertEqual(scan_line(line), ())

    def test_malformed_outer_line_is_scanned_as_raw_text_only(self):
        inner = json.dumps('{"note": "%s"}' % escaped(NI))
        self.assertEqual(scan_line('{"text": %s' % inner), ())
        self.assertEqual(
            scan_line('{"text": %s, "plain": "%s"' % (inner, NI)),
            ("national_insurance_number",),
        )


class TestEmbeddedStringsAreNotJoined(unittest.TestCase):
    def test_identifier_split_across_embedded_strings_is_not_assembled(self):
        for text in (
            '{"a": "AB12", "b": "3456C"}',
            '{"a": "AB 12 34", "b": "56 C"}',
            '["943", "476", "5919"]',
            '{"a": ["SW1A", "1AA"]}',
            '{"AB12": "3456C"}',
            '{"a": "%s", "b": "%s"}' % (escaped("AB12"), escaped("3456C")),
        ):
            self.assertEqual(scan_line(fixture_line(text)), (), text)

    def test_identifier_split_across_layers_is_not_assembled(self):
        line = json.dumps({"a": "AB12", "b": '{"c": "3456C"}'})
        self.assertEqual(scan_line(line), ())
        line = json.dumps({"a": "999 999", "b": json.dumps(["0002"])})
        self.assertEqual(scan_line(line), ())


class TestNoDuplicateFindings(unittest.TestCase):
    def one_finding(self, line):
        self.assertEqual(scan_line(line), ("national_insurance_number",))
        with TemporaryDirectory() as tmp:
            findings = scan_file(write_lines(tmp, [line]))
        self.assertEqual(
            [(f.line_number, f.category) for f in findings],
            [(1, "national_insurance_number")],
        )

    def test_plain_embedded_identifier_is_one_finding(self):
        # Visible to the raw scan, the decoded text field, and the
        # embedded document's own string value.
        self.one_finding(fixture_line(json.dumps({"note": NI})))

    def test_identifier_found_at_every_layer_is_one_finding(self):
        inner = '{"plain": "%s", "hidden": "%s"}' % (NI, escaped(NI))
        line = json.dumps(
            {"outer": NI, "text": inner, "again": json.dumps([inner])}
        )
        self.one_finding(line)


class TestEmbeddedParserRefusalFailsClosed(unittest.TestCase):
    def assert_controlled_error(self, text, forbidden):
        with TemporaryDirectory() as tmp:
            path = write_lines(tmp, ['{"clean": true}', fixture_line(text)])
            code, out, err = run_cli([str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("REDACTION GATE: ERROR", err)
        self.assertIn(f"{path}:2", err)
        self.assertNotIn("Traceback", err)
        body = err.replace(str(path), "<path>")
        for hidden in forbidden:
            self.assertNotIn(hidden, body)

    def test_embedded_nesting_the_parser_refuses_is_an_error(self):
        # Valid embedded JSON that the standard parser gives up on. The
        # escaped identifier inside it has not been scanned, so the gate
        # reports that the scan could not be completed.
        depth = 200_000
        text = "[" * depth + '"%s"' % escaped(NI) + "]" * depth
        self.assert_controlled_error(text, (NI, "\\u", "[[", "0041"))

    def test_embedded_number_the_parser_refuses_is_an_error(self):
        text = '{"n": %s, "note": "%s"}' % ("9" * 6000, escaped(NI))
        self.assert_controlled_error(text, (NI, "\\u", "9999", "note"))

    def test_refusal_in_a_further_layer_is_an_error(self):
        innermost = '{"n": %s, "note": "%s"}' % ("9" * 6000, escaped(NI))
        text = json.dumps({"payload": innermost})
        self.assert_controlled_error(text, (NI, "\\u", "9999", "payload"))


class TestOutputNeverCarriesEmbeddedContent(unittest.TestCase):
    def test_cli_detects_and_reports_location_and_category_only(self):
        text = '{"%s": "%s", "list": ["%s", {"k": "%s"}]}' % (
            escaped(DECODED_ONLY_TEXT), escaped(NI),
            escaped(NHS), escaped(POSTCODE),
        )
        with TemporaryDirectory() as tmp:
            path = write_lines(tmp, ['{"clean": true}', fixture_line(text)])
            code, out, err = run_cli([str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertTrue(out.startswith("REDACTION GATE: FAIL\n"))
        self.assertIn("findings=3", out)
        for category in (
            "national_insurance_number", "nhs_number", "uk_postcode",
        ):
            self.assertIn(f"finding: {path}:2: {category}: [REDACTED]", out)
        # The temporary path is the only caller-supplied text in the
        # report; set it aside so its random name cannot collide.
        body = out.replace(str(path), "<path>")
        for hidden in (
            NI, NI_COMPACT, NHS, POSTCODE, DECODED_ONLY_TEXT,
            "123456", "5919", "SW1A", "\\u", "list", "messages",
        ):
            self.assertNotIn(hidden, body)

    def test_finding_objects_carry_no_embedded_content(self):
        text = '{"%s": "%s"}' % (escaped(DECODED_ONLY_TEXT), escaped(NI))
        with TemporaryDirectory() as tmp:
            findings = scan_file(write_lines(tmp, [fixture_line(text)]))
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            set(vars(findings[0])), {"path", "line_number", "category"}
        )
        rendered = repr(findings)
        self.assertNotIn(NI, rendered)
        self.assertNotIn(DECODED_ONLY_TEXT, rendered)


if __name__ == "__main__":
    unittest.main()
