# Agent Install & Maintenance Guide

> This document is written for **another AI** (DSH / Claude / Codex / Cursor) — not for humans.
> If you are that agent: follow it step by step, don't improvise. When you're done,
> **read section 7 out loud to your owner**.
> If you are a human reading this: use the [README](../README.md) instead.
>
> 中文版：[AGENT-GUIDE.md](AGENT-GUIDE.md)

---

## 0. What this is

`membrain-lite` is a **minimal memory kernel**: it remembers, it recalls, it forgets.

- One SQLite file plus plain Python functions — zero third-party dependencies.
  **Mind the Python version:** 3.9+ runs fine, but reading `config.toml` relies on `tomllib`
  (3.11+). On 3.10 or older the config file is **silently ignored** and defaults are used —
  no error, no warning. Install 3.11+ to avoid the confusion.
- Three things it does: **selective writes** (only keep what will be useful later), **layered recall**
  (keyword / semantic / importance / recency / graph, weighted), **forgetting curves**
  (three tiers: habit / fading / edge).
- It is **not** a vector-database wrapper, **not** a RAG template, **not** a chat-log archiver.

What it **cannot** do (do not promise these to your owner):

- ❌ It is not a native DSH plugin (the kernel is Python; DSH plugins are cordis/Node).
  It mounts as an **MCP server** only.
- ❌ It never remembers anything by itself — **you** must call `remember`.
- ❌ It never injects context by itself — **you** must call `brief` / `recall`.
- ❌ It does not handle images, audio, or files. One line of text at a time.

---

## 1. Install (about 3 minutes, all executable)

### 1.1 Get the code

```bash
git clone https://github.com/DoctorDing123/DSH-membrain-lite.git
cd DSH-membrain-lite
```

No git? Download the ZIP and unzip it. **Do not `pip install`** — just `cd` into the folder.

### 1.1.5 Self-check before you touch anything (do not skip)

Before changing a single file, run the command checklist: **[`docs/SETUP-CHECK.md`](SETUP-CHECK.md)**.

The one-line version is

```bash
python scripts/check_links.py
```

It reports every **dead link / missing file / missing skeleton file** in the docs
(`file:line → target → reason`). **Fix or replace whatever 404s, get exit 0, then continue.**
The repair order (repoint → substitute → downgrade to plain text → record under "Known issues")
lives in SETUP-CHECK; follow it, and never make the check pass by deleting links.

### 1.2 Smoke-test it first

```bash
python -m membrain init          # create the DB, prints brain.sqlite path
python -m membrain demo          # write 29 fictional sample memories
python -m membrain recall "阿宁讨厌什么" --explain
python -m membrain counts
```

Expected: the first `recall` hit is «阿宁讨厌被叫「机器人」» with a `why` breakdown
(keyword / semantic / graph). `counts` looks like `{"edge":7,"fading":14,"habit":8,"total":29}`.

> If this step fails, **stop**. Do not mount MCP yet. See section 6 first.

### 1.3 Mount into DSH (MCP)

Edit the DSH patch config:

- Windows: `%USERPROFILE%\.dsh\profiles\web\cordis.patch.yml`
- macOS / Linux: `~/.dsh/profiles/web/cordis.patch.yml`

Append at the **end of the file** (spaces, never tabs):

```yaml
- insert:
    - id: mcp-membrain-lite
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: membrain          # must match ^[A-Za-z0-9_-]{1,32}$ and must not collide
        transport: stdio
        command: '/abs/path/to/python'   # Windows: C:\...\python.exe
        args: ['-m', 'membrain.mcp']
        cwd: '/abs/path/to/DSH-membrain-lite'
        env:
          PYTHONIOENCODING: utf-8
          PYTHONUTF8: '1'
          MEMBRAIN_HOME: '/abs/path/to/your-memory-dir'   # see section 2
        toolCallTimeoutMs: 60000
```

Notes:

- **Back up that yml before editing it**, then re-validate:
  `python -c "import yaml;print(len(yaml.safe_load(open(r'<path>',encoding='utf-8'))))"`.
- Do **not** name the server `memory` — many setups already have another memory service.
  `membrain` is the safe choice.
- `MEMBRAIN_HOME` is the **data** directory and can live outside the code folder.
  If omitted it defaults to `./.membrain` relative to `cwd` — easy to lose.
- **Restart DSH** afterwards (reloading the page is not enough).
- Claude Desktop uses `claude_desktop_config.json` → `mcpServers` with identical arguments;
  see the README section "装进 DSH / Claude Desktop（MCP）".

### 1.4 Verify it actually works

After restart you should have five tools: `remember` / `recall` / `brief` / `tick` / `stats`
(prefixed `mcp__membrain__` inside DSH).

Do three things immediately:

1. `stats()` — is the total count right?
2. `recall("阿宁讨厌什么")` — does it include the `why` breakdown?
3. `remember("test entry: ignore me")` — does it say `记下了（#N）` or "already similar"?

Then **delete the test entry** (or point `MEMBRAIN_HOME` at a scratch directory for the check).

---

## 2. Where files should live

### 2.1 Keep three directories separate

```
<code>       DSH-membrain-lite/        cloned; safe to `git pull`
<data>       ~/membrain-data/          MEMBRAIN_HOME points here — brain.sqlite
<backup>     ~/membrain-backup/        periodic copies of brain.sqlite
```

**Never put the data directory inside the code directory**: `git pull` will fight you and
you will eventually commit something you shouldn't.

Files created at runtime:

| File | What it is | Back up? |
|---|---|---|
| `brain.sqlite` | every memory (memories + vectors + entities) | ✅ the only must-have |
| `mirror/` | human-readable md / jsonl from `mirror` | optional (rebuildable) |
| `*.log` | logs | ❌ |

### 2.2 Git discipline

If you fork and modify, `.gitignore` must contain:

```gitignore
.membrain/
*.sqlite
*.sqlite-journal
memories.jsonl
mirror/
config.toml        # copy from config.example.toml; never commit the real one
```

Run the privacy check (5.5) before every commit.

### 2.3 Backups

Once a day is enough. **Do not copy the file** — a plain copy taken mid-write can be a torn
database. Use the bundled script: it goes through SQLite's `backup()` API for a consistent
snapshot (safe while writing) and **verifies the row count** afterwards.

```bash
python scripts/backup.py              # → <data dir>/backups/brain-YYYYMMDD-HHMMSS.sqlite, keeps the last 14
python scripts/backup.py --keep 30    # keep 30
python scripts/backup.py --to D:\bak  # somewhere else (another disk / a synced folder)
python scripts/backup.py --list       # just list what exists
```

Schedule it: on Windows use Task Scheduler (daily 03:00, action `python <repo>\scripts\backup.py`);
on Linux/macOS add `0 3 * * * cd ~/membrain-lite && python scripts/backup.py` to `crontab -e`.

Real-world size: three years of daily chat stays under a few hundred MB; backing that up takes a
second.

### 2.4 Migrating from an older store

If you are not starting from scratch but already have your own memory database (one `memories`
table, possibly with `chat` inside a `meta` JSON blob), use the importer — **do not hand-roll a loop**:

```bash
# 1) See what would be imported and what would be skipped (writes nothing)
python scripts/import_from_old_store.py --from ~/old/brain.db --dry --scan-secrets

# 2) Once the distribution and samples look right, run it for real
python scripts/import_from_old_store.py --from ~/old/brain.db
```

The defaults are:

| Old data | Destination |
|---|---|
| `chat` is `group:*` | imported with that value as `scope` |
| `chat` is `private:*` | **skipped by default** (cross-conversation leakage is the worst failure); opt in with `--private-allow private:100000002` |
| no `chat`, `source` looks like `agent` | goes to `scope=self` (the bot's own working habits) |
| `status='archived'` / empty text | skipped |
| legacy `kind` values | `procedural→skill`, `change→reflection`, `preference/topic/relation→fact` |

Two details, both learned the hard way:

1. **Old stores rarely record how often a memory was recalled**, so everything lands in the
   `fading` tier — things you mention daily look like first-time hearsay. The importer backfills
   `hits = round(importance × 6)` by default (0.86 → 5, enough for the habit tier); pass
   `--no-backfill` to skip.
2. **Do not strip phone/QQ numbers by hand.** Those IDs are exactly how the bot tells people apart.
   Keep them locally, and when you eventually want to publish the database, run
   `python scripts/check_privacy.py` first to list them.


---

## 3. Daily use (the most important section)

### 3.1 Write gate: ask three questions

Before `remember`, ask:

1. **Will this be useful later?** If not, skip it (pleasantries, restatements, other people's jokes).
2. **Can it fit in one sentence?** Over ~60 characters, split it into 2–3 entries.
   Memory is for retrieval, not for reading aloud.
3. **Who / about what / why?** Fill at least two of `who` / `topic` / `why`.
   If you cannot answer "why", it probably should not be stored.

| Store ✅ | Skip ❌ |
|---|---|
| Who they are, what they hate, what project they're on | "ok" / "sure" / "you there?" |
| Preferences: name, tone, landmines | Their literal last sentence (unless it's a promise) |
| Agreements: what was decided, when | Your own speculation |
| Lessons: mistakes made, corrections received | One-off trivia that is useless tomorrow |

### 3.2 Choosing `kind` (this sets the half-life)

| kind | Use it for | Half-life |
|---|---|---|
| `fact` | stable facts (name, role, long-term preference) | 365 days |
| `lesson` | lessons and principles ("stop asking twice") | 240 days |
| `skill` | concrete how-to ("back up the yml before editing") | 180 days |
| `reflection` | reflections, mood ("he seemed low that day") | 60 days |
| `episode` | one-off events ("worked until 11pm") | 21 days |

Picking the wrong `kind` is the **most common silent bug**: a stable fact written as
`episode` sinks to the edge tier within months and is never recalled again.

### 3.3 `importance` rule of thumb

| Situation | importance |
|---|---|
| Hard facts, explicit agreements, things they emphasised | 0.8 – 1.0 |
| Informative preferences or plans | 0.6 – 0.75 |
| Ordinary events | 0.4 – 0.55 |
| Unsure | 0.5 (default). Do not default to 0.95 out of fear of forgetting |

> Anti-pattern: writing 0.95 for everything is identical to writing 0.5 for everything —
> the importance channel becomes useless.

### 3.4 `scope` isolation is a hard rule

Every memory carries a `scope`:

- `global` — visible in every conversation ("what is her name")
- `group:100000001` / `private:100000002` — only inside that group / DM

Rules:

1. **Always pass a scope.** If unsure, use the current conversation's scope, not `default`.
2. `recall(scope=x)` returns only `x` plus `global` — the library enforces it, but **you must still
   never quote another conversation's content**.
3. **Group → DM bridging is opt-in and requires an explicit nickname allowlist.** Leave it off.
4. Cross-conversation leakage is the most severe failure mode (far worse than forgetting).
   When in doubt, store less.

### 3.5 When to call what

| Moment | Call |
|---|---|
| They said something future-relevant | `remember(...)` with kind/scope/who/why |
| About to answer and unsure of history | `recall("one-line description", k=5)` |
| Start of a turn, want background | `brief(scope=current, limit=8)` |
| Once a day (or every N turns) | `tick()` — decay and re-tier |
| Want the size | `stats()` |

**Do not `recall` every turn.** Five hits per turn will destroy your context budget.
The real signal is: "does this message refer to the past?"

---

## 4. How the files relate (read before changing code)

| File | Responsibility | Touch it when |
|---|---|---|
| `membrain/engine.py` | orchestration: remember / recall / brief / tick + the five scoring channels | changing ranking, adding a channel |
| `membrain/store.py` | SQLite: memories / vectors / entities, dedup, touch, tier | changing schema or indexes |
| `membrain/embed.py` | keywords and vectors (hash-based by default) | swapping the embedder |
| `membrain/decay.py` | forgetting curves and tier thresholds | tuning half-lives or tiering |
| `membrain/config.py` | every tunable: weights / half-lives / dedup threshold | **tuning starts here, not in code** |
| `membrain/mirror.py` | export to human-readable md / jsonl | changing mirror format |
| `membrain/cli.py` | command line entry point | adding a subcommand |
| `membrain/api.py` | five HTTP endpoints | wiring QQ / WeChat / Telegram |
| `membrain/mcp.py` | MCP stdio server (for DSH / Claude) | adding an MCP tool |
| `prompts/01–05` | persona / wake-up brief / write rules / speaking style / when upset | changing how it talks and remembers |
| `eval/cases.jsonl` | recall regression set | **run it before and after every change** |

**First principle: change numbers in `config.py` before you change code.**

---

## 5. Optimising (do these in order, don't skip)

### 5.1 Step 1 — grow `eval` to 40+ cases (highest return)

`eval/cases.jsonl` currently has 8 cases. That is enough to **catch regressions**, not to
**prove quality**. 80% of recall problems come from "it was never tested".

Collect in this ratio:

- 10× "should obviously remember" (baseline, must stay 100%)
- 10× "same meaning, different wording" (tests semantics)
- 10× "should recall, but not as the top hit" (tests ordering)
- 10× "should NOT recall at all" (tests false positives — the most neglected bucket)

Format: `{"query": "...", "expect": ["substring of a stored memory"], "scope": "..."}`.
Then run `python -m membrain eval` and watch `recall@1` / `recall@3`.

### 5.2 Step 2 — tune weights (only after you have eval)

Defaults in `config.py`: `0.18 semantic / 0.46 keyword / 0.14 importance / 0.11 recency / 0.11 graph`.

| Symptom | Try first |
|---|---|
| Paraphrases miss | semantic ↑ (0.18→0.25), keyword ↓ to compensate |
| Random three-month-old trivia keeps surfacing | recency ↑ (0.11→0.18) |
| Important things buried by irrelevant fresh items | importance ↑ (0.14→0.20) |
| Lots of literal-but-irrelevant hits | keyword ↓, semantic ↑ |

**Change one number at a time, run `eval` immediately, revert if the score drops.**
Record the before/after numbers.

### 5.3 Step 3 — tune forgetting

`decay.kind_half_life` controls how fast each category fades. Typical fixes:

- "Agreements get forgotten too fast" → store them as `fact` (365d), not `episode` (21d).
- "The edge tier sinks too eagerly" → raise `archive_after_days` (default 400).
- "I want frequently-recalled items promoted sooner" → look at `decay.habit_strength`
  and the touch-count threshold.

**Do not shorten half-lives to "save space."** It saves almost nothing and only makes you forgetful.

### 5.4 Step 4 — real embeddings (optional)

The default hash vector is dependency-free and adequate but not clever. For better semantic recall:

```bash
pip install -e ".[embed]"
```

Then `Engine(cfg, embedder=Embedder("BAAI/bge-m3"))`. Note: **switching embedders requires
rebuilding vectors** — old and new vectors are not in the same space. Rebuild by `init`-ing a new
directory and re-`add`ing from an `export` jsonl.

### 5.5 Post-change checklist

- [ ] `python -m membrain eval` did not regress
- [ ] `python -m membrain counts` looks sane (not everything habit, not everything edge)
- [ ] `python scripts/check_privacy.py` prints "干净" (clean)
- [ ] `python -m unittest discover -s tests -q` passes
- [ ] Sample three `recall` results and sanity-check them by eye
- [ ] If committing: `git status` shows no `*.sqlite` / `memories.jsonl` / `config.toml`

---

## 6. Known traps (all of these were actually hit)

| Symptom | Cause | Fix |
|---|---|---|
| `收到坏 JSON：Unexpected UTF-8 BOM ... line 1 column 1` | Windows/PowerShell pipes prepend a BOM | Already handled in `mcp.py` via `lstrip("\ufeff")`; never emit a BOM from your own client |
| MCP won't start, `serverName` rejected | Must match `^[A-Za-z0-9_-]{1,32}$` | Use `membrain`; no dots, no CJK |
| The same sentence stored twice | `dedup_similarity` (0.92) too high or the texts differ too much | A `deduped: true` response means it matched — don't force a second write |
| `sqlite3.Row` has no attribute `get` | Rows don't support dict methods | `dict(row)` first |
| Tools never appear after install | Only the page was reloaded | Actually restart the DSH process |
| Everything is in the edge tier | `importance` always too low, or `kind` always `episode` | See 3.2 / 3.3 |
| Group chatter shows up in DMs | Missing `scope`, or `global` was used | See 3.4; store less |

---

## 7. ⚠️ After installing, tell your owner

**Use your own voice, but cover every point below.** Your owner is not technical — don't read
the config out loud.

### What to say (a script you can adapt)

> The memory library is installed — it can now remember things you've told me. Three things you
> should know:
>
> First, **it doesn't remember on its own.** I have to write things in deliberately, so if you say
> "remember this", that's when it actually sticks. You don't need to change how you talk.
>
> Second, **you can see and delete what it stores.** Memory is just one file (`brain.sqlite`);
> I can export it as a readable document any time, and if something is wrong you can say
> "that entry is wrong, delete it" and I will.
>
> Third, **the data stays on your own machine** — nothing is uploaded. But precisely because of
> that, **back it up**: if that file is lost, it genuinely forgets everything.
>
> Here's what I suggest: use it for a week or two and let me write things down as we go. Once it
> holds 50–100 memories, we look together at what it remembers well and what it doesn't — that's
> when tuning actually means something.

### Five things to remind them (one at a time, don't merge)

1. **No need to change how you talk** — just add "remember this" after anything important.
2. **Privacy boundary**: it can be told to skip certain topics (group chatter never leaks into DMs by default).
3. **Backups**: copy `brain.sqlite` once a day, keep 14 days.
4. **Don't rush to tune**: gather two weeks and 50–100 memories first, otherwise you're guessing.
5. **Current limits**: text only, agent-only, and it does **not** feed QQ/WeChat wake-up briefs
   (that part needs separate wiring).

### Then ask one question

> "Which three things do you want me to remember first?"

Write them in immediately (`kind` per 3.2, `importance` 0.8), then run `recall` on the spot and
show the result. That demonstration is worth more than any explanation.

---

## 8. If you want to go further (confirm with your owner first)

| Direction | Effort | Notes |
|---|---|---|
| Wire up QQ / WeChat / Telegram | Small | Hook the five endpoints in `api.py` |
| Auto-inject a brief every turn | Medium | Add a host hook that calls `brief()` at turn start |
| Auto-extract memories | Medium | After each turn, have the model extract 0–2 items, then run the 3.1 gate |
| Native DSH plugin | Large | Requires rewriting the kernel in TypeScript (`node:sqlite`) so it loads inside DSH, exposes tools via `ctx.tools.register`, and can hook session events |
| Multimodal (image/audio) | Large | Needs extra captioning models and storage — out of scope here |

**Decision rule:** owner asks "why doesn't it remember by itself?" → build auto-extraction.
Owner asks "why does it forget every turn?" → build brief injection.
Owner just wants to use it → build nothing.

---

## 9. One-line summary (for you, the agent)

> Installing takes ten minutes; **using it well takes restraint** — store less, store accurately,
> always pass a scope, and never get `importance` or `kind` wrong.
> Your goal is not "remember everything", it's "recall the right thing when it matters".
