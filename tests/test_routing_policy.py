"""Tests for the Ticket 10 routing-policy registry.

Covers the closed registry, immutability, unknown-key rejection, and —
through the genuine production ``decide_case`` path — the exact
threshold-boundary semantics of each policy: strictly below the
threshold escalates, exactly at the threshold does not.
"""

import dataclasses
import unittest

from agenttrail.decision import CONFIDENCE_THRESHOLD, decide_case
from agenttrail.routing_policy import (
    LEGACY_BASELINE_POLICY_KEY,
    ROUTING_POLICIES,
    SUPPORTED_ROUTING_POLICY_KEYS,
    RoutingPolicyError,
    resolve_routing_policy,
)
from tests.support_fixtures import tool_response

CASE = {"age_band": "18-24", "income_band": "low", "evidence_status": "complete"}


class _StubClient:
    """Returns one canned tool response; no fixtures, no network."""

    def __init__(self, decision, confidence):
        template = (
            "DECIDED_EVIDENCE_FOR_INCOME"
            if decision == "decide"
            else "ESCALATED_EVIDENCE_FOR_INCOME"
        )
        self._tool_input = {
            "decision": decision,
            "confidence": confidence,
            "rationale_template": template,
        }

    def converse(self, **request):
        return tool_response(dict(self._tool_input))


def _route(policy_key, decision, confidence):
    """Run one canned response through the production routing path."""
    policy = resolve_routing_policy(policy_key)
    result = decide_case(
        CASE,
        _StubClient(decision, confidence),
        model_id="test-model-id",
        confidence_threshold=policy.confidence_threshold,
    )
    return result


class RoutingPolicyRegistryTest(unittest.TestCase):
    def test_registry_contains_exactly_v1_and_v2(self):
        self.assertEqual(SUPPORTED_ROUTING_POLICY_KEYS, ("v1", "v2"))

    def test_v1_threshold_is_the_production_threshold(self):
        # v1 must preserve current production behaviour exactly; its
        # threshold is the decision module's own constant.
        self.assertEqual(
            ROUTING_POLICIES["v1"].confidence_threshold,
            CONFIDENCE_THRESHOLD,
        )
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.70)

    def test_v2_differs_from_v1_by_one_threshold_change_only(self):
        v1 = ROUTING_POLICIES["v1"]
        v2 = ROUTING_POLICIES["v2"]
        self.assertEqual(v2.confidence_threshold, 0.95)
        self.assertNotEqual(v1.confidence_threshold, v2.confidence_threshold)
        # The policy carries nothing but its key, threshold, and the
        # fixed rule statement — no other behavioural surface exists.
        self.assertEqual(
            sorted(f.name for f in dataclasses.fields(v2)),
            ["confidence_threshold", "key", "rule"],
        )

    def test_policies_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ROUTING_POLICIES["v1"].confidence_threshold = 0.0

    def test_resolve_returns_registered_policies(self):
        for key in SUPPORTED_ROUTING_POLICY_KEYS:
            self.assertIs(resolve_routing_policy(key), ROUTING_POLICIES[key])

    def test_unknown_policy_key_fails_clearly(self):
        for bad in ("v3", "V1", "", None, 1, ["v1"]):
            with self.assertRaises(RoutingPolicyError) as ctx:
                resolve_routing_policy(bad)
            self.assertIn("supported policies: v1, v2", str(ctx.exception))

    def test_legacy_baseline_policy_is_v1(self):
        self.assertEqual(LEGACY_BASELINE_POLICY_KEY, "v1")
        self.assertIn(LEGACY_BASELINE_POLICY_KEY, ROUTING_POLICIES)


class ThresholdBoundaryTest(unittest.TestCase):
    """Boundary semantics through the real decide_case routing path."""

    def test_v1_decide_exactly_at_threshold_stands(self):
        result = _route("v1", "decide", 0.70)
        self.assertEqual(result["decision"], "decide")
        self.assertEqual(result["confidence"], 0.70)

    def test_v1_decide_strictly_below_threshold_escalates(self):
        result = _route("v1", "decide", 0.69)
        self.assertEqual(result["decision"], "escalate")
        # The model's confidence is preserved unchanged on override.
        self.assertEqual(result["confidence"], 0.69)

    def test_v1_decide_above_threshold_stands(self):
        self.assertEqual(_route("v1", "decide", 0.71)["decision"], "decide")

    def test_v2_decide_exactly_at_threshold_stands(self):
        result = _route("v2", "decide", 0.95)
        self.assertEqual(result["decision"], "decide")
        self.assertEqual(result["confidence"], 0.95)

    def test_v2_decide_strictly_below_threshold_escalates(self):
        result = _route("v2", "decide", 0.9499)
        self.assertEqual(result["decision"], "escalate")
        self.assertEqual(result["confidence"], 0.9499)

    def test_v2_decide_above_threshold_stands(self):
        self.assertEqual(_route("v2", "decide", 0.96)["decision"], "decide")

    def test_escalations_are_never_demoted_by_any_policy(self):
        # The threshold only ever converts decide -> escalate.
        for key in SUPPORTED_ROUTING_POLICY_KEYS:
            self.assertEqual(
                _route(key, "escalate", 0.99)["decision"], "escalate"
            )


if __name__ == "__main__":
    unittest.main()
