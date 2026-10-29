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
                "model_env": "OPENAI_MODEL", "keys": ("OPENAI_API_KEY",), "needs_model": True},
    "gemini": {"name": "Gemini", "vendor": "google", "transport": "api", "provider": "gemini",
               "model_env": "GEMINI_MODEL", "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
               "default_model": "gemini-3.1-flash-lite"},
    "grok": {"name": "Grok", "vendor": "xai", "transport": "api", "provider": "openai-compatible",
             "model_env": "GROK_MODEL", "keys": ("XAI_API_KEY",), "needs_model": True,
             "base_url_env": "XAI_BASE_URL", "base_url": "https://api.x.ai/v1"},
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

# Debate roles. The text goes into that AI's own system prompt (not into the shared chat).
ROLES = {
    "proposer": ("제안자", "매 차례 구체적인 해결책이나 개선안을 하나 내세요. 앞선 비판을 반영해 수정안을 내도 됩니다."),
    "checker": ("현실검증", "나온 제안의 비용, 일정, 필요한 사람과 자원, 실행 순서를 따지고, 빠진 전제나 위험을 "
                         "구체적으로 지적하세요."),
    "opponent": ("반대자", "악마의 변호인으로서 근거를 들어 반대 입장을 내세요. 상대 논리에 설득되면 그 점은 "
                        "인정하되, 남아 있는 다른 약점을 새로 찾아 제기하세요. 근거 없는 반대는 하지 마세요."),
    "synthesizer": ("종합정리", "지금까지 합의된 것, 남은 쟁점, 다음에 따져야 할 질문을 짧게 정리하세요. "
                             "자기 의견은 최소화하세요."),
    "pro": ("찬성", "주제에 찬성하는 입장입니다. 토론 끝까지 찬성 입장을 유지하며 근거를 들어 주장하고, 반대 측 "
                   "논거에 구체적으로 반박하세요. 상대의 타당한 지적은 인정하되 입장은 바꾸지 마세요."),
    "con": ("반대", "주제에 반대하는 입장입니다. 토론 끝까지 반대 입장을 유지하며 근거를 들어 주장하고, 찬성 측 "
                   "논거에 구체적으로 반박하세요. 상대의 타당한 지적은 인정하되 입장은 바꾸지 마세요."),
}

# preset -> (label, roles handed out in speaking order, required participant count or None)
PRESETS = {
    "free": ("자유 토론", [], None),
    "roles": ("역할 분담 (제안·검증·반대·정리)", ["proposer", "checker", "opponent", "synthesizer"], None),
    "procon1": ("찬반 1:1", ["pro", "con"], 2),
    "procon2": ("찬반 2:2", ["pro", "con", "pro", "con"], 4),
}
# With fewer than 4 AIs, "roles" keeps the most useful ones.
ROLES_BY_COUNT = {2: ["proposer", "opponent"], 3: ["proposer", "opponent", "synthesizer"]}


def assign_roles(kinds: list[str], preset: str, overrides: dict[str, str] | None = None) -> tuple[dict, str]:
    """Return ({kind: role_key}, error). Preset roles go out in speaking order; overrides win."""
    if preset not in PRESETS:
        return {}, f"모르는 토론 방식: {preset}"
    label, order, need = PRESETS[preset]
    if need and len(kinds) != need:
        return {}, f"{label}은(는) AI {need}개를 골라야 합니다 (지금 {len(kinds)}개)."
    if preset == "roles" and len(kinds) in ROLES_BY_COUNT:
        order = ROLES_BY_COUNT[len(kinds)]
    roles = {k: order[i] for i, k in enumerate(kinds) if i < len(order)}
    for k, r in (overrides or {}).items():
        if k in kinds and r in ROLES:
            roles[k] = r
        elif k in kinds and r == "none":
            roles.pop(k, None)
    if preset.startswith("procon") and not {"pro", "con"} <= set(roles.values()):
        return {}, "찬반 토론에는 찬성과 반대가 각각 1명 이상 있어야 합니다."
    return roles, ""

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


SETTING_VARS = ("RUNNER_PASSWORD", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                "ANTHROPIC_API_KEY", "XAI_API_KEY", "GEMINI_MODEL", "OPENAI_MODEL", "CLAUDE_MODEL", "GROK_MODEL")


def tidy_env(env=os.environ) -> list[str]:
    """Fix common settings.env mistakes in place; return notes for the user.

    Docker --env-file keeps quotes and spaces as part of the value, an empty line like
    `ANTHROPIC_API_KEY=` still sets the variable, and a `claude setup-token` token pasted
    into ANTHROPIC_API_KEY makes Claude reject it as an invalid API key."""
    notes = []
    for k in list(env):
        if k in SETTING_VARS:
            v = env[k].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1].strip()
            if v != env[k]:
                env[k] = v
                notes.append(f"{k}: 값 앞뒤의 공백/따옴표를 지웠습니다.")
        if env[k] == "":
            del env[k]
    if env.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-oat"):
        token = env.pop("ANTHROPIC_API_KEY")
        if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
            notes.append("ANTHROPIC_API_KEY에 구독 토큰이 들어 있어 무시했습니다. 비워 두세요.")
        else:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token
            notes.append("ANTHROPIC_API_KEY에 들어 있던 구독 토큰(sk-ant-oat…)을 CLAUDE_CODE_OAUTH_TOKEN으로 옮겨 "
                         "사용합니다. settings.env에서도 옮겨 두세요.")
    return notes


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
        elif t.get("needs_model") and not os.environ.get(t["model_env"]):
            out.append(f"{t['name']}: {t['model_env']} 환경변수(모델 이름)가 없습니다.")
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
    roles: dict[str, str] = field(default_factory=dict)  # kind -> ROLES key
    max_messages: int | None = None
    followups: list[str] | None = None
    min_round_trips: int = 10
    timeout_min: float | None = None  # default: 2 minutes per AI message, at least 30
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
        (self.out_dir / "roles.json").write_text(json.dumps(
            {SEAT_TYPES[k]["name"]: ROLES[r][0] for k, r in self.roles.items()}, ensure_ascii=False))
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
                if t.get("provider") == "openai-compatible":
                    cmd += ["--base-url", os.environ.get(t["base_url_env"]) or t["base_url"],
                            "--vendor", t["vendor"], "--key-env", t["keys"][0]]
                if model:
                    cmd += ["--model", model]
                if self.roles.get(k):
                    label, desc = ROLES[self.roles[k]]
                    cmd += ["--role", f"{label}: {desc}"]
                logs[t["name"]] = self.out_dir / f"seat-{k}.log"
                procs[t["name"]] = subprocess.Popen(
                    [sys.executable, str(ROOT / "mb.py"), *cmd], cwd=ROOT,
                    stdout=logs[t["name"]].open("w"), stderr=subprocess.STDOUT,
                    env=dict(os.environ, PYTHONUNBUFFERED="1", MB_URL=self.base, MB_ROOM=rid,
                             MB_TOKEN=seat["token"]))
            time.sleep(3)

            self._status("토론 진행 중")
            user = BoardClient(self.base, rid, ut)
            lineup = ", ".join(f"{SEAT_TYPES[k]['name']}={ROLES[self.roles[k]][0]}"
                               for k in self.kinds if self.roles.get(k))
            user.post(f"주제: {self.topic}\n" + (f"역할: {lineup}\n각자 맡은 역할에 맞게 발언하고, " if lineup
                      else "서로의 주장에 구체적으로 반박하거나 보완하면서, ") + "각 발언은 4~6문장으로 짧게 해주세요.", None)
            timeout_min = self.timeout_min or max(30, 2 * max_messages)
            shown, deadline, failed = 0, time.time() + timeout_min * 60, ""
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
                    failed = f"제한 시간 {timeout_min:g}분을 넘겨 중단했습니다."
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
