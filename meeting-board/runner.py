"""Debate runner web page for an always-on box (e.g. a Synology NAS in Docker).

    RUNNER_PASSWORD=... python runner.py [--port 8790] [--data ./data]

Open http://<host>:8790, log in (any user name + RUNNER_PASSWORD), type a topic, pick the
participants, press 시작. The debate shows live on the page; results are kept under
<data>/results/. One debate runs at a time.

The board server is started by this process on 127.0.0.1 only; just this page is exposed.
This page has no HTTPS. Use it on your home network or over a VPN (e.g. Tailscale), and do
not port-forward it to the internet.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tools.debate import _local, Debate, missing_requirements, SEAT_TYPES, tidy_env  # noqa: E402

PASSWORD = os.environ.get("RUNNER_PASSWORD", "")
RUN_NAME = re.compile(r"^\d{8}-\d{6}$")
RUN_FILES = {"transcript.json": "application/json", "verify.txt": "text/plain",
             **{f"seat-{k}.log": "text/plain" for k in SEAT_TYPES}}


class State:
    def __init__(self, data: Path, board: str):
        self.data, self.board = data, board
        self.lock = threading.Lock()
        self.debate: Debate | None = None
        self.messages: list[tuple[int, str, str, str]] = []  # seq, name, vendor, text
        self.status = ""
        self.run_name = ""
        self.result = None
        self.notes: list[str] = []

    def running(self) -> bool:
        return self.debate is not None and self.result is None

    def start(self, topic: str, kinds: list[str]) -> str:
        with self.lock:
            if self.running():
                return "이미 토론이 진행 중입니다."
            problems = missing_requirements(kinds, server=True)
            if problems:
                return " / ".join(problems)
            self.run_name = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.messages, self.result, self.status = [], None, "시작"
            self.debate = Debate(
                base=self.board, kinds=kinds, topic=topic, out_dir=self.data / "results" / self.run_name,
                on_message=lambda m, who: self.messages.append(
                    (m["sequence"], who, m["sender_vendor"], m["text"].strip())),
                on_status=lambda s: setattr(self, "status", s))
            threading.Thread(target=self._run, daemon=True).start()
            return ""

    def _run(self) -> None:
        d = self.debate
        (d.out_dir).mkdir(parents=True, exist_ok=True)
        (d.out_dir / "meta.json").write_text(json.dumps(
            {"topic": d.topic, "seats": d.kinds}, ensure_ascii=False))
        self.result = d.run()


def seat_ready(kind: str) -> bool:
    name = SEAT_TYPES[kind]["name"]
    return not any(p.startswith(name) for p in missing_requirements([kind], server=True))


def page(title: str, body: str, refresh: bool = False) -> bytes:
    meta = '<meta http-equiv="refresh" content="4">' if refresh else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{html.escape(title)}</title>
<style>
:root{{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e2e2dc;--accent:#2f5d8a;--ok:#2e7d4f;--bad:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ececea;--muted:#9a9a94;--card:#20201f;--line:#33332f;--accent:#8fb6e0;--ok:#7cc79a;--bad:#f2a49d}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;margin:0}}
main{{max-width:760px;margin:0 auto;padding:16px}}
h1{{font-size:1.3rem}} h2{{font-size:1.05rem;margin-top:2rem}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}}
.who{{font-weight:600}} .vendor{{color:var(--muted);font-size:.85rem}} .text{{white-space:pre-wrap;margin-top:4px}}
.human{{border-left:4px solid var(--accent)}} .muted{{color:var(--muted)}}
.ok{{color:var(--ok);font-weight:600}} .bad{{color:var(--bad);font-weight:600}}
textarea{{width:100%;box-sizing:border-box;min-height:90px;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg)}}
button{{font:inherit;padding:8px 18px;border-radius:8px;border:0;background:var(--accent);color:var(--bg);cursor:pointer}}
label{{margin-right:14px;white-space:nowrap}} a{{color:var(--accent)}} pre{{white-space:pre-wrap;font-size:.8rem}}
</style></head><body><main>{body}</main></body></html>""".encode()


def render_messages(msgs) -> str:
    out = []
    for seq, who, vendor, text in msgs:
        cls = "card human" if vendor == "human" else "card"
        out.append(f'<div class="{cls}"><span class="who">{seq}. {html.escape(who)}</span> '
                   f'<span class="vendor">{html.escape(vendor)}</span><div class="text">{html.escape(text)}</div></div>')
    return "\n".join(out)


def make_handler(state: State):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _authed(self) -> bool:
            h = self.headers.get("Authorization", "")
            if h.startswith("Basic "):
                try:
                    _, _, pw = base64.b64decode(h[6:]).decode().partition(":")
                    if hmac.compare_digest(pw.encode(), PASSWORD.encode()):
                        return True
                except Exception:
                    pass
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="AI debate"')
            self.end_headers()
            return False

        def _send(self, body: bytes, ctype: str = "text/html; charset=utf-8", code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, to: str):
            self.send_response(303)
            self.send_header("Location", to)
            self.end_headers()

        def do_GET(self):
            if not self._authed():
                return
            path = urllib.parse.urlparse(self.path).path
            if path == "/":
                return self._send(self.home())
            parts = path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "runs" and RUN_NAME.match(parts[1]):
                d = state.data / "results" / parts[1]
                if len(parts) == 2:
                    return self._send(self.run_page(parts[1], d))
                if len(parts) == 3 and parts[2] in RUN_FILES and (d / parts[2]).is_file():
                    return self._send((d / parts[2]).read_bytes(), RUN_FILES[parts[2]] + "; charset=utf-8")
            self._send(page("없음", "<p>페이지가 없습니다. <a href='/'>처음으로</a></p>"), code=404)

        def do_POST(self):
            if not self._authed():
                return
            n = int(self.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(self.rfile.read(min(n, 20000)).decode())
            if self.path == "/start":
                topic = (form.get("topic") or [""])[0].strip()[:2000]
                kinds = [k for k in SEAT_TYPES if k in form.get("seat", [])]
                err = "주제를 입력하세요." if not topic else state.start(topic, kinds)
                return self._redirect("/?err=" + urllib.parse.quote(err) if err else "/")
            if self.path == "/stop" and state.debate:
                state.debate.stop_event.set()
            self._redirect("/")

        def home(self) -> bytes:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            err = (q.get("err") or [""])[0]
            body = ["<h1>AI 토론방</h1>"]
            if err:
                body.append(f'<p class="bad">{html.escape(err)}</p>')
            for n in state.notes:
                body.append(f'<p class="muted">설정 확인: {html.escape(n)}</p>')
            running = state.running()
            if running:
                d = state.debate
                body.append(f'<p><b>진행 중</b> · {html.escape(state.status)} · '
                            f'{" · ".join(SEAT_TYPES[k]["name"] for k in d.kinds)}</p>'
                            '<form method="post" action="/stop"><button>중단</button></form>')
                body.append(render_messages(state.messages))
            else:
                checks = "".join(
                    f'<label><input type="checkbox" name="seat" value="{k}" checked> {t["name"]}</label>'
                    for k, t in SEAT_TYPES.items() if seat_ready(k))
                body.append(f"""<form method="post" action="/start" class="card">
<p><textarea name="topic" placeholder="토론 주제를 입력하세요" required></textarea></p>
<p>{checks}</p><p><button>시작</button></p></form>""")
                if state.result is not None:
                    r = state.result
                    verdict = '<span class="ok">PASSED</span>' if r.passed else '<span class="bad">NOT PASSED</span>'
                    body.append(f'<p>방금 끝난 토론: {verdict} · 왕복 {r.round_trips}회 · AI 발언 {r.messages}개 · '
                                f'<a href="/runs/{state.run_name}">기록 보기</a></p>')
                    if r.error:
                        body.append(f'<pre class="bad">{html.escape(r.error)}</pre>')
            body.append("<h2>지난 토론</h2>" + self.history())
            return page("AI 토론방", "\n".join(body), refresh=running)

        def history(self) -> str:
            root = state.data / "results"
            rows = []
            for d in sorted(root.glob("*"), reverse=True)[:30] if root.exists() else []:
                if not RUN_NAME.match(d.name):
                    continue
                meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
                v = (d / "verify.txt").read_text() if (d / "verify.txt").exists() else ""
                tag = ('<span class="ok">PASSED</span>' if "RESULT: PASSED" in v else
                       '<span class="bad">NOT PASSED</span>' if v else '<span class="muted">진행 중/중단</span>')
                rows.append(f'<div class="card"><a href="/runs/{d.name}">{d.name}</a> {tag}<br>'
                            f'<span class="muted">{html.escape(meta.get("topic", "")[:120])}</span></div>')
            return "\n".join(rows) or '<p class="muted">아직 없습니다.</p>'

        def run_page(self, name: str, d: Path) -> bytes:
            if not (d / "transcript.json").exists():
                return page(name, f"<p>기록이 없습니다. <a href='/'>처음으로</a></p>")
            t = json.loads((d / "transcript.json").read_text())
            names = {p["participant_id"]: p["display_name"] for p in t["participants"]}
            msgs = [(m["sequence"], names.get(m["sender_id"], "?"), m["sender_vendor"], m["text"].strip())
                    for m in t["messages"]]
            links = " · ".join(f'<a href="/runs/{name}/{f}">{f}</a>' for f in RUN_FILES if (d / f).exists())
            return page(name, f"<p><a href='/'>← 처음으로</a></p><h1>{name}</h1><p>{links}</p>"
                        + render_messages(msgs))

    return H


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.environ.get("RUNNER_PORT", 8790)))
    ap.add_argument("--board-port", type=int, default=8787)
    ap.add_argument("--data", default=os.environ.get("MB_DATA", str(HERE / "data")))
    a = ap.parse_args()
    global PASSWORD
    notes = tidy_env()
    for n in notes:
        print("설정 확인:", n, flush=True)
    PASSWORD = os.environ.get("RUNNER_PASSWORD", "")
    if not PASSWORD:
        sys.exit("RUNNER_PASSWORD 환경변수를 설정하세요 (이 페이지의 비밀번호).")
    data = Path(a.data)
    (data / "results").mkdir(parents=True, exist_ok=True)
    board = f"http://127.0.0.1:{a.board_port}"
    server = subprocess.Popen([sys.executable, "-m", "board.server", "--host", "127.0.0.1",
                               "--port", str(a.board_port), "--db", str(data / "board.sqlite3")], cwd=HERE)
    for _ in range(50):
        try:
            _local.open(board + "/", timeout=1).close()
            break
        except OSError:
            time.sleep(0.2)
    else:
        server.terminate()
        sys.exit("보드 서버가 뜨지 않았습니다.")
    ready = [t["name"] for k, t in SEAT_TYPES.items() if seat_ready(k)]
    print(f"AI 토론방: http://{a.host}:{a.port}  (사용 가능: {', '.join(ready) or '없음'})", flush=True)
    try:
        state = State(data, board)
        state.notes = notes
        ThreadingHTTPServer((a.host, a.port), make_handler(state)).serve_forever()
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
