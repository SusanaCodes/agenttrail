"""Append-only JSONL audit trail for AgentTrail decisions.

One structured audit record per completed audited decision, written as one
JSON object on one line to an append-only JSONL file. This record is the
structured audit artefact designed to support Article 12 traceability; it
is consumed by the later evaluation and redaction-gate tickets.

Each new record carries a ``decision_id`` — a random, non-derived UUIDv4
generated once at record build time — so a stored record can later be
looked up by ID (``agenttrail.record_view``). Records written before the
identifier was introduced lack it and remain valid trail members.

PII is excluded by construction, not by convention:

* Records are built from an explicit allow-list of fields; the original
  case object is never serialised wholesale.
* Every string field is constrained by an enum, a bounded identifier
  pattern, or the canonical timestamp format. The rationale must be an
  exact rendering of an allow-listed template from ``agenttrail.decision``
  for the record's own decision and case fields, so arbitrary prose cannot
  enter the trail through any public function in this module.
* Validation error messages name the offending field but never echo raw
  input values, and nothing here logs complete audit records.

Delivery guarantee (be honest): each successful audited invocation appends
exactly one line. This is NOT transactional exactly-once delivery across
Bedrock and the filesystem — a crash between append and return leaves a
record the caller never saw; a crash mid-write can leave a truncated final
line. No fsync is performed. An appended record survives a process crash
but may be lost following an operating-system crash or power failure.
Concurrent writers rely on O_APPEND atomicity for a single small write,
which POSIX provides for local filesystems but network filesystems may not.
"""

import json
import math
import os
import re
import uuid
from datetime import datetime, timezone

from agenttrail.decision import (
    CONFIDENCE_THRESHOLD,
    DECISIONS,
    INPUT_ENUMS,
    PROMPT_VERSION,
    RATIONALE_TEMPLATES,
    SYSTEM_INSTRUCTION,
    TEMPLATE_FOR_DECISION,
    decide_case,
    resolve_model_id,
    validate_case,
)

# case_ref reuses the golden dataset case_id convention
# (data/golden_cases.schema.json): bounded, opaque, no prose.
CASE_REF_PATTERN = re.compile(r"^SYN-[0-9]{3}$")

# Bounded identifier for Bedrock model or inference-profile IDs
# (e.g. "eu.anthropic.claude-sonnet-4-20250514-v1:0"). No whitespace.
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

# Same convention as the golden dataset_version.
PROMPT_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# Canonical lowercase UUIDv4, as produced by new_decision_id(). Random
# and never derived from case data, so the identifier itself can carry
# no PII and never changes once written.
DECISION_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

# Single canonical RFC 3339 format: UTC, second precision, trailing "Z".
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

RESULT_FIELDS = ("decision", "confidence", "rationale")

# Every required audit field. The closed record shape is exactly these
# plus OPTIONAL_AUDIT_FIELDS below; nothing else is ever accepted.
AUDIT_FIELDS = (
    "case_ref",
    "age_band",
    "income_band",
    "evidence_status",
    "decision",
    "confidence",
    "rationale",
    "model_id",
    "prompt_version",
    "timestamp",
)

# Optional by history, not by policy: decision_id was added in Ticket 11
# and every record built here since then carries one, but records
# written earlier are still valid trail members and must stay readable.
OPTIONAL_AUDIT_FIELDS = ("decision_id",)


class AuditValidationError(ValueError):
    """An audit record (or a field destined for one) failed validation."""


class AuditWriteError(RuntimeError):
    """The append to the audit trail failed; the decision is unaudited."""


def _utc_now():
    return datetime.now(timezone.utc)


def new_decision_id():
    """Random decision identifier: canonical lowercase UUIDv4.

    Generated exactly once when a record is built and stored in the
    record; never derived from case data, the timestamp, or the record's
    position in the trail, and never regenerated during lookup.
    """
    return str(uuid.uuid4())


def _render_timestamp(clock):
    now = clock()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise AuditValidationError(
            "clock must return a timezone-aware datetime"
        )
    return now.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)


def _require_identifier(record, field, pattern):
    value = record[field]
    # fullmatch: in Python, `$` with match() would accept a trailing newline.
    if not isinstance(value, str) or not pattern.fullmatch(value):
        # Deliberately does not echo the rejected value: it may be prose.
        raise AuditValidationError(
            f"{field} must be a string matching {pattern.pattern}"
        )


def validate_audit_record(record):
    """Validate a complete audit record; raise AuditValidationError.

    Enforces the exact closed field set, all enums and identifier
    patterns, confidence bounds, the canonical timestamp format, and
    that the rationale is exactly the allow-listed template rendering
    for the record's own decision and case fields. ``decision_id`` is
    validated when present; legacy records without one remain valid.
    """
    if not isinstance(record, dict):
        raise AuditValidationError("audit record must be a mapping")
    missing = sorted(set(AUDIT_FIELDS) - set(record))
    if missing:
        raise AuditValidationError(f"audit record missing fields: {missing}")
    extra = set(record) - set(AUDIT_FIELDS) - set(OPTIONAL_AUDIT_FIELDS)
    if extra:
        # A count, not the names: an unexpected key is supplied content
        # and may itself be prose or an identifier.
        raise AuditValidationError(
            f"audit record has {len(extra)} unexpected field(s); allowed "
            f"fields: {sorted(AUDIT_FIELDS + OPTIONAL_AUDIT_FIELDS)}"
        )

    if "decision_id" in record:
        _require_identifier(record, "decision_id", DECISION_ID_PATTERN)
    _require_identifier(record, "case_ref", CASE_REF_PATTERN)
    _require_identifier(record, "model_id", MODEL_ID_PATTERN)
    _require_identifier(record, "prompt_version", PROMPT_VERSION_PATTERN)
    _require_identifier(record, "timestamp", TIMESTAMP_PATTERN)
    # Pattern match plus a real parse: rejects e.g. month 13.
    try:
        datetime.strptime(record["timestamp"], TIMESTAMP_FORMAT)
    except ValueError:
        raise AuditValidationError("timestamp is not a valid UTC datetime")

    for field, allowed in INPUT_ENUMS.items():
        if record[field] not in allowed:
            raise AuditValidationError(f"{field} is not one of {allowed}")
    if record["decision"] not in DECISIONS:
        raise AuditValidationError(f"decision is not one of {DECISIONS}")

    confidence = record["confidence"]
    if isinstance(confidence, bool) or not isinstance(
        confidence, (int, float)
    ):
        raise AuditValidationError("confidence must be numeric")
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise AuditValidationError(
            "confidence must be a finite value in [0.0, 1.0]"
        )

    # The rationale must be exactly what the decision module's template
    # mechanism renders for this decision and these case fields. This
    # reuses (never duplicates) the allow-listed templates, so arbitrary
    # rationale text can never pass validation.
    template = TEMPLATE_FOR_DECISION[record["decision"]]
    expected_rationale = RATIONALE_TEMPLATES[template].format(
        evidence_status=record["evidence_status"],
        income_band=record["income_band"],
    )
    if record["rationale"] != expected_rationale:
        raise AuditValidationError(
            "rationale is not the allow-listed template rendering for "
            "this decision and case"
        )
    return record


def build_audit_record(
    case_ref,
    case,
    result,
    model_id,
    prompt_version=PROMPT_VERSION,
    clock=_utc_now,
    id_generator=new_decision_id,
):
    """Build a validated audit record from allow-listed fields only.

    ``case`` is the structured case input and ``result`` the mapping
    returned by ``decide_case``. Both are validated; unknown fields in
    either are rejected. The timestamp and decision_id are generated
    internally from ``clock`` and ``id_generator`` (UTC now and a random
    UUIDv4 by default; both injectable for deterministic tests) —
    callers cannot supply either value directly.
    """
    validated = validate_case(case)
    if not isinstance(result, dict) or set(result) != set(RESULT_FIELDS):
        raise AuditValidationError(
            f"result must contain exactly the fields {sorted(RESULT_FIELDS)}"
        )
    record = {
        "decision_id": id_generator(),
        "case_ref": case_ref,
        "age_band": validated["age_band"],
        "income_band": validated["income_band"],
        "evidence_status": validated["evidence_status"],
        "decision": result["decision"],
        "confidence": result["confidence"],
        "rationale": result["rationale"],
        "model_id": model_id,
        "prompt_version": prompt_version,
        "timestamp": _render_timestamp(clock),
    }
    return validate_audit_record(record)


def append_audit_record(audit_path, record):
    """Append one validated record to the JSONL trail; append-only.

    The record is fully validated before the file is opened, and — in
    addition to the read-side validation, which tolerates legacy
    records — a new record is refused unless it carries a decision_id.
    The writer never generates one: build_audit_record is the only
    place an ID is created, exactly once per record. Encoding is
    deterministic (sorted keys, compact separators, ASCII-only), one JSON
    object on one line ending in exactly one newline, written with a
    single append-mode write. The file is opened with O_APPEND only —
    never read, rewritten, truncated, or deleted — and created with
    0o600 permissions where the platform honours the mode. Write failures
    raise AuditWriteError; there are no retries.
    """
    validate_audit_record(record)
    # Write-side integrity: legacy records without a decision_id stay
    # readable, but every newly appended record must carry one (already
    # pattern-validated above when present).
    if "decision_id" not in record:
        raise AuditValidationError(
            "new audit records must carry a decision_id; only records "
            "written before its introduction may lack one"
        )
    line = json.dumps(
        record, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )
    encoded = (line + "\n").encode("utf-8")
    try:
        fd = os.open(
            os.fspath(audit_path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
    except OSError as exc:
        raise AuditWriteError(f"cannot open audit trail: {exc}") from exc
    try:
        written = os.write(fd, encoded)
        if written != len(encoded):
            raise AuditWriteError(
                f"partial audit append: wrote {written} of "
                f"{len(encoded)} bytes"
            )
    except OSError as exc:
        raise AuditWriteError(f"audit append failed: {exc}") from exc
    finally:
        os.close(fd)


def decide_case_audited(
    case,
    bedrock_client,
    case_ref,
    audit_path,
    model_id=None,
    confidence_threshold=CONFIDENCE_THRESHOLD,
    prompt_version=PROMPT_VERSION,
    system_instruction=SYSTEM_INSTRUCTION,
    clock=_utc_now,
    id_generator=new_decision_id,
):
    """Decide one case with exactly one Bedrock call and one audit line.

    Orchestration: validate inputs, resolve the effective model ID once,
    call ``decide_case`` exactly once, build and validate the audit
    record, append it, and only then return the decision result.

    ``prompt_version`` and ``system_instruction`` default to the v1
    prompt contract; the Ticket 9 version registry supplies the pair
    for other agent versions, so the trail always records the prompt
    version that actually produced the decision.

    Auditing is not optional on this path. If validation, the Bedrock
    call, or model-response validation fails, zero records are written.
    If the append fails, AuditWriteError propagates and the (unaudited)
    decision is not returned.
    """
    if not isinstance(case_ref, str) or not CASE_REF_PATTERN.fullmatch(
        case_ref
    ):
        raise AuditValidationError(
            f"case_ref must be a string matching {CASE_REF_PATTERN.pattern}"
        )
    validated = validate_case(case)

    effective_model_id = resolve_model_id(model_id)
    if not isinstance(
        effective_model_id, str
    ) or not MODEL_ID_PATTERN.fullmatch(effective_model_id):
        raise AuditValidationError(
            f"model_id must be a string matching {MODEL_ID_PATTERN.pattern}"
        )

    result = decide_case(
        validated,
        bedrock_client,
        model_id=effective_model_id,
        confidence_threshold=confidence_threshold,
        system_instruction=system_instruction,
    )

    record = build_audit_record(
        case_ref,
        validated,
        result,
        effective_model_id,
        prompt_version=prompt_version,
        clock=clock,
        id_generator=id_generator,
    )
    append_audit_record(audit_path, record)
    return result
