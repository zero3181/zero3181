"""One-command cross-vendor debate: ChatGPT, Gemini and Claude (or any two of them).

    python quick_test.py                                  # Gemini vs Claude (1:1)
    python quick_test.py --seats chatgpt,gemini,claude    # 3-way
    python quick_test.py --topic "토론 주제"

Needs Python 3.10+ and, per participant:
  ChatGPT  OPENAI_API_KEY   (an OpenAI API key; a ChatGPT Plus subscription does not include it)
  Gemini   GEMINI_API_KEY
  Claude   the `claude` CLI, logged in (or CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY set)

Starts its own board server, runs the debate (printed live), saves transcript.json and
verify.txt under results/<time>/, prints PASSED or NOT PASSED, and shuts everything down.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tools.debate import _local, Debate, missing_requirements, SEAT_TYPES, tail  # noqa: E402

DEFAULT_TOPIC = ("소규모 오픈소스 프로젝트에서 코드 리뷰를 AI에게 맡길 때의 장단점과, "
                 "사람 리뷰어가 반드시 남겨야 할 역할은 무엇인가?")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="여러 회사 AI 토론을 한 번에 실행합니다.")
    ap.add_argument("--seats", default="gemini,claude",
                    help=f"참가자, 발언 순서대로 쉼표로 구분 (가능: {','.join(SEAT_TYPES)})")
    ap.add_argument("--topic", default=DEFAULT_TOPIC, help="토론 주제")
    ap.add_argument("--chatgpt-model", help="OpenAI 모델 (기본: OPENAI_MODEL 환경변수 또는 코드 기본값)")
    ap.add_argument("--gemini-model", help="Gemini 모델 (기본 gemini-3.1-flash-lite, 무료 티어는 모델별 하루 20회)")
    ap.add_argument("--claude-model", help="Claude 모델 (기본: Claude Code 기본값)")
    ap.add_argument("--messages", type=int, help="AI 발언 수 합계. 기본은 참가자당 15회")
    ap.add_argument("--followup", action="append",
                    help="AI들이 할 말이 없어 보일 때 던질 사회자 질문 (여러 번 지정 가능, 기본 3개)")
    ap.add_argument("--no-followup", action="store_true", help="사회자 질문을 던지지 않음")
    ap.add_argument("--min-round-trips", type=int, default=10)
    ap.add_argument("--timeout-min", type=float, help="전체 제한 시간(분). 기본: AI 발언당 2분, 최소 30분")
    a = ap.parse_args()

    kinds = [k.strip().lower() for k in a.seats.split(",") if k.strip()]
    problems = missing_requirements(kinds)
    if sys.version_info < (3, 10):
        problems.append("Python 3.10 이상이 필요합니다.")
    if problems:
        sys.exit("시작할 수 없습니다:\n- " + "\n- ".join(problems))

    out = HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mb-quick-"))
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    names = " · ".join(SEAT_TYPES[k]["name"] for k in kinds)
    server = subprocess.Popen([sys.executable, "-m", "board.server", "--port", str(port),
                               "--db", str(tmp / "board.sqlite3")], cwd=HERE,
                              stdout=(out / "server.log").open("w"), stderr=subprocess.STDOUT)
    try:
        print(f"보드 서버 시작 (port {port}), 참가자: {names}")
        for _ in range(50):
            try:
                _local.open(base + "/", timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            print("서버가 뜨지 않았습니다:\n" + tail(out / "server.log"))
            return 1

        def show(m: dict, who: str) -> None:
            print(f"── {m['sequence']:>2}. {who} ({m['sender_vendor']})\n{m['text'].strip()}\n", flush=True)

        d = Debate(base=base, kinds=kinds, topic=a.topic, out_dir=out,
                   models={"chatgpt": a.chatgpt_model, "gemini": a.gemini_model, "claude": a.claude_model},
                   max_messages=a.messages, followups=[] if a.no_followup else a.followup,
                   min_round_trips=a.min_round_trips, timeout_min=a.timeout_min, on_message=show,
                   on_room=lambda rid, ct, ut: print(f"브라우저로 보기: {base}/#room={rid}&ct={ct}&ut={ut}\n"))
        try:
            res = d.run()
        except KeyboardInterrupt:
            print("\n중단했습니다.")
            return 130
        if res.report:
            print("\n".join(res.report.splitlines()[-9:]))
        if res.error:
            print("\n" + res.error)
        print(f"\n저장 위치: {out}")
        return 0 if res.passed else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
