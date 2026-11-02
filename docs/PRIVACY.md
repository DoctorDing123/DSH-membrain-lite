# 隐私说明

这个仓库是**公开模板**，里面不含任何真实用户的数据。

## 示例数据全是编的

`data/seed_demo.jsonl`、`eval/cases.jsonl`、`examples/radial/memories.jsonl` 里的所有
人物、群名、对话、事件都是虚构的：

| 角色 | 名字 | 说明 |
|---|---|---|
| 机器人 | 小满 | 演示用的人格名 |
| 主人 | 阿宁 | 演示用的所有者名 |
| 群友 | 阿吉 | 喜欢晒辣椒 |
| 群友 | 老周 | 爱开玩笑 |
| 群 | 阳台种菜群 | 虚构群名 |

没有 QQ 号、没有手机号、没有真实群名、没有真实聊天记录。

## 你自己用的时候

你的记忆库应该在**仓库之外**（默认在 `./.membrain/`，已被 `.gitignore` 忽略）。
如果要把自己的数据也纳入版本管理，请用**私有仓库**，并且至少注意：

- `.membrain/brain.sqlite` 里有原文，不要提交
- `mirror` 生成的 `人物/*.md`、`日记/*.md` 也含原文
- token、cookie、IM 桥接配置一律不要进仓库

## 提交前自查

```bash
python scripts/check_privacy.py
```

脚本会扫全仓，命中以下任一就把文件名和行号打出来（退出码 1）：

- 本仓库已知的虚构/真实人名混入（在 `scripts/check_privacy.py` 的 `DENY` 里维护）
- 常见凭据形态：`Bearer `、`access_token=`、`cookie:`、`sk-` 开头的 key
- 11 位手机号、5 到 12 位纯数字（QQ 号/群号）

## 版本历史

仓库以**单个提交**发布，历史里没有早期版本的示例数据。
如果你 fork 后想彻底确认，可以：

```bash
git log --all -p | grep -iE "qq|手机|token" || echo "clean"
```
