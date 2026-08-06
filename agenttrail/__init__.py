"""AgentTrail application package."""

from agenttrail.audit import (
    AuditValidationError,
    AuditWriteError,
    append_audit_record,
    build_audit_record,
    decide_case_audited,
    validate_audit_record,
)
from agenttrail.decision import (
    CONFIDENCE_THRESHOLD,
    PROMPT_VERSION,
    CaseValidationError,
    ModelResponseError,
    decide_case,
    resolve_model_id,
    validate_case,
)

# Replay only. The live recording path (agenttrail.record_fixtures) is
# deliberately not imported here.
from agenttrail.fixtures import (
    FixtureNotFoundError,
    FixtureValidationError,
    ReplayBedrockClient,
    load_fixtures,
    request_fingerprint,
)

__all__ = [
    "AuditValidationError",
    "AuditWriteError",
    "CONFIDENCE_THRESHOLD",
    "CaseValidationError",
    "FixtureNotFoundError",
    "FixtureValidationError",
    "ModelResponseError",
    "PROMPT_VERSION",
    "ReplayBedrockClient",
    "append_audit_record",
    "build_audit_record",
    "decide_case",
    "decide_case_audited",
    "load_fixtures",
    "request_fingerprint",
    "resolve_model_id",
    "validate_audit_record",
    "validate_case",
]
