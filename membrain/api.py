# -*- coding: utf-8 -*-
"""HTTP 接口：给聊天机器人 / 前端 / 手机页用。

只要四条：什么都能问（/recall）、什么都能记（/remember）、
唤醒简报（/brief）、活着吗（/health）。
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .engine import Engine


def serve(engine: Engine, port: int | None = None, host: str = "127.0.0.1") -> None:
    port = int(port or engine.cfg.port)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, code: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:  # noqa: BLE001
                return {}

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/health"):
                return self._json({"ok": True, "counts": engine.store.counts()})
            if self.path.startswith("/brief"):
                return self._json({"ok": True, "text": engine.brief()})
            self._json({"ok": False, "error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            data = self._body()
            if self.path.startswith("/recall"):
                return self._json({"ok": True, "items": engine.recall(
                    str(data.get("query") or ""), int(data.get("k") or 5),
                    scope=data.get("scope") or None,
                    explain=bool(data.get("explain")))})
            if self.path.startswith("/remember"):
                return self._json(engine.remember(
                    str(data.get("text") or ""), kind=str(data.get("kind") or "episode"),
                    scope=str(data.get("scope") or "default"),
                    importance=float(data.get("importance") or 0.5),
                    who=data.get("who"), topic=data.get("topic"),
                    why=data.get("why"), note=data.get("note")))
            if self.path.startswith("/tick"):
                return self._json({"ok": True, "changed": engine.tick()})
            self._json({"ok": False, "error": "not found"}, 404)

        def log_message(self, fmt, *args):  # 静音
            return

    print(f"membrain api on http://{host}:{port}  (db={engine.cfg.db_path})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
