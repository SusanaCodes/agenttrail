"""Reading the labelled golden dataset for evaluation (Ticket 5).

Splits each golden record into the part the agent may see and the part
it may not. ``LabelledCase.model_input`` holds exactly the three
enumerated input fields; the expected routing label and confidence band
stay on the evaluation side and are never passed to a decision function,
a Bedrock request, or an audit record.

Records are returned in the dataset's own line order so that downstream
reporting is deterministic, and input validation reuses
``agenttrail.decision.validate_case`` rather than restating the schema.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from agenttrail.audit import CASE_REF_PATTERN
from agenttrail.decision import DECISIONS, validate_case

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "golden_cases.jsonl"
)

# The expected.* vocabulary of data/golden_cases.schema.json. Input enums
# and routing values come from the decision module rather than being
# restated here; only the confidence band has no package-level home.
CONFIDENCE_BANDS = ("high", "medium", "low")

# The low-confidence subset is an existing dataset property, not a rule
# invented for this ticket: docs/golden-dataset.md defines it as the
# cases labelled expected.confidence_band == "low" (which in v1.0.0 are
# exactly the evidence_status == "missing" cases), and
# tests/test_golden_dataset.py asserts every one of them must escalate.
LOW_CONFIDENCE_BAND = "low"

DATASET_FIELDS = ("case_id", "dataset_version", "input", "expected")
EXPECTED_FIELDS = ("routing", "confidence_band", "reason_code")


class GoldenDatasetError(ValueError):
    """The golden dataset could not be read as a trustworthy label set."""


@dataclass(frozen=True)
class LabelledCase:
    """One golden case split into model input and evaluation-only labels."""

    case_id: str
    model_input: dict
    expected_routing: str
    confidence_band: str


def load_labelled_cases(dataset_path=DEFAULT_DATASET_PATH):
    """Load every golden case in original file order, validating each.

    Raises GoldenDatasetError on a missing file, a blank or malformed
    line, a duplicate case_id, an input that fails decision-path
    validation, or an out-of-vocabulary expected label.
    """
    dataset_path = Path(dataset_path)
    if not dataset_path.is_file():
        raise GoldenDatasetError(f"golden dataset not found: {dataset_path}")
    cases = []
    seen = set()
    # As in the audit reader: a byte sequence that is not UTF-8 is a
    # malformed dataset, reported by path only. The decode error's
    # message quotes the bytes, so it is neither interpolated nor chained.
    try:
        with open(dataset_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                where = f"{dataset_path}:{line_no}"
                if not line.strip():
                    raise GoldenDatasetError(
                        f"{where}: blank line in golden dataset"
                    )
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GoldenDatasetError(
                        f"{where}: malformed JSON: {exc}"
                    ) from exc
                cases.append(_build_labelled_case(record, where, seen))
    except UnicodeDecodeError:
        raise GoldenDatasetError(
            f"{dataset_path}: golden dataset is not valid UTF-8 text"
        ) from None
    if not cases:
        raise GoldenDatasetError(f"golden dataset is empty: {dataset_path}")
    return tuple(cases)


def _build_labelled_case(record, where, seen):
    if not isinstance(record, dict):
        raise GoldenDatasetError(f"{where}: golden case must be a mapping")
    missing = sorted(set(DATASET_FIELDS) - set(record))
    if missing:
        raise GoldenDatasetError(
            f"{where}: golden case missing fields: {missing}"
        )

    case_id = record["case_id"]
    if not isinstance(case_id, str) or not CASE_REF_PATTERN.fullmatch(case_id):
        raise GoldenDatasetError(
            f"{where}: case_id must be a string matching "
            f"{CASE_REF_PATTERN.pattern}"
        )
    if case_id in seen:
        raise GoldenDatasetError(f"{where}: duplicate case_id {case_id}")
    seen.add(case_id)

    # Reuses the decision path's own validator, so a case that could not
    # legally be sent to the agent is rejected before any replay happens.
    try:
        model_input = validate_case(record["input"])
    except ValueError as exc:
        raise GoldenDatasetError(
            f"{where}: invalid case input: {exc}"
        ) from exc

    expected = record["expected"]
    if not isinstance(expected, dict):
        raise GoldenDatasetError(f"{where}: expected must be a mapping")
    missing = sorted(set(EXPECTED_FIELDS) - set(expected))
    if missing:
        raise GoldenDatasetError(f"{where}: expected missing fields: {missing}")
    if expected["routing"] not in DECISIONS:
        raise GoldenDatasetError(
            f"{where}: expected.routing is not one of {DECISIONS}"
        )
    if expected["confidence_band"] not in CONFIDENCE_BANDS:
        raise GoldenDatasetError(
            f"{where}: expected.confidence_band is not one of "
            f"{list(CONFIDENCE_BANDS)}"
        )
    return LabelledCase(
        case_id=case_id,
        model_input=model_input,
        expected_routing=expected["routing"],
        confidence_band=expected["confidence_band"],
    )
