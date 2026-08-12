"""Tests for Ticket 10 policy replay.

Two layers of coverage:

* A compact synthetic world (four golden cases, a deterministic fake
  recording, a genuine v1-produced trail) exercises the full replay
  path — flips, counts, ordering, provenance, and every fail-closed
  edge — without touching committed data.
* An end-to-end test replays a trail produced from the committed golden
  dataset and the committed genuine v1 fixture recording, asserting the
  exact deterministic flip the proposed v2 policy produces.

No test here manually sets a flip flag: every flip asserted below was
derived by comparing a stored audit decision with a decision genuinely
produced through ``decide_case`` over recorded fixtures.
"""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from agenttrail.audit import (
    build_audit_record,
    append_audit_record,
    decide_case_audited,
)
from agenttrail.decision import (
    RATIONALE_TEMPLATES,
    TEMPLATE_FOR_DECISION,
)
from agenttrail.eval import resolve_fixture_model_id
from agenttrail.fixtures import (
    DEFAULT_FIXTURE_PATH,
    FixtureValidationError,
    ReplayBedrockClient,
)
from agenttrail.golden import DEFAULT_DATASET_PATH, load_labelled_cases
from agenttrail.policy_replay import (
    BASELINE_PROVENANCE_DECLARED,
    PolicyReplayError,
    format_replay_report,
    main,
    replay_policy,
)
from agenttrail.record_fixtures import record_fixtures, write_fixture_file
from agenttrail.routing_policy import RoutingPolicyError
from tests.support_fixtures import (
    MODEL_ID,
    fixed_clock,
    no_aws_credentials,
    no_network,
    tool_response,
)

# Synthetic world: deterministic fake model behaviour keyed on
# (evidence_status, income_band). Confidences are chosen to exercise
# both sides of the proposed v2 boundary (0.95): 0.85 and 0.75 flip,
# 0.95 sits exactly at the threshold and must not flip, and the
# escalation can never flip regardless of confidence.
FAKE_BEHAVIOUR = {
    ("complete", "low"): ("decide", 0.85),
    ("partial", "low"): ("escalate", 0.80),
    ("missing", "low"): ("decide", 0.95),
    ("complete", "high"): ("decide", 0.75),
}

SYNTHETIC_CASES = (
    {
        "case_id": "SYN-101",
        "input": {
            "age_band": "18-24",
            "income_band": "low",
            "evidence_status": "complete",
        },
    },
    {
        "case_id": "SYN-102",
        "input": {
            "age_band": "25-39",
            "income_band": "low",
            "evidence_status": "partial",
        },
    },
    {
        "case_id": "SYN-103",
        "input": {
            "age_band": "40-64",
            "income_band": "low",
            "evidence_status": "missing",
        },
    },
    {
        "case_id": "SYN-104",
        "input": {
            "age_band": "65-plus",
            "income_band": "high",
            "evidence_status": "complete",
        },
    },
)


class _FakeLiveClient:
    """Deterministic stand-in for the live client during recording."""

    def converse(self, **request):
        payload = json.loads(request["messages"][0]["content"][0]["text"])
        decision, confidence = FAKE_BEHAVIOUR[
            (payload["evidence_status"], payload["income_band"])
        ]
        return tool_response(
            {
                "decision": decision,
                "confidence": confidence,
                "rationale_template": TEMPLATE_FOR_DECISION[decision],
            }
        )


def _rationale(decision, case_input):
    return RATIONALE_TEMPLATES[TEMPLATE_FOR_DECISION[decision]].format(
        evidence_status=case_input["evidence_status"],
        income_band=case_input["income_band"],
    )


def _run_cli(argv):
    """Run the CLI in-process, capturing exit code, stdout, stderr."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
        stderr
    ):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class _SyntheticWorld(unittest.TestCase):
    """Builds the shared synthetic dataset, fixtures, and v1 trail."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="agenttrail-replay-")
        cls.addClassCleanup(cls._tmp.cleanup)
        root = Path(cls._tmp.name)

        cls.dataset_path = root / "golden.jsonl"
        with open(cls.dataset_path, "w", encoding="utf-8") as f:
            for case in SYNTHETIC_CASES:
                decision, confidence = FAKE_BEHAVIOUR[
                    (
                        case["input"]["evidence_status"],
                        case["input"]["income_band"],
                    )
                ]
                f.write(
                    json.dumps(
                        {
                            "case_id": case["case_id"],
                            "dataset_version": "1.0.0",
                            "input": case["input"],
                            "expected": {
                                "routing": decision,
                                "confidence_band": "medium",
                                "reason_code": "SYNTHETIC",
                            },
                        }
                    )
                    + "\n"
                )

        cls.fixture_path = root / "fixtures.jsonl"
        cases = [
            {**case, "dataset_version": "1.0.0"} for case in SYNTHETIC_CASES
        ]
        cls.fixture_entries = record_fixtures(
            cases, _FakeLiveClient(), MODEL_ID, clock=fixed_clock
        )
        write_fixture_file(cls.fixture_entries, cls.fixture_path)

        # The genuine v1-produced historical trail, written in reverse
        # case order so ordering must come from the replay, not the file.
        cls.trail_path = root / "trail.jsonl"
        client = ReplayBedrockClient(cls.fixture_path)
        for case in reversed(SYNTHETIC_CASES):
            decide_case_audited(
                case["input"],
                client,
                case_ref=case["case_id"],
                audit_path=cls.trail_path,
                model_id=MODEL_ID,
                clock=fixed_clock,
            )

    def replay(self, target="v2", **overrides):
        kwargs = {
            "fixture_path": self.fixture_path,
            "dataset_path": self.dataset_path,
            "legacy_baseline_policy": "v1",
        }
        kwargs.update(overrides)
        return replay_policy(self.trail_path, target, **kwargs)

    def write_trail(self, name, records):
        path = Path(self._tmp.name) / name
        for record in records:
            append_audit_record(path, record)
        return path

    def build_record(self, case_id, case_input, decision, confidence):
        return build_audit_record(
            case_id,
            case_input,
            {
                "decision": decision,
                "confidence": confidence,
                "rationale": _rationale(decision, case_input),
            },
            MODEL_ID,
            clock=fixed_clock,
        )


class PolicyReplayResultTest(_SyntheticWorld):
    def test_replay_against_v1_produces_no_flips(self):
        result = self.replay(target="v1")
        self.assertEqual(result.records_evaluated, 4)
        self.assertEqual(result.unchanged, 4)
        self.assertEqual(result.flipped, 0)
        self.assertEqual(result.flip_rate, 0.0)
        self.assertEqual(result.flips, ())

    def test_v2_produces_the_expected_deterministic_flips(self):
        result = self.replay()
        self.assertEqual(result.target_policy, "v2")
        self.assertEqual(result.records_evaluated, 4)
        self.assertEqual(result.unchanged, 2)
        self.assertEqual(result.flipped, 2)
        self.assertEqual(result.flip_rate, 2 / 4)
        self.assertEqual(
            [
                (
                    f.case_ref,
                    f.stored_decision,
                    f.replayed_decision,
                    f.stored_confidence,
                    f.replayed_confidence,
                )
                for f in result.flips
            ],
            [
                ("SYN-101", "decide", "escalate", 0.85, 0.85),
                ("SYN-104", "decide", "escalate", 0.75, 0.75),
            ],
        )

    def test_flips_are_sorted_by_case_ref_despite_trail_order(self):
        # The trail was written in reverse case order in setUpClass.
        result = self.replay()
        refs = [f.case_ref for f in result.flips]
        self.assertEqual(refs, sorted(refs))

    def test_decide_at_exact_v2_threshold_does_not_flip(self):
        # SYN-103 was stored as decide with confidence exactly 0.95:
        # at-threshold must stand under v2, exactly as under v1.
        result = self.replay()
        self.assertNotIn(
            "SYN-103", [f.case_ref for f in result.flips]
        )

    def test_flip_compares_stored_decision_with_genuine_replay(self):
        # A trail whose stored decision for SYN-101 is escalate (a
        # perfectly valid historical record) must flip the other way
        # under v1, because the genuine replay of the recorded response
        # routes it decide at threshold 0.70. The comparison baseline
        # is the stored audit decision — there is no side channel.
        case_input = SYNTHETIC_CASES[0]["input"]
        trail = self.write_trail(
            "stored-escalate.jsonl",
            [self.build_record("SYN-101", case_input, "escalate", 0.85)],
        )
        result = replay_policy(
            trail,
            "v1",
            fixture_path=self.fixture_path,
            dataset_path=self.dataset_path,
            legacy_baseline_policy="v1",
        )
        self.assertEqual(result.flipped, 1)
        flip = result.flips[0]
        self.assertEqual(flip.stored_decision, "escalate")
        self.assertEqual(flip.replayed_decision, "decide")

    def test_declared_legacy_baseline_is_reported(self):
        result = self.replay()
        self.assertEqual(result.baseline_policy, "v1")
        self.assertEqual(
            result.baseline_provenance, BASELINE_PROVENANCE_DECLARED
        )
        self.assertEqual(result.declared_provenance_records, 4)

    def test_report_labels_the_declaration_and_affected_count(self):
        report = format_replay_report(self.replay())
        self.assertIn("baseline policy:            v1", report)
        self.assertIn("declared legacy assumption", report)
        self.assertIn("not recorded fact", report)
        self.assertIn("records using declaration:  4", report)
        self.assertIn("evidence, not an approval", report)

    def test_report_rendering_is_byte_stable(self):
        first = format_replay_report(self.replay())
        second = format_replay_report(self.replay())
        self.assertEqual(first, second)
        self.assertIn("- SYN-101: decide -> escalate", first)

    def test_report_omits_flip_section_when_nothing_flipped(self):
        report = format_replay_report(self.replay(target="v1"))
        self.assertNotIn("flipped cases:", report)
        self.assertIn("flipped:                    0", report)


class PolicyReplayProvenanceTest(_SyntheticWorld):
    def test_missing_legacy_declaration_fails(self):
        with self.assertRaises(PolicyReplayError) as ctx:
            self.replay(legacy_baseline_policy=None)
        message = str(ctx.exception)
        self.assertIn("--legacy-baseline-policy v1", message)
        self.assertIn("AC-25", message)

    def test_policy_version_is_not_inferred_from_prompt_version(self):
        # Every record in the trail carries prompt_version 1.0.0, yet
        # without an explicit declaration the replay must still refuse:
        # a prompt version can never establish the routing policy.
        trail_lines = self.trail_path.read_text(encoding="utf-8").splitlines()
        for line in trail_lines:
            self.assertEqual(json.loads(line)["prompt_version"], "1.0.0")
        with self.assertRaises(PolicyReplayError) as ctx:
            self.replay(legacy_baseline_policy=None)
        self.assertIn("never inferred from prompt_version", str(ctx.exception))

    def test_unsupported_legacy_declaration_fails(self):
        for bad in ("v2", "v0", "V1", ""):
            with self.assertRaises(PolicyReplayError) as ctx:
                self.replay(legacy_baseline_policy=bad)
            self.assertIn(
                "unsupported legacy baseline declaration", str(ctx.exception)
            )


class PolicyReplayFailClosedTest(_SyntheticWorld):
    def test_unknown_target_policy_fails(self):
        with self.assertRaises(RoutingPolicyError):
            self.replay(target="v9")

    def test_empty_trail_fails(self):
        empty = Path(self._tmp.name) / "empty-trail.jsonl"
        empty.touch()
        with self.assertRaises(PolicyReplayError) as ctx:
            replay_policy(
                empty,
                "v2",
                fixture_path=self.fixture_path,
                dataset_path=self.dataset_path,
                legacy_baseline_policy="v1",
            )
        self.assertIn("no records", str(ctx.exception))

    def test_record_missing_required_fields_fails(self):
        broken = Path(self._tmp.name) / "broken-trail.jsonl"
        first_line = self.trail_path.read_text(encoding="utf-8").splitlines()[0]
        record = json.loads(first_line)
        del record["decision"]
        broken.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaises(Exception) as ctx:
            replay_policy(
                broken,
                "v2",
                fixture_path=self.fixture_path,
                dataset_path=self.dataset_path,
                legacy_baseline_policy="v1",
            )
        self.assertIn("missing fields", str(ctx.exception))

    def test_duplicate_case_refs_fail(self):
        case_input = SYNTHETIC_CASES[0]["input"]
        trail = self.write_trail(
            "duplicate-trail.jsonl",
            [
                self.build_record("SYN-101", case_input, "decide", 0.85),
                self.build_record("SYN-101", case_input, "decide", 0.85),
            ],
        )
        with self.assertRaises(PolicyReplayError) as ctx:
            replay_policy(
                trail,
                "v2",
                fixture_path=self.fixture_path,
                dataset_path=self.dataset_path,
                legacy_baseline_policy="v1",
            )
        self.assertIn("duplicate audit records", str(ctx.exception))

    def test_record_unmatched_to_a_source_case_fails(self):
        case_input = SYNTHETIC_CASES[0]["input"]
        trail = self.write_trail(
            "unmatched-trail.jsonl",
            [self.build_record("SYN-199", case_input, "decide", 0.85)],
        )
        with self.assertRaises(PolicyReplayError) as ctx:
            replay_policy(
                trail,
                "v2",
                fixture_path=self.fixture_path,
                dataset_path=self.dataset_path,
                legacy_baseline_policy="v1",
            )
        self.assertIn("cannot be matched to a source case", str(ctx.exception))

    def test_record_disagreeing_with_source_input_fails(self):
        altered = dict(SYNTHETIC_CASES[0]["input"], age_band="65-plus")
        trail = self.write_trail(
            "disagreeing-trail.jsonl",
            [self.build_record("SYN-101", altered, "decide", 0.85)],
        )
        with self.assertRaises(PolicyReplayError) as ctx:
            replay_policy(
                trail,
                "v2",
                fixture_path=self.fixture_path,
                dataset_path=self.dataset_path,
                legacy_baseline_policy="v1",
            )
        self.assertIn("disagrees with the source case", str(ctx.exception))

    def test_unknown_prompt_version_fails(self):
        case_input = SYNTHETIC_CASES[0]["input"]
        record = build_audit_record(
            "SYN-101",
            case_input,
            {
                "decision": "decide",
                "confidence": 0.85,
                "rationale": _rationale("decide", case_input),
            },
            MODEL_ID,
            prompt_version="9.9.9",
            clock=fixed_clock,
        )
        trail = self.write_trail("unknown-prompt-trail.jsonl", [record])
        with self.assertRaises(PolicyReplayError) as ctx:
            replay_policy(
                trail,
                "v2",
                fixture_path=self.fixture_path,
                dataset_path=self.dataset_path,
                legacy_baseline_policy="v1",
            )
        self.assertIn("unknown prompt_version", str(ctx.exception))

    def test_missing_fixture_fails_closed(self):
        # A fixture set covering only three of the four recorded cases:
        # nothing is skipped, the replay fails instead.
        subset_path = Path(self._tmp.name) / "subset-fixtures.jsonl"
        subset = [
            e for e in self.fixture_entries if e["case_id"] != "SYN-104"
        ]
        write_fixture_file(subset, subset_path)
        with self.assertRaises(PolicyReplayError) as ctx:
            self.replay(fixture_path=subset_path)
        self.assertIn("replay failed for case SYN-104", str(ctx.exception))
        self.assertIn("no recorded fixture", str(ctx.exception))

    def test_tampered_fixture_fingerprint_fails_closed(self):
        # Alter a stored request without updating request_sha256: the
        # existing fingerprint validation must reject the file.
        tampered_path = Path(self._tmp.name) / "tampered-fixtures.jsonl"
        entries = [json.loads(json.dumps(e)) for e in self.fixture_entries]
        entries[0]["request"]["system"][0]["text"] += " tampered"
        with open(tampered_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        with self.assertRaises(FixtureValidationError) as ctx:
            self.replay(fixture_path=tampered_path)
        self.assertIn("does not match", str(ctx.exception))

    def test_duplicate_fixture_entries_fail_closed(self):
        duplicated_path = Path(self._tmp.name) / "duplicate-fixtures.jsonl"
        with open(duplicated_path, "w", encoding="utf-8") as f:
            for entry in [self.fixture_entries[0], self.fixture_entries[0]]:
                f.write(json.dumps(entry) + "\n")
        with self.assertRaises(FixtureValidationError) as ctx:
            self.replay(fixture_path=duplicated_path)
        self.assertIn("duplicate", str(ctx.exception))

    def test_replay_makes_no_network_call_and_needs_no_credentials(self):
        with no_network(), no_aws_credentials(os.environ):
            result = self.replay()
        self.assertEqual(result.flipped, 2)

    def test_trail_file_is_byte_for_byte_unchanged_by_replay(self):
        before = hashlib.sha256(self.trail_path.read_bytes()).hexdigest()
        self.replay()
        self.replay(target="v1")
        after = hashlib.sha256(self.trail_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)


class PolicyReplayCliTest(_SyntheticWorld):
    def cli_args(self, *extra):
        return [
            "--audit-path",
            str(self.trail_path),
            "--fixtures",
            str(self.fixture_path),
            "--dataset",
            str(self.dataset_path),
            *extra,
        ]

    def test_valid_replay_with_flips_exits_zero(self):
        code, stdout, stderr = _run_cli(
            self.cli_args(
                "--target-policy", "v2", "--legacy-baseline-policy", "v1"
            )
        )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("flipped:                    2", stdout)
        self.assertIn("- SYN-101: decide -> escalate", stdout)

    def test_cli_output_is_byte_stable_across_runs(self):
        args = self.cli_args(
            "--target-policy", "v2", "--legacy-baseline-policy", "v1"
        )
        first = _run_cli(args)
        second = _run_cli(args)
        self.assertEqual(first, second)

    def test_missing_declaration_exits_nonzero_without_report(self):
        code, stdout, stderr = _run_cli(
            self.cli_args("--target-policy", "v2")
        )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("--legacy-baseline-policy v1", stderr)

    def test_unsupported_declaration_exits_nonzero(self):
        code, stdout, stderr = _run_cli(
            self.cli_args(
                "--target-policy", "v2", "--legacy-baseline-policy", "v2"
            )
        )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("unsupported legacy baseline declaration", stderr)

    def test_unknown_target_policy_is_rejected_by_the_cli(self):
        with self.assertRaises(SystemExit) as ctx:
            _run_cli(self.cli_args("--target-policy", "v9"))
        self.assertEqual(ctx.exception.code, 2)

    def test_missing_trail_exits_nonzero(self):
        code, stdout, stderr = _run_cli(
            [
                "--audit-path",
                str(Path(self._tmp.name) / "does-not-exist.jsonl"),
                "--fixtures",
                str(self.fixture_path),
                "--dataset",
                str(self.dataset_path),
                "--target-policy",
                "v2",
                "--legacy-baseline-policy",
                "v1",
            ]
        )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("policy replay error", stderr)


class CommittedInputsEndToEndTest(unittest.TestCase):
    """Replay over a trail produced from the committed golden dataset
    and the committed genuine v1 fixture recording."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="agenttrail-replay-e2e-")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.trail_path = Path(cls._tmp.name) / "trail.jsonl"
        client = ReplayBedrockClient(DEFAULT_FIXTURE_PATH)
        model_id = resolve_fixture_model_id(DEFAULT_FIXTURE_PATH)
        for case in load_labelled_cases(DEFAULT_DATASET_PATH):
            decide_case_audited(
                case.model_input,
                client,
                case_ref=case.case_id,
                audit_path=cls.trail_path,
                model_id=model_id,
                clock=fixed_clock,
            )

    def test_v2_replay_flips_exactly_the_one_below_threshold_decide(self):
        # The committed v1 recording holds decide@0.95 x11,
        # decide@0.90 x1 (SYN-031), escalate@0.90 x24. Raising the
        # escalation threshold to 0.95 flips exactly SYN-031.
        result = replay_policy(
            self.trail_path, "v2", legacy_baseline_policy="v1"
        )
        self.assertEqual(result.records_evaluated, 36)
        self.assertEqual(result.unchanged, 35)
        self.assertEqual(result.flipped, 1)
        self.assertEqual(result.flip_rate, 1 / 36)
        flip = result.flips[0]
        self.assertEqual(flip.case_ref, "SYN-031")
        self.assertEqual(flip.stored_decision, "decide")
        self.assertEqual(flip.replayed_decision, "escalate")
        self.assertEqual(flip.stored_confidence, 0.9)
        self.assertEqual(flip.replayed_confidence, 0.9)

    def test_v1_replay_of_a_v1_trail_produces_no_flips(self):
        result = replay_policy(
            self.trail_path, "v1", legacy_baseline_policy="v1"
        )
        self.assertEqual(result.records_evaluated, 36)
        self.assertEqual(result.flipped, 0)

    def test_end_to_end_cli_run_succeeds_offline(self):
        args = [
            "--audit-path",
            str(self.trail_path),
            "--target-policy",
            "v2",
            "--legacy-baseline-policy",
            "v1",
        ]
        with no_network(), no_aws_credentials(os.environ):
            code, stdout, stderr = _run_cli(args)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("records evaluated:          36", stdout)
        self.assertIn("flipped:                    1", stdout)
        self.assertIn(
            "- SYN-031: decide -> escalate (stored confidence 0.9000, "
            "replayed confidence 0.9000)",
            stdout,
        )


if __name__ == "__main__":
    unittest.main()
