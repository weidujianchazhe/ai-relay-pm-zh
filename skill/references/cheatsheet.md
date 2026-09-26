# 速查卡（一屏）

> **用途**：任务简报随附 / 接手前速览 / 首次启动随附。
> **收录标准**：只放「**不知道就要返工**」的条款。细则一律按指针去查——速查卡不是细则的压缩版。
> **长度纪律**：全文不超过一屏。超了就是收错了东西。

---

**接手三步**
① 读 `tasks/<卡>.md`（认领：写「承接」）→ ② 沿卡「上次交接」读 `reports/<一篇>` → ③ 需要全局判断时读 `STATE.md` / `MAP.md`
**除这三处，其余文件按需拉取。**
**成本单位是字符，不是文件数**：卡 + 指针记录 ≤ `{{config:capacity.onboarding_max_chars}}` 字符（单卡 ≤ `{{config:capacity.card_max_chars}}`）——
跑 `overview.py` 看「接手包」一行。**读进来的东西会留在上下文里。**
**留痕不是读物**：`REVIEWS.md` / `archives\` / `reports\` 冷区 / `INDEX.md` 冷区是**只增的记录**，只在核查、恢复、追责时才查——**不进接手路径**（读取纪律见 `references/artifacts.md` §8）。

**设计两件套**（要先定方案时）：① 蓝图 `designs\<主题>.blueprint.md`——**一屏结构图，给人看**，每轮整篇重写 ② 详述 `designs\<主题>.md`——叙述与理由，**只做定点改**
> **先蓝图、后详述**（方向没定不写长文）；未批准的设计不生成执行卡；拆完或作废后 `closeout.py design-archive` 收进 `designs\archives\`（**不放工作记录归档**）

**作业四条**
① **进度锚点**：每完成一个子步骤就覆盖写卡「进度锚点」一行——中断可续
② **摘要写回**：读过记录就把增量写回卡的「要点 / 已提炼」——**每篇记录最多被读一次**
③ **单写者**：一份数据同时只有一个写者；写前读 revision/hash，写后验；不以时间戳裁决
④ **档案只进不出**：`reports\` 与 `archives\` 禁删禁移（唯一例外＝归档流程，移后同步索引指向）

**提交项数随形态（light 三项 / standard·coordination 四项）（缺一不算提交）**
① 交接记录（6+1 块）→ ② 任务卡更新或归档 → ③ 索引**先冷区后热区** → ④ `STATE.md` 字段级更新

**机械步骤跑脚本，不要手改共享文件**：
`python scripts/closeout.py <根> new-record "<主题>"` ｜ `… index-add --id … --type …`
`… archive-reports` ｜ `… card-archive <卡名>`

**提交前必跑**：`python scripts/check_closeout.py <根>` —— **退出码 1 即不得声称完成。**

**写代码前后**
- **写前**：查项目标杆文件与范例；**判据**（有阈值、可机检）见 `references/code-quality.md`，**风格与工作方式**（靠人读）见 `references/code-style.md`
- **写后**：`python scripts/code_metrics.py <源码根>`

**五条绝不**
① 不伪造：恢复不出的内容标「数据待补」
② 不盲覆盖：`STATE.md` 等共享文件**写前重读**，只改自己那条
③ 不静默：异常不吞、失败路径必须有归宿
④ 不自审：执行者与复核者必须**不同标识**
⑤ 不绕门禁：门禁红了就改代码，不改门禁

---

**派发口令（对 AI 说即可，不必记命令）**：「新建任务：<要做的事>」｜「接着做 <卡名>」｜「这件事先出个设计卡」
> 任务卡**由人开口、AI 落卡**：说一句，AI 跑 `closeout.py new-card` 生成骨架（说明见 `references/onboarding.md` §6）。

**常用命令（复制即用）**

```
python scripts/overview.py           <工作区根>   # 一屏全貌
python scripts/validate_workspace.py <工作区根>   # 结构校验
python scripts/check_closeout.py     <工作区根>   # 提交门禁
python scripts/check_index.py        <工作区根>   # 索引完整性
python scripts/reconcile.py          <工作区根>   # 三方一致性
python scripts/code_metrics.py       <源码根>     # 代码度量
python scripts/closeout.py           <工作区根> new-card "<任务名>"   # 建任务卡骨架（--design 建的是设计卡）
python scripts/stamp.py --ai-id                   # 取 AI 标识（认领时）
python scripts/audit_all.py          <工作区根>   # 全盘核查 + 留痕
python scripts/closeout.py           <工作区根> reviews-archive     # REVIEWS 溢出滚动归档（超限时做一次）
```

**指针**：形态判定与初始化 → `references/onboarding.md` ｜ 产物字段与冻结区 → `references/artifacts.md` ｜ 术语 → `references/glossary.md`
