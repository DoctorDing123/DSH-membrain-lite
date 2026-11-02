# 给 AI agent 的安装与维护指南

> 这份文档是写给**另一个 AI（DSH / Claude / Codex / Cursor）**看的，不是写给人看的。
> 如果你是那个 agent：照着做，别自由发挥；做完之后，**用第 7 节的话转告你的主人**。
> 如果你是人在读：直接看 [README](../README.md) 的「三分钟上手」就行。
>
> English: **[AGENT-GUIDE.en.md](AGENT-GUIDE.en.md)**

---

## 0. 先搞清楚这是什么

`membrain-lite` 是一个**最小记忆内核**：会记、会想、会忘。

- 一个 SQLite 文件 + 一堆纯 Python 函数，零第三方依赖。
  **Python 版本要分清**：3.9+ 能跑；但读 `config.toml` 靠的是 3.11+ 的 `tomllib`，
  低于 3.11 时配置文件会被**静默忽略**（只用默认值，不报错）——所以装 3.11+ 最省事。
- 三件事：**写入有取舍**（只存以后用得上的）、**召回有分层**（关键词/语义/重要度/新鲜度/图谱五路加权）、**遗忘有曲线**（三层：习惯 / 可逐渐遗忘 / 边缘）。
- 它**不是**向量数据库封装，**不是** RAG 模板，**不是**聊天记录归档器。

它**不能**做的事（别向主人承诺）：

- ❌ 不是 DSH 原生插件（内核是 Python，DSH 插件是 cordis/Node），只能以 **MCP server** 形式挂载。
- ❌ 不会自动记住任何东西——**得你主动调 `remember`**。
- ❌ 不会自动注入简报——**得你主动调 `brief` / `recall`**。
- ❌ 不处理图片/语音/文件，只处理一句话文本。

---

## 1. 装（约 3 分钟，全部可执行）

### 1.1 拿到代码

```bash
git clone https://github.com/DoctorDing123/DSH-membrain-lite.git
cd DSH-membrain-lite
```

没装 git 也可以让人下载 ZIP 解压。**不要 `pip install`**，直接 `cd` 进仓库就能跑。

### 1.2 先跑一次，确认能跑

```bash
python -m membrain init          # 建库，打印 brain.sqlite 路径
python -m membrain demo          # 写 29 条虚构示例（小满/阿宁/阿吉/老周）
python -m membrain recall "阿宁讨厌什么" --explain
python -m membrain counts
```

期望：`recall` 的第 1 条是「阿宁讨厌被叫「机器人」」，并打印 `why`（keyword / semantic / graph 分项）。`counts` 形如 `{"edge":7,"fading":14,"habit":8,"total":29}`。

> 如果这一步就失败，**停**。别往下装 MCP。先看第 6 节「已知坑」。

### 1.3 挂进 DSH（MCP）

编辑 DSH 的补丁配置：

- Windows：`%USERPROFILE%\.dsh\profiles\web\cordis.patch.yml`
- macOS / Linux：`~/.dsh/profiles/web/cordis.patch.yml`

在**文件末尾**追加（缩进用空格，别用 tab）：

```yaml
- insert:
    - id: mcp-membrain-lite
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: membrain          # 必须匹配 ^[A-Za-z0-9_-]{1,32}$，且不能和已有的重名
        transport: stdio
        command: '/绝对路径/到/python' # Windows 写 C:\...\python.exe
        args: ['-m', 'membrain.mcp']
        cwd: '/绝对路径/到/DSH-membrain-lite'
        env:
          PYTHONIOENCODING: utf-8
          PYTHONUTF8: '1'
          MEMBRAIN_HOME: '/绝对路径/到/你的记忆目录'   # 数据放哪，见第 2 节
        toolCallTimeoutMs: 60000
```

要点：

- **改之前先备份这个 yml**，改完用 `python -c "import yaml,sys;print(len(yaml.safe_load(open(r'<路径>',encoding='utf-8'))))"` 验证还能解析。
- `serverName` 不能叫 `memory`（很多人已经挂了另一个 memory 服务），叫 `membrain` 最稳。
- `MEMBRAIN_HOME` 是**数据目录**，可以和代码目录分开；不写就默认 `./.membrain`（跟着 cwd 走，容易丢）。
- 改完**重启 DSH**（不是刷新页面）。
- 顺带一提：Claude Desktop 走 `claude_desktop_config.json` 的 `mcpServers`，参数一模一样，见 README「装进 DSH / Claude Desktop（MCP）」。

### 1.4 验证装好了

重启后你应该能看到五个工具：`remember` / `recall` / `brief` / `tick` / `stats`（在 DSH 里前缀是 `mcp__membrain__`）。

立刻做三件事验活：

1. `stats()` → 看总条数对不对；
2. `recall("阿宁讨厌什么")` → 看有没有带 `why` 分项；
3. `remember("测试条目：忽略我")` → 看返回的是 `记下了（#N）` 还是「这条跟已有的很像」。

验完**把测试条目删掉**（或者一开始就 `MEMBRAIN_HOME` 指一个临时目录验）。

---

## 2. 文件该怎么摆

### 2.1 三个目录要分开

```
<代码目录>   DSH-membrain-lite/        克隆下来的，可以随时 git pull
<数据目录>   ~/membrain-data/           MEMBRAIN_HOME 指向这里 —— brain.sqlite
<备份目录>   ~/membrain-backup/         定期把 brain.sqlite 拷一份
```

**不要把数据目录放进代码目录**：`git pull` 会冲突，而且容易手滑提交上去。

`brain.sqlite` 之外，运行后会生成：

| 文件 | 是什么 | 要不要备份 |
|---|---|---|
| `brain.sqlite` | 全部记忆（memories + vectors + entities） | ✅ 唯一必须备份的 |
| `mirror/` | `mirror` 命令导出的可读 md / jsonl | 可选（能重建） |
| `*.log` | 日志 | ❌ |

### 2.2 git 纪律

如果你要把这个仓库 fork 后改，`.gitignore` 必须包含：

```gitignore
.membrain/
*.sqlite
*.sqlite-journal
memories.jsonl
mirror/
config.toml        # 从 config.example.toml 复制，别提交真实配置
```

提交前跑一遍隐私检查（第 5.3 节）。

### 2.3 备份

一天一次就够，**SQLite 直接拷文件**（不要在有写入时拷，先停掉 DSH 或选空闲）：

```
复制 brain.sqlite → 备份目录/brain-YYYYMMDD.sqlite
保留最近 14 份
```

真实规模参照：三年日常聊天大概几百 MB 以内，几百 MB 的 SQLite 拷一下是秒级。

---

## 3. 日常怎么用（最重要的一节）

### 3.1 写入闸门：先问三个问题

想 `remember` 之前，逐条问：

1. **以后用得上吗？** 用不上就不写（寒暄、复述、群里别人的玩笑）。
2. **能一句话说完吗？** 超过 60 字就拆成 2–3 条。记忆是给检索用的，不是给朗读用的。
3. **因为谁 / 在聊什么 / 为什么记？** 三个里至少填两个（`who` / `topic` / `why`）。答不上「为什么」的，多半不该记。

| 该记 ✅ | 别记 ❌ |
|---|---|
| 他是谁、讨厌什么、在做什么项目 | 「哦」「好」「嗯嗯」「在吗」 |
| 偏好：称呼、语气、雷区 | 他刚说的原话（除非本身就是承诺） |
| 约定：说好要做的事、时间 | 你自己刚编的推测 |
| 教训：踩过的坑、被纠正的原因 | 一次性、明天就用不上的琐事 |

### 3.2 `kind` 怎么选（直接决定半衰期）

| kind | 记什么 | 半衰期 |
|---|---|---|
| `fact` | 稳定事实（名字、身份、长期偏好） | 365 天 |
| `lesson` | 教训、原则（「别再追问他」） | 240 天 |
| `skill` | 具体做法（「部署要先备份 yml」） | 180 天 |
| `reflection` | 反思、情绪（「他那天有点低落」） | 60 天 |
| `episode` | 一次性事件（「今天他加班到 11 点」） | 21 天 |

选错 `kind` 是**最常见的隐性错误**：把稳定事实写成 `episode`，三个月后就被压到 edge 层、再也想不起来。

### 3.3 `importance` 经验值

| 情况 | importance |
|---|---|
| 硬事实、明确约定、被点名强调过 | 0.8 – 1.0 |
| 有信息量的偏好/计划 | 0.6 – 0.75 |
| 普通事件 | 0.4 – 0.55 |
| 拿不准 | 0.5（默认）；别为了「怕忘」一律写 0.95 |

> 反面教材：所有记忆都写 0.95，等于所有记忆都写 0.5——重要度这一路就废了。

### 3.4 `scope` 隔离是硬规矩

每条记忆都带 `scope`：

- `global`：任何会话可见（「她叫什么名字」）
- `group:100000001` / `private:100000002`：只在这个群 / 这个私聊

规则：

1. **写的时候一定带 scope**，不确定就按当前会话填，不要偷懒用 `default`。
2. `recall(scope=x)` 只会返回 `x` 或 `global`，这是库层面保证的，但**你仍然不能主动拿别的会话的原文去说**。
3. **群 → 私聊的单向桥接需要显式昵称白名单**，默认不要打开。
4. 跨会话泄漏是最严重的事故（比记不住严重得多）。宁可少记。

### 3.5 什么时候调什么

| 时机 | 调用 |
|---|---|
| 对方说了「以后用得上」的东西 | `remember(...)`（带 kind/scope/who/why） |
| 回答前想确认旧事 | `recall("一句话描述", k=5)` |
| 每轮开始时想带背景 | `brief(scope=当前会话, limit=8)` |
| 一天一次（或每 N 轮） | `tick()` —— 跑衰减、分层 |
| 想看规模 | `stats()` |

**别每轮都 `recall`**：一次 5 条 × 每轮，上下文就废了。判断标准是「这话里有没有指代过去」。

---

## 4. 文件之间是什么关系（改代码前先看这个）

| 文件 | 职责 | 什么时候动它 |
|---|---|---|
| `membrain/engine.py` | 编排：remember / recall / brief / tick 的主流程 + 五路打分 | 改打分逻辑、加新分路 |
| `membrain/store.py` | SQLite：memories / vectors / entities，去重、touch、tier | 改表结构、加索引 |
| `membrain/embed.py` | 关键词与向量（默认零依赖 hash 向量） | 换 embedding |
| `membrain/decay.py` | 遗忘曲线、tier 判定 | 调半衰期、调分层阈值 |
| `membrain/config.py` | 全部可调参数（权重 / 半衰期 / 去重阈值） | 调参优先看这里，别改代码 |
| `membrain/mirror.py` | 导出人可读的 md / jsonl | 改镜像格式 |
| `membrain/cli.py` | 命令行入口 | 加子命令 |
| `membrain/api.py` | HTTP 五个接口 | 接微信/QQ/Telegram |
| `membrain/mcp.py` | MCP stdio server（给 DSH / Claude 用） | 加 MCP 工具 |
| `prompts/01–05` | 人格 / 唤醒简报 / 写入规则 / 说话风格 / 闹脾气 | 改「它怎么说话、怎么记」 |
| `eval/cases.jsonl` | 召回回归集 | **每次调参前后都跑** |

**调参第一原则：先改 `config.py` 里的数值，再考虑改代码。**

---

## 5. 后续怎么优化（按这个顺序做，别跳）

### 5.1 第一步：把 eval 扩到 40 条以上（收益最大）

`eval/cases.jsonl` 现在只有 8 条，**只能防回归，不能证明好坏**。80% 的召回问题来自「压根没测」。

扩的时候按这个比例收集：

- 10 条「明显该想起来」的（基线，必须 100%）
- 10 条「换个说法也要想起来」的（考语义）
- 10 条「想起来但不该是第一条」的（考排序）
- 10 条「压根不该想起来」的（考误召回，这条最容易被忽略）

每条格式：`{"query": "...", "expect": ["记忆里已有的原文片段"], "scope": "..."}`。加完跑 `python -m membrain eval`，看 `recall@1` / `recall@3`。

### 5.2 第二步：调权重（有 eval 之后再动）

`config.py` 默认 `0.18 语义 / 0.46 关键词 / 0.14 重要度 / 0.11 新鲜度 / 0.11 图谱`。

| 症状 | 先试 |
|---|---|
| 换个说法就想不起来 | 语义 ↑（0.18→0.25），关键词 ↓ 同步 |
| 老想起三个月前的临时事 | 新鲜度 ↑（0.11→0.18） |
| 重要的事被无关的新事压住 | 重要度 ↑（0.14→0.20） |
| 想起一堆字面像但不相关的 | 关键词 ↓，语义 ↑ |

**一次只改一个数，改完立刻 `eval`，掉分就退回。** 记下每次改动前后的数字。

### 5.3 第三步：调遗忘曲线

`decay.kind_half_life` 决定每类记忆掉多快。常见调法：

- 「约定」被忘得太快 → 约定写成 `fact`（365 天）而不是 `episode`（21 天）；
- 觉得 edge 层太急着沉底 → 调 `archive_after_days`（默认 400 天）；
- 想让「被反复想起」更早进 habit → 看 `decay.habit_strength` 与 touch 次数阈值。

**不要缩短半衰期来「省空间」**——它省不了多少，只会让你看起来健忘。

### 5.4 第四步：换真 embedding（可选）

默认是零依赖的 hash 向量，够用但不聪明。要提升语义召回：

```bash
pip install -e ".[embed]"
```

然后 `Engine(cfg, embedder=Embedder("BAAI/bge-m3"))`。注意：**换 embedding 必须重建 vectors**（旧向量和新模型不在同一空间），做法是 `init` 到新目录 + 从 `export` 的 jsonl 重新 `add`。

### 5.5 每次改完的自检清单

- [ ] `python -m membrain eval` 不掉分
- [ ] `python -m membrain counts` 三层数量合理（不该全是 habit 或全是 edge）
- [ ] `python scripts/check_privacy.py` 输出「干净」
- [ ] `python -m unittest discover -s tests -q` 通过
- [ ] 抽样 `recall` 三条，人眼判断是否合理
- [ ] 如果提交：`git status` 里没有 `*.sqlite` / `memories.jsonl` / `config.toml`

---

## 6. 已知坑（都是真实踩过的）

| 症状 | 原因 | 处理 |
|---|---|---|
| `收到坏 JSON：Unexpected UTF-8 BOM ... line 1 column 1` | Windows / PowerShell 管道在首行塞了 BOM | 已在 `mcp.py` 里 `lstrip("\ufeff")`；自己写客户端时也别带 BOM |
| MCP 起不来，`serverName` 报错 | 只许 `^[A-Za-z0-9_-]{1,32}$` | 用 `membrain`，别用带点或中文的名字 |
| 同一句话写了两遍 | 去重阈值 `dedup_similarity`（0.92）太高或文本差异太大 | 返回里带 `deduped: true` 说明判重了，别硬写 |
| `sqlite3.Row` 报 `has no attribute 'get'` | Row 不支持字典方法 | `dict(row)` 再取值 |
| 装完工具不出现 | 只刷新了页面，没重启 DSH | 真重启进程 |
| 记忆全在 edge 层 | 写入时 `importance` 一律给低了，或 `kind` 全用 `episode` | 按 3.2 / 3.3 修正 |
| 群里的话出现在私聊 | 没带 `scope`，或用了 `global` | 见 3.4，宁可少记 |

---

## 7. ⚠️ 装完之后，请转告你的主人

**用你自己的语气说，但下面这些点都要说到。** 主人不懂技术，别念配置。

### 给主人的一段话（可以直接照着说）

> 记忆库装好了，它现在能记住你以前说过的话。有三件事想跟你说清楚：
>
> 第一，**它不会自己记**。要我把话记进去，得我主动写；所以你说「这个记住」的时候，我才会真的记下来。你平时怎么说话都不用改。
>
> 第二，**它记的东西你可以看、可以删**。记忆就是一个文件（`brain.sqlite`），我随时能导出成文档给你看；记错的地方你直接说「这条不对，删掉」，我就删。
>
> 第三，**数据只在你自己的电脑上**，不上传任何地方。但正因为在本地，**记得备份**——这个文件丢了，它就真失忆了。
>
> 接下来我建议按这个顺序来：先用一两周，我边用边记；等它记了 50–100 条，我们再一起看一次哪些记得好、哪些记得没用，那时候调参数才有意义。

### 要提醒主人的 5 件事（逐条说，别合并）

1. **不用改说话习惯**，只要在重要的话后面加一句「这个记住」/「别忘」。
2. **隐私边界**：可以让它少记或不记某些话题（群里的话默认不会串到私聊）。
3. **备份**：一天一次拷 `brain.sqlite`，保留 14 天。
4. **别急着调参**：先用两周，攒到 50–100 条再优化，否则就是瞎调。
5. **现在的能力边界**：只记文字、只给 agent 用、不会自动进 QQ/微信的唤醒提示（那部分要另外接）。

### 主动问主人一个问题

> 「你想先让我记住哪三件事？」

拿到答案后**立刻写进去**（`kind` 按 3.2 选，`importance` 给 0.8），当场 `recall` 一遍给他看效果。这一步能让主人立刻感受到它有用，比任何解释都强。

---

## 8. 如果你想做得更深（先跟主人确认，别自己开工）

| 方向 | 工作量 | 说明 |
|---|---|---|
| 接 QQ / 微信 / Telegram | 小 | 把 `api.py` 五个接口接到消息回调 |
| 每轮自动注入简报 | 中 | 在宿主里加钩子，每轮开头调 `brief()` 塞进上下文 |
| 自动抽取记忆 | 中 | 每轮结束让模型从对话里抽 0–2 条，再过 3.1 的闸门 |
| 做成 DSH 原生插件 | 大 | 内核要用 TypeScript 重写（`node:sqlite`），才能随 DSH 加载、用 `ctx.tools.register` 暴露工具、挂 session 钩子 |
| 多模态（图片/语音） | 大 | 需要额外的描述模型 + 存储，超出本仓库范围 |

**判断标准**：主人问「为什么它不自己记」→ 做「自动抽取」；主人问「为什么每轮它都忘」→ 做「自动注入简报」；主人只想用起来 → 什么都别加。

---

## 9. 一句话总结（给 agent 自己看）

> 装好它只要十分钟；**用好它要的是克制**——少记、记准、带 scope、别把重要度和 kind 写错。
> 你的目标不是「记住一切」，是「该想起来的时候想得起来」。
