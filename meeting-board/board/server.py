"""Cross-Vendor AI Meeting Board server.

Model-agnostic message board. It never calls any AI model itself.
Seats (adapters) connect over HTTP and exchange plain text only.

Python standard library only. Run:
    python -m board.server --port 8787
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC_DIR = Path(__file__).parent / "static"
MAX_TEXT = 20_000
MAX_WAIT = 60.0
ONLINE_WINDOW = 45.0  # seconds since last_seen to count as online

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
  room_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,             -- running | paused | stopped
  conductor_token_hash TEXT NOT NULL,
  floor_participant_id TEXT,        -- AI seat whose turn it is (NULL = none yet)
  max_ai_messages INTEGER,          -- auto-stop after this many AI messages (NULL = no limit)
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS participants (
  participant_id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  kind TEXT NOT NULL,               -- ai | human
  display_name TEXT NOT NULL,
  vendor TEXT NOT NULL,
  model TEXT,
  transport TEXT,
  session_id TEXT,
  session_meta TEXT,                -- JSON reported by the seat at join time
  status TEXT NOT NULL,             -- invited | online | offline | left
  last_seen REAL,
  cursor INTEGER NOT NULL DEFAULT 0,
  seat_order INTEGER NOT NULL,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  message_id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  sender_id TEXT NOT NULL,
  sender_vendor TEXT NOT NULL,
  sender_kind TEXT NOT NULL,
  text TEXT NOT NULL,
  reply_to TEXT,
  provenance TEXT,                  -- JSON reported by the seat (vendor response id, etc.)
  created_at TEXT NOT NULL,
  UNIQUE(room_id, sequence)
);
CREATE TABLE IF NOT EXISTS control_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Board:
    """Storage + long-poll coordination. Thread-safe."""

    def __init__(self, db_path: str = ":memory:"):
        self.db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.versions: dict[str, int] = {}  # room_id -> change counter

    # ---------- helpers ----------
    def _bump(self, room_id: str) -> None:
        self.versions[room_id] = self.versions.get(room_id, 0) + 1
        self.cond.notify_all()

    def _room(self, room_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        if not row:
            raise ApiError(404, "room not found")
        return row

    def _log(self, room_id: str, action: str, detail: dict | None = None) -> None:
        self.db.execute(
            "INSERT INTO control_log(room_id, action, detail, created_at) VALUES (?,?,?,?)",
            (room_id, action, json.dumps(detail or {}, ensure_ascii=False), now_iso()),
        )

    def auth_conductor(self, room_id: str, token: str | None) -> sqlite3.Row:
        with self.lock:
            room = self._room(room_id)
        if not token or not secrets.compare_digest(hash_token(token), room["conductor_token_hash"]):
            raise ApiError(403, "conductor token required")
        return room

    def auth_participant(self, room_id: str, token: str | None) -> sqlite3.Row:
        if not token:
            raise ApiError(401, "participant token required")
        with self.lock:
            self._room(room_id)
            row = self.db.execute(
                "SELECT * FROM participants WHERE room_id=? AND token_hash=?",
                (room_id, hash_token(token)),
            ).fetchone()
        if not row:
            raise ApiError(403, "invalid participant token")
        return row

    def _touch(self, pid: str) -> None:
        self.db.execute(
            "UPDATE participants SET last_seen=?, status=CASE WHEN status='left' THEN 'left' ELSE 'online' END "
            "WHERE participant_id=?",
            (time.time(), pid),
        )

    @staticmethod
    def _participant_public(p: sqlite3.Row) -> dict:
        last_seen = p["last_seen"]
        status = p["status"]
        if status == "online" and (last_seen is None or time.time() - last_seen > ONLINE_WINDOW):
            status = "offline"
        return {
            "participant_id": p["participant_id"],
            "kind": p["kind"],
            "display_name": p["display_name"],
            "vendor": p["vendor"],
            "model": p["model"],
            "transport": p["transport"],
            "session_id": p["session_id"],
            "session_meta": json.loads(p["session_meta"]) if p["session_meta"] else None,
            "status": status,
            "last_seen": datetime.fromtimestamp(last_seen, timezone.utc).isoformat(timespec="seconds")
            if last_seen
            else None,
            "cursor": p["cursor"],
            "seat_order": p["seat_order"],
        }

    @staticmethod
    def _message_public(m: sqlite3.Row) -> dict:
        return {
            "message_id": m["message_id"],
            "room_id": m["room_id"],
            "sequence": m["sequence"],
            "sender_id": m["sender_id"],
            "sender_vendor": m["sender_vendor"],
            "sender_kind": m["sender_kind"],
            "text": m["text"],
            "reply_to": m["reply_to"],
            "provenance": json.loads(m["provenance"]) if m["provenance"] else None,
            "created_at": m["created_at"],
        }

    def _room_public(self, room: sqlite3.Row) -> dict:
        ai_count = self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE room_id=? AND sender_kind='ai'", (room["room_id"],)
        ).fetchone()[0]
        last_seq = self.db.execute(
            "SELECT COALESCE(MAX(sequence),0) FROM messages WHERE room_id=?", (room["room_id"],)
        ).fetchone()[0]
        return {
            "room_id": room["room_id"],
            "title": room["title"],
            "status": room["status"],
            "floor_participant_id": room["floor_participant_id"],
            "max_ai_messages": room["max_ai_messages"],
            "ai_message_count": ai_count,
            "last_sequence": last_seq,
            "created_at": room["created_at"],
            "version": self.versions.get(room["room_id"], 0),
        }

    def _participants(self, room_id: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM participants WHERE room_id=? ORDER BY seat_order", (room_id,)
        ).fetchall()

    # ---------- conductor operations ----------
    def create_room(self, title: str, max_ai_messages: int | None, user_name: str = "User") -> dict:
        with self.lock:
            room_id = "room_" + uuid.uuid4().hex[:12]
            conductor = "ct_" + secrets.token_urlsafe(24)
            self.db.execute(
                "INSERT INTO rooms VALUES (?,?,?,?,?,?,?)",
                (room_id, title[:200] or "Untitled room", "running", hash_token(conductor), None,
                 max_ai_messages, now_iso()),
            )
            user = self._add_participant(room_id, "human", user_name, "human", None, "board-ui")
            self._log(room_id, "create_room", {"title": title})
            self._bump(room_id)
            return {"room_id": room_id, "conductor_token": conductor, "user": user}

    def _add_participant(self, room_id, kind, display_name, vendor, model, transport) -> dict:
        pid = ("ai_" if kind == "ai" else "hu_") + uuid.uuid4().hex[:10]
        token = "pt_" + secrets.token_urlsafe(24)
        order = self.db.execute(
            "SELECT COALESCE(MAX(seat_order),0)+1 FROM participants WHERE room_id=?", (room_id,)
        ).fetchone()[0]
        self.db.execute(
            "INSERT INTO participants(participant_id, room_id, kind, display_name, vendor, model, transport,"
            " status, seat_order, token_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, room_id, kind, display_name[:80], vendor[:40], model, transport, "invited", order,
             hash_token(token), now_iso()),
        )
        return {"participant_id": pid, "token": token, "kind": kind, "display_name": display_name,
                "vendor": vendor}

    def add_seat(self, room_id: str, display_name: str, vendor: str, model: str | None,
                 transport: str | None) -> dict:
        with self.lock:
            self._room(room_id)
            if not vendor:
                raise ApiError(400, "vendor is required")
            seat = self._add_participant(room_id, "ai", display_name or vendor, vendor, model, transport)
            room = self._room(room_id)
            if room["floor_participant_id"] is None:
                self.db.execute("UPDATE rooms SET floor_participant_id=? WHERE room_id=?",
                                (seat["participant_id"], room_id))
            self._log(room_id, "add_seat", {"participant_id": seat["participant_id"], "vendor": vendor})
            self._bump(room_id)
            return seat

    def control(self, room_id: str, action: str, args: dict) -> dict:
        with self.lock:
            room = self._room(room_id)
            if action == "pause":
                if room["status"] == "stopped":
                    raise ApiError(409, "room is stopped")
                self.db.execute("UPDATE rooms SET status='paused' WHERE room_id=?", (room_id,))
            elif action == "resume":
                if room["status"] == "stopped":
                    raise ApiError(409, "room is stopped")
                self.db.execute("UPDATE rooms SET status='running' WHERE room_id=?", (room_id,))
            elif action == "stop":
                self.db.execute("UPDATE rooms SET status='stopped' WHERE room_id=?", (room_id,))
            elif action == "set_floor":
                pid = args.get("participant_id")
                p = self.db.execute(
                    "SELECT * FROM participants WHERE room_id=? AND participant_id=? AND kind='ai'",
                    (room_id, pid),
                ).fetchone()
                if not p:
                    raise ApiError(400, "participant_id must be an AI seat in this room")
                self.db.execute("UPDATE rooms SET floor_participant_id=? WHERE room_id=?", (pid, room_id))
            elif action == "set_max_ai_messages":
                val = args.get("max_ai_messages")
                self.db.execute("UPDATE rooms SET max_ai_messages=? WHERE room_id=?",
                                (int(val) if val else None, room_id))
            else:
                raise ApiError(400, f"unknown control action: {action}")
            self._log(room_id, action, args)
            self._bump(room_id)
            return self._room_public(self._room(room_id))

    def snapshot(self, room_id: str, after: int = 0) -> dict:
        with self.lock:
            room = self._room(room_id)
            msgs = self.db.execute(
                "SELECT * FROM messages WHERE room_id=? AND sequence>? ORDER BY sequence", (room_id, after)
            ).fetchall()
            return {
                "room": self._room_public(room),
                "participants": [self._participant_public(p) for p in self._participants(room_id)],
                "messages": [self._message_public(m) for m in msgs],
            }

    def events(self, room_id: str, after: int, version: int, timeout: float) -> dict:
        """Conductor/UI long-poll: block until the room changes."""
        deadline = time.time() + min(timeout, MAX_WAIT)
        with self.cond:
            self._room(room_id)
            while self.versions.get(room_id, 0) <= version:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self.cond.wait(remaining)
            return self.snapshot(room_id, after)

    def transcript(self, room_id: str) -> dict:
        with self.lock:
            snap = self.snapshot(room_id, 0)
            snap["control_log"] = [dict(r) for r in self.db.execute(
                "SELECT action, detail, created_at FROM control_log WHERE room_id=? ORDER BY id", (room_id,)
            ).fetchall()]
            snap["exported_at"] = now_iso()
            return snap

    # ---------- participant operations ----------
    def join(self, room_id: str, p: sqlite3.Row, body: dict) -> dict:
        with self.lock:
            session_id = str(body.get("session_id") or "")[:200] or None
            meta = body.get("session_meta") or {}
            model = body.get("model") or p["model"]
            transport = body.get("transport") or p["transport"]
            self.db.execute(
                "UPDATE participants SET session_id=?, session_meta=?, model=?, transport=?, status='online',"
                " last_seen=? WHERE participant_id=?",
                (session_id, json.dumps(meta, ensure_ascii=False)[:4000], model, transport, time.time(),
                 p["participant_id"]),
            )
            self._log(room_id, "join", {"participant_id": p["participant_id"], "session_id": session_id})
            self._bump(room_id)
            row = self.db.execute("SELECT * FROM participants WHERE participant_id=?",
                                  (p["participant_id"],)).fetchone()
            return {"participant": self._participant_public(row), "room": self._room_public(self._room(room_id))}

    def roster(self, room_id: str) -> dict:
        """What a seat may know about others: names and vendors only.
        Other seats' session ids / meta / cursors are not exposed to participants."""
        with self.lock:
            return {"participants": [
                {"participant_id": p["participant_id"], "display_name": p["display_name"],
                 "vendor": p["vendor"], "kind": p["kind"]}
                for p in self._participants(room_id)]}

    def heartbeat(self, room_id: str, p: sqlite3.Row) -> dict:
        with self.lock:
            was_online = self._participant_public(p)["status"] == "online"
            self._touch(p["participant_id"])
            if not was_online:
                self._bump(room_id)
            return {"room": self._room_public(self._room(room_id))}

    def leave(self, room_id: str, p: sqlite3.Row) -> dict:
        with self.lock:
            self.db.execute("UPDATE participants SET status='left' WHERE participant_id=?", (p["participant_id"],))
            self._log(room_id, "leave", {"participant_id": p["participant_id"]})
            self._bump(room_id)
            return {"ok": True}

    def _pending_for(self, room_id: str, p: sqlite3.Row) -> list[sqlite3.Row]:
        cursor = self.db.execute("SELECT cursor FROM participants WHERE participant_id=?",
                                 (p["participant_id"],)).fetchone()[0]
        return self.db.execute(
            "SELECT * FROM messages WHERE room_id=? AND sequence>? AND sender_id<>? ORDER BY sequence",
            (room_id, cursor, p["participant_id"]),
        ).fetchall()

    def wait(self, room_id: str, p: sqlite3.Row, timeout: float) -> dict:
        """Seat long-poll. Returns when (room running AND it's this seat's turn AND there are unread
        messages from others) or when the room is stopped or the timeout elapses.
        Does not advance the cursor: the seat calls ack() after reading."""
        deadline = time.time() + min(max(timeout, 0), MAX_WAIT)
        pid = p["participant_id"]
        with self.cond:
            while True:
                self._touch(pid)
                room = self._room(room_id)
                if room["status"] == "stopped":
                    return {"state": "stopped", "messages": [], "room": self._room_public(room)}
                pending = self._pending_for(room_id, p)
                my_turn = p["kind"] == "human" or room["floor_participant_id"] == pid
                if room["status"] == "running" and my_turn and pending:
                    return {"state": "ready", "messages": [self._message_public(m) for m in pending],
                            "room": self._room_public(room)}
                remaining = deadline - time.time()
                if remaining <= 0:
                    state = "paused" if room["status"] == "paused" else ("not_your_turn" if pending else "idle")
                    return {"state": state, "messages": [], "room": self._room_public(room)}
                # Wake at least every 15s to refresh last_seen.
                self.cond.wait(min(remaining, 15.0))

    def ack(self, room_id: str, p: sqlite3.Row, sequence: int) -> dict:
        with self.lock:
            self.db.execute(
                "UPDATE participants SET cursor=MAX(cursor, ?) WHERE participant_id=?",
                (int(sequence), p["participant_id"]),
            )
            self._bump(room_id)
            cur = self.db.execute("SELECT cursor FROM participants WHERE participant_id=?",
                                  (p["participant_id"],)).fetchone()[0]
            return {"cursor": cur}

    def post(self, room_id: str, p: sqlite3.Row, body: dict) -> dict:
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(400, "text is required")
        if len(text) > MAX_TEXT:
            raise ApiError(413, f"text longer than {MAX_TEXT} chars")
        reply_to = body.get("reply_to") or None
        provenance = body.get("provenance") or None
        with self.lock:
            room = self._room(room_id)
            if room["status"] == "stopped":
                raise ApiError(409, "room is stopped")
            if p["kind"] == "ai":
                if room["status"] == "paused":
                    raise ApiError(409, "room is paused")
                if room["floor_participant_id"] != p["participant_id"]:
                    raise ApiError(409, "not your turn")
            reply_seq = None
            if reply_to:
                r = self.db.execute("SELECT sequence FROM messages WHERE room_id=? AND message_id=?",
                                    (room_id, reply_to)).fetchone()
                if not r:
                    raise ApiError(400, "reply_to does not exist in this room")
                reply_seq = r["sequence"]
            seq = self.db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM messages WHERE room_id=?",
                                  (room_id,)).fetchone()[0]
            mid = "msg_" + uuid.uuid4().hex[:16]
            self.db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?)",
                (mid, room_id, seq, p["participant_id"], p["vendor"], p["kind"], text, reply_to,
                 json.dumps(provenance, ensure_ascii=False)[:4000] if provenance else None, now_iso()),
            )
            # Own message counts as read; replying implies having read up to reply_to.
            self.db.execute("UPDATE participants SET cursor=MAX(cursor, ?, ?) WHERE participant_id=?",
                            (seq, reply_seq or 0, p["participant_id"]))
            self._touch(p["participant_id"])
            if p["kind"] == "ai":
                self._advance_floor(room_id, p["participant_id"])
                ai_count = self.db.execute(
                    "SELECT COUNT(*) FROM messages WHERE room_id=? AND sender_kind='ai'", (room_id,)
                ).fetchone()[0]
                if room["max_ai_messages"] and ai_count >= room["max_ai_messages"]:
                    self.db.execute("UPDATE rooms SET status='stopped' WHERE room_id=?", (room_id,))
                    self._log(room_id, "auto_stop", {"ai_message_count": ai_count})
            self._bump(room_id)
            m = self.db.execute("SELECT * FROM messages WHERE message_id=?", (mid,)).fetchone()
            return {"message": self._message_public(m)}

    def _advance_floor(self, room_id: str, current_pid: str) -> None:
        seats = [r["participant_id"] for r in self.db.execute(
            "SELECT participant_id FROM participants WHERE room_id=? AND kind='ai' AND status<>'left'"
            " ORDER BY seat_order", (room_id,)).fetchall()]
        if not seats:
            return
        idx = seats.index(current_pid) if current_pid in seats else -1
        nxt = seats[(idx + 1) % len(seats)]
        self.db.execute("UPDATE rooms SET floor_participant_id=? WHERE room_id=?", (nxt, room_id))


class Handler(BaseHTTPRequestHandler):
    board: Board  # set on the class by make_server
    server_version = "MeetingBoard/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter logs
        if os.environ.get("MB_HTTP_LOG"):
            super().log_message(fmt, *args)

    # ---- plumbing ----
    def _send(self, status: int, payload, content_type="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Browser seats (userscripts) call from other origins; tokens are in headers, not cookies.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _token(self) -> str | None:
        h = self.headers.get("Authorization", "")
        return h[7:].strip() if h.lower().startswith("bearer ") else None

    def _read_raw_body(self) -> None:
        """Always drain the request body, even for endpoints that ignore it. Otherwise leftover
        bytes corrupt the next request on a keep-alive connection."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > 200_000:
            self.close_connection = True
            raise ApiError(413, "body too large")
        self._raw = self.rfile.read(n) if n else b""

    def _body(self) -> dict:
        if not self._raw:
            return {}
        try:
            data = json.loads(self._raw)
        except json.JSONDecodeError:
            raise ApiError(400, "invalid JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON object expected")
        return data

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        try:
            self._raw = b""
            self._read_raw_body()
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            if not parts or parts[0] != "api":
                return self._static(url.path)
            result = self._route(method, parts[1:], q)
            self._send(200, result)
        except ApiError as e:
            self._send(e.status, {"error": e.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # pragma: no cover
            self._send(500, {"error": f"internal error: {type(e).__name__}"})

    def _static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR.resolve() not in target.parents or not target.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def _route(self, method: str, parts: list[str], q: dict):
        b = self.board
        tok = self._token()
        if parts == ["health"]:
            return {"ok": True}
        if parts == ["rooms"] and method == "POST":
            body = self._body()
            mx = body.get("max_ai_messages")
            return b.create_room(str(body.get("title") or "Untitled room"), int(mx) if mx else None,
                                 str(body.get("user_name") or "User"))
        if len(parts) < 2 or parts[0] != "rooms":
            raise ApiError(404, "unknown endpoint")
        rid = parts[1]
        rest = parts[2:]

        # ----- conductor (control channel) -----
        if rest == [] and method == "GET":
            b.auth_conductor(rid, tok)
            return b.snapshot(rid, int(q.get("after", 0)))
        if rest == ["events"] and method == "GET":
            b.auth_conductor(rid, tok)
            return b.events(rid, int(q.get("after", 0)), int(q.get("version", -1)),
                            float(q.get("timeout", 25)))
        if rest == ["transcript"] and method == "GET":
            b.auth_conductor(rid, tok)
            return b.transcript(rid)
        if rest == ["verify"] and method == "GET":
            b.auth_conductor(rid, tok)
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from tools.verify import render_report, verify
            t = b.transcript(rid)
            rep = verify(t, int(q.get("min_round_trips", 10)))
            rep["report_text"] = render_report(t, rep)
            return rep
        if rest == ["seats"] and method == "POST":
            b.auth_conductor(rid, tok)
            body = self._body()
            return b.add_seat(rid, str(body.get("display_name") or ""), str(body.get("vendor") or ""),
                              body.get("model"), body.get("transport"))
        if rest == ["control"] and method == "POST":
            b.auth_conductor(rid, tok)
            body = self._body()
            return b.control(rid, str(body.get("action") or ""), body.get("args") or {})

        # ----- participants (message channel; text only, no control rights) -----
        if rest == ["join"] and method == "POST":
            p = b.auth_participant(rid, tok)
            return b.join(rid, p, self._body())
        if rest == ["roster"] and method == "GET":
            p = b.auth_participant(rid, tok)
            return b.roster(rid)
        if rest == ["heartbeat"] and method == "POST":
            p = b.auth_participant(rid, tok)
            return b.heartbeat(rid, p)
        if rest == ["leave"] and method == "POST":
            p = b.auth_participant(rid, tok)
            return b.leave(rid, p)
        if rest == ["wait"] and method == "GET":
            p = b.auth_participant(rid, tok)
            return b.wait(rid, p, float(q.get("timeout", 25)))
        if rest == ["ack"] and method == "POST":
            p = b.auth_participant(rid, tok)
            return b.ack(rid, p, int(self._body().get("sequence", 0)))
        if rest == ["messages"] and method == "POST":
            p = b.auth_participant(rid, tok)
            return b.post(rid, p, self._body())
        raise ApiError(404, "unknown endpoint")


def make_server(host: str, port: int, db_path: str = ":memory:") -> tuple[ThreadingHTTPServer, Board]:
    board = Board(db_path)
    handler = type("BoundHandler", (Handler,), {"board": board})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv, board


def main():
    ap = argparse.ArgumentParser(description="Cross-Vendor AI Meeting Board")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--db", default=os.environ.get("MB_DB", "meeting_board.sqlite3"))
    args = ap.parse_args()
    srv, _ = make_server(args.host, args.port, args.db)
    print(f"Meeting Board listening on http://{args.host}:{args.port}  (db: {args.db})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
