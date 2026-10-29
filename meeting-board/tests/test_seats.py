"""Seat adapter request-format tests against a local fake vendor endpoint (no real vendor)."""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seats.adapters import APISeat, CommandSeat  # noqa: E402
from seats.base import BoardMessage  # noqa: E402

SEEN = []


class FakeVendor(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        out = {"id": f"chatcmpl-fake-{len(SEEN)}", "model": body["model"],
               "choices": [{"message": {"role": "assistant", "content": f"fake reply {len(SEEN)}"}}]}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)


def msg(i, text):
    return BoardMessage(f"msg_{i}", i, "ai_x", "openai", "ai", text, None, "t", "ChatGPT")


class SeatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeVendor)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_meta_seat_uses_chat_completions_and_keeps_private_history(self):
        SEEN.clear()
        os.environ["META_BASE_URL"] = self.base
        seat = APISeat(None, provider="meta", api_key="k-test")
        r1 = seat.respond([msg(1, "hello")])
        r2 = seat.respond([msg(3, "second")])
        self.assertEqual(seat.vendor, "meta")
        self.assertEqual(SEEN[0]["path"], "/v1/chat/completions")
        self.assertEqual(SEEN[0]["auth"], "Bearer k-test")
        self.assertEqual(r1.provenance["vendor_response_id"], "chatcmpl-fake-1")
        # 2nd request carries this seat's own history: system, user1, assistant1, user2.
        roles = [m["role"] for m in SEEN[1]["body"]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertIn("msg_3", SEEN[1]["body"]["messages"][-1]["content"])
        self.assertEqual(r2.text, "fake reply 2")

    def test_failed_call_does_not_duplicate_history_on_retry(self):
        SEEN.clear()
        seat = APISeat(None, provider="openai-compatible", api_key="k",
                       base_url="http://127.0.0.1:9/v1", vendor="x", model="m")
        with self.assertRaises(Exception):
            seat.respond([msg(1, "hello")])  # nothing listens on port 9
        self.assertEqual(seat.history, [])
        seat.base_url = self.base
        seat.respond([msg(1, "hello")])
        roles = [m["role"] for m in SEEN[0]["body"]["messages"]]
        self.assertEqual(roles, ["system", "user"])

    def test_claude_seat_resumes_session_after_failed_first_call(self):
        import tempfile
        from seats.adapters import ClaudeCodeSeat
        d = Path(tempfile.mkdtemp())
        calls = d / "calls.txt"
        fake = d / "claude"
        # Fake CLI: the first call creates the session but fails with an API error.
        fake.write_text(f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
open({str(calls)!r}, "a").write(" ".join(a for a in args if a in ("--session-id", "--resume")) + "\\n")
sid = args[args.index("--session-id") + 1] if "--session-id" in args else args[args.index("--resume") + 1]
first = "--session-id" in args
print(json.dumps({{"session_id": sid, "is_error": first, "result": "API Error: overloaded" if first else "ok reply"}}))
sys.exit(1 if first else 0)
""")
        fake.chmod(0o755)
        seat = ClaudeCodeSeat(None, claude_bin=str(fake))
        with self.assertRaisesRegex(RuntimeError, "API Error: overloaded"):
            seat.respond([msg(1, "hi")])
        r = seat.respond([msg(1, "hi")])
        self.assertEqual(r.text, "ok reply")
        self.assertEqual(calls.read_text().split("\n")[:2], ["--session-id", "--resume"])

    def test_openai_compatible_requires_base_url_and_custom_vendor(self):
        SEEN.clear()
        seat = APISeat(None, provider="openai-compatible", api_key="k", base_url=self.base,
                       vendor="instinct", model="some-model")
        r = seat.respond([msg(1, "hi")])
        self.assertEqual(seat.vendor, "instinct")
        self.assertEqual(SEEN[0]["body"]["model"], "some-model")
        self.assertEqual(r.text, "fake reply 1")

    def test_command_seat_passes_text_only_via_stdin(self):
        bridge = [sys.executable, "-c",
                  "import sys,os; t=sys.stdin.read(); print('bridge got', len(t), 'chars', os.environ['MB_SEAT_SESSION_ID'])"]
        seat = CommandSeat(None, vendor="instinct", command=bridge, session_id="sess-1")
        r = seat.respond([msg(1, "$(touch /tmp/mb-pwned); rm -rf /")])
        self.assertTrue(r.text.startswith("bridge got"))
        self.assertIn("sess-1", r.text)
        self.assertFalse(Path("/tmp/mb-pwned").exists())


if __name__ == "__main__":
    unittest.main()
