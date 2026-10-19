# 学习路径 · 从零到能作业（原「设计蓝图 · 总览」）

> **本文件是【学习路径】，只回答一件事：我该怎么一步步学会用它。** 读一次即可，之后不必再读。
> **细则以 `references/` 为准**（本文件是与它不一致时的**从属面**，不承载协议）。
> **页索引在文件末**（`blueprint/02~08` 是进阶阅读，按需翻）。
> **网页版**：<https://zyzep6f7.qwenwork.host/> —— 托管方人工同步，**不一致时以本目录为准**。

---

## 第 0 步 · 这是什么（30 秒）

**一套让 AI 接手项目时「读得少、接得上、赖不掉」的协作协议。**
不绑定平台、不绑定语言、不依赖任何服务：正文是 Markdown，门禁是 Python 标准库脚本。

> **核心命题**：项目可以复杂沉重，**上手成本不随之增长**。

## 第 1 步 · 我需要它吗（三个问题）

| 你的情况 | 需要吗 |
|---|---|
| 一个人、一次做完、不打算再回来 | ❌ **不需要** |
| 换人 / 换 AI / 隔几周回来，要重新讲一遍背景 | ✅ **需要**（指针链解决它）|
| 「我改好了」但没人能验证，或改坏了说不清 | ✅ **需要**（锚源 + 门禁解决它）|

## 第 2 步 · 最小上手（4 条命令）

```
① 建项目目录 + 建管理区（默认同级、名 = <项目名>-管理区）
   → 展开技能包后，跑：python scripts/validate_workspace.py <管理区>
② 判形态：读 references/onboarding.md §1（命中即停，从严到宽）
③ 建第一张任务卡：python scripts/closeout.py <管理区> new-card --project <项目> --module <模块> --skip-design
④ 提交前跑门禁：python scripts/check_closeout.py <管理区>
```

> ★ **只做到这里就能开工。** 其余能力（设计卡 / 多语言 / 并发 / 审计）**按需再学**。

## 第 3 步 · 跑通一轮（建卡 → 作业 → 提交 → 归档）

```
建卡（上一步③）→ 作业 → 写交接记录：python scripts/closeout.py <管理区> new-record "<主题>" --ai <标识>
→ 填 6+1 块 → 跑 check_closeout 通过 → 建卡归档：python scripts/closeout.py <管理区> card-archive "<卡名>"
```

> ★ **三态输出**：`[通过]` / `[问题]` / `[待核]`，退出码 0/1/2/3 —— **门禁由退出码说话，不由读文档判断**。

## 第 4 步 · 按需深入（选一个，不贪多）

| 你想解决 | 读 |
|---|---|
| 接手时该读什么、怎么写记录 | `references/config` 之外：`references/workflow.md` · `references/artifacts.md` |
| 写代码的规矩 | `references/cheatsheet.md`（一屏）→ `references/code-quality.md`（判据）|
| 设计先想清楚 | `references/design.md`（★ 含「先跳过」：研究后再补设计）|
| 多人 / 多 AI 同时写 | `references/concurrency.md` |
| 出事了要恢复 | `references/recovery.md` |
| 想懂它为什么这样设计 | `blueprint/02~08`（进阶阅读，非必读）|

> ★ **学习到此结束。** 日常只需 `SKILL.md` 的路由表 + 五条不变量。
