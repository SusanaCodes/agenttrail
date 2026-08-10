"""Synthesise the SYNTHETIC v2 demo fixture set (Ticket 9).

Generates ``fixtures/bedrock-converse-v2-synthetic.jsonl``: the
deterministic response set for the intentionally unsafe ``v2`` agent
version registered in ``agenttrail.versions``. Unlike the genuine v1
recording made by ``agenttrail.record_fixtures``, every entry here is
SYNTHETIC — no Bedrock call is made, no AWS credentials are used, and
nothing in this file may ever be presented as a captured live response.
The provenance markers are deliberate and threefold: the file name says
``synthetic``, every response's ``toolUseId`` starts with
``tooluse_synthetic_demo_``, and ``recorded_at`` is the fixed synthesis
date below, not a live capture time.

What the set encodes: the plausible behaviour of an agent whose prompt
(v2, ``2.0.0``) makes it over-confident. Three of the twelve golden
low-confidence cases — ``AFFECTED_CASE_IDS`` — return a confident
``decide`` instead of escalating; every other case mirrors the decision,
confidence, and rationale template of the genuine v1 recording for the
same case. The result is a visible, explainable regression: 9/12
low-confidence escalations, rate 0.7500, and a blocked CI gate.

Integrity is not weakened: entries are built by driving the production
``decide_case`` request path (so the stored request is byte-for-byte the
v2 Converse request and the synthetic response must parse through the
production extractor), validated by the standard fixture contract, and
published atomically via the recorder's own writer. Output is
byte-for-byte reproducible — the committed file must always equal a
fresh run, which tests/test_demo_scenario.py asserts.

    python3 -m agenttrail.demo_fixtures [--overwrite]
"""

import argparse
import sys
from copy import deepcopy
from pathlib import Path

from agenttrail.decision import TEMPLATE_FOR_DECISION, decide_case
from agenttrail.fixtures import (
    FIXTURE_FORMAT_VERSION,
    FixtureValidationError,
    load_fixtures,
    request_fingerprint,
    validate_fixture_entry,
)
from agenttrail.record_fixtures import (
    DEFAULT_DATASET_PATH,
    RecordingError,
    load_golden_cases,
    write_fixture_file,
)
from agenttrail.versions import AGENT_VERSIONS

V2 = AGENT_VERSIONS["v2"]

# Fixed synthesis date (when this generator was authored), so output is
# byte-for-byte reproducible. It is NOT a live-capture time.
SYNTHETIC_RECORDED_AT = "2026-08-10T00:00:00Z"

SYNTHETIC_TOOL_USE_ID_PREFIX = "tooluse_synthetic_demo_"

# The low-confidence golden cases the over-confident v2 agent
# auto-decides instead of escalating. Three of twelve: enough to make
# the regression unmistakable (rate 0.7500 against a required 1.0000)
# while leaving the rest of the set untouched and easy to review.
AFFECTED_CASE_IDS = ("SYN-003", "SYN-015", "SYN-027")

# At or above the 0.70 threshold, so the escalation override in
# decide_case does not rescue the case: the unsafe decide stands.
OVERCONFIDENT_CONFIDENCE = 0.92

OVERCONFIDENT_TOOL_INPUT = {
    "decision": "decide",
    "confidence": OVERCONFIDENT_CONFIDENCE,
    "rationale_template": TEMPLATE_FOR_DECISION["decide"],
}


class _SyntheticReplyClient:
    """Returns one prepared synthetic response, capturing the request."""

    def __init__(self, response):
        self._response = response
        self.requests = []

    def converse(self, **request):
        self.requests.append(deepcopy(request))
        return deepcopy(self._response)


def _synthetic_response(case_id, tool_input):
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": (
                                SYNTHETIC_TOOL_USE_ID_PREFIX + case_id
                            ),
                            "name": "submit_decision",
                            "input": deepcopy(tool_input),
                        }
                    }
                ],
            }
        },
        "stopReason": "tool_use",
    }


def _v1_tool_input(v1_by_case, case_id):
    entry = v1_by_case.get(case_id)
    if entry is None:
        raise RecordingError(
            f"no v1 fixture for case {case_id}; the v1 set must cover "
            "every golden case before the v2 demo set can mirror it"
        )
    content = entry["response"]["output"]["message"]["content"]
    return deepcopy(content[0]["toolUse"]["input"])


def synthesize_v2_fixtures(
    dataset_path=DEFAULT_DATASET_PATH,
    v1_fixture_path=AGENT_VERSIONS["v1"].fixture_path,
):
    """Build the complete validated v2 entry list, in case_id order.

    Affected cases get the over-confident ``decide``; all others mirror
    the v1 recording's tool input. Every request is produced by the
    production ``decide_case`` path under the v2 system instruction, and
    every synthetic response must parse through the production response
    extractor before it is stored.
    """
    cases = load_golden_cases(dataset_path)
    v1_fixtures = load_fixtures(v1_fixture_path)
    v1_by_case = {e["case_id"]: e for e in v1_fixtures.values()}

    model_ids = {e["model_id"] for e in v1_fixtures.values()}
    if len(model_ids) != 1:
        raise RecordingError(
            "v1 fixture set must cover exactly one model ID, found "
            f"{len(model_ids)}"
        )
    model_id = model_ids.pop()

    case_ids = {c["case_id"] for c in cases}
    missing = sorted(set(AFFECTED_CASE_IDS) - case_ids)
    if missing:
        raise RecordingError(
            f"affected demo cases are not in the golden dataset: {missing}"
        )
    low_ids = {
        c["case_id"]
        for c in cases
        if c.get("expected", {}).get("confidence_band") == "low"
    }
    not_low = sorted(set(AFFECTED_CASE_IDS) - low_ids)
    if not_low:
        raise RecordingError(
            "affected demo cases must be labelled low-confidence, "
            f"but these are not: {not_low}"
        )

    entries = []
    for case in cases:
        case_id = case["case_id"]
        if case_id in AFFECTED_CASE_IDS:
            tool_input = deepcopy(OVERCONFIDENT_TOOL_INPUT)
        else:
            tool_input = _v1_tool_input(v1_by_case, case_id)
        response = _synthetic_response(case_id, tool_input)
        client = _SyntheticReplyClient(response)
        # Drives the real request builder and response extractor; a
        # synthetic response the production path cannot parse can never
        # be published.
        decide_case(
            case["input"],
            client,
            model_id=model_id,
            system_instruction=V2.system_instruction,
        )
        if len(client.requests) != 1:
            raise RecordingError(
                f"expected exactly one converse call for {case_id}, "
                f"observed {len(client.requests)}"
            )
        request = client.requests[0]
        entry = {
            "fixture_format_version": FIXTURE_FORMAT_VERSION,
            "case_id": case_id,
            "dataset_version": case["dataset_version"],
            "recorded_at": SYNTHETIC_RECORDED_AT,
            "model_id": model_id,
            "prompt_version": V2.prompt_version,
            "request_sha256": request_fingerprint(request),
            "request": request,
            "response": response,
        }
        validate_fixture_entry(entry)
        entries.append(entry)
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.demo_fixtures",
        description=(
            "Synthesise the deterministic v2 demo fixture set. Entirely "
            "offline: no Bedrock call, no AWS credentials, no network. "
            "Every entry is synthetic and marked as such."
        ),
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Golden dataset JSONL path",
    )
    parser.add_argument(
        "--output",
        default=str(V2.fixture_path),
        help="Fixture JSONL output path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing fixture set (deliberate, reviewed act)",
    )
    args = parser.parse_args(argv)

    try:
        entries = synthesize_v2_fixtures(dataset_path=args.dataset)
        if Path(args.output).exists() and not args.overwrite:
            raise RecordingError(
                f"{args.output} already exists; pass --overwrite to "
                "replace it"
            )
        write_fixture_file(entries, args.output, overwrite=args.overwrite)
    except (RecordingError, FixtureValidationError, OSError) as exc:
        print(f"demo fixture synthesis failed: {exc}", file=sys.stderr)
        return 2

    print(
        f"synthesised {len(entries)} SYNTHETIC v2 demo fixtures "
        f"(prompt {V2.prompt_version}, affected cases: "
        f"{', '.join(AFFECTED_CASE_IDS)}) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
