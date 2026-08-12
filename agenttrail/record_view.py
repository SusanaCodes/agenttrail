"""Record view: look up one stored decision record by ID (Ticket 11).

Reads the append-only JSONL audit trail and renders one already-stored
decision record for a human auditor, investigator, or governance
reviewer. This is a stored-record lookup, not a replay: nothing here
invokes Bedrock, the agent, or any network service; no decision is
regenerated; and the trail is never modified during lookup.

Rendering is allow-listed by construction. The view prints exactly the
approved structured audit fields with fixed labels and ordering — it
never dumps a raw object or raw JSON. A record carrying any field
outside the audit allow-list fails validation and the lookup refuses to
render it at all, so an unexpected sensitive value can never reach the
output. This is deliberately narrow: it does not detect or redact
arbitrary PII; the safety property is that only approved,
already-structured fields are ever rendered.

Legacy records written before the decision ID was introduced are valid
trail members but carry no ID, so a lookup skips them — they can never
match, falsely or otherwise, and never cause a crash.

Exit codes: 0 record found and rendered, 1 no record carries the given
decision ID, 2 the trail cannot serve as evidence (missing or
unreadable file, malformed JSONL, invalid record, duplicate decision
IDs) or the decision-ID argument is not a valid identifier.
"""

import argparse
import sys
from pathlib import Path

from agenttrail.audit import (
    DECISION_ID_PATTERN,
    AuditValidationError,
    validate_audit_record,
)
from agenttrail.audit_reader import AuditTrailReadError, iter_audit_records


class RecordViewError(ValueError):
    """The lookup could not produce trustworthy output. Fail closed."""


class RecordNotFoundError(RecordViewError):
    """No stored record carries the requested decision ID."""


class DuplicateDecisionIdError(RecordViewError):
    """More than one stored record carries the same decision ID."""


# Shown instead of an ID for records written before decision IDs
# existed. Never a substitute identifier — such records cannot be
# looked up by ID at all.
LEGACY_DECISION_ID_TEXT = "(not recorded; record predates decision IDs)"


def lookup_decision_record(trail_path, decision_id):
    """Return the single stored record whose decision_id matches.

    Streams the trail one line at a time without rewriting it. Raises
    RecordViewError for an invalid decision-ID argument,
    AuditTrailReadError for a missing, unreadable, malformed, or
    invalid trail (deliberately distinct from "not found"),
    DuplicateDecisionIdError when more than one record matches, and
    RecordNotFoundError when none does.
    """
    if not isinstance(decision_id, str) or not DECISION_ID_PATTERN.fullmatch(
        decision_id
    ):
        # Deliberately does not echo the rejected value: it may be prose.
        raise RecordViewError(
            "decision id must be a string matching "
            f"{DECISION_ID_PATTERN.pattern} (a case reference is not a "
            "decision ID)"
        )
    trail = Path(trail_path)
    if not trail.is_file():
        raise AuditTrailReadError(
            f"audit trail is not a readable file: {trail}"
        )
    match = None
    try:
        for record in iter_audit_records(trail):
            # Legacy records predate decision IDs; they never match.
            if record.get("decision_id") != decision_id:
                continue
            if match is not None:
                raise DuplicateDecisionIdError(
                    f"duplicate audit records for decision {decision_id}; "
                    "refusing to choose between them"
                )
            match = record
    except OSError as exc:
        raise AuditTrailReadError(
            f"cannot read audit trail {trail}: {exc.__class__.__name__}"
        ) from exc
    if match is None:
        raise RecordNotFoundError(
            f"no audit record found for decision {decision_id} in {trail}"
        )
    return match


def format_decision_record(record):
    """Render one validated record with stable labels and ordering.

    Validation runs first, so a record with any field outside the audit
    allow-list is refused (AuditValidationError) rather than rendered.
    Every printed value comes from an explicitly named approved field;
    a missing decision_id (legacy record) is labelled as absent, never
    invented.
    """
    validate_audit_record(record)
    decision_id = record.get("decision_id", LEGACY_DECISION_ID_TEXT)
    confidence = record["confidence"]
    return "\n".join(
        [
            "Decision record",
            "---------------",
            f"Decision ID: {decision_id}",
            f"Case reference: {record['case_ref']}",
            "",
            "Structured inputs",
            "-----------------",
            f"Age band: {record['age_band']}",
            f"Income band: {record['income_band']}",
            f"Evidence status: {record['evidence_status']}",
            "",
            "Outcome",
            "-------",
            f"Decision: {record['decision']}",
            f"Confidence: {confidence:.4f} (scale 0.0-1.0; uncalibrated)",
            f"Rationale: {record['rationale']}",
            "",
            "Provenance",
            "----------",
            f"Model ID: {record['model_id']}",
            f"Prompt version: {record['prompt_version']}",
            f"Timestamp: {record['timestamp']}",
        ]
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.record_view",
        description=(
            "Look up one stored decision record by decision ID in the "
            "append-only audit trail and print it in human-readable "
            "form. This is a stored-record lookup, not a replay: the "
            "agent is not re-run, no Bedrock or network call is made, "
            "no decision is regenerated, and the trail is never "
            "modified."
        ),
    )
    parser.add_argument(
        "--trail",
        required=True,
        help="path to the append-only audit trail (JSONL)",
    )
    parser.add_argument(
        "--decision-id",
        required=True,
        help="decision ID (UUIDv4) stored in the audit record",
    )
    args = parser.parse_args(argv)

    try:
        record = lookup_decision_record(args.trail, args.decision_id)
        rendered = format_decision_record(record)
    except RecordNotFoundError as exc:
        print(f"record view: {exc}", file=sys.stderr)
        return 1
    except (RecordViewError, AuditTrailReadError, AuditValidationError) as exc:
        print(f"record view error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Stored audit record from {args.trail} "
        "(lookup of an existing record; no model call)"
    )
    print()
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
