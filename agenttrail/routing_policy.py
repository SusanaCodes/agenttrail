"""Explicit routing-policy registry for policy replay (Ticket 10).

One validated central mapping from a routing-policy key to the single
value a routing policy determines today: the escalation confidence
threshold applied by the production routing rule in
``agenttrail.decision.decide_case`` ("a ``decide`` whose confidence is
strictly below the threshold escalates; at or above the threshold it
stands"). Policy-specific values live here and nowhere else — the
decision path takes the resolved threshold as its existing explicit
parameter and contains no policy conditionals, and nothing mutates a
module-level threshold to switch policy.

Two policies are registered:

* ``v1`` — the current production policy. Its threshold is imported
  from ``agenttrail.decision`` (never restated), so it is definitionally
  identical to production behaviour, including the exact meaning of
  "below", "at", and "above" the threshold.
* ``v2`` — a proposed stricter policy for change-impact analysis: one
  documented rule change only, raising the escalation threshold so an
  automated ``decide`` must carry at least the confidence the recorded
  model reports on routine complete-evidence cases (0.95). Everything
  else — prompt, tool schema, model, parsing, at-threshold semantics —
  is unchanged. Registering ``v2`` approves nothing; it only makes the
  proposal explicit enough to replay against.

Policy selection is always explicit and resolved through this closed
registry; unknown keys are rejected with ``RoutingPolicyError``. A
routing policy is not an agent version: ``agenttrail.versions`` selects
the prompt contract and fixture set, while a routing policy selects only
the post-response routing threshold.
"""

import math
from dataclasses import dataclass

from agenttrail.decision import CONFIDENCE_THRESHOLD

# The proposed v2 escalation threshold. 0.95 is the modal confidence the
# genuine v1 recording reports for routine complete-evidence decisions,
# so the proposal reads: auto-decide only at routine-case confidence;
# route anything below it to a human. At-threshold still decides,
# exactly as in v1.
V2_CONFIDENCE_THRESHOLD = 0.95


class RoutingPolicyError(ValueError):
    """The requested routing policy is not in the supported registry."""


@dataclass(frozen=True)
class RoutingPolicy:
    """One immutable, versioned routing policy.

    ``rule`` is a fixed human-readable statement of the policy used in
    deterministic reports; it is documentation, never executed.
    """

    key: str
    confidence_threshold: float
    rule: str


ROUTING_POLICIES = {
    "v1": RoutingPolicy(
        key="v1",
        confidence_threshold=CONFIDENCE_THRESHOLD,
        rule=(
            "decide stands at confidence >= "
            f"{CONFIDENCE_THRESHOLD:.2f}; below escalates"
        ),
    ),
    "v2": RoutingPolicy(
        key="v2",
        confidence_threshold=V2_CONFIDENCE_THRESHOLD,
        rule=(
            "decide stands at confidence >= "
            f"{V2_CONFIDENCE_THRESHOLD:.2f}; below escalates"
        ),
    ),
}

SUPPORTED_ROUTING_POLICY_KEYS = tuple(sorted(ROUTING_POLICIES))

# The only routing policy that may be declared as the legacy baseline
# for historical records that predate stored policy provenance
# (AC-25). The declaration is an operator-supplied assumption, so it is
# restricted to the one policy production has ever run.
LEGACY_BASELINE_POLICY_KEY = "v1"


def _validate_registry():
    # The registry is the single source of policy truth, so it is
    # checked once at import: a malformed entry must fail loudly here,
    # not surface later as a wrong replay verdict.
    for key, policy in ROUTING_POLICIES.items():
        if policy.key != key:
            raise RoutingPolicyError(
                f"registry key {key!r} disagrees with entry key "
                f"{policy.key!r}"
            )
        threshold = policy.confidence_threshold
        if isinstance(threshold, bool) or not isinstance(
            threshold, (int, float)
        ):
            raise RoutingPolicyError(
                f"routing policy {key!r} has a non-numeric threshold"
            )
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise RoutingPolicyError(
                f"routing policy {key!r} threshold is not a finite value "
                "in [0.0, 1.0]"
            )
        if not isinstance(policy.rule, str) or not policy.rule.strip():
            raise RoutingPolicyError(
                f"routing policy {key!r} has an empty rule statement"
            )
    if ROUTING_POLICIES["v1"].confidence_threshold != CONFIDENCE_THRESHOLD:
        raise RoutingPolicyError(
            "routing policy v1 must preserve the production threshold"
        )
    if LEGACY_BASELINE_POLICY_KEY not in ROUTING_POLICIES:
        raise RoutingPolicyError(
            "the legacy baseline policy is not registered"
        )
    thresholds = {p.confidence_threshold for p in ROUTING_POLICIES.values()}
    if len(thresholds) != len(ROUTING_POLICIES):
        raise RoutingPolicyError(
            "routing policies must have distinct thresholds"
        )


_validate_registry()


def resolve_routing_policy(key):
    """Resolve a policy key to its RoutingPolicy; unknown keys reject.

    The error message names the supported keys so an operator can
    correct the invocation without reading the source.
    """
    if isinstance(key, str) and key in ROUTING_POLICIES:
        return ROUTING_POLICIES[key]
    raise RoutingPolicyError(
        f"unsupported routing policy {key!r}; supported policies: "
        f"{', '.join(SUPPORTED_ROUTING_POLICY_KEYS)}"
    )
