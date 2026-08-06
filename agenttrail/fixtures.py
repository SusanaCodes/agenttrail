"""Strict replay of recorded Bedrock Converse responses (Ticket 4).

Replays fixtures recorded once from the real model so evaluation runs are
deterministic, fast, offline, credential-free, and cost-free. Matching is
by SHA-256 fingerprint of the complete canonicalised Converse request —
never merely by case ID — so any change to the prompt, tool schema, model
ID, inference configuration, or case input causes an explicit fixture
miss instead of silently replaying an obsolete response.

Fail-closed by design: there is no live fallback, no record-on-miss, and
no hybrid client. This module never imports boto3, never reads AWS
credentials, and never touches the network. Live recording lives only in
``agenttrail.record_fixtures``.

Replay proves repeatability of a recorded snapshot; it says nothing about
current live-model quality. Fixtures go stale whenever the prompt
contract, tool schema, model, or dataset changes — the fingerprint makes
that staleness loud, and re-recording is a deliberate, reviewed act.
"""

import copy
import hashlib
import json
import re
from pathlib import Path

# Reuse the audit module's identifier conventions rather than redefining
# them; fixture case_ids follow the golden dataset case_id convention.
from agenttrail.audit import (
    CASE_REF_PATTERN,
    MODEL_ID_PATTERN,
    PROMPT_VERSION_PATTERN,
    TIMESTAMP_PATTERN,
)

FIXTURE_FORMAT_VERSION = "1.0.0"

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "bedrock-converse-v1.jsonl"
)

# The complete, closed fixture entry shape. Exactly these fields.
FIXTURE_FIELDS = (
    "fixture_format_version",
    "case_id",
    "dataset_version",
    "recorded_at",
    "model_id",
    "prompt_version",
    "request_sha256",
    "request",
    "response",
)

# A stored request must be the complete Converse request produced by
# decide_case: exactly these keyword arguments, nothing stripped, nothing
# extra. All of them are covered by the fingerprint.
REQUEST_FIELDS = ("modelId", "system", "messages", "toolConfig", "inferenceConfig")

SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Transport-level metadata must never be stored in a fixture.
FORBIDDEN_RESPONSE_FIELDS = ("ResponseMetadata", "metrics")


class FixtureValidationError(ValueError):
    """A fixture file or entry violates the fixture contract."""


class FixtureNotFoundError(LookupError):
    """No recorded fixture exists for this exact request. Fail closed."""


def canonicalise_request(request):
    """Serialise a Converse request to canonical deterministic JSON.

    Sorted keys at every nesting level, compact separators, ASCII-only,
    NaN/Infinity rejected. Two structurally equal requests canonicalise
    identically regardless of dictionary insertion order.
    """
    if not isinstance(request, dict):
        raise FixtureValidationError("request must be a mapping")
    try:
        return json.dumps(
            request,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FixtureValidationError(
            f"request is not canonically JSON-serialisable: {exc}"
        ) from exc


def request_fingerprint(request):
    """SHA-256 hex digest of the canonicalised complete request."""
    canonical = canonicalise_request(request)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_pattern(entry, field, pattern):
    value = entry[field]
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise FixtureValidationError(
            f"{field} must be a string matching {pattern.pattern}"
        )


def validate_fixture_entry(entry):
    """Validate one fixture entry against the fixture contract.

    Enforces the exact closed field set, identifier patterns, the complete
    request shape, absence of transport metadata in the response, and —
    critically — that the stored request_sha256 matches a fingerprint
    recomputed from the stored request.
    """
    if not isinstance(entry, dict):
        raise FixtureValidationError("fixture entry must be a mapping")
    missing = sorted(set(FIXTURE_FIELDS) - set(entry))
    if missing:
        raise FixtureValidationError(f"fixture entry missing fields: {missing}")
    extra = sorted(set(entry) - set(FIXTURE_FIELDS))
    if extra:
        raise FixtureValidationError(
            f"fixture entry has unexpected fields: {extra}"
        )

    if entry["fixture_format_version"] != FIXTURE_FORMAT_VERSION:
        raise FixtureValidationError(
            "unsupported fixture_format_version "
            f"{entry['fixture_format_version']!r}; "
            f"this reader supports {FIXTURE_FORMAT_VERSION}"
        )
    _require_pattern(entry, "case_id", CASE_REF_PATTERN)
    _require_pattern(entry, "dataset_version", PROMPT_VERSION_PATTERN)
    _require_pattern(entry, "recorded_at", TIMESTAMP_PATTERN)
    _require_pattern(entry, "model_id", MODEL_ID_PATTERN)
    _require_pattern(entry, "prompt_version", PROMPT_VERSION_PATTERN)
    _require_pattern(entry, "request_sha256", SHA256_HEX_PATTERN)

    request = entry["request"]
    if not isinstance(request, dict):
        raise FixtureValidationError("request must be a mapping")
    if set(request) != set(REQUEST_FIELDS):
        raise FixtureValidationError(
            f"request must contain exactly the fields {sorted(REQUEST_FIELDS)}"
        )
    if request["modelId"] != entry["model_id"]:
        raise FixtureValidationError(
            "request modelId does not match the entry's model_id"
        )

    if entry["request_sha256"] != request_fingerprint(request):
        raise FixtureValidationError(
            f"request_sha256 for case {entry['case_id']} does not match the "
            "stored request; the fixture has been tampered with or corrupted"
        )

    response = entry["response"]
    if not isinstance(response, dict) or "output" not in response:
        raise FixtureValidationError(
            "response must be a mapping in Bedrock Converse shape "
            "(with an 'output' field)"
        )
    forbidden = sorted(set(response) & set(FORBIDDEN_RESPONSE_FIELDS))
    if forbidden:
        raise FixtureValidationError(
            f"response contains transport metadata fields: {forbidden}"
        )
    return entry


def load_fixtures(fixture_path):
    """Load and fully validate a fixture JSONL file.

    Returns a dict mapping request fingerprint -> fixture entry. Rejects
    unreadable files, malformed JSON lines, invalid entries, duplicate
    request fingerprints, and duplicate case_ids.
    """
    fixture_path = Path(fixture_path)
    if not fixture_path.is_file():
        raise FixtureValidationError(
            f"fixture file not found: {fixture_path}; record fixtures "
            "explicitly with python3 -m agenttrail.record_fixtures"
        )
    fixtures = {}
    seen_case_ids = set()
    with open(fixture_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                raise FixtureValidationError(
                    f"{fixture_path}:{line_no}: blank line in fixture file"
                )
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FixtureValidationError(
                    f"{fixture_path}:{line_no}: malformed JSON: {exc}"
                ) from exc
            try:
                validate_fixture_entry(entry)
            except FixtureValidationError as exc:
                raise FixtureValidationError(
                    f"{fixture_path}:{line_no}: {exc}"
                ) from exc
            fingerprint = entry["request_sha256"]
            if fingerprint in fixtures:
                raise FixtureValidationError(
                    f"{fixture_path}:{line_no}: duplicate request "
                    f"fingerprint {fingerprint}"
                )
            if entry["case_id"] in seen_case_ids:
                raise FixtureValidationError(
                    f"{fixture_path}:{line_no}: duplicate case_id "
                    f"{entry['case_id']}"
                )
            seen_case_ids.add(entry["case_id"])
            fixtures[fingerprint] = entry
    if not fixtures:
        raise FixtureValidationError(f"fixture file is empty: {fixture_path}")
    return fixtures


class ReplayBedrockClient:
    """Replays recorded Converse responses by exact request fingerprint.

    Implements the ``converse(**request)`` interface expected by
    ``decide_case``, so it is injectable wherever a bedrock-runtime
    client is. It holds no live client, imports no AWS SDK, and raises
    FixtureNotFoundError on any request that was not recorded — there is
    deliberately no fallback of any kind.
    """

    def __init__(self, fixture_path=DEFAULT_FIXTURE_PATH):
        self._fixtures = load_fixtures(fixture_path)

    def __len__(self):
        return len(self._fixtures)

    def case_ids(self):
        """Sorted case_ids covered by the loaded fixture set."""
        return sorted(e["case_id"] for e in self._fixtures.values())

    def converse(self, **request):
        fingerprint = request_fingerprint(request)
        entry = self._fixtures.get(fingerprint)
        if entry is None:
            raise FixtureNotFoundError(
                f"no recorded fixture for request fingerprint {fingerprint}; "
                "the prompt, tool schema, model ID, inference configuration, "
                "or case input differs from what was recorded. Re-record "
                "fixtures explicitly; replay never falls back to a live model"
            )
        # Deep copy so caller mutation cannot corrupt later replays.
        return copy.deepcopy(entry["response"])
