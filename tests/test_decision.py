"""Unit tests for the Bedrock decide-or-escalate call (Ticket 2).

Uses a fake Bedrock client — no AWS credentials, network access, or
Bedrock cost. Standard library only.
"""

import json
import unittest

from agenttrail.decision import (
    CONFIDENCE_THRESHOLD,
    TOOL_NAME,
    CaseValidationError,
    ModelResponseError,
    decide_case,
    validate_case,
)

VALID_CASE = {
    "age_band": "18-24",
    "income_band": "low",
    "evidence_status": "complete",
}

MODEL_ID = "test-model-id"


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


class FakeBedrockClient:
    """Records converse() calls and returns a canned response."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class TestDecideCase(unittest.TestCase):
    def decide(self, response, case=VALID_CASE, **kwargs):
        client = FakeBedrockClient(response)
        result = decide_case(case, client, model_id=MODEL_ID, **kwargs)
        return result, client

    def test_high_confidence_decide_returned_correctly(self):
        result, _ = self.decide(tool_response({
            "decision": "decide",
            "confidence": 0.92,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        self.assertEqual(result, {
            "decision": "decide",
            "confidence": 0.92,
            "rationale": "Decided: complete for low applicant",
        })

    def test_high_confidence_escalate_returned_correctly(self):
        case = {
            "age_band": "40-64",
            "income_band": "high",
            "evidence_status": "partial",
        }
        result, _ = self.decide(tool_response({
            "decision": "escalate",
            "confidence": 0.85,
            "rationale_template": "ESCALATED_EVIDENCE_FOR_INCOME",
        }), case=case)
        self.assertEqual(result, {
            "decision": "escalate",
            "confidence": 0.85,
            "rationale": "Escalated: partial for high applicant",
        })

    def test_low_confidence_decide_becomes_escalate(self):
        result, _ = self.decide(tool_response({
            "decision": "decide",
            "confidence": 0.40,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        self.assertEqual(result["decision"], "escalate")
        self.assertEqual(
            result["rationale"], "Escalated: complete for low applicant"
        )

    def test_confidence_exactly_at_threshold_is_not_escalated(self):
        result, _ = self.decide(tool_response({
            "decision": "decide",
            "confidence": CONFIDENCE_THRESHOLD,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        self.assertEqual(result["decision"], "decide")

    def test_original_confidence_preserved_after_escalation(self):
        result, _ = self.decide(tool_response({
            "decision": "decide",
            "confidence": 0.42,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        self.assertEqual(result["decision"], "escalate")
        self.assertEqual(result["confidence"], 0.42)

    def test_threshold_is_injectable(self):
        response = tool_response({
            "decision": "decide",
            "confidence": 0.75,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        })
        result, _ = self.decide(response, confidence_threshold=0.9)
        self.assertEqual(result["decision"], "escalate")
        result, _ = self.decide(response, confidence_threshold=0.5)
        self.assertEqual(result["decision"], "decide")

    def test_rationale_rendered_from_case_fields_and_template(self):
        case = {
            "age_band": "65-plus",
            "income_band": "medium",
            "evidence_status": "missing",
        }
        result, _ = self.decide(tool_response({
            "decision": "escalate",
            "confidence": 0.90,
            "rationale_template": "ESCALATED_EVIDENCE_FOR_INCOME",
        }), case=case)
        self.assertEqual(
            result["rationale"], "Escalated: missing for medium applicant"
        )

    def test_arbitrary_model_rationale_text_cannot_enter_result(self):
        # A free-text rationale field in the tool input is an extra field
        # and must be rejected — never rendered.
        with self.assertRaises(ModelResponseError):
            self.decide(tool_response({
                "decision": "decide",
                "confidence": 0.9,
                "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
                "rationale": "Applicant Jane Smith is clearly eligible",
            }))

    def test_invalid_input_rejected_before_bedrock_called(self):
        client = FakeBedrockClient(tool_response({}))
        invalid_cases = [
            None,
            {},
            {"age_band": "18-24", "income_band": "low"},  # missing field
            dict(VALID_CASE, extra="x"),                  # extra field
            dict(VALID_CASE, income_band="rich"),         # bad enum value
            dict(VALID_CASE, case_id="SYN-001"),          # metadata leak
        ]
        for case in invalid_cases:
            with self.assertRaises(CaseValidationError, msg=case):
                decide_case(case, client, model_id=MODEL_ID)
        self.assertEqual(client.calls, [])

    def test_missing_or_malformed_tool_output_raises_typed_error(self):
        malformed_responses = [
            {},                                                     # no output
            {"output": {"message": {"content": []}}},               # no toolUse
            {"output": {"message": {"content": [{"text": "ok"}]}}},  # text only
            tool_response({"decision": "decide", "confidence": 0.9,
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME"},
                          tool_name="other_tool"),                  # wrong tool
            tool_response({"decision": "decide"}),                  # missing fields
            tool_response({"decision": "approve", "confidence": 0.9,
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME"}),
            tool_response({"decision": "decide", "confidence": "high",
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME"}),
            tool_response({"decision": "decide", "confidence": True,
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME"}),
            tool_response({"decision": "decide", "confidence": 1.4,
                           "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME"}),
            tool_response({"decision": "decide", "confidence": 0.9,
                           "rationale_template": "MADE_UP_TEMPLATE"}),
            tool_response({"decision": "decide", "confidence": 0.9,
                           "rationale_template": "ESCALATED_EVIDENCE_FOR_INCOME"}),
        ]
        for response in malformed_responses:
            with self.assertRaises(ModelResponseError, msg=response):
                self.decide(response)

    def test_invalid_confidence_threshold_rejected_before_bedrock_called(self):
        client = FakeBedrockClient(tool_response({
            "decision": "decide",
            "confidence": 0.9,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        invalid_thresholds = [
            None,
            True,
            False,
            "0.7",
            -0.1,
            1.1,
            float("nan"),
            float("inf"),
            float("-inf"),
        ]
        for threshold in invalid_thresholds:
            with self.assertRaises(ValueError, msg=threshold):
                decide_case(
                    VALID_CASE,
                    client,
                    model_id=MODEL_ID,
                    confidence_threshold=threshold,
                )
        self.assertEqual(client.calls, [])

    def test_text_alongside_valid_tool_call_raises(self):
        # The contract is tool-only output: free text next to an otherwise
        # valid tool call must be rejected, never silently ignored.
        response = tool_response({
            "decision": "decide",
            "confidence": 0.9,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        })
        response["output"]["message"]["content"].insert(
            0, {"text": "Here is my decision:"}
        )
        with self.assertRaises(ModelResponseError):
            self.decide(response)

    def test_malformed_content_raises_model_response_error(self):
        valid_tool_use = {
            "toolUseId": "tooluse_test",
            "name": TOOL_NAME,
            "input": {
                "decision": "decide",
                "confidence": 0.9,
                "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
            },
        }
        malformed_contents = [
            "not a list",
            {"toolUse": valid_tool_use},
            None,
            42,
            [42],
            ["toolUse"],
            [{"toolUse": "not an object"}],
            [{"toolUse": valid_tool_use, "text": "extra text in same block"}],
        ]
        for content in malformed_contents:
            response = {"output": {"message": {"content": content}}}
            with self.assertRaises(ModelResponseError, msg=content):
                self.decide(response)

    def test_bedrock_called_exactly_once(self):
        _, client = self.decide(tool_response({
            "decision": "decide",
            "confidence": 0.9,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        self.assertEqual(len(client.calls), 1)

    def test_only_structured_input_sent_no_labels_or_metadata(self):
        golden_record = {
            "case_id": "SYN-001",
            "dataset_version": "1.0.0",
            "input": dict(VALID_CASE),
            "expected": {
                "routing": "decide",
                "confidence_band": "high",
                "reason_code": "EVIDENCE_COMPLETE_LOW_INCOME",
            },
        }
        _, client = self.decide(tool_response({
            "decision": "decide",
            "confidence": 0.9,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }), case=golden_record["input"])

        call = client.calls[0]
        self.assertEqual(call["modelId"], MODEL_ID)
        # The user message carries exactly the validated input, sorted keys.
        messages = call["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0]["content"]), 1)
        payload = messages[0]["content"][0]["text"]
        self.assertEqual(payload, json.dumps(VALID_CASE, sort_keys=True))
        self.assertEqual(json.loads(payload), VALID_CASE)
        # No golden labels or metadata anywhere in the request.
        serialized_request = json.dumps(call, sort_keys=True, default=str)
        for forbidden in ("SYN-001", "dataset_version", "expected",
                          "routing", "confidence_band", "reason_code",
                          "EVIDENCE_COMPLETE_LOW_INCOME"):
            self.assertNotIn(forbidden, serialized_request)

    def test_request_uses_forced_tool_choice_and_deterministic_config(self):
        _, client = self.decide(tool_response({
            "decision": "decide",
            "confidence": 0.9,
            "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
        }))
        call = client.calls[0]
        self.assertEqual(
            call["toolConfig"]["toolChoice"], {"tool": {"name": TOOL_NAME}}
        )
        tool_schema = call["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
        self.assertNotIn("rationale", tool_schema["properties"])
        self.assertFalse(tool_schema["additionalProperties"])
        self.assertEqual(call["inferenceConfig"]["temperature"], 0.0)

    def test_model_id_required_when_env_unset(self):
        import os
        from unittest import mock

        client = FakeBedrockClient(tool_response({}))
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                decide_case(VALID_CASE, client)
        self.assertEqual(client.calls, [])


class TestValidateCase(unittest.TestCase):
    def test_returns_sorted_normalized_copy(self):
        validated = validate_case(VALID_CASE)
        self.assertEqual(validated, VALID_CASE)
        self.assertEqual(
            list(validated), ["age_band", "evidence_status", "income_band"]
        )


if __name__ == "__main__":
    unittest.main()
