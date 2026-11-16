"""A tiny fake of Apertus's OpenAI-compatible endpoint, for tests without the model.

    python scripts/fake_apertus.py [port]        # default 8089, loopback only

POST /v1/chat/completions answers deterministically from the system message:
- "Translate ... into <Lang>. ... Reply with JSON only" -> {"lang": "fr", "text": "[<Lang>] <text>"}
- "Translate ... into <Lang>. ..."                        -> "[<Lang>] <text>"
- "Translate ... into Chinese. ..."                        -> a fixed Chinese sentence (so the
  only server voice today, zh, has real Chinese to read aloud)
- "Rewrite ... in plain ..."                               -> "In simple words: <text>" (numbers kept)
GET /v1/models and /health answer 200. Nothing is logged or stored.
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def answer(system, user):
    target = re.search(r"into (\w+)", system)
    lang = target.group(1) if target else "?"
    text = "我头痛三天了。请给我一点水。" if lang == "Chinese" else f"[{lang}] {user}"
    if "JSON only" in system:
        return json.dumps({"lang": "fr", "text": text})
    if system.startswith("Translate"):
        return text
    if system.startswith("Rewrite"):
        return f"In simple words: {user}"
    return user


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/v1/models", "/health"):
            self._send(200, {"data": [{"id": "fake-apertus"}], "status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            messages = json.loads(self.rfile.read(length))["messages"]
            system = next(m["content"] for m in messages if m["role"] == "system")
            user = next(m["content"] for m in messages if m["role"] == "user")
        except (ValueError, KeyError, StopIteration, TypeError):
            self._send(400, {"error": "bad request"})
            return
        self._send(200, {
            "object": "chat.completion",
            "model": "fake-apertus",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": answer(system, user)}}],
        })

    def log_message(self, *args):
        pass  # no request lines: texts never reach a log


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8089
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
