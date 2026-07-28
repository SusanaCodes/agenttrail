"""Integration tests for the audited decision path (Ticket 3).

Fake Bedrock client only — no network, no AWS credentials. All audit
files live in temporary directories; no real project trail is touched.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from agenttrail.audit import (
    AUDIT_FIELDS,
    AuditValidationError,
    AuditWriteError,
    decide_case_audited,
)
from agenttrail.decision import (
    PROMPT_VERSION,
    TOOL_NAME,
    CaseValidationError,
    ModelResponseError,
)

VALID_CASE = {
    "age_band": "18-24",
    "income_band": "low",
    "evidence_status": "complete",
}

MODEL_ID = "eu.anthropic.claude-sonnet-4-20250514-v1:0"
CASE_REF = "SYN-001"
FIXED_TIMESTAMP = "2026-07-27T12:00:00Z"


def fixed_clock():
    return datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def tool_response(tool_input, tool_name=TOOL_NAME):
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tooluse_test",
                            "name": tool_name,
                            "input": tool_input,
                        }
                    }
                ],
            }
        },
        "stopReason": "tool_use",
    }


DECIDE_RESPONSE = tool_response({
    "decision": "decide",
    "confidence": 0.92,
    "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
})


class FakeBedrockClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class TestDecideCaseAudited(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audit_path = Path(self.tmp.name) / "trail.jsonl"

    def run_audited(self, response=DECIDE_RESPONSE, case=VALID_CASE,
                    case_ref=CASE_REF, **kwargs):
        client = FakeBedrockClient(response)
        kwargs.setdefault("model_id", MODEL_ID)
        kwargs.setdefault("clock", fixed_clock)
        result = decide_case_audited(
            case, client, case_ref, self.audit_path, **kwargs
        )
        return result, client

    def read_records(self):
        content = self.audit_path.read_text(encoding="utf-8")
        return [json.loads(line) for line in content.splitlines()]

    def test_success_returns_result_and_appends_exactly_one_record(self):
        result, _ = self.run_audited()
        self.assertEqual(result, {
            "decision": "decide",
            "confidence": 0.92,
            "rationale": "Decided: complete for low applicant",
        })
        records = self.read_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], {
            "case_ref": CASE_REF,
            "age_band": "18-24",
            "income_band": "low",
            "evidence_status": "complete",
            "decision": "decide",
            "confidence": 0.92,
            "rationale": "Decided: complete for low applicant",
            "model_id": MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "timestamp": FIXED_TIMESTAMP,
        })

    def test_every_required_field_is_present_and_populated(self):
        self.run_audited()
        record = self.read_records()[0]
        self.assertEqual(set(record), set(AUDIT_FIELDS))
        for field in AUDIT_FIELDS:
            self.assertIsNotNone(record[field], field)
            self.assertNotEqual(record[field], "", field)

    def test_two_invocations_append_two_lines_first_unchanged(self):
        self.run_audited()
        first_bytes = self.audit_path.read_bytes()
        self.run_audited(case_ref="SYN-002")
        self.assertTrue(self.audit_path.read_bytes().startswith(first_bytes))
        records = self.read_records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["case_ref"], "SYN-001")
        self.assertEqual(records[1]["case_ref"], "SYN-002")

    def test_bedrock_called_exactly_once(self):
        _, client = self.run_audited()
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["modelId"], MODEL_ID)

    def test_effective_model_id_from_env_is_persisted(self):
        env_model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        with mock.patch.dict(
            os.environ, {"BEDROCK_MODEL_ID": env_model_id}, clear=True
        ):
            _, client = self.run_audited(model_id=None)
        self.assertEqual(client.calls[0]["modelId"], env_model_id)
        self.assertEqual(self.read_records()[0]["model_id"], env_model_id)

    def test_unresolvable_model_id_means_no_call_and_no_record(self):
        client = FakeBedrockClient(DECIDE_RESPONSE)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                decide_case_audited(
                    VALID_CASE, client, CASE_REF, self.audit_path,
                    model_id=None, clock=fixed_clock,
                )
        self.assertEqual(client.calls, [])
        self.assertFalse(self.audit_path.exists())

    def test_persisted_decision_matches_threshold_override(self):
        result, _ = self.run_audited(tool_response({
            "decision": "decide",
            "confidence": 0.40,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        record = self.read_records()[0]
        self.assertEqual(result["decision"], "escalate")
        self.assertEqual(record["decision"], "escalate")
        self.assertEqual(record["confidence"], 0.40)
        self.assertEqual(
            record["rationale"], "Escalated: complete for low applicant"
        )
        self.assertEqual(record["rationale"], result["rationale"])

    def test_invalid_case_means_no_call_and_no_record(self):
        for case in (None, {}, dict(VALID_CASE, name="Jane Smith"),
                     dict(VALID_CASE, income_band="rich")):
            client = FakeBedrockClient(DECIDE_RESPONSE)
            with self.assertRaises(CaseValidationError, msg=case):
                decide_case_audited(
                    case, client, CASE_REF, self.audit_path,
                    model_id=MODEL_ID, clock=fixed_clock,
                )
            self.assertEqual(client.calls, [])
        self.assertFalse(self.audit_path.exists())

    def test_invalid_case_ref_means_no_call_and_no_record(self):
        for case_ref in ("case 1", "SYN-001\n", " SYN-001", "", None):
            client = FakeBedrockClient(DECIDE_RESPONSE)
            with self.assertRaises(AuditValidationError, msg=case_ref):
                decide_case_audited(
                    VALID_CASE, client, case_ref, self.audit_path,
                    model_id=MODEL_ID, clock=fixed_clock,
                )
            self.assertEqual(client.calls, [])
        self.assertFalse(self.audit_path.exists())

    def test_invalid_bedrock_output_writes_no_record(self):
        malformed = [
            {},
            tool_response({"decision": "approve", "confidence": 0.9,
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME"}),
            tool_response({"decision": "decide", "confidence": 0.9,
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
                           "rationale": "Jane Smith is clearly eligible"}),
        ]
        for response in malformed:
            with self.assertRaises(ModelResponseError, msg=response):
                self.run_audited(response)
        self.assertFalse(self.audit_path.exists())

    def test_write_failure_raises_and_returns_no_unaudited_decision(self):
        blocked_path = Path(self.tmp.name) / "is_a_directory"
        blocked_path.mkdir()
        client = FakeBedrockClient(DECIDE_RESPONSE)
        with self.assertRaises(AuditWriteError):
            decide_case_audited(
                VALID_CASE, client, CASE_REF, blocked_path,
                model_id=MODEL_ID, clock=fixed_clock,
            )
        # The decision happened (one call) but was never returned unaudited.
        self.assertEqual(len(client.calls), 1)

    def test_timestamp_is_canonical_and_deterministic_under_injected_clock(self):
        self.run_audited()
        self.run_audited(case_ref="SYN-002")
        for record in self.read_records():
            self.assertEqual(record["timestamp"], FIXED_TIMESTAMP)

    def test_default_clock_produces_canonical_utc_timestamp(self):
        from agenttrail.audit import TIMESTAMP_PATTERN

        client = FakeBedrockClient(DECIDE_RESPONSE)
        decide_case_audited(
            VALID_CASE, client, CASE_REF, self.audit_path, model_id=MODEL_ID
        )
        self.assertRegex(self.read_records()[0]["timestamp"], TIMESTAMP_PATTERN)


if __name__ == "__main__":
    unittest.main()
