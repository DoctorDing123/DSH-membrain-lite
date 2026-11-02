# 架构

## 一句话

写完就忘的是日志，会忘但忘不干净的是记忆。

## 数据流

```
用户说话
  → 抽取（谁 / 什么事 / 为什么记）
  → remember()：去重 → 打分重要度 → 写 memories + vectors + entities
  → 空闲 / 每天 tick()：跑衰减，改 tier
  → 被问到时 recall()：五路打分 → top-k → touch（被想起）
  → brief()：把几条最硬的塞进 system prompt
```

## 为什么分数这么配

| 分路 | 权重 | 为什么 |
|---|---|---|
| 关键词 | 0.46 | 中文短查询里字面命中比语义可靠 |
| 语义 | 0.18 | 兜住同义改写，但不该主导 |
| 重要度 | 0.14 | 人工/规则标的「这条重要」要能压过新鲜度 |
| 新鲜度 | 0.11 | 防止三个月前的临时事件压过昨天的事 |
| 图谱 | 0.11 | 「说到阿吉就想起投喂」这类联想 |

调参流程：改 `config.py` → `python -m membrain eval` → 掉分就退回。
`eval/cases.jsonl` 只有 8 条，够用来防回归；真实项目建议扩到 40 条以上。

## 三层遗忘

```
habit   strength 高 且被想起 >= 5 次     —— 习惯、原则、口头禅
fading  正常区间                        —— 大部分记忆
edge    strength <= 0.18                —— 快忘了，还查得到
```

`tier` 只影响展示与排序，不会让记忆消失；
真正消失只发生在 `archive_after_days` 之后（默认 400 天）。

## 会话隔离

每条记忆有 `scope`：

- `global`：任何会话都能看到（比如「她叫什么」）
- `group:100000001`：只在这个群
- `private:100000002`：只在这个私聊

`recall(scope=x)` 返回 `scope == x or scope == 'global'`。
**群 → 私聊的单向桥接**需要显式加昵称白名单，不要默认打开。

## 扩展点

- 换 embedding：`Engine(cfg, embedder=Embedder("bge-m3"))`
- 换存储：`Store` 只要实现 `add/touch/all_active/vectors/entities_of/neighbors/update_strength/archive/counts`
- 换打分：继承 `Engine` 覆盖 `recall()`
- 接微信/QQ/Telegram：把 `api.py` 那五个接口接到你的消息回调即可
