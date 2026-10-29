"""Run one AI debate on a running board server: create a room, start the seat processes,
post the topic, act as moderator when the AIs run dry, then save and verify the transcript.

Used by quick_test.py (local, one command) and runner.py (NAS / server web page).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seats.base import BoardClient  # noqa: E402
from tools.verify import render_report, verify  # noqa: E402

# Seat order is speaking order.
SEAT_TYPES = {
    "chatgpt": {"name": "ChatGPT", "vendor": "openai", "transport": "api", "provider": "openai",
                "model_env": "OPENAI_MODEL", "keys": ("OPENAI_API_KEY",)},
    "gemini": {"name": "Gemini", "vendor": "google", "transport": "api", "provider": "gemini",
               "model_env": "GEMINI_MODEL", "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
               "default_model": "gemini-3.1-flash-lite"},
    "claude": {"name": "Claude", "vendor": "anthropic", "transport": "claude-code-cli",
               "model_env": "CLAUDE_MODEL"},
}

DEFAULT_FOLLOWUPS = [
    "(사회자) 지금까지 나온 결론 중 가장 약한 부분을 서로 하나씩 골라 반박해 주세요. 구체적인 예시를 들어 주세요.",
    "(사회자) 이 결론이 현실에서 실패하는 시나리오를 하나씩 제시하고, 상대의 시나리오에 대한 대응책을 논의해 주세요.",
    "(사회자) 실제로 적용한다면 첫 주에 무엇부터 해야 할까요? 서로의 우선순위에 반박해 주세요.",
]
IDLE_CHARS = 100  # an AI reply shorter than this counts as "nothing more to add"
PER_SEAT_MESSAGES = 15  # leaves room for >=10 cross-vendor replies even after moderator questions

_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(base: str, method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    req = urllib.request.Request(f"{base}/api{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with _local.open(req, timeout=30) as r:
        return json.loads(r.read())


def tail(path: Path, n: int = 8) -> str:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(line[:300] for line in lines[-n:])


def missing_requirements(kinds: list[str], server: bool = False) -> list[str]:
    """Human-readable problems that would stop these seats from starting.

    server=True: no interactive `claude` login exists (NAS / Docker), so Claude needs a token."""
    out = []
    for k in kinds:
        t = SEAT_TYPES.get(k)
        if not t:
            out.append(f"모르는 참가자: {k} (가능: {', '.join(SEAT_TYPES)})")
        elif t.get("keys") and not any(os.environ.get(v) for v in t["keys"]):
            out.append(f"{t['name']}: {t['keys'][0]} 환경변수가 없습니다.")
        elif k == "claude" and not shutil.which("claude"):
            out.append("Claude: `claude` 명령을 찾을 수 없습니다. Claude Code를 설치하세요.")
        elif k == "claude" and server and not (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
                                                or os.environ.get("ANTHROPIC_API_KEY")):
            out.append("Claude: CLAUDE_CODE_OAUTH_TOKEN(구독 토큰) 또는 ANTHROPIC_API_KEY가 없습니다.")
    if len(set(kinds)) < 2:
        out.append("서로 다른 참가자가 2명 이상 필요합니다.")
    return out


@dataclass
class DebateResult:
    room_id: str = ""
    passed: bool = False
    report: str = ""
    error: str = ""
    out_dir: Path | None = None
    round_trips: int = 0
    messages: int = 0


@dataclass
class Debate:
    base: str  # board server URL, e.g. http://127.0.0.1:8787
    kinds: list[str]
    topic: str
    out_dir: Path
    models: dict[str, str] = field(default_factory=dict)
    max_messages: int | None = None
    followups: list[str] | None = None
    min_round_trips: int = 10
    timeout_min: float = 30
    on_message: Callable[[dict, str], None] | None = None  # (message, display_name)
    on_room: Callable[[str, str, str], None] | None = None  # (room_id, conductor_token, user_token)
    on_status: Callable[[str], None] | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)

    def _status(self, s: str) -> None:
        if self.on_status:
            self.on_status(s)

    def run(self) -> DebateResult:
        res = DebateResult(out_dir=self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        max_messages = self.max_messages or PER_SEAT_MESSAGES * len(self.kinds)
        followups = list(DEFAULT_FOLLOWUPS if self.followups is None else self.followups)
        procs: dict[str, subprocess.Popen] = {}
        logs: dict[str, Path] = {}
        try:
            names = [SEAT_TYPES[k]["name"] for k in self.kinds]
            self._status("방 만들기")
            room = api(self.base, "POST", "/rooms",
                       {"title": " vs ".join(names) + f": {self.topic[:40]}", "max_ai_messages": max_messages})
            rid, ct, ut = room["room_id"], room["conductor_token"], room["user"]["token"]
            res.room_id = rid
            if self.on_room:
                self.on_room(rid, ct, ut)

            self._status("AI 연결")
            for k in self.kinds:
                t = SEAT_TYPES[k]
                model = self.models.get(k) or os.environ.get(t["model_env"]) or t.get("default_model")
                seat = api(self.base, "POST", f"/rooms/{rid}/seats",
                           {"vendor": t["vendor"], "display_name": t["name"], "model": model,
                            "transport": t["transport"]}, ct)
                if k == "claude":
                    cmd = ["run-seat", "claude-code"]
                else:
                    cmd = ["run-seat", "api", "--provider", t["provider"]]
                if model:
                    cmd += ["--model", model]
                logs[t["name"]] = self.out_dir / f"seat-{k}.log"
                procs[t["name"]] = subprocess.Popen(
                    [sys.executable, str(ROOT / "mb.py"), *cmd], cwd=ROOT,
                    stdout=logs[t["name"]].open("w"), stderr=subprocess.STDOUT,
                    env=dict(os.environ, PYTHONUNBUFFERED="1", MB_URL=self.base, MB_ROOM=rid,
                             MB_TOKEN=seat["token"]))
            time.sleep(3)

            self._status("토론 진행 중")
            user = BoardClient(self.base, rid, ut)
            user.post(f"주제: {self.topic}\n서로의 주장에 구체적으로 반박하거나 보완하면서, "
                      "각 발언은 4~6문장으로 짧게 해주세요.", None)
            shown, deadline, failed = 0, time.time() + self.timeout_min * 60, ""
            while True:
                t = api(self.base, "GET", f"/rooms/{rid}/transcript", token=ct)
                pnames = {p["participant_id"]: p["display_name"] for p in t["participants"]}
                for m in t["messages"][shown:]:
                    if self.on_message:
                        self.on_message(m, pnames.get(m["sender_id"], "?"))
                shown = len(t["messages"])
                ai_count = sum(m["sender_kind"] == "ai" for m in t["messages"])
                if t["room"]["status"] == "stopped" or ai_count >= max_messages:
                    break
                last = t["messages"][-len(self.kinds):]
                if followups and len(last) == len(self.kinds) and all(
                        m["sender_kind"] == "ai" and len(m["text"].strip()) < IDLE_CHARS for m in last):
                    user.post(followups.pop(0), None)
                dead = [n for n, p in procs.items() if p.poll() is not None]
                if dead:
                    log = tail(logs[dead[0]], 40)
                    reasons = [ln for ln in log.splitlines() if "model call failed (attempt" in ln]
                    failed = (f"{dead[0]} 쪽 연결이 중간에 끊겼습니다. 원인:\n"
                              + (reasons[-1] if reasons else tail(logs[dead[0]])))
                    if "429" in log:
                        failed += "\n→ API 사용 한도(429)에 걸린 것 같습니다. 나중에 다시 하거나 모델을 바꾸세요."
                    break
                if self.stop_event.is_set():
                    failed = "사용자가 중단했습니다."
                    break
                if time.time() > deadline:
                    failed = f"제한 시간 {self.timeout_min:g}분을 넘겨 중단했습니다."
                    break
                time.sleep(2)
            if failed:
                try:
                    api(self.base, "POST", f"/rooms/{rid}/control", {"action": "stop", "args": {}}, ct)
                except OSError:
                    pass

            self._status("결과 저장, 검증")
            t = api(self.base, "GET", f"/rooms/{rid}/transcript", token=ct)
            (self.out_dir / "transcript.json").write_text(json.dumps(t, ensure_ascii=False, indent=2))
            rep = verify(t, self.min_round_trips)
            res.report = render_report(t, rep)
            (self.out_dir / "verify.txt").write_text(res.report + "\n")
            res.passed, res.round_trips = rep["passed"], rep["round_trips"]
            res.messages = sum(m["sender_kind"] == "ai" for m in t["messages"])
            res.error = failed
            return res
        except Exception as e:  # report instead of crashing the caller (web runner)
            res.error = f"{type(e).__name__}: {e}"
            return res
        finally:
            for p in procs.values():
                if p.poll() is None:
                    p.terminate()
            for p in procs.values():
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
            self._status("끝")
