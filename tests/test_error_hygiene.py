"""Error-message hygiene for rejected inputs and model output (AC-36).

A rejected case value, a rejected model value, or an unexpected key name
must never be copied into an exception message: those messages reach
stderr and therefore CI logs. Errors may still name the known field, the
category of failure, and the allowed set.

Mirrors ``test_error_messages_never_echo_rejected_values`` in
tests/test_audit.py for the decision and golden-dataset paths, extends
it to unexpected audit-record keys and to fixture entries, and drives
the real ``ci_gate`` and ``record_view`` CLI error paths end to end. Every marker
below is synthetic, and all test data lives in temporary directories:
nothing here reads or writes the committed dataset or fixtures.
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
from agenttrail.audit import AuditValidationError, validate_audit_record
from agenttrail.audit_reader import AuditTrailReadError, read_audit_trail
from agenttrail.decision import (
    INPUT_ENUMS,
    TOOL_NAME,
    CaseValidationError,
    ModelResponseError,
    decide_case,
    validate_case,
)
from agenttrail.fixtures import (
    FIXTURE_FORMAT_VERSION,
    FixtureValidationError,
    load_fixtures,
    validate_fixture_entry,
)
from agenttrail.golden import GoldenDatasetError, load_labelled_cases
from support_fixtures import no_network, tool_response
from test_ci_gate_regression import twelve_low_cases
from test_eval_failures import build_synthetic
from test_record_view import DECISION_ID_1, record_one, run_cli, write_trail

# Distinctive synthetic markers. None is a real identifier; each is
# unlikely to occur in any legitimate message, so its presence in an
# error can only mean the rejected content was echoed.
CASE_VALUE_MARKER = "ZZCASEVALUE-4f7a91-MARKER"
CASE_KEY_MARKER = "zz_case_key_c03d58_marker"
MODEL_VALUE_MARKER = "ZZMODELVALUE-9be216-MARKER"
MODEL_KEY_MARKER = "zz_model_key_71aa0e_marker"
MODEL_TOOL_MARKER = "zz_model_tool_5d44c7_marker"
AUDIT_KEY_MARKER = "zz_audit_key_e8b302_marker"
AUDIT_VALUE_MARKER = "ZZAUDITVALUE-26dd7c-MARKER"
FIXTURE_FIELD_MARKER = "zz_fixture_field_3fa9b1_marker"
FIXTURE_VALUE_MARKER = "ZZFIXTUREVALUE-b7c450-MARKER"
FIXTURE_VERSION_MARKER = "ZZFIXTUREVERSION-0d6e82-MARKER"
# Out-of-range confidence with a digit run no real message contains.
MODEL_NUMBER_MARKER = 73190.4682
MODEL_NUMBER_TEXT = "73190"

ALL_MARKERS = (
    CASE_VALUE_MARKER,
    CASE_KEY_MARKER,
    MODEL_VALUE_MARKER,
    MODEL_KEY_MARKER,
    MODEL_TOOL_MARKER,
    MODEL_NUMBER_TEXT,
    AUDIT_KEY_MARKER,
    AUDIT_VALUE_MARKER,
    FIXTURE_FIELD_MARKER,
    FIXTURE_VALUE_MARKER,
    FIXTURE_VERSION_MARKER,
)

VALID_CASE = {
    "age_band": "18-24",
    "income_band": "low",
    "evidence_status": "complete",
}

VALID_TOOL_INPUT = {
    "decision": "decide",
    "confidence": 0.95,
    "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
}

MODEL_ID = "test-model-id"


class _FakeClient:
    def __init__(self, response):
        self.response = response

    def converse(self, **kwargs):
        return self.response


def _rejected_model_responses():
    """(label, response) pairs, each rejected for one planted marker."""

    def with_input(**changes):
        return tool_response({**VALID_TOOL_INPUT, **changes})

    return (
        ("tool name", tool_response(dict(VALID_TOOL_INPUT), MODEL_TOOL_MARKER)),
        ("decision", with_input(decision=MODEL_VALUE_MARKER)),
        ("confidence type", with_input(confidence=MODEL_VALUE_MARKER)),
        ("confidence range", with_input(confidence=MODEL_NUMBER_MARKER)),
        ("template", with_input(rationale_template=MODEL_VALUE_MARKER)),
        ("unexpected key", with_input(**{MODEL_KEY_MARKER: "x"})),
        ("unexpected key value", with_input(extra_field=MODEL_VALUE_MARKER)),
    )


class TestCaseValidationErrorHygiene(unittest.TestCase):
    def assert_clean(self, message, label):
        for marker in ALL_MARKERS:
            self.assertNotIn(marker, message, label)

    def test_rejected_case_values_are_not_echoed(self):
        for field in INPUT_ENUMS:
            with self.assertRaises(CaseValidationError) as ctx:
                validate_case({**VALID_CASE, field: CASE_VALUE_MARKER})
            message = str(ctx.exception)
            self.assert_clean(message, field)
            # The known field is still named, so the error stays useful.
            self.assertIn(field, message)

    def test_rejected_structured_case_values_are_not_echoed(self):
        for value in ([CASE_VALUE_MARKER], {"note": CASE_VALUE_MARKER}):
            with self.assertRaises(CaseValidationError) as ctx:
                validate_case({**VALID_CASE, "income_band": value})
            self.assert_clean(str(ctx.exception), repr(type(value)))

    def test_unexpected_case_keys_are_not_echoed(self):
        with self.assertRaises(CaseValidationError) as ctx:
            validate_case({**VALID_CASE, CASE_KEY_MARKER: CASE_VALUE_MARKER})
        message = str(ctx.exception)
        self.assert_clean(message, "unexpected key")
        self.assertIn("unexpected", message)

    def test_golden_loader_does_not_echo_rejected_case_content(self):
        valid = twelve_low_cases()
        bad_value = json.loads(json.dumps(valid))
        bad_value[0]["input"]["income_band"] = CASE_VALUE_MARKER
        bad_key = json.loads(json.dumps(valid))
        bad_key[0]["input"][CASE_KEY_MARKER] = CASE_VALUE_MARKER
        for label, cases in (("value", bad_value), ("key", bad_key)):
            with tempfile.TemporaryDirectory() as tmp:
                dataset = Path(tmp) / "golden.jsonl"
                dataset.write_text(
                    "".join(json.dumps(c) + "\n" for c in cases),
                    encoding="utf-8",
                )
                with self.assertRaises(GoldenDatasetError) as ctx:
                    load_labelled_cases(dataset)
            message = str(ctx.exception)
            self.assert_clean(message, label)
            self.assertIn("invalid case input", message)


class TestModelResponseErrorHygiene(unittest.TestCase):
    def test_rejected_model_values_and_keys_are_not_echoed(self):
        for label, response in _rejected_model_responses():
            with self.assertRaises(ModelResponseError) as ctx:
                decide_case(
                    VALID_CASE, _FakeClient(response), model_id=MODEL_ID
                )
            message = str(ctx.exception)
            for marker in ALL_MARKERS:
                self.assertNotIn(marker, message, label)

    def test_errors_still_identify_the_failure(self):
        expectations = {
            "tool name": TOOL_NAME,
            "decision": "decision",
            "confidence type": "confidence",
            "confidence range": "confidence",
            "template": "rationale_template",
            "unexpected key": "unexpected",
        }
        responses = dict(_rejected_model_responses())
        for label, expected in expectations.items():
            with self.assertRaises(ModelResponseError) as ctx:
                decide_case(
                    VALID_CASE,
                    _FakeClient(responses[label]),
                    model_id=MODEL_ID,
                )
            self.assertIn(expected, str(ctx.exception), label)


class TestAuditValidationErrorHygiene(unittest.TestCase):
    """An unexpected audit-record key, directly and through a real reader."""

    def marked_record(self):
        return record_one(**{AUDIT_KEY_MARKER: AUDIT_VALUE_MARKER})

    def assert_clean(self, text, label):
        for marker in ALL_MARKERS:
            self.assertNotIn(marker, text, label)

    def test_valid_record_passes(self):
        # Guards the tests below: only the planted key makes them fail.
        self.assertEqual(validate_audit_record(record_one()), record_one())

    def test_unexpected_audit_key_is_not_echoed(self):
        with self.assertRaises(AuditValidationError) as ctx:
            validate_audit_record(self.marked_record())
        message = str(ctx.exception)
        self.assert_clean(message, "validator")
        self.assertIn("unexpected", message)
        # The known, allowed fields are still listed.
        self.assertIn("case_ref", message)

    def test_audit_reader_does_not_echo_unexpected_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            trail = write_trail(tmp, [self.marked_record()])
            with self.assertRaises(AuditTrailReadError) as ctx:
                read_audit_trail(trail)
        message = str(ctx.exception)
        self.assert_clean(message, "reader")
        self.assertIn("invalid audit record", message)

    def test_record_view_cli_does_not_expose_unexpected_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            trail = write_trail(tmp, [self.marked_record()])
            code, out, err = run_cli(
                ["--trail", str(trail), "--decision-id", DECISION_ID_1]
            )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("record view error", err)
        self.assert_clean(out + err, "record_view CLI")

    def test_record_view_cli_still_renders_a_valid_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            trail = write_trail(tmp, [record_one()])
            code, out, err = run_cli(
                ["--trail", str(trail), "--decision-id", DECISION_ID_1]
            )
        self.assertEqual((code, err), (0, ""))
        self.assertIn(DECISION_ID_1, out)


def _plant_unexpected_fixture_field(entry):
    entry[FIXTURE_FIELD_MARKER] = FIXTURE_VALUE_MARKER


def _plant_unsupported_fixture_version(entry):
    entry["fixture_format_version"] = FIXTURE_VERSION_MARKER


class TestFixtureValidationErrorHygiene(unittest.TestCase):
    """A fixture entry with an unexpected field or an unsupported version."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _, self.fixtures = build_synthetic(
            Path(self.tmp.name), twelve_low_cases()
        )

    def first_entry(self):
        first_line = self.fixtures.read_text(encoding="utf-8").splitlines()[0]
        return json.loads(first_line)

    def rewrite_first_entry(self, mutate):
        lines = self.fixtures.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        mutate(entry)
        lines[0] = json.dumps(entry, sort_keys=True)
        self.fixtures.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def assert_clean(self, text, label):
        for marker in ALL_MARKERS:
            self.assertNotIn(marker, text, label)

    def test_unmodified_temporary_fixtures_are_valid(self):
        # Guards the tests below: only the planted content makes them fail.
        self.assertEqual(
            validate_fixture_entry(self.first_entry()), self.first_entry()
        )
        self.assertEqual(len(load_fixtures(self.fixtures)), 12)

    def test_unexpected_fixture_field_is_not_echoed(self):
        entry = self.first_entry()
        _plant_unexpected_fixture_field(entry)
        with self.assertRaises(FixtureValidationError) as ctx:
            validate_fixture_entry(entry)
        message = str(ctx.exception)
        self.assert_clean(message, "validator, unexpected field")
        self.assertIn("unexpected", message)
        # The known, allowed fields are still listed.
        self.assertIn("request_sha256", message)

    def test_unsupported_fixture_version_is_not_echoed(self):
        entry = self.first_entry()
        _plant_unsupported_fixture_version(entry)
        with self.assertRaises(FixtureValidationError) as ctx:
            validate_fixture_entry(entry)
        message = str(ctx.exception)
        self.assert_clean(message, "validator, version")
        # The field and the supported version are still identified.
        self.assertIn("fixture_format_version", message)
        self.assertIn(FIXTURE_FORMAT_VERSION, message)

    def test_load_fixtures_does_not_echo_rejected_content(self):
        for label, mutate in (
            ("unexpected field", _plant_unexpected_fixture_field),
            ("version", _plant_unsupported_fixture_version),
        ):
            original = self.fixtures.read_text(encoding="utf-8")
            self.rewrite_first_entry(mutate)
            with self.assertRaises(FixtureValidationError) as ctx:
                load_fixtures(self.fixtures)
            self.fixtures.write_text(original, encoding="utf-8")
            self.assert_clean(str(ctx.exception), f"loader, {label}")


class TestGateErrorPathHygiene(unittest.TestCase):
    """The real ci_gate CLI, fed temporary rejected inputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.dataset, self.fixtures = build_synthetic(
            self.tmp_path, twelve_low_cases()
        )

    def run_gate(self):
        stdout, stderr = StringIO(), StringIO()
        scrubbed = {
            k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"
        }
        argv = ["--dataset", str(self.dataset), "--fixtures", str(self.fixtures)]
        with no_network(), \
                mock.patch.dict(os.environ, scrubbed, clear=True), \
                mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(sys, "stderr", stderr):
            code = gatemod.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_gate_error_is_clean(self, label):
        code, out, err = self.run_gate()
        self.assertNotEqual(code, 0, label)
        self.assertEqual(code, 2, label)
        self.assertIn("gate error", err, label)
        for marker in ALL_MARKERS:
            self.assertNotIn(marker, out, label)
            self.assertNotIn(marker, err, label)

    def rewrite_first_line(self, path, mutate):
        lines = path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        mutate(record)
        lines[0] = json.dumps(record, sort_keys=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def tamper_tool_input(self, **changes):
        def mutate(entry):
            block = entry["response"]["output"]["message"]["content"][0]
            block["toolUse"]["input"].update(changes)

        self.rewrite_first_line(self.fixtures, mutate)

    def test_unmodified_temporary_inputs_pass(self):
        # Guards the tests below: the only reason they fail is the
        # planted content.
        code, out, err = self.run_gate()
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("CI GATE: PASS\n"))

    def test_rejected_case_value_is_not_exposed(self):
        def mutate(record):
            record["input"]["evidence_status"] = CASE_VALUE_MARKER

        self.rewrite_first_line(self.dataset, mutate)
        self.assert_gate_error_is_clean("case value")

    def test_unexpected_case_key_is_not_exposed(self):
        def mutate(record):
            record["input"][CASE_KEY_MARKER] = CASE_VALUE_MARKER

        self.rewrite_first_line(self.dataset, mutate)
        self.assert_gate_error_is_clean("case key")

    def test_rejected_model_decision_is_not_exposed(self):
        self.tamper_tool_input(decision=MODEL_VALUE_MARKER)
        self.assert_gate_error_is_clean("model decision")

    def test_rejected_model_confidence_is_not_exposed(self):
        self.tamper_tool_input(confidence=MODEL_NUMBER_MARKER)
        self.assert_gate_error_is_clean("model confidence")

    def test_rejected_model_template_is_not_exposed(self):
        self.tamper_tool_input(rationale_template=MODEL_VALUE_MARKER)
        self.assert_gate_error_is_clean("model template")

    def test_unexpected_model_key_is_not_exposed(self):
        self.tamper_tool_input(**{MODEL_KEY_MARKER: MODEL_VALUE_MARKER})
        self.assert_gate_error_is_clean("model key")

    def test_unexpected_model_tool_name_is_not_exposed(self):
        def mutate(entry):
            block = entry["response"]["output"]["message"]["content"][0]
            block["toolUse"]["name"] = MODEL_TOOL_MARKER

        self.rewrite_first_line(self.fixtures, mutate)
        self.assert_gate_error_is_clean("model tool name")

    def test_unexpected_fixture_field_is_not_exposed(self):
        self.rewrite_first_line(self.fixtures, _plant_unexpected_fixture_field)
        self.assert_gate_error_is_clean("fixture field")

    def test_unsupported_fixture_version_is_not_exposed(self):
        self.rewrite_first_line(
            self.fixtures, _plant_unsupported_fixture_version
        )
        self.assert_gate_error_is_clean("fixture version")


if __name__ == "__main__":
    unittest.main()
