"""Explicit, deliberate recording of Bedrock Converse fixtures (Ticket 4).

Records one genuine Bedrock response per golden case by driving the
existing ``decide_case`` path through a capturing wrapper, so the stored
request is byte-for-byte the production Converse request. Invoked only
by a human:

    python3 -m agenttrail.record_fixtures --model-id <id> [--region <r>]

Costs real money and requires AWS credentials. It is never invoked by
tests, package imports, replay runs, or CI, and there is no automatic or
record-on-miss behaviour anywhere. boto3 is imported only inside
``_create_live_client`` on this explicit path.

The fixture set is written atomically: entries are validated, written to
a temporary file, re-validated by loading that file, and only then moved
over the target with ``os.replace``. A failure part-way through leaves
no partial authoritative fixture file. An existing fixture set is never
overwritten unless ``--overwrite`` is supplied.

Responses are stored exactly as the model produced them (the tool input
is never rewritten to match golden labels). Only transport metadata —
SDK ResponseMetadata (HTTP headers, AWS request IDs) and per-call latency
metrics — is stripped. Credentials and environment details are never
captured because only the Converse request/response bodies are stored.
"""

import argparse
import json
import os
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from agenttrail.audit import TIMESTAMP_FORMAT
from agenttrail.decision import PROMPT_VERSION, decide_case, resolve_model_id
from agenttrail.fixtures import (
    DEFAULT_FIXTURE_PATH,
    FIXTURE_FORMAT_VERSION,
    FORBIDDEN_RESPONSE_FIELDS,
    load_fixtures,
    request_fingerprint,
    validate_fixture_entry,
)

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "golden_cases.jsonl"
)


class RecordingError(RuntimeError):
    """Fixture recording failed; no fixture set was published."""


def _utc_now():
    return datetime.now(timezone.utc)


def _create_live_client(region=None):
    # Deliberately the only place in the package that touches boto3.
    import boto3

    kwargs = {"region_name": region} if region else {}
    return boto3.client("bedrock-runtime", **kwargs)


class _CapturingClient:
    """Passes converse() through to a real client, capturing the exchange."""

    def __init__(self, live_client):
        self._live = live_client
        self.captured = []

    def converse(self, **request):
        response = self._live.converse(**request)
        self.captured.append(
            {
                "request": deepcopy(request),
                "response": strip_transport_metadata(response),
            }
        )
        return response


def strip_transport_metadata(response):
    """Copy a Converse response without transport-level metadata."""
    if not isinstance(response, dict):
        raise RecordingError("Bedrock response is not a mapping")
    return {
        key: deepcopy(value)
        for key, value in response.items()
        if key not in FORBIDDEN_RESPONSE_FIELDS
    }


def load_golden_cases(dataset_path=DEFAULT_DATASET_PATH):
    """Load golden cases, sorted by case_id, rejecting duplicates."""
    cases = []
    with open(dataset_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            record = json.loads(line)
            for field in ("case_id", "dataset_version", "input"):
                if field not in record:
                    raise RecordingError(
                        f"{dataset_path}:{line_no}: golden case missing "
                        f"{field!r}"
                    )
            cases.append(record)
    case_ids = [c["case_id"] for c in cases]
    if len(case_ids) != len(set(case_ids)):
        raise RecordingError("golden dataset contains duplicate case_ids")
    return sorted(cases, key=lambda c: c["case_id"])


def record_fixtures(cases, bedrock_client, model_id, clock=_utc_now):
    """Record one validated fixture entry per golden case, in case_id order.

    Each case goes through the production ``decide_case`` path exactly
    once; the captured request/response pair is stored verbatim (minus
    transport metadata). Any validation or model failure aborts the whole
    recording — nothing partial is returned.
    """
    recorded_at = clock().astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)
    entries = []
    seen_fingerprints = set()
    for case in sorted(cases, key=lambda c: c["case_id"]):
        capturing = _CapturingClient(bedrock_client)
        # decide_case validates the response; only parseable responses
        # can ever be recorded. Its result is deliberately unused here.
        decide_case(case["input"], capturing, model_id=model_id)
        if len(capturing.captured) != 1:
            raise RecordingError(
                f"expected exactly one converse call for {case['case_id']}, "
                f"observed {len(capturing.captured)}"
            )
        exchange = capturing.captured[0]
        fingerprint = request_fingerprint(exchange["request"])
        if fingerprint in seen_fingerprints:
            raise RecordingError(
                f"duplicate request fingerprint for {case['case_id']}"
            )
        seen_fingerprints.add(fingerprint)
        entry = {
            "fixture_format_version": FIXTURE_FORMAT_VERSION,
            "case_id": case["case_id"],
            "dataset_version": case["dataset_version"],
            "recorded_at": recorded_at,
            "model_id": model_id,
            "prompt_version": PROMPT_VERSION,
            "request_sha256": fingerprint,
            "request": exchange["request"],
            "response": exchange["response"],
        }
        validate_fixture_entry(entry)
        entries.append(entry)
    return entries


def write_fixture_file(entries, fixture_path, overwrite=False):
    """Atomically publish a complete, validated fixture set.

    Writes to a temporary file in the target directory, re-validates the
    whole file by loading it, then replaces the target in one rename.
    Refuses to touch an existing fixture set unless ``overwrite`` is True.
    """
    fixture_path = Path(fixture_path)
    if fixture_path.exists() and not overwrite:
        raise RecordingError(
            f"{fixture_path} already exists; pass --overwrite to replace "
            "it after review"
        )
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=fixture_path.parent, prefix=fixture_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(
                    json.dumps(
                        entry,
                        sort_keys=True,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        # Full contract re-check on the bytes actually written.
        load_fixtures(tmp_path)
        os.replace(tmp_path, fixture_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return fixture_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.record_fixtures",
        description=(
            "Record genuine Bedrock Converse fixtures for every golden "
            "case. Makes one paid Bedrock call per case."
        ),
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Bedrock model ID (defaults to BEDROCK_MODEL_ID)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (defaults to the SDK's resolved region)",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Golden dataset JSONL path",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_FIXTURE_PATH),
        help="Fixture JSONL output path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing fixture set (deliberate, reviewed act)",
    )
    args = parser.parse_args(argv)

    model_id = resolve_model_id(args.model_id)
    cases = load_golden_cases(args.dataset)
    if Path(args.output).exists() and not args.overwrite:
        raise RecordingError(
            f"{args.output} already exists; pass --overwrite to replace it"
        )
    client = _create_live_client(args.region)
    entries = record_fixtures(cases, client, model_id)
    write_fixture_file(entries, args.output, overwrite=args.overwrite)
    print(
        f"recorded {len(entries)} fixtures for model {model_id} "
        f"(prompt {PROMPT_VERSION}) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
