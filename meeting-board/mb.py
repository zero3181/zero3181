#!/usr/bin/env python3
"""Meeting Board command line.

Conductor (control channel, needs conductor token):
  mb.py create-room --title T [--max-ai-messages N]
  mb.py add-seat   --vendor openai --name ChatGPT [--model M] [--transport web]
  mb.py control    pause|resume|stop
  mb.py transcript [--out file.json]
  mb.py verify     [--file transcript.json] [--min-round-trips 10]

Human participant (message channel):
  mb.py say "text"                         (uses the user token)

Run a seat process (message channel, needs that seat's token):
  mb.py run-seat dummy       --vendor openai --label ChatGPT-dummy
  mb.py run-seat claude-code [--model M]
  mb.py run-seat api         --provider openai|anthropic|gemini|meta [--model M]
  mb.py run-seat api         --provider openai-compatible --base-url U --vendor V --key-env K --model M
  mb.py run-seat command     --vendor instinct --bridge "python my_bridge.py"

Agent-operated seat (an already-open agent session, e.g. an interactive Claude Code
session, drives these two commands itself; blocking costs no tokens):
  mb.py agent-wait --session-id S [--vendor-model M]
  mb.py agent-post --reply-to MSG_ID --text "..."   (or --text-file f / stdin)

Connection settings come from flags or env: MB_URL, MB_ROOM, MB_CONDUCTOR_TOKEN,
MB_TOKEN (seat token), MB_USER_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from seats.base import BoardClient, BoardMessage, frame_for_model, load_names  # noqa: E402

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def conductor_req(args, method, path, body=None, timeout=30):
    url = f"{args.url.rstrip('/')}/api{path}"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if getattr(args, "conductor_token", None):
        req.add_header("Authorization", f"Bearer {args.conductor_token}")
    try:
        with _opener.open(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"error {e.code}: {e.read().decode(errors='replace')}")


def need(v, name):
    if not v:
        sys.exit(f"missing {name} (flag or env)")
    return v


def cmd_create_room(a):
    r = conductor_req(a, "POST", "/rooms", {"title": a.title, "max_ai_messages": a.max_ai_messages})
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"\nexport MB_URL={a.url} MB_ROOM={r['room_id']} MB_CONDUCTOR_TOKEN={r['conductor_token']} "
          f"MB_USER_TOKEN={r['user']['token']}", file=sys.stderr)
    print(f"UI: {a.url}/#room={r['room_id']}&ct={r['conductor_token']}&ut={r['user']['token']}",
          file=sys.stderr)


def cmd_add_seat(a):
    r = conductor_req(a, "POST", f"/rooms/{need(a.room, 'MB_ROOM')}/seats",
                      {"vendor": a.vendor, "display_name": a.name, "model": a.model, "transport": a.transport})
    print(json.dumps(r, ensure_ascii=False, indent=2))


def cmd_control(a):
    args = {}
    if a.action == "set_floor":
        args = {"participant_id": need(a.participant, "--participant")}
    r = conductor_req(a, "POST", f"/rooms/{need(a.room, 'MB_ROOM')}/control", {"action": a.action, "args": args})
    print(json.dumps(r, ensure_ascii=False, indent=2))


def cmd_say(a):
    c = BoardClient(a.url, need(a.room, "MB_ROOM"), need(a.user_token, "MB_USER_TOKEN"))
    print(json.dumps(c.post(a.text, a.reply_to), ensure_ascii=False, indent=2))


def cmd_transcript(a):
    r = conductor_req(a, "GET", f"/rooms/{need(a.room, 'MB_ROOM')}/transcript")
    s = json.dumps(r, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(s)
        print(f"wrote {a.out}", file=sys.stderr)
    else:
        print(s)


def cmd_verify(a):
    from tools.verify import render_report, verify
    if a.file:
        t = json.loads(Path(a.file).read_text())
    else:
        t = conductor_req(a, "GET", f"/rooms/{need(a.room, 'MB_ROOM')}/transcript")
    rep = verify(t, a.min_round_trips)
    print(render_report(t, rep))
    sys.exit(0 if rep["passed"] else 1)


def seat_client(a):
    return BoardClient(a.url, need(a.room, "MB_ROOM"), need(a.token, "MB_TOKEN"))


def cmd_run_seat(a):
    from seats.adapters import APISeat, ClaudeCodeSeat, CommandSeat, DummySeat
    c = seat_client(a)
    if a.kind == "dummy":
        seat = DummySeat(c, vendor=a.vendor or "dummy", label=a.label or (a.vendor or "Dummy"))
    elif a.kind == "claude-code":
        seat = ClaudeCodeSeat(c, model=a.model)
    elif a.kind == "api":
        seat = APISeat(c, provider=need(a.provider, "--provider"), model=a.model, base_url=a.base_url,
                       vendor=a.vendor, key_env=a.key_env)
    elif a.kind == "command":
        import shlex
        seat = CommandSeat(c, vendor=need(a.vendor, "--vendor"), command=shlex.split(need(a.bridge, "--bridge")),
                           model=a.model, session_id=a.session_id)
    else:
        sys.exit("unknown seat kind")
    try:
        n = seat.run(max_replies=a.max_replies)
        print(f"seat finished after {n} replies", file=sys.stderr)
    except KeyboardInterrupt:
        seat.stop()


# ---- agent-operated seat: the open session itself is the AI; these are its I/O ----
STATE_DIR = Path(os.environ.get("MB_STATE_DIR", Path.home() / ".meeting-board"))


def cmd_agent_wait(a):
    c = seat_client(a)
    state_file = STATE_DIR / f"{c.room_id}-{c.token[-8:]}.json"
    st = json.loads(state_file.read_text()) if state_file.exists() else {}
    if not st.get("joined"):
        c.join(need(a.session_id, "--session-id"), a.vendor_model, "agent-operated-cli",
               {"note": "an already-open agent session drives mb.py agent-wait/agent-post itself"})
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        st = {"joined": True}
        state_file.write_text(json.dumps(st))
    names = load_names(c.roster())
    waited = 0.0
    while True:
        r = c.wait(25)
        waited += 25
        if r["state"] == "stopped":
            print("ROOM_STOPPED")
            return
        if r["state"] == "ready":
            break
        if a.max_wait and waited >= a.max_wait:
            print(f"NO_NEW_MESSAGES state={r['state']}")
            return
    msgs = [BoardMessage.from_json(m, names) for m in r["messages"]]
    # No ack here: agent-post with --reply-to advances the cursor. If the agent crashes before
    # posting, the next agent-wait shows the same messages again instead of losing them.
    print(frame_for_model(msgs))
    print(f"\nREPLY_TO={msgs[-1].message_id}")


def cmd_agent_post(a):
    c = seat_client(a)
    text = a.text
    if a.text_file:
        text = Path(a.text_file).read_text()
    if text is None:
        text = sys.stdin.read()
    r = c.post(text.strip(), a.reply_to, {"seat": "agent-operated-cli", "session_id": a.session_id})
    m = r["message"]
    print(f"POSTED {m['message_id']} seq={m['sequence']} reply_to={m['reply_to']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("MB_URL", "http://127.0.0.1:8787"))
    ap.add_argument("--room", default=os.environ.get("MB_ROOM"))
    ap.add_argument("--conductor-token", default=os.environ.get("MB_CONDUCTOR_TOKEN"))
    ap.add_argument("--token", default=os.environ.get("MB_TOKEN"), help="seat participant token")
    ap.add_argument("--user-token", default=os.environ.get("MB_USER_TOKEN"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-room"); p.add_argument("--title", default="Cross-Vendor AI Room")
    p.add_argument("--max-ai-messages", type=int); p.set_defaults(f=cmd_create_room)

    p = sub.add_parser("add-seat"); p.add_argument("--vendor", required=True); p.add_argument("--name")
    p.add_argument("--model"); p.add_argument("--transport"); p.set_defaults(f=cmd_add_seat)

    p = sub.add_parser("control"); p.add_argument("action", choices=["pause", "resume", "stop", "set_floor"])
    p.add_argument("--participant"); p.set_defaults(f=cmd_control)

    p = sub.add_parser("say"); p.add_argument("text"); p.add_argument("--reply-to"); p.set_defaults(f=cmd_say)

    p = sub.add_parser("transcript"); p.add_argument("--out"); p.set_defaults(f=cmd_transcript)

    p = sub.add_parser("verify"); p.add_argument("--file"); p.add_argument("--min-round-trips", type=int, default=10)
    p.set_defaults(f=cmd_verify)

    p = sub.add_parser("run-seat"); p.add_argument("kind", choices=["dummy", "claude-code", "api", "command"])
    p.add_argument("--vendor"); p.add_argument("--label"); p.add_argument("--model")
    p.add_argument("--provider", help="openai | anthropic | gemini | meta | openai-compatible")
    p.add_argument("--base-url"); p.add_argument("--key-env", help="env var holding the API key")
    p.add_argument("--bridge", help="command seat: bridge program (stdin=meeting text, stdout=reply)")
    p.add_argument("--session-id")
    p.add_argument("--max-replies", type=int); p.set_defaults(f=cmd_run_seat)

    p = sub.add_parser("agent-wait"); p.add_argument("--session-id"); p.add_argument("--vendor-model")
    p.add_argument("--max-wait", type=float, default=0, help="seconds; 0 = wait forever")
    p.set_defaults(f=cmd_agent_wait)

    p = sub.add_parser("agent-post"); p.add_argument("--reply-to", required=True); p.add_argument("--text")
    p.add_argument("--text-file"); p.add_argument("--session-id"); p.set_defaults(f=cmd_agent_post)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
