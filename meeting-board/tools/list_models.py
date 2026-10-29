"""Print the chat models your API key can use, to pick a value for *_MODEL in settings.env.

    python tools/list_models.py chatgpt     # OPENAI_API_KEY  -> OPENAI_MODEL
    python tools/list_models.py grok        # XAI_API_KEY     -> GROK_MODEL
    python tools/list_models.py gemini      # GEMINI_API_KEY  -> GEMINI_MODEL

On the NAS (reads the key from settings.env, so it never appears on the command line):
    sudo docker run --rm --env-file settings.env ai-debate python tools/list_models.py grok
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.debate import tidy_env  # noqa: E402

# Model ids containing these are not chat models (images, audio, embeddings, ...).
NOT_CHAT = ("embedding", "tts", "whisper", "dall-e", "image", "audio", "realtime", "transcribe",
            "moderation", "imagine", "video", "sora", "search")

TARGETS = {
    "chatgpt": ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "grok": ("XAI_API_KEY", "GROK_MODEL", "XAI_BASE_URL", "https://api.x.ai/v1"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
}


def list_models(kind: str) -> list[str]:
    key_env, _, base_env, base = TARGETS[kind]
    key = os.environ.get(key_env) or (os.environ.get("GOOGLE_API_KEY") if kind == "gemini" else None)
    if not key:
        raise SystemExit(f"{key_env}가 settings.env에 없습니다.")
    base = (os.environ.get(base_env) or base).rstrip("/")
    if kind == "gemini":
        req = urllib.request.Request(f"{base}/models?pageSize=200", headers={"x-goog-api-key": key})
    else:
        req = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
    req.add_header("User-Agent", "meeting-board/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"{base} 에 연결하지 못했습니다: {e.reason}") from None
    if kind == "gemini":
        ids = [m["name"].removeprefix("models/") for m in data.get("models", [])
               if "generateContent" in m.get("supportedGenerationMethods", [])]
    else:
        ids = [m["id"] for m in data.get("data", [])]
    return sorted(i for i in ids if not any(w in i.lower() for w in NOT_CHAT))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in TARGETS:
        raise SystemExit(f"사용법: python tools/list_models.py {'|'.join(TARGETS)}")
    tidy_env()
    kind = sys.argv[1]
    ids = list_models(kind)
    print("\n".join(ids) if ids else "(대화용 모델이 없습니다)")
    print(f"\n→ 이 중 하나를 settings.env 에 {TARGETS[kind][1]}=모델이름 으로 넣으세요.")


if __name__ == "__main__":
    main()
