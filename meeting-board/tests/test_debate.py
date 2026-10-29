"""settings.env clean-up used by the NAS runner."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.debate import tidy_env  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
