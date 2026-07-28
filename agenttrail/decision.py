"""Decide or escalate a synthetic benefit case with one Bedrock Converse call.

Synthetic evaluation logic only — this does NOT implement real UK benefit
policy. One application-level ``converse()`` invocation per case, using
Bedrock tool use with a forced tool choice. The model never produces free
text: it may only call ``submit_decision``, and the rationale is rendered
locally from an allow-listed template filled with validated case fields.

Note on confidence: the model-reported confidence is uncalibrated in v1.
It must not be interpreted as a statistical probability; it is only used
for the threshold comparison below.
"""

import json
import math
import os

# Input enums mirror data/golden_cases.schema.json (input section).
AGE_BANDS = ["18-24", "25-39", "40-64", "65-plus"]
INCOME_BANDS = ["low", "medium", "high"]
EVIDENCE_STATUSES = ["complete", "partial", "missing"]

INPUT_ENUMS = {
    "age_band": AGE_BANDS,
    "income_band": INCOME_BANDS,
    "evidence_status": EVIDENCE_STATUSES,
}

DECISIONS = ["decide", "escalate"]

# Version of the prompt contract: system instruction, tool schema, forced
# tool choice, and rationale templates below. Bump when any of them change.
PROMPT_VERSION = "1.0.0"

# v1 threshold: confidence strictly below this always escalates.
CONFIDENCE_THRESHOLD = 0.70

TOOL_NAME = "submit_decision"

# Allow-listed rationale templates. Slots are filled only from the
# validated case input — never from values echoed by the model.
RATIONALE_TEMPLATES = {
    "DECIDED_EVIDENCE_FOR_INCOME": (
        "Decided: {evidence_status} for {income_band} applicant"
    ),
    "ESCALATED_EVIDENCE_FOR_INCOME": (
        "Escalated: {evidence_status} for {income_band} applicant"
    ),
}

TEMPLATE_FOR_DECISION = {
    "decide": "DECIDED_EVIDENCE_FOR_INCOME",
    "escalate": "ESCALATED_EVIDENCE_FOR_INCOME",
}

SYSTEM_INSTRUCTION = (
    "You triage synthetic benefit cases. Decide only when the structured "
    "evidence clearly supports an automated decision; escalate when evidence "
    "is incomplete or you are uncertain. Respond exclusively by calling the "
    "submit_decision tool. Never produce free text."
)

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": TOOL_NAME,
                "description": (
                    "Submit the decision for the case. The rationale is "
                    "rendered by the caller from the selected template."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "decision": {"type": "string", "enum": DECISIONS},
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                            },
                            "rationale_template": {
                                "type": "string",
                                "enum": sorted(RATIONALE_TEMPLATES),
                            },
                        },
                        "required": [
                            "decision",
                            "confidence",
                            "rationale_template",
                        ],
                        "additionalProperties": False,
                    }
                },
            }
        }
    ],
    "toolChoice": {"tool": {"name": TOOL_NAME}},
}

INFERENCE_CONFIG = {"temperature": 0.0, "maxTokens": 256}


class CaseValidationError(ValueError):
    """The structured case input failed validation before any model call."""


class ModelResponseError(RuntimeError):
    """Bedrock returned a missing, malformed, or contradictory tool call."""


def validate_case(case):
    """Validate a structured case against the golden input schema.

    Returns a plain dict with exactly the three enumerated fields.
    Raises CaseValidationError on missing fields, extra fields, or values
    outside the schema — without calling Bedrock.
    """
    if not isinstance(case, dict):
        raise CaseValidationError("case must be a mapping of input fields")
    missing = sorted(set(INPUT_ENUMS) - set(case))
    if missing:
        raise CaseValidationError(f"missing input fields: {missing}")
    extra = sorted(set(case) - set(INPUT_ENUMS))
    if extra:
        raise CaseValidationError(f"unexpected input fields: {extra}")
    for field, allowed in INPUT_ENUMS.items():
        if case[field] not in allowed:
            raise CaseValidationError(
                f"{field}={case[field]!r} is not one of {allowed}"
            )
    return {field: case[field] for field in sorted(INPUT_ENUMS)}


def resolve_model_id(model_id=None):
    """Resolve the effective Bedrock model ID.

    Falls back to the BEDROCK_MODEL_ID environment variable; raises
    ValueError when neither is provided. Never returns None or "".
    """
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID")
    if not model_id:
        raise ValueError(
            "model_id not provided and BEDROCK_MODEL_ID is not set"
        )
    return model_id


def _extract_tool_input(response):
    """Extract and structurally validate the forced tool call."""
    try:
        content = response["output"]["message"]["content"]
    except (KeyError, TypeError):
        raise ModelResponseError("response has no output message content")

    if not isinstance(content, list):
        raise ModelResponseError("response content is not a list")
    if len(content) != 1:
        raise ModelResponseError(
            "response must contain exactly one content block, "
            f"got {len(content)}"
        )
    block = content[0]
    if not isinstance(block, dict) or set(block) != {"toolUse"}:
        raise ModelResponseError(
            "the single content block must contain only a toolUse response"
        )
    tool_use = block["toolUse"]
    if not isinstance(tool_use, dict):
        raise ModelResponseError("toolUse block is not an object")

    if tool_use.get("name") != TOOL_NAME:
        raise ModelResponseError(
            f"model called unexpected tool {tool_use.get('name')!r}"
        )

    tool_input = tool_use.get("input")
    if not isinstance(tool_input, dict):
        raise ModelResponseError("toolUse input is not an object")

    required = {"decision", "confidence", "rationale_template"}
    missing = sorted(required - set(tool_input))
    if missing:
        raise ModelResponseError(f"tool input missing fields: {missing}")
    extra = sorted(set(tool_input) - required)
    if extra:
        raise ModelResponseError(f"tool input has unexpected fields: {extra}")

    decision = tool_input["decision"]
    if decision not in DECISIONS:
        raise ModelResponseError(f"invalid decision {decision!r}")

    confidence = tool_input["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ModelResponseError(f"confidence {confidence!r} is not numeric")
    if not 0.0 <= confidence <= 1.0:
        raise ModelResponseError(
            f"confidence {confidence!r} is outside [0.0, 1.0]"
        )

    template = tool_input["rationale_template"]
    if template not in RATIONALE_TEMPLATES:
        raise ModelResponseError(f"invalid rationale template {template!r}")
    if template != TEMPLATE_FOR_DECISION[decision]:
        raise ModelResponseError(
            f"template {template!r} contradicts decision {decision!r}"
        )

    return decision, float(confidence), template


def decide_case(
    case,
    bedrock_client,
    model_id=None,
    confidence_threshold=CONFIDENCE_THRESHOLD,
):
    """Decide or escalate one structured case with a single Bedrock call.

    This is the unaudited low-level decision primitive, retained for
    Ticket 2 compatibility. Production callers requiring the one-audit-
    record-per-decision guarantee must use
    ``agenttrail.audit.decide_case_audited``, which wraps this function.

    ``bedrock_client`` is an injected bedrock-runtime client (never created
    at import time). ``model_id`` defaults to the BEDROCK_MODEL_ID
    environment variable. Returns {"decision", "confidence", "rationale"}.
    """
    validated = validate_case(case)

    if isinstance(confidence_threshold, bool) or not isinstance(
        confidence_threshold, (int, float)
    ):
        raise ValueError(
            f"confidence_threshold {confidence_threshold!r} is not numeric"
        )
    if not math.isfinite(confidence_threshold) or not (
        0.0 <= confidence_threshold <= 1.0
    ):
        raise ValueError(
            f"confidence_threshold {confidence_threshold!r} is not a finite "
            "value in [0.0, 1.0]"
        )

    model_id = resolve_model_id(model_id)

    response = bedrock_client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_INSTRUCTION}],
        messages=[
            {
                "role": "user",
                "content": [{"text": json.dumps(validated, sort_keys=True)}],
            }
        ],
        toolConfig=TOOL_CONFIG,
        inferenceConfig=INFERENCE_CONFIG,
    )

    decision, confidence, template = _extract_tool_input(response)

    # Low-confidence decisions always escalate; the model's confidence
    # value is preserved unchanged. Exactly-at-threshold is not overridden.
    if decision == "decide" and confidence < confidence_threshold:
        decision = "escalate"
        template = TEMPLATE_FOR_DECISION["escalate"]

    rationale = RATIONALE_TEMPLATES[template].format(
        evidence_status=validated["evidence_status"],
        income_band=validated["income_band"],
    )

    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": rationale,
    }
