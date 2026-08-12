"""Policy replay: what would change under a proposed policy (Ticket 10).

Replays historical audited cases under an explicitly versioned
alternative routing policy and reports which stored routing decisions
would change. It answers one governance question:

> What would have changed in past routing decisions if this proposed
> policy had been applied?

A flip is a case whose replayed routing decision — genuinely produced by
the production decision path under the target policy — differs from the
routing decision stored in the historical audit record. This is
change-impact analysis only: a replay full of flips is a successful
replay, never a gate failure, and nothing here approves or rejects the
proposed policy.

The pipeline is deliberately end-to-end and reuses the existing
machinery rather than restating any of it:

    audit trail -> audit_reader (validated records)
                -> golden dataset (source-case match)
                -> ReplayBedrockClient (exact fixture fingerprint)
                -> decide_case under the target policy's threshold
                -> stored vs replayed decision -> flip report

Audit-integrity guarantees:

* Read-only: the trail is opened by the standard reader and never
  modified, rewritten, or backfilled.
* The recorded model response is retrieved only through the exact
  request-fingerprint fixture mechanism. Confidence is never copied out
  of the audit record and re-thresholded as a fake "replay" — the
  response is re-parsed and re-routed by the production path.
* Reusing recorded responses is sound only because a routing-policy
  change applies AFTER the model response. A changed prompt would
  change the canonical request fingerprint, so prompt replay works only
  where exact fixtures for that prompt already exist; recording new
  fixtures is outside this module and there is no live fallback.
* Missing, duplicate, malformed, or mismatched fixtures and records
  fail closed. No record is silently skipped: an incomplete replay
  would understate policy impact, so it fails instead.

Policy provenance: historical records carry ``prompt_version`` but not
``policy_version`` (future storage is AC-25), and a prompt version can
never establish which routing policy was in force. Records without
policy provenance are rejected unless the operator explicitly declares
the legacy baseline (``--legacy-baseline-policy v1``); the report then
states prominently that the baseline is a declared assumption, not
recorded fact.

Offline by construction — the only Bedrock client used is
``ReplayBedrockClient``; no live call, no AWS credentials, no network.

Exit codes: 0 for any complete valid replay (with or without flips), 2
for invalid arguments, unknown policies, a missing legacy declaration,
invalid records, unmatched cases, or fixture failures.
"""

import argparse
import sys
from dataclasses import dataclass

from agenttrail.audit import AuditValidationError
from agenttrail.audit_reader import AuditTrailReadError, read_audit_trail
from agenttrail.decision import (
    INPUT_ENUMS,
    CaseValidationError,
    ModelResponseError,
    decide_case,
)
from agenttrail.fixtures import (
    DEFAULT_FIXTURE_PATH,
    FixtureNotFoundError,
    FixtureValidationError,
    ReplayBedrockClient,
)
from agenttrail.golden import (
    DEFAULT_DATASET_PATH,
    GoldenDatasetError,
    load_labelled_cases,
)
from agenttrail.routing_policy import (
    LEGACY_BASELINE_POLICY_KEY,
    SUPPORTED_ROUTING_POLICY_KEYS,
    RoutingPolicyError,
    resolve_routing_policy,
)
from agenttrail.versions import AGENT_VERSIONS, AgentVersionError

# The fixed provenance wording for a baseline supplied by the operator's
# legacy declaration rather than read from the records themselves.
BASELINE_PROVENANCE_DECLARED = "declared legacy assumption"


class PolicyReplayError(RuntimeError):
    """The replay could not produce a trustworthy report. Fail closed."""


# Every failure the replay deliberately fails closed on, for the CLI's
# single error-to-exit-code mapping. Mirrors eval.EVALUATION_ERRORS.
REPLAY_ERRORS = (
    PolicyReplayError,
    RoutingPolicyError,
    AgentVersionError,
    GoldenDatasetError,
    AuditTrailReadError,
    AuditValidationError,
    FixtureValidationError,
    FixtureNotFoundError,
    CaseValidationError,
    ModelResponseError,
    OSError,
)


@dataclass(frozen=True)
class FlippedCase:
    """One case whose replayed routing differs from the stored routing.

    Confidences are included because they materially explain a
    threshold flip; they expose no case content beyond what the audit
    record already carries.
    """

    case_ref: str
    stored_decision: str
    replayed_decision: str
    stored_confidence: float
    replayed_confidence: float


@dataclass(frozen=True)
class PolicyReplayResult:
    """Machine-readable outcome of one complete policy replay."""

    baseline_policy: str
    baseline_provenance: str
    declared_provenance_records: int
    target_policy: str
    target_rule: str
    records_evaluated: int
    unchanged: int
    flipped: int
    flip_rate: float
    flips: tuple


def _validate_provenance(records, legacy_baseline_policy):
    """Enforce explicit policy provenance for every record.

    Returns the number of records whose baseline rests on the operator's
    legacy declaration. ``policy_version`` is looked for on the record
    itself and nowhere else — in particular it is never inferred from
    ``prompt_version``, which identifies the prompt contract, not the
    routing policy in force.
    """
    if legacy_baseline_policy is not None and (
        legacy_baseline_policy != LEGACY_BASELINE_POLICY_KEY
    ):
        raise PolicyReplayError(
            f"unsupported legacy baseline declaration "
            f"{legacy_baseline_policy!r}: production has only ever run "
            f"routing policy {LEGACY_BASELINE_POLICY_KEY!r}, so that is "
            "the only baseline that may be declared for records without "
            "stored policy provenance"
        )
    undeclared = sum(1 for r in records if "policy_version" not in r)
    if undeclared and legacy_baseline_policy is None:
        raise PolicyReplayError(
            f"{undeclared} audit record(s) carry no policy_version "
            "(stored policy provenance is future work, AC-25) and no "
            "legacy baseline was declared; pass --legacy-baseline-policy "
            f"{LEGACY_BASELINE_POLICY_KEY} to declare explicitly that "
            "these records were produced under routing policy "
            f"{LEGACY_BASELINE_POLICY_KEY}. This declaration is an "
            "operator-supplied assumption, not recorded fact, and is "
            "never inferred from prompt_version"
        )
    return undeclared


def replay_policy(
    audit_path,
    target_policy,
    fixture_path=DEFAULT_FIXTURE_PATH,
    dataset_path=DEFAULT_DATASET_PATH,
    legacy_baseline_policy=None,
):
    """Replay a historical trail under ``target_policy``; report flips.

    Every record is replayed or the whole run fails — a partially
    replayed trail would understate policy impact. The trail itself is
    only ever read, via the standard audit reader.
    """
    target = resolve_routing_policy(target_policy)

    records = read_audit_trail(audit_path)
    if not records:
        raise PolicyReplayError(
            f"audit trail contains no records: {audit_path}; refusing to "
            "report a replay over zero records"
        )

    declared_records = _validate_provenance(records, legacy_baseline_policy)

    cases_by_id = {
        case.case_id: case for case in load_labelled_cases(dataset_path)
    }
    # The prompt contract that produced each record, resolved from the
    # RECORDED prompt_version so the rebuilt request is exactly the
    # recorded one. This reconstructs the prompt only — it says nothing
    # about policy provenance, which is handled above.
    version_by_prompt = {
        version.prompt_version: version
        for version in AGENT_VERSIONS.values()
    }

    # Fails closed on a missing or invalid fixture set before any replay.
    client = ReplayBedrockClient(fixture_path)

    seen_case_refs = set()
    flips = []
    unchanged = 0
    # case_ref ascending: the canonical deterministic replay order.
    for record in sorted(records, key=lambda r: r["case_ref"]):
        case_ref = record["case_ref"]
        if case_ref in seen_case_refs:
            raise PolicyReplayError(
                f"duplicate audit records for case {case_ref}; the trail "
                "is ambiguous about which stored decision is the baseline"
            )
        seen_case_refs.add(case_ref)

        case = cases_by_id.get(case_ref)
        if case is None:
            raise PolicyReplayError(
                f"audit record for case {case_ref} cannot be matched to a "
                f"source case in {dataset_path}"
            )
        stored_input = {field: record[field] for field in INPUT_ENUMS}
        if stored_input != case.model_input:
            raise PolicyReplayError(
                f"audit record for case {case_ref} disagrees with the "
                "source case's input fields; refusing to replay a "
                "different case under its reference"
            )

        version = version_by_prompt.get(record["prompt_version"])
        if version is None:
            raise PolicyReplayError(
                f"audit record for case {case_ref} was produced by "
                f"unknown prompt_version {record['prompt_version']!r}; "
                "the recorded request cannot be reconstructed"
            )

        # The genuine production path: request construction, exact
        # fixture fingerprint lookup, model-response validation, and
        # routing under the target policy's threshold. The replay owns
        # no copy of any of it.
        try:
            replayed = decide_case(
                case.model_input,
                client,
                model_id=record["model_id"],
                confidence_threshold=target.confidence_threshold,
                system_instruction=version.system_instruction,
            )
        except (FixtureNotFoundError, ModelResponseError) as exc:
            raise PolicyReplayError(
                f"replay failed for case {case_ref}: {exc}"
            ) from exc

        if replayed["decision"] == record["decision"]:
            unchanged += 1
        else:
            flips.append(
                FlippedCase(
                    case_ref=case_ref,
                    stored_decision=record["decision"],
                    replayed_decision=replayed["decision"],
                    stored_confidence=record["confidence"],
                    replayed_confidence=replayed["confidence"],
                )
            )

    evaluated = len(records)
    return PolicyReplayResult(
        baseline_policy=LEGACY_BASELINE_POLICY_KEY,
        baseline_provenance=BASELINE_PROVENANCE_DECLARED,
        declared_provenance_records=declared_records,
        target_policy=target.key,
        target_rule=target.rule,
        records_evaluated=evaluated,
        unchanged=unchanged,
        flipped=len(flips),
        flip_rate=len(flips) / evaluated,
        flips=tuple(flips),
    )


def format_replay_report(result):
    """Deterministic plain-text report built only from controlled values.

    The baseline-provenance declaration is stated once, prominently, at
    report level; it covers every record counted on the line below it.
    """
    rate = result.flip_rate
    lines = [
        "AgentTrail policy replay",
        f"baseline policy:            {result.baseline_policy}",
        f"baseline provenance:        {result.baseline_provenance} "
        "(operator-supplied, not recorded fact)",
        f"records using declaration:  {result.declared_provenance_records}",
        f"target policy:              {result.target_policy} "
        f"({result.target_rule})",
        f"records evaluated:          {result.records_evaluated}",
        f"unchanged:                  {result.unchanged}",
        f"flipped:                    {result.flipped}",
        f"flip rate:                  {rate:.4f} ({rate * 100:.2f}%)",
    ]
    if result.flips:
        lines.append("flipped cases:")
        lines.extend(
            f"- {flip.case_ref}: {flip.stored_decision} -> "
            f"{flip.replayed_decision} "
            f"(stored confidence {flip.stored_confidence:.4f}, "
            f"replayed confidence {flip.replayed_confidence:.4f})"
            for flip in result.flips
        )
    lines.append(
        "change-impact analysis only: this report is evidence, not an "
        "approval or rejection of the target policy"
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.policy_replay",
        description=(
            "Replay a historical audit trail under an alternative "
            "routing policy and report which stored routing decisions "
            "would change. Read-only over the trail, offline, "
            "deterministic: model responses come from recorded fixtures "
            "matched by exact request fingerprint; no AWS credentials "
            "or network access are used. Flips are successful output, "
            "not a failure."
        ),
    )
    parser.add_argument(
        "--audit-path",
        required=True,
        help="path to the historical append-only audit trail (JSONL)",
    )
    parser.add_argument(
        "--fixtures",
        default=str(DEFAULT_FIXTURE_PATH),
        help=(
            "recorded fixture JSONL path; defaults to the committed "
            "v1 recording"
        ),
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="golden dataset JSONL path (source cases for the records)",
    )
    parser.add_argument(
        "--target-policy",
        required=True,
        choices=SUPPORTED_ROUTING_POLICY_KEYS,
        help="routing policy to replay the trail under",
    )
    parser.add_argument(
        "--legacy-baseline-policy",
        default=None,
        help=(
            "explicit declaration that records without stored policy "
            f"provenance were produced under this policy; only "
            f"{LEGACY_BASELINE_POLICY_KEY!r} is declarable. Required "
            "for current records, which predate stored policy_version "
            "(AC-25)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = replay_policy(
            args.audit_path,
            args.target_policy,
            fixture_path=args.fixtures,
            dataset_path=args.dataset,
            legacy_baseline_policy=args.legacy_baseline_policy,
        )
    except REPLAY_ERRORS as exc:
        print(f"policy replay error: {exc}", file=sys.stderr)
        return 2

    print(f"audit trail:                {args.audit_path}")
    print(f"fixtures:                   {args.fixtures}")
    print(f"dataset:                    {args.dataset}")
    print(format_replay_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
