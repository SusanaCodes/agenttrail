"""Replay tests over the committed genuine fixture set (Ticket 4).

These tests run against fixtures/bedrock-converse-v1.jsonl — real
recorded Bedrock responses. Until the explicit live recording has been
performed and reviewed, the whole module is skipped with an honest
reason rather than fabricating fixtures to turn it green.

Needs no AWS credentials and makes no Bedrock calls: the full run is
executed with socket functions patched to fail and AWS credential
variables scrubbed.
"""

import os
import tempfile
import unittest
from pathlib import Path

from agenttrail.audit import decide_case_audited
from agenttrail.decision import PROMPT_VERSION, decide_case
from agenttrail.fixtures import (
    DEFAULT_FIXTURE_PATH,
    ReplayBedrockClient,
    load_fixtures,
)
from agenttrail.record_fixtures import load_golden_cases
from support_fixtures import no_aws_credentials, no_network

FIXTURES_RECORDED = DEFAULT_FIXTURE_PATH.is_file()
SKIP_REASON = (
    f"{DEFAULT_FIXTURE_PATH} not recorded yet — genuine Bedrock fixtures "
    "require the explicit approved run of "
    "python3 -m agenttrail.record_fixtures"
)


@unittest.skipUnless(FIXTURES_RECORDED, SKIP_REASON)
class TestRecordedFixtureReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden_cases = load_golden_cases()
        cls.fixtures = load_fixtures(DEFAULT_FIXTURE_PATH)
        cls.client = ReplayBedrockClient(DEFAULT_FIXTURE_PATH)
        model_ids = {e["model_id"] for e in cls.fixtures.values()}
        assert len(model_ids) == 1, "fixture set spans multiple model IDs"
        cls.model_id = model_ids.pop()

    def replay_all(self):
        return [
            decide_case(case["input"], self.client, model_id=self.model_id)
            for case in self.golden_cases
        ]

    def test_every_golden_case_has_exactly_one_fixture(self):
        golden_ids = [c["case_id"] for c in self.golden_cases]
        fixture_ids = sorted(e["case_id"] for e in self.fixtures.values())
        self.assertEqual(fixture_ids, sorted(golden_ids))

    def test_no_fixture_for_unknown_golden_case(self):
        golden_ids = {c["case_id"] for c in self.golden_cases}
        for entry in self.fixtures.values():
            self.assertIn(entry["case_id"], golden_ids)

    def test_provenance_matches_current_contract(self):
        by_case = {c["case_id"]: c for c in self.golden_cases}
        for entry in self.fixtures.values():
            self.assertEqual(entry["prompt_version"], PROMPT_VERSION)
            self.assertEqual(
                entry["dataset_version"],
                by_case[entry["case_id"]]["dataset_version"],
            )

    def test_every_recorded_response_passes_the_decision_parser(self):
        # decide_case succeeding implies the recorded tool call parsed,
        # validated, and rendered an allow-listed rationale.
        results = self.replay_all()
        self.assertEqual(len(results), 36)
        for result in results:
            self.assertEqual(
                set(result), {"decision", "confidence", "rationale"}
            )
            self.assertIn(result["decision"], ("decide", "escalate"))

    def test_two_full_runs_are_identical(self):
        self.assertEqual(self.replay_all(), self.replay_all())

    def test_full_run_offline_without_aws_credentials(self):
        with no_aws_credentials(os.environ), no_network():
            # Reload from disk inside the guard: proving the whole replay
            # path — load, fingerprint, decide — needs no network or creds.
            client = ReplayBedrockClient(DEFAULT_FIXTURE_PATH)
            first = [
                decide_case(case["input"], client, model_id=self.model_id)
                for case in self.golden_cases
            ]
            second = [
                decide_case(case["input"], client, model_id=self.model_id)
                for case in self.golden_cases
            ]
        self.assertEqual(first, second)

    def test_audited_path_works_with_replay_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "replay.audit.jsonl"
            for case in self.golden_cases:
                result = decide_case_audited(
                    case["input"],
                    self.client,
                    case_ref=case["case_id"],
                    audit_path=audit_path,
                    model_id=self.model_id,
                )
                self.assertIn(result["decision"], ("decide", "escalate"))
            with open(audit_path, encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 36)


if __name__ == "__main__":
    unittest.main()
