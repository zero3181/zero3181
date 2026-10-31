"""Debate runner web page for an always-on box (e.g. a Synology NAS in Docker).

    RUNNER_PASSWORD=... python runner.py [--port 8790] [--data ./data]

Open http://<host>:8790, enter RUNNER_PASSWORD (kept for 30 days per device), type a topic,
pick the participants, press 시작. The debate shows live on the page; results are kept under
<data>/results/. One debate runs at a time.

The board server is started by this process on 127.0.0.1 only; just this page is exposed.
This page has no HTTPS. Use it on your home network or over a VPN (e.g. Tailscale), and do
not port-forward it to the internet.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
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

from tools.debate import (_local, assign_roles, Debate, missing_requirements, PER_SEAT_MESSAGES, PRESETS,  # noqa: E402
                          ROLES, SEAT_TYPES, tidy_env)

PASSWORD = os.environ.get("RUNNER_PASSWORD", "")
MAX_TOPIC_CHARS = 10_000
# Form data arrives URL-encoded: one Korean character becomes 9 bytes (%XX%XX%XX).
MAX_FORM_BYTES = MAX_TOPIC_CHARS * 9 + 20_000
RUN_NAME = re.compile(r"^\d{8}-\d{6}$")
RUN_FILES = {"transcript.json": "application/json", "verify.txt": "text/plain", "roles.json": "application/json",
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
        self.preset, self.per_seat, self.role_labels = "free", PER_SEAT_MESSAGES, {}

    def running(self) -> bool:
        return self.debate is not None and self.result is None

    def start(self, topic: str, kinds: list[str], preset: str = "free", overrides: dict | None = None,
              per_seat: int = PER_SEAT_MESSAGES) -> str:
        with self.lock:
            if self.running():
                return "이미 토론이 진행 중입니다."
            problems = missing_requirements(kinds, server=True)
            if problems:
                return " / ".join(problems)
            roles, err = assign_roles(kinds, preset, overrides)
            if err:
                return err
            self.run_name = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.messages, self.result, self.status = [], None, "시작"
            self.preset, self.per_seat = preset, per_seat
            self.role_labels = {SEAT_TYPES[k]["name"]: ROLES[r][0] for k, r in roles.items()}
            self.debate = Debate(
                base=self.board, kinds=kinds, topic=topic, out_dir=self.data / "results" / self.run_name,
                roles=roles, max_messages=per_seat * len(kinds),
                # >=10 round trips needs ~15 messages per AI; with fewer, check what is possible.
                min_round_trips=min(10, max(1, per_seat - 5)),
                on_message=lambda m, who: self.messages.append(
                    (m["sequence"], who, m["sender_vendor"], m["text"].strip())),
                on_status=lambda s: setattr(self, "status", s))
            threading.Thread(target=self._run, daemon=True).start()
            return ""

    def _run(self) -> None:
        d = self.debate
        (d.out_dir).mkdir(parents=True, exist_ok=True)
        (d.out_dir / "meta.json").write_text(json.dumps(
            {"topic": d.topic, "seats": d.kinds, "preset": self.preset, "per_seat": self.per_seat},
            ensure_ascii=False))
        self.result = d.run()


class LoginGuard:
    """Limit wrong-password attempts (the page may be reachable from the internet).

    Per client: 5 wrong passwords in 10 minutes -> that client is blocked for 15 minutes.
    Overall: 30 wrong passwords in 1 hour from anywhere -> logins are refused for 15 minutes."""

    PER_CLIENT, WINDOW = 5, 600
    GLOBAL, GLOBAL_WINDOW = 30, 3600
    LOCK = 900

    def __init__(self):
        self.lock = threading.Lock()
        self.fails: dict[str, list[float]] = {}
        self.until: dict[str, float] = {}

    def wait_seconds(self, client: str, now: float | None = None) -> int:
        now = now or time.time()
        with self.lock:
            until = max(self.until.get(client, 0), self.until.get("*", 0))
        return int(until - now) if until > now else 0

    def failed(self, client: str, now: float | None = None) -> None:
        now = now or time.time()
        with self.lock:
            for key, limit, window in ((client, self.PER_CLIENT, self.WINDOW), ("*", self.GLOBAL, self.GLOBAL_WINDOW)):
                hits = [t for t in self.fails.get(key, []) if t > now - window] + [now]
                self.fails[key] = hits
                if len(hits) >= limit:
                    self.until[key] = now + self.LOCK
                    self.fails[key] = []


GUARD = LoginGuard()

SESSION_COOKIE = "debate_session"
SESSION_DAYS = 30


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class Sessions:
    """Login sessions kept for SESSION_DAYS, saved under the data folder so a container restart
    does not log anyone out. Only a hash of each token is stored. Every session is tied to the
    current RUNNER_PASSWORD: changing the password logs out all devices."""

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        try:
            self.items: dict[str, dict] = json.loads(path.read_text())
        except (OSError, ValueError):
            self.items = {}

    def _pw(self) -> str:
        return _sha("pw:" + PASSWORD)[:16]

    def _save(self) -> None:
        now = time.time()
        self.items = {k: v for k, v in self.items.items() if v["exp"] > now and v["pw"] == self._pw()}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.items[_sha(token)] = {"exp": time.time() + SESSION_DAYS * 86400, "pw": self._pw()}
            self._save()
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self.lock:
            v = self.items.get(_sha(token))
            return bool(v and v["exp"] > time.time() and v["pw"] == self._pw())

    def drop(self, token: str | None) -> None:
        if token:
            with self.lock:
                self.items.pop(_sha(token), None)
                self._save()


def login_page(err: str = "") -> bytes:
    msg = f'<p class="bad">{html.escape(err)}</p>' if err else ""
    # The hidden user name field lets password managers (Safari/iCloud Keychain, Chrome) save the password.
    return page("로그인", f"""<h1>AI 토론방</h1>{msg}
<form method="post" action="/login" class="card">
<input type="text" name="username" value="ai-debate" autocomplete="username" style="display:none" tabindex="-1" aria-hidden="true">
<p><label for="pw">비밀번호</label></p>
<p><input id="pw" type="password" name="password" autocomplete="current-password" required autofocus
  style="width:100%;box-sizing:border-box;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg)"></p>
<p><button>들어가기</button></p>
<p class="muted">한 번 들어가면 이 기기에서는 {SESSION_DAYS}일 동안 다시 묻지 않습니다.</p>
</form>""")


def client_id(peer: str, headers) -> str:
    """The real client address. Behind a reverse proxy on the NAS the peer is a private address,
    so use the address the proxy forwards (X-Forwarded-For / X-Real-IP) when there is one."""
    try:
        private = ipaddress.ip_address(peer).is_private
    except ValueError:
        private = False
    fwd = (headers.get("X-Forwarded-For") or headers.get("X-Real-IP") or "").split(",")[0].strip()
    return fwd if private and fwd else peer


def short(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


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
label{{margin-right:14px;white-space:nowrap}}
.role{{font-size:.8rem;padding:1px 7px;border-radius:9px;background:var(--line)}}
select,input[type=number]{{font:inherit;padding:4px 6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}}
button.link{{background:none;color:var(--accent);padding:4px 0;text-decoration:underline}}
.seatrow{{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:6px 0}} a{{color:var(--accent)}} pre{{white-space:pre-wrap;font-size:.8rem}}
</style></head><body><main>{body}</main></body></html>""".encode()


def debate_text(msgs, roles: dict | None = None, header: str = "") -> str:
    """Plain-text version of a debate for copying or saving."""
    out = [header.strip(), ""] if header.strip() else []
    for seq, who, vendor, text in msgs:
        role = (roles or {}).get(who)
        out.append(f"[{seq}] {who}" + (f" ({role})" if role else "") + (" · 사회자/사용자" if vendor == "human" else ""))
        out += [text, ""]
    return "\n".join(out).strip() + "\n"


def copy_button(text: str, download: str = "") -> str:
    """A '전체 복사' button. navigator.clipboard needs HTTPS, so plain-HTTP LAN access falls back
    to selecting a hidden textarea and execCommand('copy')."""
    dl = f' · <a href="{download}">텍스트 파일로 받기</a>' if download else ""
    return (f'<p><button type="button" onclick="copyAll(this)">전체 복사</button>{dl}</p>'
            f'<textarea id="alltext" readonly style="position:absolute;left:-9999px;top:0">{html.escape(text)}</textarea>'
            """<script>
function copyAll(btn){
  var t=document.getElementById('alltext'), done=function(){btn.textContent='복사됨';setTimeout(function(){btn.textContent='전체 복사'},2000)};
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t.value).then(done,fallback)}else{fallback()}
  function fallback(){t.select();t.setSelectionRange(0,t.value.length);try{document.execCommand('copy');done()}catch(e){btn.textContent='복사 실패'}}
}
</script>""")


def render_messages(msgs, roles: dict | None = None) -> str:
    out = []
    for seq, who, vendor, text in msgs:
        cls = "card human" if vendor == "human" else "card"
        role = (roles or {}).get(who)
        tag = f' <span class="role">{html.escape(role)}</span>' if role else ""
        out.append(f'<div class="{cls}"><span class="who">{seq}. {html.escape(who)}</span>{tag} '
                   f'<span class="vendor">{html.escape(vendor)}</span><div class="text">{html.escape(text)}</div></div>')
    return "\n".join(out)


def make_handler(state: State):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _token(self) -> str | None:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == SESSION_COOKIE:
                    return v
            return None

        def _authed(self) -> bool:
            if state.sessions.valid(self._token()):
                return True
            self._redirect("/login")
            return False

        def _login(self, form: dict) -> None:
            client = client_id(self.client_address[0], self.headers)
            wait = GUARD.wait_seconds(client)
            if wait:
                return self._send(login_page(f"비밀번호를 여러 번 틀려 잠시 잠겼습니다. "
                                             f"{wait // 60 + 1}분 뒤에 다시 시도하세요."), code=429)
            pw = (form.get("password") or [""])[0]
            if not hmac.compare_digest(pw.encode(), PASSWORD.encode()):
                GUARD.failed(client)
                return self._send(login_page("비밀번호가 맞지 않습니다."), code=401)
            token = state.sessions.create()
            # Secure only when the browser reached us over HTTPS (NAS reverse proxy); plain-HTTP LAN
            # access would otherwise never get the cookie back.
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
            self.send_response(303)
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_DAYS * 86400}; "
                                           f"HttpOnly; SameSite=Lax{secure}")
            self.send_header("Location", "/")
            self.end_headers()

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
            path = urllib.parse.urlparse(self.path).path
            if path == "/login":
                return self._send(login_page())
            if not self._authed():
                return
            if path == "/":
                return self._send(self.home())
            parts = path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "runs" and RUN_NAME.match(parts[1]):
                d = state.data / "results" / parts[1]
                if len(parts) == 2:
                    return self._send(self.run_page(parts[1], d))
                if len(parts) == 3 and parts[2] == "debate.txt" and (d / "transcript.json").is_file():
                    body = self.run_text(parts[1], d).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="ai-debate-{parts[1]}.txt"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    return self.wfile.write(body)
                if len(parts) == 3 and parts[2] in RUN_FILES and (d / parts[2]).is_file():
                    return self._send((d / parts[2]).read_bytes(), RUN_FILES[parts[2]] + "; charset=utf-8")
            self._send(page("없음", "<p>페이지가 없습니다. <a href='/'>처음으로</a></p>"), code=404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if self.path == "/login":
                return self._login(urllib.parse.parse_qs(self.rfile.read(min(n, 4096)).decode(errors="replace")))
            if not self._authed():
                return
            if self.path == "/logout":
                state.sessions.drop(self._token())
                self.send_response(303)
                self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
                self.send_header("Location", "/login")
                return self.end_headers()
            if n > MAX_FORM_BYTES:
                self.rfile.read(n)
                return self._redirect("/?err=" + urllib.parse.quote(
                    f"입력이 너무 깁니다. 주제는 {MAX_TOPIC_CHARS:,}자까지 쓸 수 있습니다."))
            form = urllib.parse.parse_qs(self.rfile.read(n).decode())
            if self.path == "/start":
                topic = (form.get("topic") or [""])[0].strip()
                if len(topic) > MAX_TOPIC_CHARS:
                    return self._redirect("/?err=" + urllib.parse.quote(
                        f"주제가 {len(topic):,}자입니다. {MAX_TOPIC_CHARS:,}자 이하로 줄여 주세요."))
                kinds = [k for k in SEAT_TYPES if k in form.get("seat", [])]
                preset = (form.get("preset") or ["free"])[0]
                overrides = {k: form[f"role_{k}"][0] for k in kinds if form.get(f"role_{k}", ["auto"])[0] != "auto"}
                try:
                    per_seat = max(2, min(30, int((form.get("per_seat") or [PER_SEAT_MESSAGES])[0])))
                except ValueError:
                    per_seat = PER_SEAT_MESSAGES
                err = "주제를 입력하세요." if not topic else state.start(topic, kinds, preset, overrides, per_seat)
                return self._redirect("/?err=" + urllib.parse.quote(err) if err else "/")
            if self.path == "/stop" and state.debate:
                state.debate.stop_event.set()
            self._redirect("/")

        def home(self) -> bytes:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            err = (q.get("err") or [""])[0]
            body = ['<form method="post" action="/logout" style="float:right">'
                    '<button class="link">로그아웃</button></form><h1>AI 토론방</h1>']
            if err:
                body.append(f'<p class="bad">{html.escape(err)}</p>')
            for n in state.notes:
                body.append(f'<p class="muted">설정 확인: {html.escape(n)}</p>')
            running = state.running()
            if running:
                d = state.debate
                lineup = " · ".join(SEAT_TYPES[k]["name"] + (f"({state.role_labels[SEAT_TYPES[k]['name']]})"
                                    if SEAT_TYPES[k]["name"] in state.role_labels else "") for k in d.kinds)
                body.append(f'<p><b>진행 중</b> · {html.escape(state.status)} · {PRESETS[state.preset][0]} · '
                            f'{html.escape(lineup)}</p>'
                            '<form method="post" action="/stop"><button>중단</button></form>')
                body.append(copy_button(debate_text(state.messages, state.role_labels)))
                body.append(render_messages(state.messages, state.role_labels))
            else:
                role_opts = '<option value="auto">방식대로</option>' + "".join(
                    f'<option value="{r}">{label}</option>' for r, (label, _) in ROLES.items()) + \
                    '<option value="none">역할 없음</option>'
                rows = "".join(
                    f'<div class="seatrow"><label><input type="checkbox" name="seat" value="{k}" checked> {t["name"]}</label>'
                    f'<select name="role_{k}" aria-label="{t["name"]} 역할">{role_opts}</select></div>'
                    for k, t in SEAT_TYPES.items() if seat_ready(k))
                presets = "".join(f'<option value="{p}">{label}</option>' for p, (label, _, _) in PRESETS.items())
                body.append(f"""<form method="post" action="/start" class="card">
<p><textarea name="topic" placeholder="토론 주제를 입력하세요 ({MAX_TOPIC_CHARS:,}자까지)" maxlength="{MAX_TOPIC_CHARS}" required></textarea></p>
<p><label>토론 방식 <select name="preset">{presets}</select></label></p>
{rows}
<p class="muted">역할은 위에서부터 발언 순서대로 배정됩니다. AI별로 바꾸려면 오른쪽에서 고르세요.</p>
<p><label>AI당 발언 수 <input type="number" name="per_seat" value="{PER_SEAT_MESSAGES}" min="2" max="30"></label></p>
<p><button>시작</button></p></form>""")
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
                mode = PRESETS.get(meta.get("preset", "free"), ("",))[0]
                rows.append(f'<div class="card"><a href="/runs/{d.name}">{d.name}</a> {tag} '
                            f'<span class="muted">{html.escape(mode)}</span><br>'
                            f'<span class="muted">{html.escape(short(meta.get("topic", ""), 120))}</span></div>')
            return "\n".join(rows) or '<p class="muted">아직 없습니다.</p>'

        def run_page(self, name: str, d: Path) -> bytes:
            if not (d / "transcript.json").exists():
                return page(name, f"<p>기록이 없습니다. <a href='/'>처음으로</a></p>")
            t = json.loads((d / "transcript.json").read_text())
            names = {p["participant_id"]: p["display_name"] for p in t["participants"]}
            msgs = [(m["sequence"], names.get(m["sender_id"], "?"), m["sender_vendor"], m["text"].strip())
                    for m in t["messages"]]
            links = " · ".join(f'<a href="/runs/{name}/{f}">{f}</a>' for f in RUN_FILES if (d / f).exists())
            roles = json.loads((d / "roles.json").read_text()) if (d / "roles.json").exists() else {}
            return page(name, f"<p><a href='/'>← 처음으로</a></p><h1>{name}</h1>"
                        + copy_button(self.run_text(name, d), f"/runs/{name}/debate.txt")
                        + render_messages(msgs, roles) + f'<p class="muted">원본 파일: {links}</p>')

        def run_text(self, name: str, d: Path) -> str:
            t = json.loads((d / "transcript.json").read_text())
            names = {p["participant_id"]: p["display_name"] for p in t["participants"]}
            msgs = [(m["sequence"], names.get(m["sender_id"], "?"), m["sender_vendor"], m["text"].strip())
                    for m in t["messages"]]
            roles = json.loads((d / "roles.json").read_text()) if (d / "roles.json").exists() else {}
            meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
            mode = PRESETS.get(meta.get("preset", "free"), ("",))[0]
            ais = [p["display_name"] for p in t["participants"] if p["kind"] == "ai"]
            header = f"AI 토론 기록 {name}\n방식: {mode}\n참가: {', '.join(ais)}"
            return debate_text(msgs, roles, header)

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
    if PASSWORD and len(PASSWORD) < 12:  # log only; not shown on the page
        print("설정 확인: RUNNER_PASSWORD가 12자보다 짧습니다. 인터넷에 공개한다면 더 긴 비밀번호로 바꾸세요.", flush=True)
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
        state.sessions = Sessions(data / "sessions.json")
        ThreadingHTTPServer((a.host, a.port), make_handler(state)).serve_forever()
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
