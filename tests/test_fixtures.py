"""Unit tests for strict fixture replay (Ticket 4).

No AWS credentials, no network, no Bedrock cost. Fixture files used here
are synthetic test scaffolding written to temporary directories — never
the committed fixture path, and never presented as genuine recordings.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from agenttrail.decision import decide_case
from agenttrail.fixtures import (
    FIXTURE_FIELDS,
    FIXTURE_FORMAT_VERSION,
    REQUEST_FIELDS,
    FixtureNotFoundError,
    FixtureValidationError,
    ReplayBedrockClient,
    canonicalise_request,
    load_fixtures,
    request_fingerprint,
    validate_fixture_entry,
)
from agenttrail.record_fixtures import record_fixtures
from support_fixtures import (
    MODEL_ID,
    FakeLiveBedrockClient,
    fixed_clock,
    no_network,
    record_temp_fixture_set,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SCHEMA_PATH = REPO_ROOT / "data" / "bedrock_fixture.schema.json"

SAMPLE_CASES = [
    {
        "case_id": "SYN-001",
        "dataset_version": "1.0.0",
        "input": {
            "age_band": "18-24",
            "income_band": "low",
            "evidence_status": "complete",
        },
    },
    {
        "case_id": "SYN-002",
        "dataset_version": "1.0.0",
        "input": {
            "age_band": "18-24",
            "income_band": "low",
            "evidence_status": "partial",
        },
    },
    {
        "case_id": "SYN-003",
        "dataset_version": "1.0.0",
        "input": {
            "age_band": "18-24",
            "income_band": "low",
            "evidence_status": "missing",
        },
    },
]


def sample_entries():
    client = FakeLiveBedrockClient()
    return record_fixtures(SAMPLE_CASES, client, MODEL_ID, clock=fixed_clock)


def write_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def entry_lines(entries):
    return [
        json.dumps(e, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        for e in entries
    ]


class TestCanonicalisation(unittest.TestCase):
    def test_hash_independent_of_key_insertion_order(self):
        a = {
            "modelId": "m",
            "system": [{"text": "s"}],
            "messages": [{"role": "user", "content": [{"text": "x"}]}],
            "toolConfig": {"tools": [], "toolChoice": {"tool": {"name": "t"}}},
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 256},
        }
        b = {
            "inferenceConfig": {"maxTokens": 256, "temperature": 0.0},
            "toolConfig": {"toolChoice": {"tool": {"name": "t"}}, "tools": []},
            "messages": [{"content": [{"text": "x"}], "role": "user"}],
            "system": [{"text": "s"}],
            "modelId": "m",
        }
        self.assertEqual(canonicalise_request(a), canonicalise_request(b))
        self.assertEqual(request_fingerprint(a), request_fingerprint(b))

    def test_meaningful_request_change_changes_hash(self):
        base = {
            "modelId": "m",
            "system": [{"text": "s"}],
            "messages": [{"role": "user", "content": [{"text": "x"}]}],
            "toolConfig": {"tools": [], "toolChoice": {"tool": {"name": "t"}}},
            "inferenceConfig": {"temperature": 0.0, "maxTokens": 256},
        }
        variants = [
            dict(base, modelId="other-model"),
            dict(base, system=[{"text": "changed system prompt"}]),
            dict(base, messages=[
                {"role": "user", "content": [{"text": "y"}]}
            ]),
            dict(base, toolConfig={
                "tools": [], "toolChoice": {"tool": {"name": "renamed"}}
            }),
            dict(base, inferenceConfig={"temperature": 0.5, "maxTokens": 256}),
        ]
        base_fp = request_fingerprint(base)
        fingerprints = {base_fp}
        for variant in variants:
            fp = request_fingerprint(variant)
            self.assertNotEqual(fp, base_fp, variant)
            fingerprints.add(fp)
        self.assertEqual(len(fingerprints), len(variants) + 1)

    def test_fingerprint_is_sha256_hex(self):
        fp = request_fingerprint({"modelId": "m"})
        self.assertRegex(fp, r"^[0-9a-f]{64}$")

    def test_non_serialisable_request_rejected(self):
        with self.assertRaises(FixtureValidationError):
            request_fingerprint({"modelId": object()})
        with self.assertRaises(FixtureValidationError):
            request_fingerprint({"inferenceConfig": float("nan")})
        with self.assertRaises(FixtureValidationError):
            request_fingerprint("not a mapping")


class TestFixtureValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixtures.jsonl"
        self.entries = sample_entries()

    def test_valid_entries_load(self):
        write_lines(self.path, entry_lines(self.entries))
        fixtures = load_fixtures(self.path)
        self.assertEqual(len(fixtures), len(SAMPLE_CASES))

    def test_malformed_json_line_rejected(self):
        write_lines(self.path, entry_lines(self.entries) + ["{not json"])
        with self.assertRaisesRegex(FixtureValidationError, "malformed JSON"):
            load_fixtures(self.path)

    def test_missing_required_fields_rejected(self):
        for field in FIXTURE_FIELDS:
            entry = copy.deepcopy(self.entries[0])
            del entry[field]
            with self.assertRaises(FixtureValidationError, msg=field):
                validate_fixture_entry(entry)

    def test_extra_field_rejected(self):
        entry = copy.deepcopy(self.entries[0])
        entry["aws_secret"] = "leak"
        with self.assertRaisesRegex(FixtureValidationError, "unexpected"):
            validate_fixture_entry(entry)

    def test_unsupported_format_version_rejected(self):
        entry = copy.deepcopy(self.entries[0])
        entry["fixture_format_version"] = "9.0.0"
        with self.assertRaisesRegex(FixtureValidationError, "format_version"):
            validate_fixture_entry(entry)

    def test_duplicate_request_fingerprints_rejected(self):
        lines = entry_lines([self.entries[0], self.entries[0]])
        write_lines(self.path, lines)
        with self.assertRaisesRegex(FixtureValidationError, "duplicate request"):
            load_fixtures(self.path)

    def test_duplicate_case_id_rejected(self):
        # Same case_id, different request (so a distinct fingerprint).
        twin = copy.deepcopy(self.entries[1])
        twin["case_id"] = self.entries[0]["case_id"]
        write_lines(self.path, entry_lines([self.entries[0], twin]))
        with self.assertRaisesRegex(FixtureValidationError, "duplicate case_id"):
            load_fixtures(self.path)

    def test_stored_request_hash_mismatch_rejected(self):
        entry = copy.deepcopy(self.entries[0])
        entry["request"]["messages"][0]["content"][0]["text"] = "tampered"
        with self.assertRaisesRegex(FixtureValidationError, "request_sha256"):
            validate_fixture_entry(entry)

    def test_request_shape_enforced(self):
        entry = copy.deepcopy(self.entries[0])
        del entry["request"]["toolConfig"]
        with self.assertRaises(FixtureValidationError):
            validate_fixture_entry(entry)
        entry = copy.deepcopy(self.entries[0])
        entry["request"]["extraField"] = 1
        with self.assertRaises(FixtureValidationError):
            validate_fixture_entry(entry)
        self.assertEqual(
            set(REQUEST_FIELDS),
            {"modelId", "system", "messages", "toolConfig", "inferenceConfig"},
        )

    def test_model_id_must_match_request_model_id(self):
        entry = copy.deepcopy(self.entries[0])
        entry["model_id"] = "some-other-model"
        with self.assertRaisesRegex(FixtureValidationError, "modelId"):
            validate_fixture_entry(entry)

    def test_transport_metadata_in_response_rejected(self):
        for field in ("ResponseMetadata", "metrics"):
            entry = copy.deepcopy(self.entries[0])
            entry["response"][field] = {"RequestId": "abc"}
            entry["request_sha256"] = request_fingerprint(entry["request"])
            with self.assertRaisesRegex(
                FixtureValidationError, "transport metadata", msg=field
            ):
                validate_fixture_entry(entry)

    def test_missing_blank_or_empty_fixture_file_rejected(self):
        with self.assertRaisesRegex(FixtureValidationError, "not found"):
            load_fixtures(self.path)
        write_lines(self.path, [])
        with self.assertRaisesRegex(FixtureValidationError, "empty"):
            load_fixtures(self.path)
        write_lines(self.path, entry_lines(self.entries) + [""])
        with self.assertRaisesRegex(FixtureValidationError, "blank line"):
            load_fixtures(self.path)

    def test_schema_file_agrees_with_runtime_contract(self):
        with open(FIXTURE_SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        self.assertEqual(set(schema["required"]), set(FIXTURE_FIELDS))
        self.assertFalse(schema["additionalProperties"])
        props = schema["properties"]
        self.assertEqual(
            props["fixture_format_version"]["const"], FIXTURE_FORMAT_VERSION
        )
        self.assertEqual(
            set(props["request"]["required"]), set(REQUEST_FIELDS)
        )
        self.assertEqual(props["request_sha256"]["pattern"], "^[0-9a-f]{64}$")


class TestReplayClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixtures.jsonl"
        record_temp_fixture_set(SAMPLE_CASES, self.path)
        self.client = ReplayBedrockClient(self.path)

    def test_replay_through_decide_case_matches_fake_run(self):
        for case in SAMPLE_CASES:
            live = decide_case(
                case["input"], FakeLiveBedrockClient(), model_id=MODEL_ID
            )
            replayed = decide_case(
                case["input"], self.client, model_id=MODEL_ID
            )
            self.assertEqual(replayed, live, case["case_id"])

    def test_unknown_request_raises_fixture_not_found(self):
        unknown = {
            "age_band": "65-plus",
            "income_band": "high",
            "evidence_status": "missing",
        }
        with self.assertRaises(FixtureNotFoundError):
            decide_case(unknown, self.client, model_id=MODEL_ID)

    def test_changed_model_id_misses_even_for_recorded_case(self):
        with self.assertRaises(FixtureNotFoundError):
            decide_case(
                SAMPLE_CASES[0]["input"], self.client, model_id="other-model"
            )

    def test_fixture_miss_fails_closed_without_network(self):
        # Even with network functions patched to assert, a miss raises
        # FixtureNotFoundError: there is no live fallback to attempt.
        with no_network():
            with self.assertRaises(FixtureNotFoundError):
                decide_case(
                    SAMPLE_CASES[0]["input"], self.client, model_id="other"
                )

    def test_replay_returns_deep_copies(self):
        first = decide_case(
            SAMPLE_CASES[0]["input"], self.client, model_id=MODEL_ID
        )
        # Mutate a raw replayed response as a hostile caller would.
        raw = self.client.converse(**self._recorded_request())
        raw["output"]["message"]["content"][0]["toolUse"]["input"][
            "decision"
        ] = "escalate"
        raw["output"]["message"]["content"].append({"text": "junk"})
        second = decide_case(
            SAMPLE_CASES[0]["input"], self.client, model_id=MODEL_ID
        )
        self.assertEqual(second, first)

    def _recorded_request(self):
        fixtures = load_fixtures(self.path)
        entry = next(
            e for e in fixtures.values() if e["case_id"] == "SYN-001"
        )
        return copy.deepcopy(entry["request"])

    def test_replay_module_never_imports_boto3(self):
        # The replay module is imported and exercised by this point; a
        # boto3 import anywhere on the replay path would show up here.
        self.assertNotIn("boto3", sys.modules)
        source = (
            REPO_ROOT / "agenttrail" / "fixtures.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import boto3", source)
        self.assertNotIn("from boto3", source)

    def test_full_replay_run_offline_and_repeatable(self):
        with no_network():
            runs = [
                [
                    decide_case(case["input"], self.client, model_id=MODEL_ID)
                    for case in SAMPLE_CASES
                ]
                for _ in range(2)
            ]
        self.assertEqual(runs[0], runs[1])


if __name__ == "__main__":
    unittest.main()
