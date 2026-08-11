"""The explicit agent-version registry (Ticket 9).

The registry is the single source of version truth for the demo
scenario: it must accept exactly v1 and v2, resolve each to the correct
prompt contract and fixture set, reject everything else clearly, and
keep the safe v1 as the only default anything falls back to.
"""

import unittest

from agenttrail.decision import PROMPT_VERSION, SYSTEM_INSTRUCTION
from agenttrail.fixtures import DEFAULT_FIXTURE_PATH
from agenttrail.versions import (
    AGENT_VERSIONS,
    DEFAULT_AGENT_VERSION_KEY,
    SUPPORTED_AGENT_VERSION_KEYS,
    V2_PROMPT_VERSION,
    V2_SYSTEM_INSTRUCTION,
    AgentVersionError,
    resolve_agent_version,
)


class TestRegistry(unittest.TestCase):
    def test_exactly_v1_and_v2_are_supported(self):
        self.assertEqual(SUPPORTED_AGENT_VERSION_KEYS, ("v1", "v2"))
        self.assertEqual(sorted(AGENT_VERSIONS), ["v1", "v2"])

    def test_default_is_the_safe_v1(self):
        self.assertEqual(DEFAULT_AGENT_VERSION_KEY, "v1")
        self.assertTrue(AGENT_VERSIONS["v1"].safe)

    def test_v2_is_marked_unsafe(self):
        self.assertFalse(AGENT_VERSIONS["v2"].safe)

    def test_v1_is_the_existing_prompt_contract(self):
        v1 = resolve_agent_version("v1")
        self.assertEqual(v1.prompt_version, PROMPT_VERSION)
        self.assertEqual(v1.prompt_version, "1.0.0")
        self.assertEqual(v1.system_instruction, SYSTEM_INSTRUCTION)
        self.assertEqual(v1.fixture_path, DEFAULT_FIXTURE_PATH)

    def test_v2_is_a_distinct_prompt_contract(self):
        v2 = resolve_agent_version("v2")
        self.assertEqual(v2.prompt_version, V2_PROMPT_VERSION)
        self.assertEqual(v2.prompt_version, "2.0.0")
        self.assertEqual(v2.system_instruction, V2_SYSTEM_INSTRUCTION)
        self.assertNotEqual(v2.system_instruction, SYSTEM_INSTRUCTION)
        self.assertNotEqual(v2.fixture_path, DEFAULT_FIXTURE_PATH)
        # The file name itself labels the set as synthetic.
        self.assertIn("synthetic", v2.fixture_path.name)

    def test_versions_never_share_contract_pieces(self):
        v1, v2 = AGENT_VERSIONS["v1"], AGENT_VERSIONS["v2"]
        self.assertNotEqual(v1.prompt_version, v2.prompt_version)
        self.assertNotEqual(v1.system_instruction, v2.system_instruction)
        self.assertNotEqual(v1.fixture_path, v2.fixture_path)


class TestResolution(unittest.TestCase):
    def test_supported_keys_resolve(self):
        for key in SUPPORTED_AGENT_VERSION_KEYS:
            self.assertEqual(resolve_agent_version(key).key, key)

    def test_unknown_versions_are_rejected_clearly(self):
        for bad in ("v3", "V1", "1", "", "v1 ", None, 1, ["v1"]):
            with self.assertRaises(AgentVersionError) as ctx:
                resolve_agent_version(bad)
            message = str(ctx.exception)
            self.assertIn("unsupported agent version", message)
            # The operator is told what would have been accepted.
            self.assertIn("v1", message)
            self.assertIn("v2", message)


if __name__ == "__main__":
    unittest.main()
