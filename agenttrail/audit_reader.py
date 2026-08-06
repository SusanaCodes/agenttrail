"""Reading back a persisted append-only audit trail (Ticket 5).

The write side lives in ``agenttrail.audit``; this is the read side that
evaluation and later gates use as their evidence. It reopens a trail
after the writes are closed and hands back only records that satisfy the
audit module's own validator — the contract is reused, never relaxed.

Everything here fails closed. A blank line, unparseable JSON, a record
that fails audit validation, a duplicate case reference, a reference
that was never evaluated, or a missing record all raise rather than
being skipped, because a silently dropped record would let an unaudited
decision pass an evaluation.
"""

import json
from pathlib import Path

from agenttrail.audit import AuditValidationError, validate_audit_record


class AuditTrailReadError(ValueError):
    """A persisted audit trail could not be read as trustworthy evidence."""


def read_audit_trail(audit_path):
    """Reopen a trail and return every record, in file order, validated."""
    audit_path = Path(audit_path)
    if not audit_path.is_file():
        raise AuditTrailReadError(f"audit trail was not created: {audit_path}")
    records = []
    with open(audit_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            where = f"{audit_path}:{line_no}"
            if not line.strip():
                raise AuditTrailReadError(
                    f"{where}: blank line in audit trail"
                )
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditTrailReadError(
                    f"{where}: malformed audit record: {exc}"
                ) from exc
            try:
                validate_audit_record(record)
            except AuditValidationError as exc:
                raise AuditTrailReadError(
                    f"{where}: invalid audit record: {exc}"
                ) from exc
            records.append(record)
    return records


def index_records_by_case(records, expected_case_ids):
    """Map case_ref -> record, requiring exactly one record per case.

    Matching is by the stable case reference, never by line position, so
    a trail written in a different order still scores correctly.
    """
    expected_case_ids = set(expected_case_ids)
    by_case = {}
    for record in records:
        case_ref = record["case_ref"]
        if case_ref in by_case:
            raise AuditTrailReadError(
                f"duplicate audit record for case {case_ref}"
            )
        if case_ref not in expected_case_ids:
            raise AuditTrailReadError(
                f"unexpected audit record for case {case_ref}"
            )
        by_case[case_ref] = record
    missing = sorted(expected_case_ids - set(by_case))
    if missing:
        raise AuditTrailReadError(
            f"missing audit records for cases: {missing}"
        )
    return by_case
