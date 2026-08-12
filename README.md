# AgentTrail

Safety-gate demo: `docs/demo-scenario.md` shows how to run the safe
`v1` agent (green CI gate) and the intentionally unsafe `v2` demo agent
(red CI gate, deployment blocked), locally and via GitHub Actions.

Policy replay: `docs/policy-replay.md` shows how to replay a historical
audit trail under a proposed routing policy and report which stored
decisions would flip (`python3 -m agenttrail.policy_replay`).
