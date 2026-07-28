# AgentTrail audit trail

**Schema:** `data/audit_record.schema.json` — **Prompt version: 1.0.0**

Each successful audited decision (`agenttrail.audit.decide_case_audited`)
appends exactly one JSON object on one line to an append-only JSONL file.
This record is a structured audit artefact designed to support Article 12
traceability; it is consumed by the later evaluation and redaction-gate
work. It is not, by itself, a claim of Article 12 compliance.

The "every decision is recorded" guarantee applies to this audited
production path (`decide_case_audited`) only. Direct calls to the
low-level `decide_case()` primitive — retained for Ticket 2
compatibility — are unaudited.

## Record fields

| Field | Constraint |
|---|---|
| `case_ref` | `^SYN-[0-9]{3}$` (golden `case_id` convention) |
| `age_band` | `18-24`, `25-39`, `40-64`, `65-plus` |
| `income_band` | `low`, `medium`, `high` |
| `evidence_status` | `complete`, `partial`, `missing` |
| `decision` | `decide`, `escalate` |
| `confidence` | finite number in `[0.0, 1.0]` (uncalibrated in v1) |
| `rationale` | exact rendering of an allow-listed local template |
| `model_id` | bounded identifier; the effective ID sent to Bedrock |
| `prompt_version` | `^[0-9]+\.[0-9]+\.[0-9]+$` |
| `timestamp` | RFC 3339 UTC, second precision, trailing `Z`; generated internally |

All fields are required, `additionalProperties` is `false`, and there are
no free-text or nested metadata fields. Records are built from an explicit
allow-list — the case object is never serialised wholesale — so PII is
excluded by construction. Shared fields reuse the golden dataset enums
verbatim; a test (`tests/test_audit.py`) fails on any drift between the
two schemas.

## Append-only

The writer opens the trail with `O_APPEND` only and performs one write per
record. It never reads, rewrites, truncates, updates, or deletes previous
records, and no update or delete API exists. New files are created with
`0o600` permissions on POSIX platforms. Write failures raise
`AuditWriteError` with no retries; the audited path then does not return
the decision.

## Honest delivery guarantee

One appended line per successful audited invocation. This is **not**
transactional exactly-once delivery across Bedrock and the filesystem: a
crash after the append but before the return leaves a record for a result
the caller never received, and a crash mid-write can leave a truncated
final line. No fsync is performed. An appended record survives a process
crash but may be lost following an operating-system crash or power
failure. Concurrent writers rely on `O_APPEND` atomicity for a single
small write, which local POSIX filesystems provide but network filesystems
may not.

Runtime trails (`audit/`, `*.audit.jsonl`) are git-ignored; the schema and
tests are version-controlled.
