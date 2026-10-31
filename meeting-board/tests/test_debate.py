"""settings.env clean-up used by the NAS runner."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.debate import assign_roles, tidy_env  # noqa: E402
from tools.list_models import list_models  # noqa: E402


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


class RolesTest(unittest.TestCase):
    def test_role_presets(self):
        four = ["chatgpt", "gemini", "grok", "claude"]
        self.assertEqual(assign_roles(four, "roles")[0],
                         {"chatgpt": "proposer", "gemini": "checker", "grok": "opponent", "claude": "synthesizer"})
        self.assertEqual(assign_roles(four, "procon2")[0],
                         {"chatgpt": "pro", "gemini": "con", "grok": "pro", "claude": "con"})
        self.assertEqual(assign_roles(["gemini", "claude"], "procon1")[0], {"gemini": "pro", "claude": "con"})
        self.assertEqual(assign_roles(["gemini", "claude"], "free")[0], {})

    def test_overrides_and_checks(self):
        self.assertEqual(assign_roles(["gemini", "claude"], "procon1", {"gemini": "con", "claude": "pro"})[0],
                         {"gemini": "con", "claude": "pro"})
        self.assertTrue(assign_roles(["gemini", "claude", "grok"], "procon2")[1])  # needs 4
        self.assertTrue(assign_roles(["gemini", "claude"], "procon1", {"claude": "pro"})[1])  # no "con" left

    def test_role_goes_into_system_prompt(self):
        from seats.adapters import APISeat
        seat = APISeat(None, provider="openai-compatible", api_key="k", base_url="http://x", vendor="v", model="m")
        self.assertNotIn("역할", seat.system_prompt())
        seat.role = "찬성: 주제에 찬성"
        self.assertTrue(seat.system_prompt().endswith("찬성: 주제에 찬성"))


class ListModelsTest(unittest.TestCase):
    def test_lists_chat_models_only(self):
        import json
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.server.auth = self.headers.get("Authorization")
                body = json.dumps({"data": [{"id": "grok-b"}, {"id": "grok-imagine-1"},
                                            {"id": "grok-a"}, {"id": "text-embedding-x"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = dict(os.environ)
        try:
            os.environ.update(XAI_API_KEY="k1", XAI_BASE_URL=f"http://127.0.0.1:{srv.server_address[1]}/v1",
                              no_proxy="127.0.0.1")
            self.assertEqual(list_models("grok"), ["grok-a", "grok-b"])
            self.assertEqual(srv.auth, "Bearer k1")
        finally:
            os.environ.clear()
            os.environ.update(old)
            srv.shutdown()



class LoginGuardTest(unittest.TestCase):
    def test_blocks_after_repeated_failures(self):
        from runner import LoginGuard, client_id
        g = LoginGuard()
        for _ in range(4):
            g.failed("1.2.3.4", now=1000)
        self.assertEqual(g.wait_seconds("1.2.3.4", now=1000), 0)
        g.failed("1.2.3.4", now=1000)
        self.assertGreater(g.wait_seconds("1.2.3.4", now=1001), 0)
        self.assertEqual(g.wait_seconds("5.6.7.8", now=1001), 0)
        self.assertEqual(g.wait_seconds("1.2.3.4", now=1000 + g.LOCK + 1), 0)
        # behind the NAS reverse proxy the forwarded address is used; a public peer can't spoof it
        self.assertEqual(client_id("172.17.0.1", {"X-Forwarded-For": "9.9.9.9, 10.0.0.1"}), "9.9.9.9")
        self.assertEqual(client_id("8.8.8.8", {"X-Forwarded-For": "9.9.9.9"}), "8.8.8.8")

    def test_global_lock(self):
        from runner import LoginGuard
        g = LoginGuard()
        for i in range(g.GLOBAL):
            g.failed(f"10.0.{i}.1", now=2000)
        self.assertGreater(g.wait_seconds("1.1.1.1", now=2001), 0)



class SessionsTest(unittest.TestCase):
    def test_login_kept_across_restart_and_dropped_on_password_change(self):
        import tempfile
        import runner
        d = Path(tempfile.mkdtemp())
        runner.PASSWORD = "first-password-123"
        s = runner.Sessions(d / "sessions.json")
        tok = s.create()
        self.assertTrue(s.valid(tok))
        self.assertFalse(s.valid("other"))
        self.assertTrue(runner.Sessions(d / "sessions.json").valid(tok))  # restart
        self.assertNotIn(tok, (d / "sessions.json").read_text())  # only a hash is stored
        runner.PASSWORD = "changed-password-456"
        self.assertFalse(runner.Sessions(d / "sessions.json").valid(tok))
        s.drop(tok)


class FinalSummaryTest(unittest.TestCase):
    def test_note_only_on_final_turn(self):
        from seats.adapters import APISeat
        from seats.base import BoardMessage, FINAL_SUMMARY_NOTE
        seat = APISeat(None, provider="openai-compatible", api_key="k", base_url="http://x", vendor="v", model="m")
        m = [BoardMessage("msg_1", 1, "ai_x", "google", "ai", "hi", None, "t", "Gemini")]
        self.assertNotIn(FINAL_SUMMARY_NOTE, seat.frame(m))
        seat.turn_note = FINAL_SUMMARY_NOTE
        self.assertTrue(seat.frame(m).endswith(FINAL_SUMMARY_NOTE))


if __name__ == "__main__":
    unittest.main()
