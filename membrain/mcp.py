# -*- coding: utf-8 -*-
"""最小 MCP server：把这个记忆内核接到任何支持 MCP 的客户端。

零依赖 —— 只用标准库，自己讲 JSON-RPC，不引入 `mcp` 包。
传输是 stdio，一行一个 JSON（MCP 的 standard input/output framing）。

启动：
    python -m membrain.mcp

在 DSH（cordis.patch.yml）里挂上去：
    - insert:
        - id: mcp-membrain
          name: '@deepseek-ai/dsh-mcp-client'
          config:
            serverName: membrain
            transport: stdio
            command: 'python'
            args: ['-m', 'membrain.mcp']
            cwd: '<这个仓库的路径>'
            env:
              MEMBRAIN_HOME: '<这个仓库的路径>\\.membrain'

挂上之后工具名会变成 mcp__membrain__remember / mcp__membrain__recall 之类。
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from .config import Config
from .engine import Engine

SERVER_NAME = "membrain"
SERVER_VERSION = "0.1.0"
# 我们会话里能讲的最低标准；客户端给的版本如果在我们认识的列表里就原样回。
KNOWN_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

# ---------------------------------------------------------------- 工具定义

TOOLS: list[dict[str, Any]] = [
    {
        "name": "remember",
        "description": (
            "记住一句话。「以后用得上」的才写：一个事实、一条偏好、一次决定、一个教训。"
            "不要写寒暄，也不要一次写一段长文——一句话一条。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要记的内容，一句话说清楚。"},
                "kind": {
                    "type": "string",
                    "enum": ["episode", "fact", "reflection", "skill", "lesson"],
                    "description": "记忆类型，默认 episode（事件）。",
                },
                "scope": {"type": "string", "description": "归属会话/场景，例如 group:100000001、private:100000002。默认 default。"},
                "importance": {"type": "number", "description": "重要度 0~1，默认 0.5。硬事实、明确约定给 0.8 以上。"},
                "who": {"type": "string", "description": "因为谁（可选）。"},
                "topic": {"type": "string", "description": "当时在聊什么（可选）。"},
                "why": {"type": "string", "description": "为什么记下来（可选）。"},
                "note": {"type": "string", "description": "备注，写「以后怎么用」最有用（可选）。"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "recall",
        "description": (
            "按一句话去翻记忆。五路加权（关键词/语义/重要度/新鲜度/图谱），"
            "返回最相关的几条，带类型、层级和分数。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用自然语言描述要找什么。"},
                "k": {"type": "integer", "description": "返回几条，默认 5。"},
                "scope": {"type": "string", "description": "只在某个会话/场景里找（可选）。"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "brief",
        "description": "唤醒时该注入的那一小段：关于主人的几条最硬的记忆。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "description": "只取某个会话/场景的（可选）。"},
                "limit": {"type": "integer", "description": "最多几条，默认 8。"},
            },
        },
    },
    {
        "name": "tick",
        "description": "让遗忘走一步（衰减 + 分层 + 归档）。建议一天跑一次或按需调用。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "stats",
        "description": "看一眼记忆库的规模：总数、各层级条数。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------- 内核

class Server:
    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._cfg: Config | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._cfg = Config.load()
            self._engine = Engine(self._cfg)
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.close()
            except Exception:  # noqa: BLE001
                pass
            self._engine = None

    # ---- 工具实现 -------------------------------------------------

    def tool_remember(self, a: dict[str, Any]) -> str:
        text = (a.get("text") or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        eng = self.engine
        res = eng.remember(
            text,
            kind=a.get("kind") or "episode",
            scope=a.get("scope") or "default",
            importance=float(a.get("importance", 0.5)),
            who=a.get("who"),
            topic=a.get("topic"),
            why=a.get("why"),
            note=a.get("note"),
        )
        if not res.get("ok"):
            return "没写下：" + str(res.get("reason") or "未知原因")
        if res.get("deduped"):
            return f"这条跟已有的 #{res['id']} 很像，没有重复写，只给它加了一次「被想起」。"
        return f"记下了（#{res['id']}）：{text}"

    def tool_recall(self, a: dict[str, Any]) -> str:
        query = (a.get("query") or "").strip()
        if not query:
            raise ValueError("query 不能为空")
        k = int(a.get("k", 5) or 5)
        eng = self.engine
        rows = eng.recall(query, k=k, scope=a.get("scope") or None, explain=True)
        if not rows:
            return "没想起相关的东西。"
        out = []
        for i, r in enumerate(rows, 1):
            got = eng.store.get(int(r["id"]))
            row = dict(got) if got is not None else {}
            tier = row.get("tier") or "?"
            kind = r.get("kind", "")
            score = r.get("score")
            head = f"{i}. [{tier}/{kind}"
            if isinstance(score, (int, float)):
                head += f" {score:.3f}"
            head += f"] {r.get('text', '')}"
            out.append(head)
            why = r.get("why")
            if isinstance(why, dict):
                bits = []
                for key in ("keyword", "semantic", "graph"):
                    val = why.get(key)
                    if isinstance(val, (int, float)) and val:
                        bits.append(f"{key} {val:.2f}")
                if why.get("neighbor"):
                    bits.append("图谱相邻")
                if bits:
                    out.append("   为什么想到它：" + "、".join(bits))
        return "\n".join(out)

    def tool_brief(self, a: dict[str, Any]) -> str:
        text = self.engine.brief(scope=a.get("scope") or None, limit=int(a.get("limit", 8) or 8))
        return text or "还没有值得唤醒时说的硬记忆。"

    def tool_tick(self, a: dict[str, Any]) -> str:
        changed = self.engine.tick()
        return (
            "遗忘走了一步："
            f"变习惯 {changed.get('habit', 0)} 条、"
            f"渐忘 {changed.get('fading', 0)} 条、"
            f"边缘 {changed.get('edge', 0)} 条、"
            f"归档 {changed.get('archived', 0)} 条。"
        )

    def tool_stats(self, a: dict[str, Any]) -> str:
        counts = self.engine.store.counts() or {}
        total = int(counts.get("total", 0)) or sum(
            int(v) for k, v in counts.items() if k != "total"
        )
        detail = "、".join(
            f"{k} {v}" for k, v in sorted(counts.items()) if k != "total"
        ) or "空"
        return f"共 {total} 条（{detail}）。库里：{self.engine.cfg.db_path}"

    # ---- JSON-RPC -------------------------------------------------

    def handle(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        method = msg.get("method")
        mid = msg.get("id", _MISSING)
        is_notification = mid is _MISSING

        if is_notification:
            # notifications/initialized、notifications/cancelled 之类，无需回应
            return None

        try:
            if method == "initialize":
                return _ok(mid, self._initialize(msg.get("params") or {}))
            if method == "ping":
                return _ok(mid, {})
            if method == "tools/list":
                return _ok(mid, {"tools": TOOLS})
            if method == "tools/call":
                return _ok(mid, self._tools_call(msg.get("params") or {}))
            if method == "resources/list":
                return _ok(mid, {"resources": []})
            if method == "prompts/list":
                return _ok(mid, {"prompts": []})
            return _err(mid, -32601, f"Method not found: {method}")
        except Exception as exc:  # noqa: BLE001
            return _err(mid, -32603, f"{type(exc).__name__}: {exc}")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        wanted = params.get("protocolVersion")
        proto = wanted if wanted in KNOWN_PROTOCOLS else KNOWN_PROTOCOLS[0]
        return {
            "protocolVersion": proto,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "这是一个很小的长期记忆库。"
                "对方说过「以后用得上」的话，用 remember 记一句；"
                "回答前想确认旧事，用 recall 或 brief 先翻一遍，别硬编。"
            ),
        }

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise ValueError("arguments 必须是对象")
        table = {
            "remember": self.tool_remember,
            "recall": self.tool_recall,
            "brief": self.tool_brief,
            "tick": self.tool_tick,
            "stats": self.tool_stats,
        }
        fn = table.get(name)
        if fn is None:
            return {
                "content": [{"type": "text", "text": f"没有这个工具：{name}"}],
                "isError": True,
            }
        try:
            text = fn(args)
        except Exception as exc:  # noqa: BLE001
            return {
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True,
            }
        return {"content": [{"type": "text", "text": text}], "isError": False}


# ---------------------------------------------------------------- 进程

_MISSING = object()


def _ok(mid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _log(msg: str) -> None:
    sys.stderr.write(f"[membrain-mcp] {msg}\n")
    sys.stderr.flush()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

    srv = Server()
    started = time.time()
    _log(f"{SERVER_NAME} {SERVER_VERSION} 就绪（stdio）")
    try:
        for line in sys.stdin:
            # 有些管道（PowerShell / Windows 下重定向）会在第一行前面塞 BOM，
            # 直接 json.loads 会炸，先剥掉。
            line = line.lstrip("\ufeff").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                _log(f"收到坏 JSON：{exc}")
                continue
            if not isinstance(msg, dict):
                _log("收到非对象消息，忽略")
                continue
            try:
                reply = srv.handle(msg)
            except Exception as exc:  # noqa: BLE001
                mid = msg.get("id")
                reply = None if mid is None else _err(mid, -32603, f"{type(exc).__name__}: {exc}")
            if reply is not None:
                sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        _log(f"退出（跑了 {time.time() - started:.1f}s）")


if __name__ == "__main__":
    main()
