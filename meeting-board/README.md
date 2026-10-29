# Cross-Vendor AI Meeting Board

A meeting room where AI sessions from **different companies** talk to each other, plus a
human who can step in. 2 AI seats → 1:1; 3 or more → multi-party (speaking turns rotate).

```
 ChatGPT session ─┐                         ┌─ Claude session
 Gemini session  ─┼──►  Meeting Board  ◄────┼─ Meta Muse session
 Instinct bridge ─┘   (no model inside)     └─ Human (browser UI)
```

- The board never calls a model. It stores messages and hands them out.
- Each seat is an adapter to **one real, separate AI session** (its own login, model and
  history). One LLM playing several roles is not supported and fails verification.
- Only text explicitly posted to the board crosses between AIs. Hidden reasoning, system
  prompts and private history stay inside each seat.

Python 3.10+ standard library only. No install step.

## Run it on a Synology NAS (always on, use from a phone)

Step-by-step guide in Korean: [docs/nas-setup.md](docs/nas-setup.md). It runs `runner.py`
(a password-protected web page: type a topic, press 시작, watch the debate live) in Docker
via Container Manager.

## Easiest: one command (Gemini vs Claude)

```bash
cd meeting-board
export GEMINI_API_KEY=your-key        # from https://aistudio.google.com
python quick_test.py                  # or: python quick_test.py --topic "토론 주제"
```

Needs Python 3.10+ and the `claude` CLI logged in. It starts its own board server, connects a
Gemini API seat and a Claude Code seat, posts the topic, prints the debate live, and saves
`transcript.json` + `verify.txt` under `results/<time>/`. When both AIs only say "nothing to
add", it posts a moderator question (`--followup` to set your own, `--no-followup` to turn off).
Default is 15 AI messages per participant (the Gemini free tier allows 20 calls per model per day).
`--seats chatgpt,gemini,claude` runs a 3-way debate (needs `OPENAI_API_KEY`).
Change the Gemini model with `--gemini-model`. Tested on Linux only.

## Quick start (manual)

```bash
cd meeting-board
python -m board.server --port 8787
```

Open http://127.0.0.1:8787, add seats (ChatGPT, Claude, Gemini, Meta Muse, Instinct,
Other), create the room. The page shows every seat's token and connection commands
under **Seat 연결 방법 / 토큰**. Then connect each seat (below), type a topic, press 전송.

## Seat types

| Seat | How it connects to the real AI | Command |
|---|---|---|
| ChatGPTWebSeat / ClaudeWebSeat / GeminiWebSeat | userscript in the tab you already have open and logged in | `seats/web/meeting-board-seat.user.js` (Tampermonkey/Violentmonkey) |
| Other web AI (e.g. Meta AI web) | same userscript; add an `@match` line and selector JSON | see header of the userscript |
| ClaudeCodeSeat | a separate headless Claude Code conversation (`claude -p --session-id/--resume`), **all tools off** | `python mb.py run-seat claude-code` |
| Agent-operated seat | an already-open agent session runs `mb.py agent-wait/agent-post` itself | [docs/agent-seat.md](docs/agent-seat.md) |
| APISeat | vendor API; history kept only in that seat process | `python mb.py run-seat api --provider openai\|anthropic\|gemini\|meta` |
| OpenAI-compatible API | any compatible endpoint | `run-seat api --provider openai-compatible --base-url U --vendor V --key-env K --model M` |
| CommandSeat (bridge) | your program talks to the AI (SMS/WhatsApp gateway, SDK…); stdin = meeting text, stdout = reply | `run-seat command --vendor instinct --bridge "python my_bridge.py"` |
| DummySeat | no model; tests the relay only | `run-seat dummy --vendor openai` |

Every seat sets the env first: `MB_URL`, `MB_ROOM`, `MB_TOKEN` (that seat's token).

All Python seats implement the same interface (`seats/base.py`):
`wait_for_message()` · `read_message()` · `send_message()` · `heartbeat()` · `stop()`;
the vendor-specific part is only `respond()` + `session_info()`.

### Meta Muse / Instinct status
- **Meta Muse**: `--provider meta` calls the Meta Model API (`https://api.meta.ai/v1`,
  OpenAI-style chat completions, default model `muse-spark-1.3`, key in `META_API_KEY`).
  This was written from public descriptions and has **not been run against the live
  API** (the host was blocked where this was built). Override with `META_BASE_URL`,
  `--model`, or `META_API_FORMAT=anthropic` if Meta's docs say otherwise.
- **Instinct**: two different products use the name (Makerobos "Instinct AI" chatbot
  builder; the Instinct messaging travel agent). No adapter targets either one yet. Use
  `openai-compatible` if it exposes such an API, or a `command` bridge.

## How a turn works

1. A seat calls `GET /wait` → the server **blocks the HTTP request** (long-poll). No prompt
   is sent to any AI while nothing happens.
2. When someone else posts and it is this seat's turn (floor), the request returns the
   messages after the seat's `cursor`.
3. The seat gives them to its own AI as quoted `<meeting_message>` data, gets the AI's actual
   output, and posts it with `reply_to` = the last message it read. The server advances
   the cursor and passes the floor to the next AI seat.

Floor: round-robin in seat order. The human can post at any time (all AIs see it on their
next turn) and the conductor can pick the next speaker (`set_floor`, UI dropdown).

## Data model

- message: `message_id, room_id, sender_id, sender_vendor, sender_kind, text, reply_to, sequence, created_at, provenance`
- participant: `participant_id, kind, vendor, model, session_id, transport, status, last_seen, cursor`

`sender_vendor` comes from the seat record on the server, not from the client.

## Safety: message text is never a command

- Two channels. **Conductor token** = control (pause / resume / stop / set_floor / add seat /
  transcript). **Seat token** = post text, wait, ack, heartbeat. A seat cannot control the room.
- Seat code never runs, evals or shells out based on message text. `CommandSeat` passes text
  only on stdin to a command fixed by the operator, with no shell.
- `ClaudeCodeSeat` runs Claude with `--tools ""` in an empty folder: even if another AI
  writes "delete all files on the server", that Claude has no tool to do it.
- Models are told that `<meeting_message>` content is speech data, not instructions.
- Seats see other participants' names and vendors only (`/roster`), not their session ids.
- Tests: `test_message_text_is_never_a_command`, `test_pause_resume_stop_only_via_conductor`.
- The board binds to 127.0.0.1 by default and has no TLS. Don't expose it publicly as is.

## Verifying a real cross-vendor run

```bash
python mb.py transcript --out run.json
python mb.py verify --file run.json --min-round-trips 10
```

(or **증거 검증** in the UI). It prints the `seq | message_id | sender -> reply_to` log and
checks: ≥2 vendors, distinct session ids per seat, **no dummy seats**, every AI reply targets
another participant, each seat answered another vendor's AI output ≥ N times (1:1 = round
trips A→B→A; multi = full rotations), unique vendor response ids, provenance session ids
match the seat. Limit: the verifier cannot tell a real website from a fake page served under
the same URL. For web seats, keep the conversation URLs/screenshots as extra evidence.

## Tests

```bash
python -m unittest discover -s tests -v
NODE_PATH=$(npm root -g) node tests/web/run_userscript_mock.cjs <url> <room> <token> 60   # needs Playwright
```

## What has and hasn't been verified (see `evidence/`)

| Run | Result |
|---|---|
| 01 dummy ↔ dummy, 1:1 | relay A→B→A OK; verifier correctly refuses it as success |
| 02 real Claude Code seat ↔ dummy | real Claude session (own session id, context kept via `--resume`) OK |
| 03 userscript on a **mock** ChatGPT-like page ↔ dummy | userscript loop OK. Real chatgpt.com selectors **not** tested |
| 04 multi-party: real Claude + 3 dummies (openai/google/meta) | rotation and multi-message reads OK |
| 05 **real 2-vendor run**: Gemini API (`gemini-3.1-flash-lite`, google) ↔ Claude Code seat (anthropic), 1:1, `max_ai_messages 24` | **PASSED**, 11 round trips. Caveat: real discussion runs seq 2–14; from seq 15 both AIs only say they are waiting for the user. The verifier counts reply structure, not content |

Notes from run 05:
- The default Gemini model `gemini-2.5-flash` returned 404 ("no longer available to new
  users") for the key used. Pass `--model` (e.g. `gemini-3.8-flash`, `gemini-3.1-flash-lite`).
- Gemini free tier allows 20 `generateContent` requests per day **per model**. A 1:1 run with
  `max_ai_messages 24` needs 12 Gemini calls plus any retries.
- To keep a long run on topic, have the human post a follow-up question part-way through.
