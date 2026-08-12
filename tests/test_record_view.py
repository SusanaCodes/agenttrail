"""Record view: lookup and rendering of stored decision records (Ticket 11).

Stored-record lookup only — every test runs offline against temporary
trails; nothing touches a real project trail or the committed record
data. Several tests additionally run under the no-network and
no-credentials guards to prove that a lookup never invokes Bedrock, the
agent, or any network service. Sensitive-looking values planted here
are synthetic test inputs only.
"""

import json
import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import agenttrail.record_view as viewmod
from agenttrail.audit import (
    AuditValidationError,
    append_audit_record,
    build_audit_record,
)
from agenttrail.audit_reader import AuditTrailReadError, read_audit_trail
from agenttrail.record_view import (
    LEGACY_DECISION_ID_TEXT,
    DuplicateDecisionIdError,
    RecordNotFoundError,
    RecordViewError,
    format_decision_record,
    lookup_decision_record,
)
from agenttrail.redaction_gate import scan_line
from support_fixtures import no_aws_credentials, no_network

MODEL_ID = "eu.anthropic.claude-sonnet-4-20250514-v1:0"
DECISION_ID_1 = "00000000-0000-4000-8000-000000000001"
DECISION_ID_2 = "00000000-0000-4000-8000-000000000002"
DECISION_ID_3 = "00000000-0000-4000-8000-000000000003"
ABSENT_ID = "ffffffff-ffff-4fff-bfff-ffffffffffff"

# Synthetic sensitive-looking value; must never reach any output.
PLANTED_NI = "AB123456C"


def record_one(**overrides):
    record = {
        "decision_id": DECISION_ID_1,
        "case_ref": "SYN-001",
        "age_band": "18-24",
        "income_band": "low",
        "evidence_status": "complete",
        "decision": "decide",
        "confidence": 0.92,
        "rationale": "Decided: complete for low applicant",
        "model_id": MODEL_ID,
        "prompt_version": "1.0.0",
        "timestamp": "2026-07-27T12:00:00Z",
    }
    record.update(overrides)
    return record


def record_two(**overrides):
    record = record_one(
        decision_id=DECISION_ID_2,
        case_ref="SYN-002",
        evidence_status="missing",
        decision="escalate",
        confidence=0.6,
        rationale="Escalated: missing for low applicant",
        timestamp="2026-07-27T12:00:05Z",
    )
    record.update(overrides)
    return record


def legacy_record(**overrides):
    record = record_one(
        case_ref="SYN-003",
        income_band="medium",
        evidence_status="partial",
        decision="escalate",
        confidence=0.85,
        rationale="Escalated: partial for medium applicant",
        timestamp="2026-07-27T12:00:10Z",
    )
    del record["decision_id"]
    record.update(overrides)
    return record


def write_trail(tmp, records, name="trail.jsonl"):
    path = Path(tmp) / name
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def run_cli(argv):
    stdout, stderr = StringIO(), StringIO()
    with mock.patch.object(sys, "stdout", stdout), \
            mock.patch.object(sys, "stderr", stderr):
        code = viewmod.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class RecordViewTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)


class TestLookup(RecordViewTestCase):
    def test_lookup_returns_the_exact_stored_record(self):
        trail = write_trail(self.tmp_path, [record_one(), record_two()])
        found = lookup_decision_record(trail, DECISION_ID_1)
        self.assertEqual(found, record_one())

    def test_lookup_selects_the_matching_record_among_many(self):
        trail = write_trail(self.tmp_path, [record_one(), record_two()])
        found = lookup_decision_record(trail, DECISION_ID_2)
        self.assertEqual(found["case_ref"], "SYN-002")
        self.assertEqual(found["decision"], "escalate")

    def test_lookup_works_on_a_trail_written_by_the_real_writer(self):
        trail = self.tmp_path / "written.jsonl"
        for record in (record_one(), record_two()):
            append_audit_record(trail, record)
        self.assertEqual(
            lookup_decision_record(trail, DECISION_ID_2), record_two()
        )

    def test_not_found_raises_record_not_found(self):
        trail = write_trail(self.tmp_path, [record_one()])
        with self.assertRaises(RecordNotFoundError) as ctx:
            lookup_decision_record(trail, ABSENT_ID)
        self.assertIn(ABSENT_ID, str(ctx.exception))

    def test_duplicate_decision_ids_are_never_silently_resolved(self):
        trail = write_trail(
            self.tmp_path,
            [record_one(), record_two(decision_id=DECISION_ID_1)],
        )
        with self.assertRaises(DuplicateDecisionIdError) as ctx:
            lookup_decision_record(trail, DECISION_ID_1)
        self.assertIn("duplicate", str(ctx.exception))

    def test_legacy_records_are_skipped_and_never_falsely_matched(self):
        trail = write_trail(self.tmp_path, [legacy_record(), record_one()])
        self.assertEqual(
            lookup_decision_record(trail, DECISION_ID_1), record_one()
        )
        with self.assertRaises(RecordNotFoundError):
            lookup_decision_record(trail, ABSENT_ID)

    def test_trail_of_only_legacy_records_reports_not_found(self):
        trail = write_trail(self.tmp_path, [legacy_record()])
        with self.assertRaises(RecordNotFoundError):
            lookup_decision_record(trail, DECISION_ID_1)

    def test_malformed_jsonl_is_distinct_from_not_found(self):
        trail = self.tmp_path / "bad.jsonl"
        trail.write_text("{not valid json\n", encoding="utf-8")
        with self.assertRaises(AuditTrailReadError) as ctx:
            lookup_decision_record(trail, DECISION_ID_1)
        self.assertNotIsInstance(ctx.exception, RecordNotFoundError)
        self.assertIn("malformed", str(ctx.exception))

    def test_blank_line_fails_closed(self):
        trail = self.tmp_path / "blank.jsonl"
        trail.write_text(
            json.dumps(record_one(), sort_keys=True) + "\n\n",
            encoding="utf-8",
        )
        with self.assertRaises(AuditTrailReadError) as ctx:
            lookup_decision_record(trail, DECISION_ID_1)
        self.assertIn("blank line", str(ctx.exception))

    def test_missing_trail_file_fails_closed(self):
        with self.assertRaises(AuditTrailReadError) as ctx:
            lookup_decision_record(
                self.tmp_path / "absent.jsonl", DECISION_ID_1
            )
        self.assertNotIsInstance(ctx.exception, RecordNotFoundError)

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_unreadable_trail_fails_closed(self):
        trail = write_trail(self.tmp_path, [record_one()])
        trail.chmod(0o000)
        try:
            with self.assertRaises(AuditTrailReadError):
                lookup_decision_record(trail, DECISION_ID_1)
        finally:
            trail.chmod(0o600)

    def test_invalid_record_structure_fails_closed(self):
        trail = write_trail(
            self.tmp_path, [record_one(decision="approve")]
        )
        with self.assertRaises(AuditTrailReadError) as ctx:
            lookup_decision_record(trail, DECISION_ID_1)
        self.assertIn("invalid audit record", str(ctx.exception))

    def test_record_with_unexpected_field_is_refused_not_served(self):
        trail = write_trail(
            self.tmp_path,
            [record_one(raw_user_input=f"NI number {PLANTED_NI}")],
        )
        with self.assertRaises(AuditTrailReadError) as ctx:
            lookup_decision_record(trail, DECISION_ID_1)
        message = str(ctx.exception)
        self.assertIn("raw_user_input", message)
        self.assertNotIn(PLANTED_NI, message)

    def test_invalid_decision_id_argument_is_rejected_without_echo(self):
        trail = write_trail(self.tmp_path, [record_one()])
        for decision_id in ("SYN-001", "", "please find case 1",
                            ABSENT_ID.upper(), None, 42):
            with self.assertRaises(RecordViewError, msg=decision_id) as ctx:
                lookup_decision_record(trail, decision_id)
            self.assertNotIsInstance(ctx.exception, RecordNotFoundError)
            if isinstance(decision_id, str) and decision_id:
                self.assertNotIn(decision_id, str(ctx.exception))

    def test_lookup_never_modifies_the_trail(self):
        trail = write_trail(self.tmp_path, [record_one(), record_two()])
        before = trail.read_bytes()
        lookup_decision_record(trail, DECISION_ID_1)
        with self.assertRaises(RecordNotFoundError):
            lookup_decision_record(trail, ABSENT_ID)
        self.assertEqual(trail.read_bytes(), before)

    def test_lookup_makes_no_network_or_model_call(self):
        trail = write_trail(self.tmp_path, [record_one()])
        with no_aws_credentials(os.environ), no_network():
            found = lookup_decision_record(trail, DECISION_ID_1)
        self.assertEqual(found, record_one())


class TestRenderer(RecordViewTestCase):
    def test_renders_all_approved_fields_with_stable_layout(self):
        self.assertEqual(
            format_decision_record(record_one()),
            "\n".join([
                "Decision record",
                "---------------",
                f"Decision ID: {DECISION_ID_1}",
                "Case reference: SYN-001",
                "",
                "Structured inputs",
                "-----------------",
                "Age band: 18-24",
                "Income band: low",
                "Evidence status: complete",
                "",
                "Outcome",
                "-------",
                "Decision: decide",
                "Confidence: 0.9200 (scale 0.0-1.0; uncalibrated)",
                "Rationale: Decided: complete for low applicant",
                "",
                "Provenance",
                "----------",
                f"Model ID: {MODEL_ID}",
                "Prompt version: 1.0.0",
                "Timestamp: 2026-07-27T12:00:00Z",
            ]),
        )

    def test_legacy_record_renders_absent_id_without_inventing_one(self):
        rendered = format_decision_record(legacy_record())
        self.assertIn(f"Decision ID: {LEGACY_DECISION_ID_TEXT}", rendered)
        self.assertIn("Case reference: SYN-003", rendered)

    def test_confidence_formatting_including_boundaries(self):
        for confidence, expected in (
            (0.0, "Confidence: 0.0000"),
            (1.0, "Confidence: 1.0000"),
            (1, "Confidence: 1.0000"),   # integer JSON number
            (0.7, "Confidence: 0.7000"),
            (0.6, "Confidence: 0.6000"),
        ):
            rendered = format_decision_record(
                record_one(confidence=confidence)
            )
            self.assertIn(expected, rendered)

    def test_unexpected_fields_are_refused_never_rendered(self):
        with self.assertRaises(AuditValidationError) as ctx:
            format_decision_record(
                record_one(raw_user_input=f"NI number {PLANTED_NI}")
            )
        self.assertNotIn(PLANTED_NI, str(ctx.exception))

    def test_output_is_never_raw_json(self):
        rendered = format_decision_record(record_one())
        self.assertNotIn("{", rendered)
        self.assertNotIn('"', rendered)

    def test_never_uses_the_word_replay(self):
        self.assertNotIn(
            "replay", format_decision_record(record_one()).lower()
        )


class TestIdentifierCompatibility(RecordViewTestCase):
    def test_build_then_lookup_round_trip_with_injected_id(self):
        record = build_audit_record(
            "SYN-001",
            {"age_band": "18-24", "income_band": "low",
             "evidence_status": "complete"},
            {"decision": "decide", "confidence": 0.92,
             "rationale": "Decided: complete for low applicant"},
            MODEL_ID,
            id_generator=lambda: DECISION_ID_3,
        )
        trail = self.tmp_path / "roundtrip.jsonl"
        append_audit_record(trail, record)
        self.assertEqual(
            lookup_decision_record(trail, DECISION_ID_3)["decision_id"],
            DECISION_ID_3,
        )

    def test_legacy_trail_remains_fully_readable(self):
        # Historical trails written before decision IDs existed must
        # still be readable evidence for evaluation and lookup alike.
        trail = write_trail(
            self.tmp_path, [legacy_record(), record_one()]
        )
        self.assertEqual(
            read_audit_trail(trail), [legacy_record(), record_one()]
        )

    def test_decision_ids_never_trigger_the_redaction_gate(self):
        # A trail an operator scans with the redaction gate must not
        # produce false findings from the new identifier.
        line = json.dumps(record_one(), sort_keys=True)
        self.assertEqual(scan_line(line), ())
        self.assertEqual(scan_line(DECISION_ID_1), ())


class TestCli(RecordViewTestCase):
    def test_success_prints_record_and_exits_zero(self):
        trail = write_trail(self.tmp_path, [record_one(), record_two()])
        code, out, err = run_cli(
            ["--trail", str(trail), "--decision-id", DECISION_ID_2]
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn(f"Decision ID: {DECISION_ID_2}", out)
        self.assertIn("Case reference: SYN-002", out)
        self.assertIn("no model call", out)
        self.assertNotIn("replay", out.lower())

    def test_output_is_deterministic_across_runs(self):
        trail = write_trail(self.tmp_path, [record_one()])
        argv = ["--trail", str(trail), "--decision-id", DECISION_ID_1]
        self.assertEqual(run_cli(argv), run_cli(argv))

    def test_success_is_fully_offline(self):
        trail = write_trail(self.tmp_path, [record_one()])
        with no_aws_credentials(os.environ), no_network():
            code, out, _ = run_cli(
                ["--trail", str(trail), "--decision-id", DECISION_ID_1]
            )
        self.assertEqual(code, 0)
        self.assertIn(f"Decision ID: {DECISION_ID_1}", out)

    def test_not_found_exits_one_with_concise_stderr(self):
        trail = write_trail(self.tmp_path, [record_one()])
        code, out, err = run_cli(
            ["--trail", str(trail), "--decision-id", ABSENT_ID]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("no audit record found", err)
        self.assertNotIn("Traceback", err)

    def test_duplicate_ids_exit_two(self):
        trail = write_trail(
            self.tmp_path,
            [record_one(), record_two(decision_id=DECISION_ID_1)],
        )
        code, out, err = run_cli(
            ["--trail", str(trail), "--decision-id", DECISION_ID_1]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("duplicate", err)
        self.assertNotIn("Traceback", err)

    def test_malformed_trail_exits_two_not_one(self):
        trail = self.tmp_path / "bad.jsonl"
        trail.write_text("{not valid json\n", encoding="utf-8")
        code, out, err = run_cli(
            ["--trail", str(trail), "--decision-id", DECISION_ID_1]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("record view error", err)
        self.assertNotIn("Traceback", err)

    def test_missing_trail_exits_two(self):
        code, out, err = run_cli([
            "--trail", str(self.tmp_path / "absent.jsonl"),
            "--decision-id", DECISION_ID_1,
        ])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("record view error", err)

    def test_case_ref_passed_as_id_exits_two_with_guidance(self):
        trail = write_trail(self.tmp_path, [record_one()])
        code, out, err = run_cli(
            ["--trail", str(trail), "--decision-id", "SYN-001"]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("case reference is not a decision ID", err)
        self.assertNotIn("Traceback", err)

    def test_planted_sensitive_field_is_never_displayed(self):
        trail = write_trail(
            self.tmp_path,
            [record_one(raw_user_input=f"NI number {PLANTED_NI}")],
        )
        code, out, err = run_cli(
            ["--trail", str(trail), "--decision-id", DECISION_ID_1]
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        for channel in (out, err):
            self.assertNotIn(PLANTED_NI, channel)
            self.assertNotIn("NI number", channel)


if __name__ == "__main__":
    unittest.main()
