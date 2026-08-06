"""Tests for the explicit fixture recording path (Ticket 4).

The recorder is exercised only with a fake Bedrock client — no AWS
credentials, network access, or Bedrock cost. Nothing here writes to the
committed fixture path.
"""

import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agenttrail.decision import (
    PROMPT_VERSION,
    ModelResponseError,
    decide_case,
)
from agenttrail.fixtures import (
    FIXTURE_FORMAT_VERSION,
    ReplayBedrockClient,
    load_fixtures,
    request_fingerprint,
)
from agenttrail.record_fixtures import (
    RecordingError,
    load_golden_cases,
    record_fixtures,
    strip_transport_metadata,
    write_fixture_file,
)
from support_fixtures import (
    FAKE_TOOL_INPUTS,
    MODEL_ID,
    FakeLiveBedrockClient,
    fixed_clock,
    tool_response,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_CASES = load_golden_cases(REPO_ROOT / "data" / "golden_cases.jsonl")


class TestRecordFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixtures.jsonl"

    def test_exactly_one_converse_call_per_golden_case(self):
        client = FakeLiveBedrockClient()
        entries = record_fixtures(
            GOLDEN_CASES, client, MODEL_ID, clock=fixed_clock
        )
        self.assertEqual(len(GOLDEN_CASES), 36)
        self.assertEqual(len(client.calls), 36)
        self.assertEqual(len(entries), 36)

    def test_entries_ordered_by_case_id_regardless_of_input_order(self):
        shuffled = list(reversed(GOLDEN_CASES))
        entries = record_fixtures(
            shuffled, FakeLiveBedrockClient(), MODEL_ID, clock=fixed_clock
        )
        case_ids = [e["case_id"] for e in entries]
        self.assertEqual(case_ids, sorted(case_ids))
        self.assertEqual(case_ids, [c["case_id"] for c in GOLDEN_CASES])

    def test_provenance_and_integrity_fields(self):
        entries = record_fixtures(
            GOLDEN_CASES[:3], FakeLiveBedrockClient(), MODEL_ID,
            clock=fixed_clock,
        )
        for entry, case in zip(entries, GOLDEN_CASES[:3]):
            self.assertEqual(
                entry["fixture_format_version"], FIXTURE_FORMAT_VERSION
            )
            self.assertEqual(entry["case_id"], case["case_id"])
            self.assertEqual(
                entry["dataset_version"], case["dataset_version"]
            )
            self.assertEqual(entry["recorded_at"], "2026-07-29T12:00:00Z")
            self.assertEqual(entry["model_id"], MODEL_ID)
            self.assertEqual(entry["prompt_version"], PROMPT_VERSION)
            self.assertEqual(
                entry["request_sha256"], request_fingerprint(entry["request"])
            )

    def test_response_stored_verbatim_minus_transport_metadata(self):
        entries = record_fixtures(
            GOLDEN_CASES[:1], FakeLiveBedrockClient(), MODEL_ID,
            clock=fixed_clock,
        )
        response = entries[0]["response"]
        self.assertNotIn("ResponseMetadata", response)
        self.assertNotIn("metrics", response)
        # Model-produced content and usage provenance are preserved.
        expected = tool_response(
            deepcopy(FAKE_TOOL_INPUTS["complete"])
        )
        self.assertEqual(response["output"], expected["output"])
        self.assertEqual(response["stopReason"], "tool_use")
        self.assertEqual(response["usage"]["totalTokens"], 125)

    def test_strip_transport_metadata_does_not_mutate_original(self):
        original = FakeLiveBedrockClient().converse(
            modelId=MODEL_ID,
            system=[{"text": "s"}],
            messages=[{"role": "user", "content": [{"text": json.dumps(
                GOLDEN_CASES[0]["input"], sort_keys=True)}]}],
            toolConfig={},
            inferenceConfig={},
        )
        stripped = strip_transport_metadata(original)
        self.assertIn("ResponseMetadata", original)
        self.assertNotIn("ResponseMetadata", stripped)
        stripped["output"] = None
        self.assertIsNotNone(original["output"])

    def test_malformed_model_response_aborts_recording(self):
        class BrokenClient:
            def converse(self, **request):
                return {"output": {"message": {"content": []}}}

        with self.assertRaises(ModelResponseError):
            record_fixtures(
                GOLDEN_CASES[:2], BrokenClient(), MODEL_ID, clock=fixed_clock
            )

    def test_write_refuses_existing_file_without_overwrite(self):
        entries = record_fixtures(
            GOLDEN_CASES[:2], FakeLiveBedrockClient(), MODEL_ID,
            clock=fixed_clock,
        )
        write_fixture_file(entries, self.path)
        original_bytes = self.path.read_bytes()
        with self.assertRaisesRegex(RecordingError, "already exists"):
            write_fixture_file(entries, self.path)
        self.assertEqual(self.path.read_bytes(), original_bytes)
        write_fixture_file(entries, self.path, overwrite=True)
        self.assertEqual(self.path.read_bytes(), original_bytes)

    def test_failed_write_leaves_no_partial_or_temp_file(self):
        entries = record_fixtures(
            GOLDEN_CASES[:2], FakeLiveBedrockClient(), MODEL_ID,
            clock=fixed_clock,
        )
        # Corrupt one entry after recording: publish must fail closed.
        entries[1]["request_sha256"] = "0" * 64
        with self.assertRaises(Exception):
            write_fixture_file(entries, self.path)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_live_client_failure_mid_run_produces_no_entries(self):
        client = FakeLiveBedrockClient(fail_after=3)
        with self.assertRaisesRegex(RuntimeError, "injected"):
            record_fixtures(GOLDEN_CASES, client, MODEL_ID, clock=fixed_clock)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_round_trip_record_then_replay_is_identical_twice(self):
        entries = record_fixtures(
            GOLDEN_CASES, FakeLiveBedrockClient(), MODEL_ID, clock=fixed_clock
        )
        write_fixture_file(entries, self.path)
        replay = ReplayBedrockClient(self.path)
        runs = [
            [
                decide_case(case["input"], replay, model_id=MODEL_ID)
                for case in GOLDEN_CASES
            ]
            for _ in range(2)
        ]
        self.assertEqual(runs[0], runs[1])
        live = [
            decide_case(
                case["input"], FakeLiveBedrockClient(), model_id=MODEL_ID
            )
            for case in GOLDEN_CASES
        ]
        self.assertEqual(runs[0], live)

    def test_written_file_is_canonical_jsonl(self):
        entries = record_fixtures(
            GOLDEN_CASES[:2], FakeLiveBedrockClient(), MODEL_ID,
            clock=fixed_clock,
        )
        write_fixture_file(entries, self.path)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line, entry in zip(lines, entries):
            self.assertEqual(
                line,
                json.dumps(
                    entry,
                    sort_keys=True,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            )
        self.assertEqual(len(load_fixtures(self.path)), 2)

    def test_duplicate_golden_case_ids_rejected(self):
        cases = [GOLDEN_CASES[0], deepcopy(GOLDEN_CASES[0])]
        with self.assertRaises(RecordingError):
            record_fixtures(
                cases, FakeLiveBedrockClient(), MODEL_ID, clock=fixed_clock
            )

    def test_importing_recorder_does_not_import_boto3(self):
        self.assertIn("agenttrail.record_fixtures", sys.modules)
        self.assertNotIn("boto3", sys.modules)


class TestLoadGoldenCases(unittest.TestCase):
    def test_loads_all_36_cases_sorted_and_unique(self):
        case_ids = [c["case_id"] for c in GOLDEN_CASES]
        self.assertEqual(len(case_ids), 36)
        self.assertEqual(case_ids, sorted(case_ids))
        self.assertEqual(len(set(case_ids)), 36)


if __name__ == "__main__":
    unittest.main()
