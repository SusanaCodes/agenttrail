"""Shared helpers for the Ticket 4 fixture tests.

Not a test module (unittest discover only collects test*.py). Provides a
deterministic fake Bedrock client, a canned tool response builder, a
recorded-to-a-temp-file fixture set, and a no-network guard. Fake data
here is test scaffolding for the replay machinery only — it is never
written to the committed fixture path and never presented as a genuine
recording.
"""

import json
import socket
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from unittest import mock

from agenttrail.decision import TOOL_NAME
from agenttrail.record_fixtures import record_fixtures, write_fixture_file

MODEL_ID = "test-model-id"


def fixed_clock():
    return datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


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


# Deterministic fake model behaviour keyed on evidence_status.
FAKE_TOOL_INPUTS = {
    "complete": {
        "decision": "decide",
        "confidence": 0.95,
        "rationale_template": "DECIDED_EVIDENCE_FOR_INCOME",
    },
    "partial": {
        "decision": "escalate",
        "confidence": 0.85,
        "rationale_template": "ESCALATED_EVIDENCE_FOR_INCOME",
    },
    "missing": {
        "decision": "escalate",
        "confidence": 0.6,
        "rationale_template": "ESCALATED_EVIDENCE_FOR_INCOME",
    },
}


class FakeLiveBedrockClient:
    """Stands in for the live bedrock-runtime client in recorder tests.

    Returns a valid, deterministic tool response derived from the case
    payload, wrapped in the transport metadata a real SDK response
    carries, so tests can prove that metadata is stripped from fixtures.
    """

    def __init__(self, fail_after=None):
        self.calls = []
        self.fail_after = fail_after

    def converse(self, **request):
        self.calls.append(deepcopy(request))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RuntimeError("injected live-client failure")
        payload = json.loads(request["messages"][0]["content"][0]["text"])
        response = tool_response(
            deepcopy(FAKE_TOOL_INPUTS[payload["evidence_status"]])
        )
        response["usage"] = {
            "inputTokens": 100,
            "outputTokens": 25,
            "totalTokens": 125,
        }
        response["metrics"] = {"latencyMs": 321}
        response["ResponseMetadata"] = {
            "RequestId": "fake-request-id",
            "HTTPStatusCode": 200,
            "HTTPHeaders": {"x-amzn-requestid": "fake-request-id"},
        }
        return response


def record_temp_fixture_set(cases, fixture_path, model_id=MODEL_ID):
    """Record a fixture set from the fake client into a temp path."""
    client = FakeLiveBedrockClient()
    entries = record_fixtures(cases, client, model_id, clock=fixed_clock)
    write_fixture_file(entries, fixture_path)
    return entries, client


@contextmanager
def no_network():
    """Patch socket connection functions to fail immediately."""

    def _refuse(*args, **kwargs):
        raise AssertionError("network access attempted during replay")

    with mock.patch.object(socket, "socket", side_effect=_refuse), \
            mock.patch.object(socket, "create_connection", side_effect=_refuse), \
            mock.patch.object(socket, "getaddrinfo", side_effect=_refuse):
        yield


@contextmanager
def no_aws_credentials(environ):
    """Strip AWS credential/config vars and plant invalid ones."""
    scrubbed = {
        key: value
        for key, value in environ.items()
        if not key.startswith("AWS_")
    }
    scrubbed["AWS_ACCESS_KEY_ID"] = "invalid"
    scrubbed["AWS_SECRET_ACCESS_KEY"] = "invalid"
    with mock.patch.dict("os.environ", scrubbed, clear=True):
        yield
