"""settings.env clean-up used by the NAS runner."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.debate import tidy_env  # noqa: E402


class TidyEnvTest(unittest.TestCase):
    def test_moves_subscription_token_out_of_api_key(self):
        env = {"ANTHROPIC_API_KEY": "sk-ant-oat01-abc", "CLAUDE_CODE_OAUTH_TOKEN": ""}
        notes = tidy_env(env)
        self.assertEqual(env, {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-abc"})
        self.assertTrue(notes)

    def test_keeps_real_api_key(self):
        env = {"ANTHROPIC_API_KEY": "sk-ant-api03-abc"}
        self.assertEqual(tidy_env(env), [])
        self.assertEqual(env, {"ANTHROPIC_API_KEY": "sk-ant-api03-abc"})

    def test_strips_quotes_and_spaces_and_drops_empty(self):
        env = {"GEMINI_API_KEY": ' "AIza-xyz" ', "ANTHROPIC_API_KEY": " ", "PATH": "/bin"}
        tidy_env(env)
        self.assertEqual(env, {"GEMINI_API_KEY": "AIza-xyz", "PATH": "/bin"})


if __name__ == "__main__":
    unittest.main()
