**简体中文**｜本仓库 [`skill/`](skill/) 即完整技能包。

# 任务卡驱动的 AI 接力项目管理（ai-relay-pm-zh）

> **最近更新：2026-10-08**（版本 v4.0.0）
>
> 通用型 AI 协作项目管理：**任务卡驱动接手 · 快照式状态 · 提交门禁 · 分层索引 · 并发控制 · 审计与恢复 · 代码质量门禁**。
> 纯文件 + 纯协议，不依赖任何平台私有接口——换人 / 换窗口之后**接得上**，改动**可追溯**。
>
> **包结构**：[`SKILL.md`](skill/SKILL.md)（只做路由）· [`MANIFEST.md`](skill/MANIFEST.md)（版本与清单唯一落点）· [`references/`](skill/references/)（协议正文 15 份）· [`scripts/`](skill/scripts/)（可执行门禁 20 个）· `templates/` · `config/` · `adapters/` · `ci/` · `blueprint/`。
> 支持多 AI / 跨平台 / 跨时间 / 跨项目接力——跨越平台、AI、时间、项目等阻碍，让接手方以更小读取代价理解工作需求、降低出错率。

**核心哲学：项目可以复杂沉重，AI 接手只读所需——负担不随项目规模增长。**


---

## 语言版本（Language versions）

| 语言 | 技能包 | 说明文档 | 安装 |
|---|---|---|---|
| **简体中文** | [`skill/`](skill/) | 本文件 | 复制 `skill/` 到技能目录 |



---

## 一、特性

| 特性 | 说明 |
|---|---|
| **任务卡驱动接手** | 接手只读对应任务卡（描述/要点/涉及/代码根路径/上次交接），精准到达，不漫读全项目 |
| **覆盖式状态** | 任务卡/STATE 永远覆盖为最新，不追加、不滚雪球；历史归 reports + INDEX |
| **收工四件套** | 交接 → 卡更新/移卡 → INDEX 登记 → STATE 同步，闭环不遗漏（未完成必建卡，完成移卡 `archives\done\`，不删卡） |
| **人读区 + AI 区** | 人读区（3 行摘要，由 AI 区自动生成）+ AI 工作坐标，人扫一眼即知任务定位 |
| **存量项目轻量接入** | 已开工项目"轻量登记 + 渐进整理"，不做深度历史整理（LEGACY_ONBOARDING.md） |
| **元管理分流** | 技能自身事务（复盘/版本/恢复登记）走工作区 `REVIEWS.md`，不污染项目 reports/INDEX |
| **稳定标识** | `TASK-ID` / `EVENT-ID` / `DESIGN-ID` 创建后永不变更；文件名可改，引用只用 ID |
| **设计卡生命周期** | 设计卡状态机（草案 → 评审中 → 已批准 / 已拒绝 / 已废弃）+ 批准门禁：**未批准不得生成执行卡** |
| **三种协作模式** | `light` / `standard` / `coordination`——各自的文件集、角色与检查、升级路径；升级即扩集、历史不回写 |
| **权限矩阵与单写者** | 执行 AI / 审计 AI / 管理者 / 恢复 AI 四角色权限清晰；单写者责任 + 冲突文件 `CONFLICT_*.md` |
| **两处封顶装置** | `INDEX` 主文件行数与 `STATE` 字数上限——接手 AI 阅读成本的**封顶装置，不是可扩容量**；超限历史移入 reports\ 与归档 |
| **平台无关** | 纯文件 + 纯协议，不依赖任何平台私有接口、技能系统或 API |

## 二、使用前提

**本地文件系统 + 命令/文件执行能力**（能落盘管理目录、读写任务卡与交接文件）。

平台按能力维度判定，不枚举平台名称——具备上述能力的平台（Harness 类 / IDE Agent / 桌面工作区 Agent 等）自动兼容。无本地文件能力的场景（网页对话 / 移动端 App / 纯对话 / API 裸调）不适用。

## 三、目录结构

```
skill/                                # 技能本体（复制到你的技能目录即可用）
├── SKILL.md                # 技能入口（定位/触发/流程/初始化清单/管理自检）
├── README.md               # 模板说明（给 AI 运行时读）
├── BLUEPRINT.md            # 设计蓝图指针
├── MAP.template.md         # 项目地图骨架（→ 实例化为 MAP.md）
├── STATE.template.md       # 当前位置快照骨架（→ 实例化为 STATE.md）
├── INDEX.template.md       # 记录索引骨架（→ 实例化为 INDEX.md）
├── LEGACY_ONBOARDING.md    # 存量项目接入指南（附带文件）
├── REVIEWS.template.md     # 技能复盘（元管理回路：阻碍/建议/处置）
├── designs\DESIGN_CARD.template.md  # 设计卡骨架（DESIGN-ID + 状态机 + 生命周期门禁）
├── tasks\TASK_CARD.template.md   # 任务卡骨架
├── reports\HANDOVER.template.md  # 最小交接模板
├── archives\README.md     # 归档说明（只进不出）
└── tools\                 # 可选工具区（checks/visualize/schedule/report/custom；checks 含协议验证器 validate_protocol.py）
```

使用流程：复制 `skill/` 到技能目录 → 新项目开工读 `SKILL.md` 初始化；存量项目读 `LEGACY_ONBOARDING.md` 接入。

## 四、安装方式

| 环境 | 方式 |
|---|---|
| **豆包** | 复制 `skill/` 到技能目录（如 `.user_skills\`） |
| **Claude Code 等支持 SKILL.md 的环境** | 复制 `skill/` 到技能目录 |
| **纯文档使用** | 直接读 `skill/SKILL.md` 按协议执行（任何 LLM 均可） |

## 五、快速上手

1. **新项目**：读 `SKILL.md` → 确认工作区根 `{WORKSPACE_ROOT}`（一次）→ 自动创建管理目录 → 填 `MAP.md` 占位符 → 在 `tasks\` 建首条任务卡 → 开始按任务卡运行
2. **存量项目**（已开工、无管理结构）：读 `LEGACY_ONBOARDING.md` → 创建管理目录 + 轻量登记当前信息 → 渐进整理历史

核心循环（运行期）：**读任务卡 → 干活 → 收工四件套（交接 → 卡更新/移卡 → INDEX → STATE）**

## 六、设计蓝图

完整设计蓝图见 `项目管理轻量化工作分配蓝图.html`（含设计定稿、读取模型、验收清单）；英文版见 `project-management-lite-blueprint.html`。两份蓝图均随本版更新到 v1.2.1：已收录稳定标识、设计生命周期、三种协作模式、权限矩阵与单写者、两处封顶装置。

## 七、许可

MIT License（见 LICENSE）。

## 制作者

- 作者：如天之星
