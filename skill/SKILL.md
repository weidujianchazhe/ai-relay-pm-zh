---
name: ai-relay-pm-zh
description: "**语言无关的软件工程管理**（C / C++ / Python 共用同一套工程模型与门禁，语言只是适配层）：新建 / 接管项目按固定流程选路径、建管理区并展开技能，降低初次使用者的学习成本；通用型 AI 协作项目管理：任务卡驱动接手、快照式状态、提交流程、分层索引、并发控制、审计与恢复、代码质量门禁。TRIGGER when: 新项目开工前初始化管理区 / 长期未动的项目需要接手 / 存量项目（已开工无管理结构）需要接入 / 多 AI 或多会话协作同一项目 / 需要为项目建立交接与审计机制 / 定义或检查项目的代码书写规范 / 或用户显式点名本技能（如 use ai-relay-pm-zh）。DO NOT TRIGGER when: 单轮问答与代码片段生成 / 与项目管理无关的纯技术问题 / 已有完整项目管理体系且本次只做业务开发。"
compatibility: "需要本地文件系统与命令执行能力。纯对话、网页版、移动端、API 裸调等无本地文件能力的环境不适用。脚本仅依赖 Python 3 标准库。"
---

# AI 协作项目管理（技能入口）

> **定位**：通用型项目管理技能，不为特定项目服务。
> **核心命题**：项目可以复杂沉重，**AI 接手只读所需**——上手成本（onboarding cost）不随项目规模增长。
## 启动先看四件事

**准入门槛（只此一条）**：**不先知道就会返工、或会破坏契约。**
不满足这条的，一律按需拉取——**把它们列进来只会让这一屏变成没人读的第二份目录**。

```
① **什么形态** —— 卡片 / 轻量工作区 / 完整工作区？
     判据见 `references/onboarding.md` §1（命中即停，从严到宽）。**形态定错是唯一需要重建的决定。**
② **项目地图在哪** —— `MAP.md`：环境 / 规则 / 协议速记 / 路径注册表。
     **可单独使用**：只存在一个 MAP 也能回答「项目在哪、代码在哪、按什么规则运转」。
③ **写代码的规矩** —— 一屏速查卡 `references/cheatsheet.md`；细则两本：**判据**（有阈值、可机检）`references/code-quality.md`，**风格与工作方式**（靠人读）`references/code-style.md`。 **非 Python 项目先读该规范 §0.2 适用范围。** **鼓励用算法（上限侧）见该规范 §0.4。**
     **不先知道，写出来的代码会被门禁拦下——那是返工，不是审查。**
③.5 **多语言工程（C / C++ / Python）** —— `references/language-adapters.md`：语言适配层、取数探针契约、能力接口（INSPECT / BUILD / TEST / AUDIT / VERIFY）与工程模型；**核心流程不含语言分支**。
③.6 **版本与架构边界** —— `references/version-boundaries.md`：v2.3.1（稳定线）↔ v3.x（演进线）的关系、**不能反向覆盖的清单**、**`TBD` 的正式含义**、下一版本的进入条件（**v3.x 迭代前必读**）。
③.7 **多语言质量适配（方案）** —— `references/language-quality-adaptation-plan.md`：**识别级 / 测量级 / 适配级**三级口径、**L0–L10 晋升门槛**、七语言 Provider 与特有风险、统一证据模型。**未适配的语言一律 TBD，不得因持有文档或能跑工具而晋升。**
③.8 **多语言质量门禁数据方案** —— `references/multi-language-quality-gate-data-schema.md`：**六质量域**（正确性/安全/可维护性/结构/测试/证据）、**统一 Finding Schema**、八语言矩阵、Severity 分级、**Evidence/Exception**（**`GRAY` 绝不得自动变 `GREEN`**）。
③.9 **质量基准怎么定（外部先验 + 项目校准）** —— `references/quality-baseline-design.md`：外部先验只决定**「什么值得测」**，真实样本才决定**「阈值在哪里」**；**证据等级 E0–E6**（**E0/E1 不得阻断**）· 规则分类 A/B/C · 基准数据集与 **TP/FP/FN/TN → FPR/DR** 统计。
③.10 **实测证据（不改语义）** —— `references/empirical-evidence/`（证据层：规则能力对比 · T5 三阶段标注 · 尺度 vs 结构 · 已知缺陷集召回矩阵）· `references/self-gate-debt.md`（本包技术债登记）。· `provider-gates.md`（**可执行门禁的接入契约与质量规范总表**：29 条档案）。**逐文件清单见 MANIFEST §2；入口只保留目录指针 —— 证据文件不再逐个枚举，避免入口成本随证据增长。**
④ **门禁怎么跑** —— 固定命令见 `references/cheatsheet.md` 末尾。
     门禁由「跑脚本看退出码」给出，不由「读文档判断」给出。
```

> 首次对话若判定为**卡片模式**：只需 `templates/CARD.md` 一个文件，本技能的其余部分**不必读**。

> **根目录入口优先级（两个视角，不要读串）**：
> - **使用者视角**——用本技能管项目：`references/README.md`（这是什么 / 怎么开始）→ 本文件（路由）。
> - **维护者视角**——改本技能本身：`MANIFEST.md`（清单与版本）→ `references/change-control.md`（改造门禁，六条缺一不得动手）。
> 两个视角的交集只有一处：**协议正文都在 `references/`**，入口文件从不承载细则。
> *（唯一例外：`references/README.md` 是**平台展示页**——技能规范不允许根目录放 README，故置于此，不属协议正文。）*

---

## 核心不变量（invariants — 改任何东西都不得破坏）

> 完整清单与理由见 `references/change-control.md` 的「不变量」节。
> 此处只列**接手者必须知道**的五条。

1. **记录指针链**：任务卡「上次交接」→ 记录「下一步」→ 索引 [接力] 行——上手成本恒定的承重墙。
2. **分层索引**：索引**热区**只保留最近若干行，**冷区**（归档文件）保有全量；行**移入不删除**。
3. **每篇记录最多被读一次**：读过即把增量**写回**任务卡（write-back）。
4. **档案只进不出**：`reports/` 与 `archives/` 下文件禁删禁移（唯一例外＝归档流程，且移后必须同步索引行指向）。
5. **数据诚实边界**：恢复不出的内容标「数据待补」，**禁止伪造**。

---

## 接手只做三件事

```
① 读任务卡        tasks/<卡>.md            —— 定位工作，不漫读全项目
② 沿指针读记录    卡上「上次交接」→ reports/<一篇>
③ 需要全局判断时   STATE.md（当前快照） / MAP.md（环境与结构）
```

**除此之外的一切文件都是按需拉取**，不进接手路径。读完这三步仍不够，再查本文件末尾的「用途路由」。

> **口径修正：「一份卡 + 一篇记录」说的是"读哪些"，不是"读多少"。**
> 成本要用**字符**量，不能用文件数量——实测某真实项目：卡中位 5,445 字符、记录中位 3,505 字符，
> 即"两份文件"≈ 8,900 字符，而**单张卡最大 22,002 字符**。**文件数恒定 ≠ 成本恒定。**
> 量尺由 `scripts/overview.py` 给（「接手包」一行）：卡 + 指针记录字符数 vs `{{config:capacity.onboarding_max_chars}}`，
> 单卡上限 `{{config:capacity.card_max_chars}}`。**读进来的东西会留在上下文里**——
> 成本不是"读了几份"，是"带了多少字符走完整场对话"。

---

## 使用前提与边界

> 本节完整论证已下沉至 `references/README.md`「入口下沉：使用前提与边界」。

## 可独立使用的四个子能力

**这张表回答"我只要其中一件，行不行"。** 答案：行——每个都能单独用；最小集见 `MANIFEST.md` 的「子能力与最小集」。

| 子能力 | 一句话 | 单独使用时的入口 |
|---|---|---|
| **项目地图 MAP** | 项目在哪 / 代码在哪 / 按什么规则运转 | 一个 `MAP.md`（`templates/MAP.template.md`） |
| **任务卡** | 一件事一张卡，换人或换窗口时只读卡就能接上 | 单文件卡 `templates/CARD.md`；要索引与门禁时用 `templates/tasks/TASK_CARD.template.md` |
| **设计卡** | 先定方案：一屏**蓝图**给人看方向，**详述**留理由；未定稿不生成任务卡 | `references/design.md`（详述 + 蓝图两件套） |

> **启用设计卡门禁时**：未定稿不生成任务卡；该门禁默认关（见 `config/defaults.yml` 的 `design_cards_enabled`）。
| **代码书写规范** | 判据（可机检）+ 风格（靠人读），两本 | `references/code-quality.md` · `references/code-style.md` · `scripts/code_metrics.py` |

> **不够再升**：从单件起步、按需扩集成完整工作区，**历史不回写**。
> **合起来用不用翻译**：四者共享同一套术语、字段名与取值口径——这是**有意的耦合**，拆开就破坏功能。

---

## Skill directory

按需加载，**不要一次全读**。

**按用途找**（文件名不一定记得住，用途记得住）：

| 你需要 | 读 |
|---|---|
| 判形态 / 首次接入 | `references/onboarding.md` · `references/cheatsheet.md` |
| 认领 / 作业 / 提交 / 归档 | `references/workflow.md` |
| 卡 / 记录 / 索引 / 快照的字段与结构 | `references/artifacts.md`（冻结区在此） |
| 谁持有卡 / 并发写规矩 | `references/concurrency.md`（实现内部见 `concurrency-internals.md`） |
| **出事了要恢复** | `references/recovery.md` |
| **审计与锚点** | `references/audit.md` |
| 写代码的判据 / 风格 | `references/code-quality.md` · `references/code-style.md` |
| 设计两件套 | `references/design.md` |
| 多 AI 分工 / 角色 | `references/collaboration.md` |
| **改本技能本身** | `references/change-control.md`（改造门禁，缺一不得动手） |
| 术语 / 历史叫法 | `references/glossary.md` |
| 无自动加载能力的 Agent | `references/agent-compatibility.md` |
| 存量项目接入 | `LEGACY_ONBOARDING.md` |
| 骨架与出厂值 | `templates/` · `config/defaults.yml` |
| 按语言落地 | `adapters/`（**不属正文**） |
| 全量文件清单与版本 | `MANIFEST.md` |
| 设计蓝图（展示用） | `BLUEPRINT.md` + `blueprint/` |

---

## 脚本（随包分发，不必手写）

> **跑哪些由形态决定**：卡片模式一个都不跑；light 提交时两个（机械步骤 + 门禁）；standard 再加核查三件套。
> 矩阵见 `references/onboarding.md` §4.0——**先看形态，再看下表**。

| 脚本 | 用途 | 何时跑 |
|---|---|---|
| `scripts/overview.py` | **一屏全貌**（地图 / 快照 / 索引热区 / 活跃卡 / 决策点）——**视图，不是门禁**，恒返回 0 | 接手前 10 秒 / 定期扫视 |
| `scripts/validate_workspace.py` | 工作区结构与配置校验（含人检标记格式与到期） | 初始化后 / 改结构后 |
| `scripts/check_closeout.py` | 提交流程门禁（6+1 块 / 归档任务卡存在 / 索引已登记 / 快照已更新） | **每次提交前** |
| `scripts/closeout.py` | **机械步骤总入口**（建卡 `new-card` / 记录骨架 / 索引镜像写 / 滚动归档 / 卡归档 / 留痕滚动 `reviews-archive`）——**不要手改共享文件** | 每次提交时 / 用户说「新建任务」时 |
| `scripts/audit_all.py` | **全盘核查**（编排全部门禁 + 机器戳留痕 + 超期自查）——**开了却没跑会自己变红** | 定期 / 接手前 |
| `scripts/setup.py` | 首次启动配置向导（本地 git 备份 / 核查周期） | 首次建工作区 |
| `scripts/check_index.py` | 索引完整性（编号递增 / 类型合法 / 指针不悬空 / 冷热一致） | 改索引后 / 定期 |
| `scripts/reconcile.py` | 三方一致性（快照 ↔ 记录 ↔ 索引）+ 时间锚 + 容量口径 | 定期 / 怀疑账实不符 |
| `scripts/code_metrics.py` | 代码度量门禁（三档阈值 + 豁免理由真伪） | 每次改代码后 |
| `scripts/gen_views.py` | 派生视图生成 + 版本一致性 + 配置占位符校验 | 改协议后 |
| `scripts/locks.py` | **并发原语层**——互斥的唯一物理实现（OS 建议锁 + 平台分支）；业务侧只用 `exclusive_resource()` | 由其它脚本调用 |
| `scripts/lease.py` | **任务租约与 fencing + 写入原语**——被 `closeout.py` 与 `check_closeout.py` 复用 | 由其它脚本调用 |
| `scripts/lang_gates.py` | **多语言门禁留痕与可查**——`record` 记各栈退出码，`check` 核痕迹新鲜度（开关开了没跑＝假账） | CI 汇总步骤 / 定期核查 |
| `scripts/concurrency_matrix.py` | **并发不变量矩阵**——故障注入验证「能保证哪些不变量」，分五档等级 | 并发相关改动后 / 定期 |
| `scripts/crash_matrix.py` | **崩溃注入矩阵**——真杀进程，验证半事务与残留是否收敛 | 改动写路径后 / 定期 |
| `scripts/stamp.py` | 机器戳与 AI 标识生成 / 校验 | 认领任务卡 / 写人检标记时 |
| `scripts/new_local.py` | 项目专属脚本脚手架 | 通用门禁覆盖不到时 |
| `scripts/selftest_gates.py` | **门禁变异自检**（注入故障，断言门禁必须变红） | 改门禁后 / CI 第一步 |

用法：`python scripts/<脚本名>.py <管理区>` —— 三态输出 `[通过] / [问题] / [待核]`（另有 `[建议]`，只提示不计数），退出码 0/1/2/3（1 = 有[问题]，2 = 仅[待核]，3 = 脚本自身错误）。

---

