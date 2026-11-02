# 设置阶段自检清单（给接手这个仓库的 agent）

> **这份文件是命令，不是说明书。**
> 你刚接手本项目、准备开始干活之前，按顺序跑完下面四步。全部 exit 0 再动手；
> 有任何一处失败，**先修，再继续**——不要带着死引用往前做。

适用对象：任何被要求「安装 / 部署 / 改这个仓库」的 agent（DSH、Claude Code、Cursor、Codex 都行）。
预期耗时：第一次 2–3 分钟，之后 30 秒。

工作目录一律为仓库根：

```bash
cd /path/to/membrain-lite          # Windows: cd C:\path\to\membrain-lite
```

---

## 第 1 步：链接与骨架（最重要，专治 404）

```bash
python scripts/check_links.py
```

它会做两件事：

1. **扫文档里的引用**——`README.md` 与 `docs/*.md` 中的 Markdown 链接、图片、HTML `src/href`、
   反引号里的仓库路径、裸 URL。本地文件必须存在，外链必须能通（HTTP >= 400 即失败）。
2. **核对骨架文件**是否齐全——`membrain/*.py`、`prompts/*.md`、`data/seed_demo.jsonl`、
   `eval/cases.jsonl`、`examples/radial/index.html`、`scripts/check_privacy.py`、`tests/test_core.py` 等。

常用开关：

```bash
python scripts/check_links.py --offline        # 没网/不想等外链时：只查本地
python scripts/check_links.py --timeout 8      # 外链超时（默认 5 秒）
python scripts/check_links.py --json           # 机器可读，便于自己解析
```

退出码：`0` 干净；`1` 有问题（输出里会逐条给 `文件:行号 → 目标 → 原因`）。

### 出了 404 怎么办（按这个顺序）

| 顺序 | 做法 | 说明 |
|---|---|---|
| 1 | **改指向** | 路径本身写错了（拼写、少一层目录、大小写），改成正确路径即可。 |
| 2 | **换资源** | 文件被删或改名，就用仓库里现成的等价文档/代码顶上。 |
| 3 | **降级为文字** | 没有替代品：去掉链接，只留一句说明，不留死链。 |
| 4 | **记录下来** | 确实需要但暂时没有的，写进本文末尾「已知问题」并注明打算怎么补。 |
| 5 | **复跑** | 改完再跑一次第 1 步，直到 exit 0。 |

示例（**下面这段故意写成坏路径，仅作示范；代码块里的内容不参与检查**）：

```
membrain/engin.py        → 拼错了，改成 membrain/engine.py
docs/OLD-PLAN.md         → 文件已删，改指 docs/ARCHITECTURE.md
docs/OBS.md              → 还没写，先把链接降级成纯文字并记进「已知问题」
```

**禁止的做法**：为了让检查通过而把链接删得只剩空标题；改 `check_links.py` 的规则去容忍真死链；
跳过失败直接提交。

---

## 第 2 步：隐私（准备对外/提交前必跑）

```bash
python scripts/check_privacy.py
```

扫的是「私人信息形态」：真实昵称、凭据、邮箱、手机号、长数字串（QQ 号/群号级别）、
以及**本机绝对路径**（`C:/Users/<你的用户名>`、`/home/<你的名>`、`/Users/<你的名>`）。

- 占位符写法不报：`C:/path/to/proj`、`/home/<you>/proj`、`~/proj`、`${HOME}/proj`。
- 退出码 `0` = 干净；`1` = 有命中，逐条给出行号。
- 命中长数字串不一定是错（示例数据里的假号码也可能命中），自己判断后决定改写还是保留；
  命中真实用户名/凭据**必须**改。

---

## 第 3 步：功能自测

```bash
python -m membrain eval
python -m unittest discover -s tests -q
```

- `eval` 期望：`cases=8  recall@1=100.0%  recall@3=100.0%`（低于 100% 说明召回链路被改坏了）。
- `unittest` 期望：`Ran 4 tests ... OK`。

> 依赖为零：只需要 Python 3.9+ 标准库。不需要 `pip install`。
> 如果 `python` 不在 PATH，用绝对路径（Windows `where python`，macOS/Linux `which python3`）。

---

## 第 4 步：冒烟（能跑起来就算过）

```bash
# Windows：只跑流程、不起服务、不开浏览器
一键体验.bat dry

# macOS / Linux：等价命令
python -m membrain init && python -m membrain demo && python -m membrain export --out examples/radial/memories.jsonl
```

MCP（stdio，不需要装 `mcp` 包）自测——喂两行 JSON-RPC，应看到 `membrain-lite` 的 serverInfo：

```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python -m membrain.mcp
```

（Windows PowerShell 用 `$env:PYTHONIOENCODING='utf-8'`；有 BOM 的输入行会被自动 strip。）

---

## 全部跑完的自检回执

四项都 exit 0 时，按这个格式回一句，方便别人一眼看出你验过：

```
[setup-check] links=ok(42 local / 1 external) privacy=clean eval=100/100 unittest=4ok smoke=ok
```

---

## 这个项目踩过的 404 坑（看到类似症状先看这里）

1. **文档里的仓库路径要按仓库根解析，不是按文件所在目录。**
   `docs/AGENT-GUIDE.md` 里写 `membrain/engine.py`，指的是根目录下的 `membrain/engine.py`。
   `check_links.py` 对反引号路径按仓库根解析、对 Markdown 链接先按文件目录再回退根目录——就是这个原因。
2. **`prompts/01–05` 是范围叙述，不是文件名。** 带 `–`、`—`、空格或以 `/` 结尾的反引号内容会被跳过。
3. **`http://127.0.0.1:8766/...` 是一键体验临时起的本地服务**，没开服务时访问会 502。
   本机/内网地址（127.、localhost、192.168.、10.、172.16–31.）一律跳过，不算 404。
4. **指向 GitHub `blob/main/...` 的固定链接**在文件改名/删除后会 404——这类是最常见的漂移源，
   能换成仓库内相对链接就不要用外链。
5. **`python`/`python3` 不一致**导致的「文件不存在」多半不是路径问题，而是命令本身没跑起来；
   先确认解释器存在再排查路径。

---

## 已知问题

（当前无。发现死引用但一时补不上的，写在这里：`- [ ] 目标 → 原因 → 计划`。）
