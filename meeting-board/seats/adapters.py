"""Concrete seat adapters.

DummySeat       - deterministic, no model. Used to verify A -> B -> A relay.
ClaudeCodeSeat  - a real, independent Claude Code session driven headlessly
                  (`claude -p --session-id/--resume`), with ALL tools disabled.
APISeat         - a real vendor API conversation (openai | anthropic | gemini).
                  Each instance keeps its own private history in this process only.

Browser seats (ChatGPTWebSeat / ClaudeWebSeat / GeminiWebSeat) live in
seats/web/meeting-board-seat.user.js because they must run inside the tab
the user already has open and logged in.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid

from .base import BoardMessage, Reply, SeatAdapter, frame_for_model, http_json


class DummySeat(SeatAdapter):
    transport = "dummy"

    def __init__(self, board, vendor: str = "dummy", label: str = "Dummy", **kw):
        super().__init__(board, **kw)
        self.vendor = vendor
        self.label = label
        self.session_id = f"dummy-{vendor}-{uuid.uuid4().hex[:8]}"
        self.turn = 0

    def session_info(self):
        return self.session_id, "dummy-echo-v1", {"note": "deterministic test seat, no model"}

    def respond(self, messages: list[BoardMessage]) -> Reply:
        self.turn += 1
        last = messages[-1]
        # Echo only a short, inert digest of the other side's text. Never acts on it.
        snippet = last.text.replace("\n", " ")[:60]
        return Reply(
            f"[{self.label} turn {self.turn}] received {last.message_id} from {last.sender_vendor}: «{snippet}»",
            {"seat": "dummy", "session_id": self.session_id, "turn": self.turn,
             "read": [m.message_id for m in messages]},
        )


class ClaudeCodeSeat(SeatAdapter):
    """One independent Claude Code conversation, kept alive across turns via --resume.

    * `--tools ""` removes every tool: even if another AI writes "delete all files",
      this Claude session physically has no file/shell tool to do it with.
    * Runs in an empty scratch directory with project/user settings not loaded.
    """

    vendor = "anthropic"
    transport = "claude-code-cli"

    def __init__(self, board, model: str | None = None, session_id: str | None = None,
                 claude_bin: str = "claude", timeout: float = 300, **kw):
        super().__init__(board, **kw)
        self.model = model
        self.session_id = session_id or str(uuid.uuid4())
        self.started = False
        self.claude_bin = shutil.which(claude_bin) or claude_bin
        self.timeout = timeout
        self.workdir = tempfile.mkdtemp(prefix="mb-claude-seat-")
        self.last_reported_model: str | None = None

    def session_info(self):
        return self.session_id, self.model, {"cli": self.claude_bin, "workdir": self.workdir,
                                             "tools": "none"}

    def respond(self, messages: list[BoardMessage]) -> Reply:
        prompt = frame_for_model(messages)
        cmd = [self.claude_bin, "-p", "--output-format", "json", "--tools", "",
               "--strict-mcp-config", "--setting-sources", "",
               "--append-system-prompt", self.system_prompt()]
        if self.model:
            cmd += ["--model", self.model]
        cmd += (["--resume", self.session_id] if self.started else ["--session-id", self.session_id])
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE",)}
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout,
                              cwd=self.workdir, env=env)
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            out = {}
        # A failed turn (e.g. API error) can still create the session. Later attempts must
        # then --resume it; --session-id again fails with "already in use".
        if out.get("session_id") == self.session_id:
            self.started = True
        if proc.returncode != 0 or out.get("is_error"):
            detail = out.get("result") or proc.stderr[-800:] or proc.stdout[-800:]
            raise RuntimeError(f"claude failed (exit {proc.returncode}): {detail}")
        self.started = True
        reported_sid = out.get("session_id")
        models = list((out.get("modelUsage") or {}).keys())
        self.last_reported_model = models[0] if models else None
        if not self.model and self.last_reported_model:
            self.model = self.last_reported_model
        return Reply(out.get("result", "").strip(), {
            "seat": "claude-code-cli",
            "requested_session_id": self.session_id,
            "reported_session_id": reported_sid,
            "reported_models": models,
            "usage": {k: out.get("usage", {}).get(k) for k in ("input_tokens", "output_tokens")},
            "duration_api_ms": out.get("duration_api_ms"),
        })


class APISeat(SeatAdapter):
    """Real vendor API conversation.

    Providers:
      openai             OpenAI Chat Completions
      anthropic          Anthropic Messages
      gemini             Google Gemini generateContent
      meta               Meta Model API (Muse Spark). Base URL https://api.meta.ai/v1, OpenAI-style
                         chat completions by default. NOT exercised against the live API from the
                         development sandbox (host blocked); check dev.meta.ai and override with
                         META_BASE_URL / --model / META_API_FORMAT=anthropic if needed.
      openai-compatible  Any OpenAI-compatible endpoint: set --base-url, --vendor, --key-env.
    Default model names are only defaults; pass --model to pin what you actually use.
    """

    transport = "vendor-api"

    DEFAULT_MODELS = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-5", "gemini": "gemini-2.5-flash",
                      "meta": "muse-spark-1.3", "openai-compatible": None}
    KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY",
               "meta": "META_API_KEY", "openai-compatible": "COMPAT_API_KEY"}
    VENDORS = {"openai": "openai", "anthropic": "anthropic", "gemini": "google", "meta": "meta"}

    def __init__(self, board, provider: str, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, vendor: str | None = None, key_env: str | None = None, **kw):
        super().__init__(board, **kw)
        if provider not in self.DEFAULT_MODELS:
            raise ValueError(f"unknown provider {provider}")
        self.provider = provider
        self.vendor = vendor or self.VENDORS.get(provider) or "unknown"
        self.base_url = base_url
        env_prefix = provider.upper().replace("-", "_")
        self.model = model or os.environ.get(f"{env_prefix}_MODEL") or self.DEFAULT_MODELS[provider]
        if not self.model:
            raise RuntimeError("--model is required for this provider")
        key_var = key_env or self.KEY_ENV[provider]
        self.api_key = api_key or os.environ.get(key_var) or (
            os.environ.get("GOOGLE_API_KEY") if provider == "gemini" else None)
        if not self.api_key:
            raise RuntimeError(f"{key_var} is not set")
        self.session_id = f"{provider}-conv-{uuid.uuid4().hex[:12]}"
        self.history: list[tuple[str, str]] = []  # private to this seat: (role, text)

    def session_info(self):
        return self.session_id, self.model, {"provider": self.provider,
                                             "history": "kept in this seat process only"}

    def respond(self, messages: list[BoardMessage]) -> Reply:
        # Add the turn to history only after the call succeeds, so a retry does not
        # send the same meeting text twice.
        self.history.append(("user", frame_for_model(messages)))
        try:
            text, prov = getattr(self, "_call_" + self.provider.replace("-", "_"))()
        except Exception:
            self.history.pop()
            raise
        self.history.append(("assistant", text))
        prov.update({"seat": "vendor-api", "provider": self.provider, "conversation": self.session_id})
        return Reply(text.strip(), prov)

    def _call_meta(self):
        base = (self.base_url or os.environ.get("META_BASE_URL", "https://api.meta.ai/v1")).rstrip("/")
        if os.environ.get("META_API_FORMAT") == "anthropic":
            return self._call_anthropic(base_override=base)
        return self._call_openai(base_override=base)

    def _call_openai_compatible(self):
        if not self.base_url:
            raise RuntimeError("--base-url is required for openai-compatible")
        return self._call_openai(base_override=self.base_url)

    def _call_openai(self, base_override: str | None = None):
        base = (base_override or self.base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        msgs = [{"role": "system", "content": self.system_prompt()}] + [
            {"role": r, "content": t} for r, t in self.history]
        out = http_json(f"{base}/chat/completions", {"model": self.model, "messages": msgs},
                        {"Authorization": f"Bearer {self.api_key}"})
        return out["choices"][0]["message"]["content"], {
            "vendor_response_id": out.get("id"), "vendor_reported_model": out.get("model")}

    def _call_anthropic(self, base_override: str | None = None):
        if base_override:
            url = f"{base_override.rstrip('/')}/messages"
        else:
            url = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        out = http_json(url, {
            "model": self.model, "max_tokens": 1024, "system": self.system_prompt(),
            "messages": [{"role": r, "content": t} for r, t in self.history]},
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
        return text, {"vendor_response_id": out.get("id"), "vendor_reported_model": out.get("model")}

    def _call_gemini(self):
        base = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        contents = [{"role": "model" if r == "assistant" else "user", "parts": [{"text": t}]}
                    for r, t in self.history]
        out = http_json(f"{base}/models/{self.model}:generateContent", {
            "systemInstruction": {"parts": [{"text": self.system_prompt()}]}, "contents": contents},
            {"x-goog-api-key": self.api_key})
        parts = out["candidates"][0]["content"].get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return text, {"vendor_response_id": out.get("responseId"),
                      "vendor_reported_model": out.get("modelVersion")}


class CommandSeat(SeatAdapter):
    """Bridge seat for agents without a usable API here (messaging agents, internal tools, ...).

    Runs a user-supplied bridge program once per turn: the framed meeting text goes to its
    stdin, and its stdout must be the AI's actual reply. The bridge is responsible for talking
    to the real AI session (e.g. a WhatsApp/SMS gateway, an SDK, a desktop app automation).

    Safety: the command line is fixed at seat start by the operator. Board text is passed only
    as stdin data, never as arguments, and no shell is used.
    """

    transport = "command-bridge"

    def __init__(self, board, vendor: str, command: list[str], session_id: str | None = None,
                 model: str | None = None, timeout: float = 600, **kw):
        super().__init__(board, **kw)
        if not command:
            raise ValueError("command is required")
        self.vendor = vendor
        self.command = command
        self.model = model
        self.session_id = session_id or f"{vendor}-bridge-{uuid.uuid4().hex[:10]}"
        self.timeout = timeout

    def session_info(self):
        return self.session_id, self.model, {"bridge": self.command[0]}

    def respond(self, messages: list[BoardMessage]) -> Reply:
        env = dict(os.environ, MB_SEAT_SESSION_ID=self.session_id)
        proc = subprocess.run(self.command, input=frame_for_model(messages), capture_output=True, text=True,
                              timeout=self.timeout, env=env, shell=False)
        if proc.returncode != 0:
            raise RuntimeError(f"bridge exited {proc.returncode}: {proc.stderr[-500:]}")
        return Reply(proc.stdout.strip(), {"seat": "command-bridge", "session_id": self.session_id})
