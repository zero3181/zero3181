"""One-command cross-vendor test: Gemini (Google API) vs Claude (Claude Code), 1:1.

    python quick_test.py
    python quick_test.py --topic "토론 주제"

Needs: Python 3.10+, GEMINI_API_KEY in the environment, and the `claude` CLI logged in.
It starts its own board server, creates a room, connects both AIs, posts the topic,
prints the conversation as it happens, then saves the transcript and the verify report
to results/<time>/ and prints PASSED or NOT PASSED. Everything it started is shut down
at the end.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from seats.base import BoardClient  # noqa: E402
from tools.verify import render_report, verify  # noqa: E402

DEFAULT_TOPIC = ("소규모 오픈소스 프로젝트에서 코드 리뷰를 AI에게 맡길 때의 장단점과, "
                 "사람 리뷰어가 반드시 남겨야 할 역할은 무엇인가?")
# Posted by the "moderator" when both AIs stop adding content (short "waiting" replies).
DEFAULT_FOLLOWUPS = [
    "(사회자) 지금까지 나온 결론 중 가장 약한 부분을 서로 하나씩 골라 반박해 주세요. 구체적인 예시를 들어 주세요.",
    "(사회자) 이 결론이 현실에서 실패하는 시나리오를 하나씩 제시하고, 상대의 시나리오에 대한 대응책을 논의해 주세요.",
    "(사회자) 실제로 적용한다면 첫 주에 무엇부터 해야 할까요? 서로의 우선순위에 반박해 주세요.",
]
IDLE_CHARS = 100  # an AI reply shorter than this counts as "nothing more to add"
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


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def preflight() -> None:
    problems = []
    if sys.version_info < (3, 10):
        problems.append("Python 3.10 이상이 필요합니다.")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        problems.append("GEMINI_API_KEY 환경변수가 없습니다. https://aistudio.google.com 에서 키를 받아 설정하세요.")
    if not shutil.which("claude"):
        problems.append("`claude` 명령을 찾을 수 없습니다. Claude Code를 설치하고 로그인하세요.")
    if problems:
        sys.exit("시작할 수 없습니다:\n- " + "\n- ".join(problems))


def tail(path: Path, n: int = 8) -> str:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(line[:300] for line in lines[-n:])


def main() -> int:
    ap = argparse.ArgumentParser(description="Gemini vs Claude 토론 테스트를 한 번에 실행합니다.")
    ap.add_argument("--topic", default=DEFAULT_TOPIC, help="토론 주제")
    ap.add_argument("--gemini-model", default="gemini-3.1-flash-lite",
                    help="Gemini 모델 (무료 티어는 모델별 하루 20회 한도)")
    ap.add_argument("--messages", type=int, default=30,
                    help="AI 발언 수 합계. 이만큼 쌓이면 자동 종료 (기본 30 = 각 15회)")
    ap.add_argument("--followup", action="append",
                    help="두 AI가 할 말이 없어 보일 때 던질 사회자 질문 (여러 번 지정 가능, 기본 3개)")
    ap.add_argument("--no-followup", action="store_true", help="사회자 질문을 던지지 않음")
    ap.add_argument("--min-round-trips", type=int, default=10)
    ap.add_argument("--timeout-min", type=float, default=20, help="전체 제한 시간(분)")
    a = ap.parse_args()
    followups = [] if a.no_followup else list(a.followup or DEFAULT_FOLLOWUPS)
    preflight()

    out = HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mb-quick-"))
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    procs: list[subprocess.Popen] = []
    logs = {"server": out / "server.log", "Gemini": out / "seat-gemini.log", "Claude": out / "seat-claude.log"}

    def start(cmd: list[str], log: Path, env: dict | None = None) -> subprocess.Popen:
        p = subprocess.Popen(cmd, cwd=HERE, stdout=log.open("w"), stderr=subprocess.STDOUT,
                             env=dict(os.environ, PYTHONUNBUFFERED="1", **(env or {})))
        procs.append(p)
        return p

    try:
        print(f"[1/5] 보드 서버 시작 (port {port})")
        start([sys.executable, "-m", "board.server", "--port", str(port), "--db", str(tmp / "board.sqlite3")],
              logs["server"])
        for _ in range(50):
            try:
                _local.open(base + "/", timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            print("서버가 뜨지 않았습니다:\n" + tail(logs["server"]))
            return 1

        print("[2/5] 방 만들기, 자리 2개 추가")
        room = api(base, "POST", "/rooms", {"title": "Quick test: Gemini vs Claude", "max_ai_messages": a.messages})
        rid, ct, ut = room["room_id"], room["conductor_token"], room["user"]["token"]
        seat_a = api(base, "POST", f"/rooms/{rid}/seats", {"vendor": "google", "display_name": "Gemini",
                                                           "model": a.gemini_model, "transport": "api"}, ct)
        seat_b = api(base, "POST", f"/rooms/{rid}/seats", {"vendor": "anthropic", "display_name": "Claude",
                                                           "model": None, "transport": "claude-code-cli"}, ct)
        print(f"      브라우저로 보기: {base}/#room={rid}&ct={ct}&ut={ut}")

        print("[3/5] AI 연결 (Gemini API, Claude Code)")
        env = {"MB_URL": base, "MB_ROOM": rid}
        seats = {
            "Gemini": start([sys.executable, "mb.py", "run-seat", "api", "--provider", "gemini",
                             "--model", a.gemini_model], logs["Gemini"], dict(env, MB_TOKEN=seat_a["token"])),
            "Claude": start([sys.executable, "mb.py", "run-seat", "claude-code"], logs["Claude"],
                            dict(env, MB_TOKEN=seat_b["token"])),
        }
        time.sleep(3)

        print("[4/5] 주제 투입, 토론 진행\n")
        user = BoardClient(base, rid, ut)
        user.post(f"주제: {a.topic}\n서로의 주장에 구체적으로 반박하거나 보완하면서, 각 발언은 4~6문장으로 짧게 해주세요.", None)

        shown, deadline = 0, time.time() + a.timeout_min * 60
        failed = None
        while True:
            t = api(base, "GET", f"/rooms/{rid}/transcript", token=ct)
            names = {p["participant_id"]: p["display_name"] for p in t["participants"]}
            for m in t["messages"][shown:]:
                who = names.get(m["sender_id"], "?")
                print(f"── {m['sequence']:>2}. {who} ({m['sender_vendor']})\n{m['text'].strip()}\n")
            shown = len(t["messages"])
            ai_count = sum(m["sender_kind"] == "ai" for m in t["messages"])
            if t["room"]["status"] == "stopped" or ai_count >= a.messages:
                break
            last = t["messages"][-2:]
            if followups and len(last) == 2 and all(
                    m["sender_kind"] == "ai" and len(m["text"].strip()) < IDLE_CHARS for m in last):
                user.post(followups.pop(0), None)
            dead = [n for n, p in seats.items() if p.poll() is not None]
            if dead:
                failed = dead[0]
                break
            if time.time() > deadline:
                failed = "timeout"
                break
            time.sleep(2)

        print("[5/5] 결과 저장, 검증")
        t = api(base, "GET", f"/rooms/{rid}/transcript", token=ct)
        (out / "transcript.json").write_text(json.dumps(t, ensure_ascii=False, indent=2))
        rep = verify(t, a.min_round_trips)
        report = render_report(t, rep)
        (out / "verify.txt").write_text(report + "\n")
        print("\n" + "\n".join(report.splitlines()[-9:]))

        if failed == "timeout":
            print(f"\n제한 시간 {a.timeout_min:g}분을 넘겨 중단했습니다.")
        elif failed:
            print(f"\n{failed} 쪽 연결이 중간에 끊겼습니다. 마지막 로그:\n{tail(logs[failed])}")
            if "429" in tail(logs[failed], 30):
                print("\n→ Gemini 무료 한도(모델별 하루 20회)를 다 쓴 것 같습니다. "
                      "내일 다시 하거나 --gemini-model 로 다른 모델을 지정하세요.")
        print(f"\n저장 위치: {out}")
        return 0 if rep["passed"] else 1
    except urllib.error.URLError as e:
        print(f"보드 서버와 통신 실패: {e}\n{tail(logs['server'])}")
        return 1
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return 130
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
