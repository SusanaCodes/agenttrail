"""Acceptance tests for the AgentTrail golden dataset (Ticket 1).

Synthetic evaluation data only — the labelling rules asserted here are
synthetic evaluation rules, NOT real UK benefit policy.

Standard library only: json, re, unittest, pathlib, itertools, collections.
"""

import itertools
import json
import re
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = REPO_ROOT / "data" / "golden_cases.jsonl"
SCHEMA_PATH = REPO_ROOT / "data" / "golden_cases.schema.json"

DATASET_VERSION = "1.0.0"
EXPECTED_CASE_COUNT = 36

CASE_ID_PATTERN = re.compile(r"^SYN-\d{3}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

AGE_BANDS = ["18-24", "25-39", "40-64", "65-plus"]
INCOME_BANDS = ["low", "medium", "high"]
EVIDENCE_STATUSES = ["complete", "partial", "missing"]
ROUTINGS = ["decide", "escalate"]
CONFIDENCE_BANDS = ["high", "medium", "low"]
REASON_CODES = [
    "EVIDENCE_COMPLETE_LOW_INCOME",
    "EVIDENCE_COMPLETE_MEDIUM_INCOME",
    "EVIDENCE_COMPLETE_HIGH_INCOME",
    "EVIDENCE_PARTIAL",
    "EVIDENCE_MISSING",
]

INPUT_ENUMS = {
    "age_band": AGE_BANDS,
    "income_band": INCOME_BANDS,
    "evidence_status": EVIDENCE_STATUSES,
}
EXPECTED_ENUMS = {
    "routing": ROUTINGS,
    "confidence_band": CONFIDENCE_BANDS,
    "reason_code": REASON_CODES,
}

# Locked expected distribution for dataset_version 1.0.0.
EXPECTED_ROUTING_COUNTS = {"decide": 12, "escalate": 24}
EXPECTED_CONFIDENCE_COUNTS = {"high": 12, "medium": 12, "low": 12}
EXPECTED_REASON_COUNTS = {
    "EVIDENCE_COMPLETE_LOW_INCOME": 4,
    "EVIDENCE_COMPLETE_MEDIUM_INCOME": 4,
    "EVIDENCE_COMPLETE_HIGH_INCOME": 4,
    "EVIDENCE_PARTIAL": 12,
    "EVIDENCE_MISSING": 12,
}
MIN_LOW_CONFIDENCE_CASES = 12


def apply_labelling_policy(income_band, evidence_status):
    """Synthetic labelling policy v1.0.0 (not real benefit policy).

    Pure function of input; age_band is deliberately never consulted.
    Returns (routing, confidence_band, reason_code).
    """
    if evidence_status == "missing":
        return "escalate", "low", "EVIDENCE_MISSING"
    if evidence_status == "partial":
        return "escalate", "medium", "EVIDENCE_PARTIAL"
    return "decide", "high", "EVIDENCE_COMPLETE_%s_INCOME" % income_band.upper()


def load_records():
    records = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            records.append((line_no, json.loads(line)))
    return records


class TestGoldenDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records()

    def test_every_line_parses(self):
        # load_records() raises on any unparseable line; here we assert
        # the file is non-empty and every line yielded a JSON object.
        self.assertEqual(len(self.records), EXPECTED_CASE_COUNT)
        for line_no, record in self.records:
            self.assertIsInstance(record, dict, f"line {line_no} is not an object")

    def test_case_ids_unique_and_well_formed(self):
        case_ids = [r["case_id"] for _, r in self.records]
        self.assertEqual(len(case_ids), len(set(case_ids)), "duplicate case_id")
        for case_id in case_ids:
            self.assertRegex(case_id, CASE_ID_PATTERN)

    def test_record_structure_is_exact(self):
        for line_no, record in self.records:
            self.assertEqual(
                set(record), {"case_id", "dataset_version", "input", "expected"},
                f"line {line_no} has unexpected top-level keys",
            )
            self.assertEqual(
                set(record["input"]), set(INPUT_ENUMS),
                f"line {line_no}: input must contain exactly the three approved fields",
            )
            self.assertEqual(
                set(record["expected"]), set(EXPECTED_ENUMS),
                f"line {line_no} has unexpected expected keys",
            )

    def test_every_string_is_constrained(self):
        # Every string in a record must be constrained by an approved enum,
        # the case ID pattern, or the version pattern. No unconstrained,
        # blank, or null values are permitted anywhere.
        for line_no, record in self.records:
            self.assertRegex(record["case_id"], CASE_ID_PATTERN)
            self.assertRegex(record["dataset_version"], VERSION_PATTERN)
            self.assertEqual(record["dataset_version"], DATASET_VERSION)
            for field, allowed in INPUT_ENUMS.items():
                self.assertIn(record["input"][field], allowed, f"line {line_no}")
            for field, allowed in EXPECTED_ENUMS.items():
                self.assertIn(record["expected"][field], allowed, f"line {line_no}")

    def test_full_input_matrix_covered_exactly_once(self):
        # Every (age_band, income_band, evidence_status) combination must
        # appear exactly once; totals alone could hide a duplicate + omission.
        combos = Counter(
            (r["input"]["age_band"], r["input"]["income_band"],
             r["input"]["evidence_status"])
            for _, r in self.records
        )
        expected = set(itertools.product(AGE_BANDS, INCOME_BANDS, EVIDENCE_STATUSES))
        self.assertEqual(set(combos), expected, "missing input combinations")
        duplicates = {c: n for c, n in combos.items() if n != 1}
        self.assertEqual(duplicates, {}, "input combinations appearing != once")

    def test_labels_follow_deterministic_policy(self):
        for line_no, record in self.records:
            routing, confidence, reason = apply_labelling_policy(
                record["input"]["income_band"], record["input"]["evidence_status"]
            )
            self.assertEqual(record["expected"]["routing"], routing, f"line {line_no}")
            self.assertEqual(
                record["expected"]["confidence_band"], confidence, f"line {line_no}"
            )
            self.assertEqual(
                record["expected"]["reason_code"], reason, f"line {line_no}"
            )

    def test_age_is_routing_inert(self):
        # For each (income_band, evidence_status), the expected label must be
        # identical across all four age bands: age alone never changes routing.
        by_combo = {}
        for _, record in self.records:
            key = (record["input"]["income_band"], record["input"]["evidence_status"])
            label = tuple(sorted(record["expected"].items()))
            by_combo.setdefault(key, set()).add(label)
        for key, labels in by_combo.items():
            self.assertEqual(
                len(labels), 1, f"age_band changed the label for {key}: {labels}"
            )

    def test_routing_distribution_is_stable(self):
        counts = Counter(r["expected"]["routing"] for _, r in self.records)
        self.assertEqual(dict(counts), EXPECTED_ROUTING_COUNTS)
        # Both routes present in meaningful numbers.
        self.assertGreaterEqual(counts["decide"], 10)
        self.assertGreaterEqual(counts["escalate"], 10)

    def test_confidence_distribution_is_stable(self):
        counts = Counter(r["expected"]["confidence_band"] for _, r in self.records)
        self.assertEqual(dict(counts), EXPECTED_CONFIDENCE_COUNTS)

    def test_reason_code_distribution_is_stable(self):
        counts = Counter(r["expected"]["reason_code"] for _, r in self.records)
        self.assertEqual(dict(counts), EXPECTED_REASON_COUNTS)

    def test_low_confidence_subset_is_explicit_and_escalates(self):
        low = [
            r for _, r in self.records
            if r["expected"]["confidence_band"] == "low"
        ]
        self.assertGreaterEqual(len(low), MIN_LOW_CONFIDENCE_CASES)
        for record in low:
            self.assertEqual(
                record["expected"]["routing"], "escalate",
                f"{record['case_id']}: low-confidence case must escalate",
            )

    def test_schema_and_dataset_agree(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        props = schema["properties"]
        self.assertEqual(set(schema["required"]),
                         {"case_id", "dataset_version", "input", "expected"})
        self.assertFalse(schema["additionalProperties"])
        for section, enums in (("input", INPUT_ENUMS), ("expected", EXPECTED_ENUMS)):
            section_schema = props[section]
            self.assertEqual(set(section_schema["required"]), set(enums))
            self.assertFalse(section_schema["additionalProperties"])
            for field, allowed in enums.items():
                self.assertEqual(
                    section_schema["properties"][field]["enum"], allowed,
                    f"schema enum mismatch for {section}.{field}",
                )
        self.assertEqual(props["case_id"]["pattern"], "^SYN-[0-9]{3}$")
        self.assertEqual(props["dataset_version"]["pattern"],
                         "^[0-9]+\\.[0-9]+\\.[0-9]+$")
        # Every enum value used in the dataset is also allowed by the schema
        # (subset check; exact distributions are asserted separately).
        for _, record in self.records:
            for field, allowed in INPUT_ENUMS.items():
                self.assertIn(record["input"][field], allowed)
            for field, allowed in EXPECTED_ENUMS.items():
                self.assertIn(record["expected"][field], allowed)


if __name__ == "__main__":
    unittest.main()
