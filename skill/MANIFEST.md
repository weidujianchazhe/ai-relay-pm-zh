# 技能包清单与权威源声明（MANIFEST）

> **版本**：`4.0.0`
> **设计区载体（v4.0.0 起）**：蓝图 = **`designs/<主题>.blueprint.html`**（人读）· 详述 = **`designs/<主题>.md`** · **设计骨架 = `designs/SKELETON.html` + `SKELETON.md`**（同一骨架两 Reading）· 归档 = **`designs/archives/`**（与任务归档分离）。
> **本版定位**：**语言无关的软件工程管理**（全局版起点）——C / C++ / Python 是同一套工程管理下的不同**适配层**；语言只决定适配，不改变管理模型。
> **状态**：**语义扩展中**（v3.9.1）——v4.0.0 里程碑：**技术抉择层已入正文**（§0.5）· **抉择与证据受审计**；此后只接受真实使用暴露的 **P0/P1 缺陷修复**，以及 `references/version-boundaries.md` §8 列出的 v3.x 触发条件。
> **本文件是版本号的唯一落点。** 目录内其他文件**不各自声明版本**。

---

## 1. 权威源声明

**本技能包的协议权威源是 `references/` 目录整体。** 分层如下：

| 层 | 位置 | 性质 |
|---|---|---|
| **协议正文** | `references/*.md` | **权威源**（唯一例外：`references/README.md` 是**平台展示页**，非协议正文）。改协议改这里（元协议见下行的两个文件） |
| **元协议** | `references/change-control.md` · `references/glossary.md` | 关于"怎么改协议"的规则（变更控制 / 术语表） |
| **入口** | `SKILL.md` | 路由表。**只回答"读哪个文件"，不承载细则** |
| **数值口径** | `config/defaults.yml` | 出厂默认值。**实例真值在实例 MAP 规则段** |
| **模板** | `templates/` | 初始化时实例化/复制的骨架 |
| **脚本** | `scripts/` | 可执行实现（确定性函数） |
| **落地附录** | `adapters/` | 按语言/栈的映射，**不属技能正文** |
| **可选工具** | `tools/` | 按需拉动，不进接手路径 |

### 数值口径（占位符约定）

协议正文**不写死任何数值**，一律用占位符：

```
{{config:<section>.<key>}}       例：{{config:code_quality.func_lines.recommended}}
```

**查值顺序（重要，读错会破坏功能）**：

```
① 实例 MAP.md 规则段        ← 运行时真值在这里（每项目可不同，这是功能契约）
② 缺失才回落 config/defaults.yml  ← 出厂默认值，仅供初始化时填入实例
```

**为什么不是「技能包默认值说了算」**：各项目阈值本就不同（字数上限、行数口径、归档阈值）。
若只读出厂默认，就**破坏了「每项目可配」这个功能**。

**校验**：`scripts/gen_views.py` 会检查正文里每一个 `{{config:...}}` 占位符
是否都能在 `config/defaults.yml` 中找到对应键——**占位符写错会被机器抓到**。

### 子能力与最小集（standalone subsets）

**四个子能力都能脱离本包其余部分单独使用**——下面不是"理论上可以"，是**实测过的可用性**。

| 子能力 | 入口 | 最小文件集 | 单独使用时**不需要** | 脚本可用性（实测） |
|---|---|---|---|---|
| **项目地图（MAP）** | `templates/MAP.template.md` | 一个 `MAP.md` | 工作区 / 索引 / 快照 / 脚本 | `overview.py <目录>` 只有 MAP 也能跑（缺的部分标「无」）· exit 0 |
| **任务卡·单文件**（卡片模式） | `templates/CARD.md` | 一个 `.md` | 索引 / 快照 / 记录 / 脚本 / 门禁——**全都不需要** | **不跑任何脚本**：提交流程＝追加一行交接流水 |
| **任务卡·工作区**（light 起） | `templates/tasks/TASK_CARD.template.md` + `references/workflow.md` §4 | `tasks/` + `reports/` + `INDEX.md` + `archives/` | MAP / STATE / REVIEWS（属 standard 起） | 提交时 `closeout.py` → `check_closeout.py`（门禁）；改索引后 `check_index.py`。**提交流程三项**，第四项「快照」属 standard |
| **设计卡** | `references/design.md` + `templates/designs/` | `designs/<卡名>.md` + `designs/<卡名>.blueprint.html` | 工作区 / 索引 / 快照（可先有设计、后拆卡） | `new-card --design` 与 `design-archive` 在**任意目录**可用 · exit 0 |
| **代码书写规范** | `references/code-quality.md` + `references/code-style.md` | `scripts/code_metrics.py` + `scripts/_common.py` + 两份规范 | 工作区 / MAP / `config/`（阈值有**脚本内兜底**） | 只拷两个脚本进项目即可跑；阈值走兜底（14 个数值，由 gen_views 第 6 节逐键比对） |
| **全套（管理区）** | `SKILL.md` | 上表全部 + `INDEX/STATE/REVIEWS/archives` | — | 全套门禁 |
| **语言适配层（C / C++ / Python）** | `references/language-adapters.md` | 探针契约 + 能力接口（INSPECT / BUILD / TEST / AUDIT / VERIFY）+ 工程模型（语言/构建/测试/工具链/目标） | 非 Python 栈的成熟工具（clang-tidy / cppcheck / cmake / ctest）未装时**只报待核，不猜度量** | `code_metrics.py` 实测 `COLLECTORS={python, c, cpp}`；c/cpp 未接线 -> `tbd` |

**为什么要维护这张表**：**功能的可用性与包的大小是两件事**。使用者常常只需要其中一件——
先给最小集，**不够再升**（升级即扩集，历史不回写）。

**合起来用为什么不用翻译**：四个子能力**共享同一套术语、字段名与取值口径**（实例 MAP 规则段 → config 兜底），
所以它们同属一个包，而不是四套各自为政的散件。**这里的耦合是有意的**（见 `references/change-control.md` §0）：

| 共享的东西 | 谁在读它 | 拆开会怎样 |
|---|---|---|
| MAP 规则段的配置标签 | 全部脚本的取值顺序 | 每个能力各配一套阈值 → 口径漂移 |
| 任务卡 / 设计卡的字段名 | 门禁脚本、恢复流程、交接 | 改名即破坏功能 |
| `DESIGN-ID` 与「拆分出的任务卡」 | 设计归档门禁 | 设计无从回溯到执行 |

**单独使用时的门禁缺口（诚实声明）**：单文件卡没有索引校验；只有 MAP 时没有快照一致性校验；
只拷 `code_metrics.py` 时读不到实例 MAP 的阈值（用脚本兜底值）。
**缺门禁要让人知道，不能让人以为还有**——所以每条都写在此表里。

---

## 2. 文件清单

```
SKILL.md                        入口 + 路由表（平台技能格式）
MANIFEST.md                     本文件：版本与清单声明
LEGACY_ONBOARDING.md            存量项目接入
BLUEPRINT.md                    设计蓝图 · **第 1 页：总览**（页索引在本文件末）
blueprint/                      设计蓝图分页 02~08（接手链路 / 门禁 / 产物 / 设计 / 代码规范 / 强耦合 / 边界）
config/defaults.yml             出厂默认值（非运行时真值；真值在实例 MAP 规则段）
references/                     协议正文（权威源，按功能域分文件；README.md 为平台展示页）
  README.md                       使用指南（这是什么 / 怎么开始）
  cheatsheet.md                   一屏速查卡（接手 / 作业 / 提交 / 绝不 / 命令）
  onboarding.md                   首次接入：形态判定 / 初始化清单 / 脚本就位
  workflow.md                     生命周期：认领 / 作业 / 提交 / 归档 / 查看
  artifacts.md                    产物规范（schema + 冻结区）
  concurrency.md                  并发：单写者 / 原子写 / CAS / 冲突 / 编号（使用者面；含保证等级表）
  concurrency-internals.md        并发实现内部：三级层级 / 共享写原语 / fencing / 两张攻击矩阵（非使用者必读）
  audit.md                        审计：锚源立论 / 四类锚点 / 各检查项 / 自检清单
  recovery.md                     恢复：缺失补全 / 断链 / 快照 / 卡重建
  code-quality.md                 代码质量（判据·可机检）：三档阈值 / 豁免 / 覆盖率 / 依赖方向 / 异常自愈
  code-style.md                   代码风格（约定·靠人读）：命名 / 版面 / 抽象复用 / 重构三回合 / 范例库 / 提交信息
  language-adapters.md            语言适配层：探针契约 / 能力接口 / 工程模型 / Environment Preflight / 工具链原则
  version-boundaries.md           版本与架构边界：v2.3.1 稳定线 ↔ v3.x 演进线 / 不可覆盖清单 / TBD 语义 / 下一版进入条件
  language-quality-adaptation-plan.md  多语言质量适配方案（母文档）：三级矩阵 / L0-L10 晋升 / 七语言 Provider / 统一证据模型 / 阈值策略 / 实施顺序
  multi-language-quality-gate-data-schema.md  多语言质量门禁数据方案（母文档）：六质量域 / Finding Schema / 八语言矩阵 / Severity-Blocking / Evidence-Exception / 四档结论 / 治理基线四项
  quality-baseline-design.md      质量基准设计：外部先验来源 / 七类数据 / 八语言优先级 / 规则 ID 草案 / 证据等级 E0-E6 / 规则分类 ABC / 基准数据集与 TP-FP-FN-TN 统计
  empirical-evidence/rule-capability-comparison.md  实测证据·规则能力对比：B30/A9/T5 三集实测（组合未获证据支持）
  empirical-evidence/t5-validation.md               实测证据·T5 验证：population 修正 / 断言 A1prime-A7 / 纯长度小总体 / C22 经验反例
  empirical-evidence/cross-set-context-confounded.md 实测证据·跨集上下文混淆实体：双记 + 跨任务一致率排除口径
  empirical-evidence/t5-phase1-s5-evidence.md         实测证据·T5 S5 全量 42 条：分布 / carry 结构 / 词表修订史 / C22 反例 / 协议偏差
  empirical-evidence/t5-phase2-s4-evidence.md         实测证据·T5 S4 分层抽样 43 条：human/agent 分层 / 5-5 同向偏移 / 重复与近名实体 / 协议偏差史
  empirical-evidence/structure-vs-scale-evidence.md   实测证据·尺度 vs 结构：规模降为观察（85 条标注依据）+ 结构模式阻断层 + 误报 9→0 收窄过程 + 3.9.2 行为变更点
  empirical-evidence/known-defects-recall.md          已知缺陷集与召回矩阵（机器生成）：8 条已知缺陷 -> 检测器 -> 覆盖/盲区 + 盲区声明 + 语言适配接口
  empirical-evidence/external-precision-audit.md      外部精度抽检记录：KohakuTerrarium 1829 文件；M1 误报 44% 已收窄 / 去重 6% 已修 / M4 未判定故只具观察级可信度
  provider-gates.md               可执行门禁的接入契约与质量规范总表（29 条档案：语言 7 / 资产 11 / 数值 4 / 待接入 7；含数值准入两问答复与六步流程）
  self-gate-debt.md                                   自门禁技术债登记：本包 scripts/ 未过自身度量门禁（已声明 · 未豁免 · 附整改计划）
  design.md                       设计：两件套（详述 + 蓝图）/ 成本纪律 / 定稿门禁 / 设计区与归档
  collaboration.md                协作：模式 / 角色 / 稳定 ID / 任务简报
  change-control.md               变更控制门禁（改协议前必读）
  glossary.md                     术语表（标准术语 ↔ 历史叫法）
  agent-compatibility.md          无自动加载能力的 Agent 的登记办法
scripts/                        可执行脚本（通用门禁；一表全览见 scripts/README.md）
  README.md                       脚本一览与用法（**先读这份**：什么时候跑哪个）
  _common.py                      公共库（取值顺序 / 扫描 / 三态输出 / 统一入口包装；不单独调用）
  check_size_budget.py            入口成本预算检查（SKILL.md 字符数 <= config 的 skill_max_chars；超限 exit=1）
  correctness_rules.py            Correctness 域结构模式规则（循环漏收集 / 裸 except 吞异常 / open 未关闭；阻断+观察）
  known_defects.py                已知缺陷集 + 召回矩阵（缺陷 -> 检测器 -> 结果/盲区；含语言适配接口 CODE_CHECKERS/PENDING_LANGS）
  provider_gate.py                通用 Provider 门禁（调用成熟工具 + 统一 JSONL 契约 + --list/--selftest；不自己实现分析器）
  overview.py                     一屏全貌（视图，非门禁）
  validate_workspace.py           结构与配置校验（含人检标记格式与到期）
  check_closeout.py               提交门禁（6+1 块 / 归档任务卡 / 索引 / 快照）
  check_index.py                  索引完整性
  check_promises.py               文档承诺 ↔ 代码行为对账（门禁是否有可达失败通道 · 筛选型死赋值）
  reconcile.py                    三方一致性 + 时间锚 + 容量口径
  code_metrics.py                 代码度量门禁（阈值 / 豁免真伪 / 依赖方向 / 扫描覆盖；含外部取数探针钩子）
  eng.py                          能力接口层（INSPECT / BUILD / TEST / AUDIT / VERIFY；Adapter Registry 分派，缺工具 -> 待核）
  capability_matrix.py            能力矩阵机检（契约级：命令拿得到吗 / 指向的东西在吗；专治"注册了 != 生效了"）
  gen_views.py                    派生视图生成 + 版本一致 + 占位符校验
  locks.py                        并发原语层（互斥的唯一物理实现：OS 建议锁 + 平台分支；业务只用 exclusive_resource）
  lease.py                        任务租约与 fencing + 写入原语（业务侧；互斥细节见 locks.py）
  lang_gates.py                   多语言门禁留痕与可查（统一退出码 + 一行摘要，不自研度量）
  concurrency_matrix.py           并发不变量矩阵（故障注入；把保证等级分成五档）
  crash_matrix.py                 崩溃注入矩阵（真杀进程：写完 tmp / 持锁中 / 替换后 / 半事务）
  stamp.py                        机器戳与 AI 标识（时间锚 / 身份锚）
  closeout.py                     提交流程的机械步骤（骨架 / 索引镜像写 / 归档 / 卡归档）
  audit_all.py                    全盘核查入口（编排 + 机器戳留痕 + 超期自查）
  setup.py                        首次启动配置向导（本地 git 备份 / 核查周期）
  selftest_gates.py               门禁变异自检（注入故障，断言门禁必须变红）
  new_local.py                    脚手架：生成符合统一接口的项目专属脚本骨架
  local/                          项目自定义脚本（技能包升级不覆盖；契约见 local/README.md）
templates/                      模板：MAP/STATE/INDEX/REVIEWS/任务卡/设计卡+设计蓝图/交接 + CARD.md（单文件卡片）
adapters/                       按语言落地附录（**各语言一份，以目录为准、不写死名单**），不属技能正文
locales/                        展示元数据（displayName / brief，供桌面插件页显示）
examples/                       范例库骨架（索引表 + 入库流程 + project/external 两分区；**本体不随包分发**）
ci/                             CI 接线样板（不属技能正文）
tools/                          可选工具规范（可视化 / 定时 / 报告；只放规范不放实现）
archives/                       归档说明
```

---

## 3. 派生视图（由脚本生成，**不得手改**）

| 派生视图 | 生成者 | 说明 |
|---|---|---|
| 本包 `references/README.md` 的「附：协议核心不变量（生成区）」 | `scripts/gen_views.py` | 从 `SKILL.md` 的核心不变量节机械抽取（标题行 → 逐条编号项） |
| **网页版设计蓝图**（外部托管 <https://zyzep6f7.qwenwork.host/>） | **人工维护**（托管方同步） | 展示面：内容取自 `blueprint/`。**与包内不一致时以包内为准**；链接失效不影响包的任何功能 |
| 实例 MAP 的「协议速记」段 | **人工维护，不是派生视图** | 它是**速查表**（change-control §0「速查表 ↔ 细则」的功能契约）：高频规则必须就地可读。与 `references/` 不一致时以 `references/` 为准 |

> **纪律**：派生视图只在**生成时**产出；改了权威源就重跑 `gen_views.py`，不依赖人工同步。

---

## 4. 版本一致性校验

```
python scripts/gen_views.py <技能包根>          # 生成派生视图
python scripts/gen_views.py <技能包根> --check  # 只校验（CI / 提交前）
```

校验内容：MANIFEST 版本 ↔ 派生视图是否过期。
**各实例副本的版本不在本包校验范围**（本包只扫自己；实例副本由使用方自管）——原句声称会校验，实测未实现，故改为如实声明。

---

## 5. 变更流程（摘要，细则见 references/change-control.md）

```
① 先过 references/change-control.md 的改造门禁（六条，缺一不得动手）
② 改 references/ 下对应正文（不是先改入口）
③ 更新本文件版本号
④ 跑 scripts/gen_views.py 重生成派生视图
⑤ 跑 scripts/validate_workspace.py 自检
```

**⚠ 冲突即提醒**：发现拟议改动与门禁/功能契约冲突时，**必须主动向用户显式提醒**，未经确认不得执行。
