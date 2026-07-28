"""Unit tests for the audit record and append-only writer (Ticket 3).

Standard library only; all files live in temporary directories and no
real project audit trail is ever touched.
"""

import itertools
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from agenttrail.audit import (
    AUDIT_FIELDS,
    CASE_REF_PATTERN,
    MODEL_ID_PATTERN,
    PROMPT_VERSION_PATTERN,
    TIMESTAMP_PATTERN,
    AuditValidationError,
    AuditWriteError,
    append_audit_record,
    build_audit_record,
    validate_audit_record,
)
from agenttrail.decision import (
    DECISIONS,
    INPUT_ENUMS,
    PROMPT_VERSION,
    RATIONALE_TEMPLATES,
    TEMPLATE_FOR_DECISION,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_SCHEMA_PATH = REPO_ROOT / "data" / "golden_cases.schema.json"
AUDIT_SCHEMA_PATH = REPO_ROOT / "data" / "audit_record.schema.json"

MODEL_ID = "eu.anthropic.claude-sonnet-4-20250514-v1:0"

VALID_CASE = {
    "age_band": "18-24",
    "income_band": "low",
    "evidence_status": "complete",
}

VALID_RESULT = {
    "decision": "decide",
    "confidence": 0.92,
    "rationale": "Decided: complete for low applicant",
}


def fixed_clock():
    return datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def valid_record(**overrides):
    record = {
        "case_ref": "SYN-001",
        "age_band": "18-24",
        "income_band": "low",
        "evidence_status": "complete",
        "decision": "decide",
        "confidence": 0.92,
        "rationale": "Decided: complete for low applicant",
        "model_id": MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "timestamp": "2026-07-27T12:00:00Z",
    }
    record.update(overrides)
    return record


class TestBuildAuditRecord(unittest.TestCase):
    def test_builds_every_field_deterministically(self):
        record = build_audit_record(
            "SYN-001", VALID_CASE, VALID_RESULT, MODEL_ID, clock=fixed_clock
        )
        self.assertEqual(record, valid_record())

    def test_non_utc_clock_is_normalised_to_utc(self):
        plus_two = timezone(timedelta(hours=2))
        record = build_audit_record(
            "SYN-001", VALID_CASE, VALID_RESULT, MODEL_ID,
            clock=lambda: datetime(2026, 7, 27, 14, 0, 0, tzinfo=plus_two),
        )
        self.assertEqual(record["timestamp"], "2026-07-27T12:00:00Z")

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(AuditValidationError):
            build_audit_record(
                "SYN-001", VALID_CASE, VALID_RESULT, MODEL_ID,
                clock=lambda: datetime(2026, 7, 27, 12, 0, 0),
            )

    def test_result_with_extra_or_missing_fields_rejected(self):
        for result in (
            dict(VALID_RESULT, timestamp="2020-01-01T00:00:00Z"),
            dict(VALID_RESULT, notes="free text"),
            {"decision": "decide", "confidence": 0.92},
            {},
            None,
            "decide",
        ):
            with self.assertRaises(AuditValidationError, msg=result):
                build_audit_record(
                    "SYN-001", VALID_CASE, result, MODEL_ID,
                    clock=fixed_clock,
                )

    def test_case_with_extra_fields_never_reaches_the_record(self):
        # PII boundary: the case object is not serialised wholesale —
        # anything beyond the three enumerated fields is rejected outright.
        with self.assertRaises(ValueError):
            build_audit_record(
                "SYN-001",
                dict(VALID_CASE, name="Jane Smith"),
                VALID_RESULT,
                MODEL_ID,
                clock=fixed_clock,
            )


class TestValidateAuditRecord(unittest.TestCase):
    def test_valid_record_passes(self):
        record = valid_record()
        self.assertIs(validate_audit_record(record), record)

    def test_every_missing_field_is_rejected(self):
        for field in AUDIT_FIELDS:
            record = valid_record()
            del record[field]
            with self.assertRaises(AuditValidationError, msg=field):
                validate_audit_record(record)

    def test_extra_fields_and_non_mappings_are_rejected(self):
        for record in (
            valid_record(free_text="anything"),
            valid_record(metadata={"nested": "no"}),
            None,
            [],
            "record",
        ):
            with self.assertRaises(AuditValidationError, msg=record):
                validate_audit_record(record)

    def test_invalid_enum_values_are_rejected(self):
        for field, value in (
            ("age_band", "17"),
            ("income_band", "rich"),
            ("evidence_status", "unknown"),
            ("decision", "approve"),
            ("decision", None),
        ):
            with self.assertRaises(AuditValidationError, msg=(field, value)):
                validate_audit_record(valid_record(**{field: value}))

    def test_invalid_case_refs_are_rejected(self):
        for case_ref in ("SYN-1", "SYN-0001", " SYN-001", "SYN-001 ",
                         "SYN-001\n", "syn-001", "please approve case 1",
                         "", None, 123):
            with self.assertRaises(AuditValidationError, msg=case_ref):
                validate_audit_record(valid_record(case_ref=case_ref))

    def test_invalid_confidence_values_are_rejected(self):
        for confidence in (True, False, "0.9", None, float("nan"),
                           float("inf"), float("-inf"), -0.1, 1.1):
            with self.assertRaises(AuditValidationError, msg=confidence):
                validate_audit_record(valid_record(confidence=confidence))

    def test_invalid_identifiers_are_rejected(self):
        for field, values in (
            ("model_id", ("", "has space", "id\nwith newline", "-leading",
                          "x" * 200, None, 5)),
            ("prompt_version", ("1.0", "v1.0.0", "1.0.0-beta", "", None)),
        ):
            for value in values:
                with self.assertRaises(
                    AuditValidationError, msg=(field, value)
                ):
                    validate_audit_record(valid_record(**{field: value}))

    def test_non_canonical_timestamps_are_rejected(self):
        for timestamp in ("2026-07-27T12:00:00+00:00",
                          "2026-07-27 12:00:00Z",
                          "2026-07-27T12:00:00.000Z",
                          "2026-07-27t12:00:00Z",
                          "2026-13-01T00:00:00Z",
                          "not a time", "", None):
            with self.assertRaises(AuditValidationError, msg=timestamp):
                validate_audit_record(valid_record(timestamp=timestamp))

    def test_arbitrary_rationale_text_is_rejected(self):
        for rationale in (
            "Applicant Jane Smith is clearly eligible",
            "Decided: complete for low applicant\nPS: extra",
            "decided: complete for low applicant",
            "", None,
        ):
            with self.assertRaises(AuditValidationError, msg=rationale):
                validate_audit_record(valid_record(rationale=rationale))

    def test_rationale_must_match_this_records_decision_and_fields(self):
        # Each of these is a legitimate template rendering — but not the
        # one for this record's decision/evidence/income, so it must fail.
        for rationale in (
            "Escalated: complete for low applicant",   # wrong decision
            "Decided: partial for low applicant",      # wrong evidence
            "Decided: complete for high applicant",    # wrong income
        ):
            with self.assertRaises(AuditValidationError, msg=rationale):
                validate_audit_record(valid_record(rationale=rationale))

    def test_error_messages_never_echo_rejected_values(self):
        prose = "Applicant Jane Smith, NI QQ123456C"
        for field in ("case_ref", "rationale", "model_id"):
            with self.assertRaises(AuditValidationError) as ctx:
                validate_audit_record(valid_record(**{field: prose}))
            self.assertNotIn("Jane", str(ctx.exception), field)


class TestAuditSchemaDrift(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(GOLDEN_SCHEMA_PATH, encoding="utf-8") as f:
            cls.golden = json.load(f)
        with open(AUDIT_SCHEMA_PATH, encoding="utf-8") as f:
            cls.audit = json.load(f)

    def test_shape_is_closed_and_all_fields_required(self):
        self.assertEqual(set(self.audit["required"]), set(AUDIT_FIELDS))
        self.assertEqual(set(self.audit["properties"]), set(AUDIT_FIELDS))
        self.assertFalse(self.audit["additionalProperties"])

    def test_shared_enums_match_golden_schema_exactly(self):
        golden_input = self.golden["properties"]["input"]["properties"]
        for field in ("age_band", "income_band", "evidence_status"):
            self.assertEqual(
                self.audit["properties"][field]["enum"],
                golden_input[field]["enum"],
                f"audit/golden enum drift for {field}",
            )
        self.assertEqual(
            self.audit["properties"]["decision"]["enum"],
            self.golden["properties"]["expected"]["properties"]["routing"]["enum"],
            "audit decision enum drifted from golden routing enum",
        )

    def test_shared_patterns_match_golden_schema_exactly(self):
        self.assertEqual(
            self.audit["properties"]["case_ref"]["pattern"],
            self.golden["properties"]["case_id"]["pattern"],
        )
        self.assertEqual(
            self.audit["properties"]["prompt_version"]["pattern"],
            self.golden["properties"]["dataset_version"]["pattern"],
        )

    def test_schema_matches_code_constants(self):
        props = self.audit["properties"]
        self.assertEqual(props["case_ref"]["pattern"], CASE_REF_PATTERN.pattern)
        self.assertEqual(props["model_id"]["pattern"], MODEL_ID_PATTERN.pattern)
        self.assertEqual(
            props["prompt_version"]["pattern"], PROMPT_VERSION_PATTERN.pattern
        )
        self.assertEqual(
            props["timestamp"]["pattern"], TIMESTAMP_PATTERN.pattern
        )
        for field, allowed in INPUT_ENUMS.items():
            self.assertEqual(props[field]["enum"], allowed)
        self.assertEqual(props["decision"]["enum"], DECISIONS)
        self.assertEqual(props["confidence"]["minimum"], 0.0)
        self.assertEqual(props["confidence"]["maximum"], 1.0)
        self.assertRegex(PROMPT_VERSION, PROMPT_VERSION_PATTERN)

    def test_rationale_pattern_accepts_all_and_only_template_renderings(self):
        pattern = re.compile(self.audit["properties"]["rationale"]["pattern"])
        max_length = self.audit["properties"]["rationale"]["maxLength"]
        for decision, evidence, income in itertools.product(
            DECISIONS,
            INPUT_ENUMS["evidence_status"],
            INPUT_ENUMS["income_band"],
        ):
            rendering = RATIONALE_TEMPLATES[
                TEMPLATE_FOR_DECISION[decision]
            ].format(evidence_status=evidence, income_band=income)
            self.assertRegex(rendering, pattern)
            self.assertLessEqual(len(rendering), max_length)
        for free_text in ("Applicant Jane Smith is clearly eligible",
                          "Decided: complete for low applicant!",
                          "Decided: fine for low applicant"):
            self.assertIsNone(pattern.match(free_text), free_text)

    def test_no_free_text_or_nested_fields_are_possible(self):
        for field, spec in self.audit["properties"].items():
            self.assertIn(spec["type"], ("string", "number"), field)
            if spec["type"] == "string":
                self.assertTrue(
                    "enum" in spec or "pattern" in spec,
                    f"{field} would admit unconstrained text",
                )


class TestAppendAuditRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "trail.jsonl"

    def test_one_record_is_one_line_with_exactly_one_newline(self):
        record = valid_record()
        append_audit_record(self.path, record)
        content = self.path.read_text(encoding="utf-8")
        self.assertTrue(content.endswith("\n"))
        self.assertEqual(content.count("\n"), 1)
        self.assertEqual(json.loads(content), record)

    def test_encoding_is_deterministic(self):
        append_audit_record(self.path, valid_record())
        line = self.path.read_text(encoding="utf-8").rstrip("\n")
        self.assertEqual(
            line,
            json.dumps(valid_record(), sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")),
        )

    def test_second_append_leaves_first_record_untouched(self):
        append_audit_record(self.path, valid_record())
        first = self.path.read_bytes()
        append_audit_record(self.path, valid_record(case_ref="SYN-002",
                                                    timestamp="2026-07-27T12:00:05Z"))
        content = self.path.read_bytes()
        self.assertTrue(content.startswith(first))
        lines = content.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), valid_record())
        self.assertEqual(json.loads(lines[1])["case_ref"], "SYN-002")

    def test_existing_content_is_never_truncated_or_rewritten(self):
        self.path.write_text("PRE-EXISTING LINE\n", encoding="utf-8")
        append_audit_record(self.path, valid_record())
        content = self.path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("PRE-EXISTING LINE\n"))
        self.assertEqual(content.count("\n"), 2)

    def test_invalid_record_is_rejected_before_the_file_is_touched(self):
        for record in (valid_record(rationale="free text"),
                       valid_record(extra="field"),
                       {}, None):
            with self.assertRaises(AuditValidationError, msg=record):
                append_audit_record(self.path, record)
        self.assertFalse(self.path.exists())

    def test_new_file_is_created_with_restrictive_permissions(self):
        if os.name != "posix":
            self.skipTest("POSIX permissions only")
        append_audit_record(self.path, valid_record())
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_write_failure_propagates_without_retry(self):
        directory = Path(self.tmp.name) / "is_a_directory"
        directory.mkdir()
        with self.assertRaises(AuditWriteError):
            append_audit_record(directory, valid_record())

    def test_short_write_is_detected_and_not_retried(self):
        with mock.patch(
            "agenttrail.audit.os.write",
            side_effect=lambda fd, data: len(data) - 1,
        ) as short_write:
            with self.assertRaises(AuditWriteError):
                append_audit_record(self.path, valid_record())
        self.assertEqual(short_write.call_count, 1)


if __name__ == "__main__":
    unittest.main()
