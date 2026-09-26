# 脚本套件（scripts/）

> **随包分发**——无需每个项目重复实现。
> 本目录是**可执行门禁**：退出码 1 即不得声称完成（`references/code-quality.md` 的机检条款全部落在这里）。

## 目录分工

| 位置 | 归属 | 升级时 |
|---|---|---|
| `scripts/*.py` | **技能包**（通用门禁） | 被覆盖 |
| `scripts/local/` | **项目**（专属判据） | **不覆盖**——也不要往里放通用检查 |
| `../ci/` | **接线样板**（GitHub Actions 等） | 覆盖；不属技能正文 |

项目专属脚本的契约与脚手架见 `scripts/local/README.md` 与 `scripts/new_local.py`。

## 即插即用（无需初始化）

- **原样复制即可**，没有"安装/生成/配置脚本"这一步。
- **不改脚本里的路径**：所有路径来自命令行参数（`<工作区根>` / `<源码根>`）。
- **不改脚本里的阈值**：阈值取自实例 MAP 规则段（缺失才回落 `config/defaults.yml`）——**改配置，不改代码**。
- **仅依赖 Python 3 标准库**：无第三方、无编译、无网络。

> **成本结构的变化**：门禁由**执行脚本**给出，不再由**读文档判断**给出。
> 接手者不需要先读完规范才知道什么算合格——**跑一次，看退出码**。

### 并发与写盘（可安全并行调用）

| 脚本 | 写盘 | 并发调用 |
|---|---|---|
| `overview.py` `validate_workspace.py` `check_closeout.py` `check_index.py` `reconcile.py` `code_metrics.py` | **只读**，不修改任何文件 | **安全**——可多进程、多 AI 同时跑 |
| `gen_views.py`（不带 `--check`） | 写本包 `README.md` | 安全：先写临时文件再 `os.replace` 原子替换；并发时内容相同、后写者胜 |
| `stamp.py` | **默认只读**（打印戳）；`--evidence --append` 会写 `REVIEWS.md`（不可并发） | 安全 |
| `closeout.py`（各子命令） | **写工作区文件**（卡 / 索引 / 归档 / 留痕） | **不可并发**：同一工作区同一时刻只允许一个写者（单写者原则，见 `references/concurrency.md`） |

**推论**：门禁脚本可以放心地跑在**正在进行中的工作区**上——它们不会与写者冲突，也不会留下半成品文件。

## 统一约定

```
输出三态     [通过] PASS · [问题] PROBLEM · [待核] TBD · [建议] NOTE（提示，不计数）
退出码       0 = 全通过 · 1 = 有[问题] · 2 = 仅[待核] · 3 = 脚本自身错误
取值顺序     实例 MAP 规则段 → 缺失才回落 config/defaults.yml
依赖         仅 Python 3 标准库（无第三方）
```

**为什么要有 [建议] 这一档**：设计上永久成立的项（如"本工作区无 git 故不做凭证比对"）如果占用
`[待核]` 通道，会让"退出码 0"永不可达，门禁信号随之失效。**常量待核必须降级为建议。**

## 先看形态：跑哪些脚本由形态决定

| 形态 | 跑什么 |
|---|---|
| 卡片模式（一个文件） | **不跑脚本**——提交＝追加一行交接流水 |
| 轻量工作区 `light` | `closeout.py`（机械步骤）→ `check_closeout.py`（门禁）；改索引后 `check_index.py` |
| 完整工作区 `standard` / `coordination` | 上面全部 ＋ `reconcile.py` · `validate_workspace.py` · `audit_all.py`（定期编排并留痕） |
| 只写代码（只要规范） | `code_metrics.py` |

> **业务写端点契约（唯一入口）**：`python scripts/closeout.py . api` ——列出全部业务写端点的
> **幂等性 / 并发保护 / 失败语义**，**从实现导出**（不手抄，故不会漂移）。

> 完整矩阵与「为什么」见 `references/onboarding.md` §4.0。**多跑不只会浪费，还会制造噪声**
> （例如给只有 MAP 的项目报「缺快照」）。

## 脚本一览

| 脚本 | 用途 | 何时跑 |
|---|---|---|
| `overview.py` | **一屏全貌**——地图 / 快照 / 索引热区 / 活跃卡 / 决策点 / **接手包成本**（卡 + 指针记录字符数 vs 上限）（**视图，恒返回 0**） | 接手前 10 秒 / 定期扫视 |
| `closeout.py` | **机械步骤总入口**——建卡（`new-card`，`--design` 一次建详述 + 蓝图）/ 记录骨架 / 索引镜像写 / 滚动归档 / 卡归档 / 留痕滚动（`reviews-archive`）/ 设计归档（`design-archive`） | 每次提交时、用户说「新建任务」时（替代手改共享文件） |
| `audit_all.py` | **全盘核查入口**——编排全部门禁 + **以机器戳留痕** + 超期自查 | 定期（默认 7 天）/ 接手前 |
| `setup.py` | **首次启动配置向导**——`--plan` 出询问单，`--apply` 执行（本地 git 备份 / 核查周期） | 首次建工作区时一次 |
| `selftest_gates.py` | **门禁变异自检**——注入故障，断言每个门禁必须变红（用例清单见脚本本身，秒级） | **改门禁后必跑** / CI 第一步 |
| `validate_workspace.py` | 工作区结构与配置校验（含**人检标记格式与到期**） | 初始化后 / 改结构后 |
| `check_closeout.py` | 提交流程门禁（6+1 块 / 归档任务卡存在 / 索引已登记 / 快照已更新） | **每次提交前** |
| `check_promises.py` | **文档承诺 ↔ 代码行为对账**——门禁是否真有可达的失败通道 · 「算了不用」的筛选型赋值 | 提交前 / 定期 |
| `check_index.py` | 索引完整性（编号递增 / 类型合法 / 指针不悬空 / 冷热一致） | 改索引后 / 定期 |
| `reconcile.py` | 三方一致性（快照 ↔ 记录 ↔ 索引）+ 时间锚 + 容量口径 | 定期 / 怀疑账实不符 |
| `code_metrics.py` | 代码度量门禁（三档阈值 / 文件长度 / 注释密度 / 豁免理由真伪 / 依赖方向 / 扫描覆盖）；`--exemptions` 导出**回查清单 + 聚集度** | 每次改代码后 / 每季度豁免回查 |
| `gen_views.py` | 派生视图生成 + 版本一致性校验 | 改协议后 |
| `stamp.py` | **机器戳与 AI 标识生成 / 校验**——`--ai-id` 产身份锚；默认产人检 `by=` 戳并报强度档 | 写人检标记时 / 认领任务卡时 / 复核戳时 |
| `locks.py` | **并发原语层**——互斥的唯一物理实现（OS 建议锁 / 平台分支 / 崩溃与暂停语义）；业务侧只该用 `exclusive_resource()` | 由其它脚本调用 |
| `lease.py` | **任务租约与 fencing + 写入原语**——`claim/release/guard/write_cas/shared_append`；复用 `locks.py` 的互斥 | 由其它脚本调用 |
| `lang_gates.py` | **多语言门禁留痕与可查**——`record` 归一各栈退出码写进元数据通道；`check` 核「开关开了却没人跑」的假账与非零真红 | CI 汇总步骤 / 定期核查 |
| `concurrency_matrix.py` | **并发不变量矩阵**——多进程故障注入，验证 I1–I8 并给出五档保证等级 | 并发相关改动后 / 定期 |
| `crash_matrix.py` | **崩溃注入矩阵**——真杀进程（写完 tmp / 持锁中 / 替换后 / 半事务），验证数据不被破坏、残留可清、重跑收敛 | 改动写路径后 / 定期 |
| `new_local.py` | **项目自定义脚本脚手架**——生成符合统一接口的骨架，只留一处 TODO 写判据 | 需要一条本项目专属检查时 |

## 用法

```bash
python scripts/overview.py           <工作区根> [--full]        # 一屏全貌
python scripts/validate_workspace.py <工作区根>
python scripts/check_closeout.py     <工作区根>
python scripts/check_index.py        <工作区根>
python scripts/reconcile.py          <工作区根>
python scripts/code_metrics.py       <源码根> [--ws=<工作区根>] [--lang=python]   # --ws 缺省时按源码根找实例 MAP
python scripts/code_metrics.py       <源码根> --exemptions                      # 豁免与预警区清单 + 聚集度（回查用，恒退出 0）
python scripts/lang_gates.py         <工作区根> record --results "node=0,python=0"  # 多语言门禁留痕（CI 里跑）
python scripts/lang_gates.py         <工作区根> check                              # 核痕迹新鲜度 / 非零真红
python scripts/closeout.py           <工作区根> repair                             # 半事务补偿（幂等，可重放）
python scripts/gen_views.py          <技能包根> [--check]
python scripts/stamp.py              <目录> --slot human-review   # 产人检机器戳
python scripts/stamp.py --ai-id [--slot main-ai]                # 产 AI 标识（身份锚）
python scripts/new_local.py <工作区根> <脚本名> --purpose "..."  # 生成项目专属脚本骨架

# 提交流程的机械步骤（替代手改共享文件）
python scripts/closeout.py <工作区根> new-record "<主题>" --ai <标识>
python scripts/closeout.py <工作区根> index-add --id EN0007 --type [接力] --topic "<主题>" --record "reports\<文件>"
python scripts/closeout.py <工作区根> archive-reports
python scripts/closeout.py <工作区根> card-archive <卡文件名>
python scripts/closeout.py <工作区根> new-card "<任务名>"            # 建任务卡骨架（--design 建的是设计卡）
python scripts/closeout.py <工作区根> reviews-archive [--dry-run]   # REVIEWS 溢出滚动归档（只增不删）
python scripts/closeout.py <工作区根> design-archive "<主题>"         # 设计归档（详述+蓝图一起移；触发条件见 references/design.md §4）

# 定期与首次
python scripts/audit_all.py <工作区根> [--code <源码根>]   # 全盘核查 + 留痕
python scripts/setup.py     <工作区根> --plan               # 首次配置询问单
python scripts/setup.py     <工作区根> --apply --git yes --audit-days 7 --cards yes --commit

# 自检与接线
python scripts/selftest_gates.py                            # 门禁变异自检（改门禁后必跑）
python scripts/stamp.py --verify "git:abc1234@2026-09-24T00:11:00+08:00"
```

## 纪律

- **脚本不硬判语义**：凡需"理解内容"才能判的，一律输出 `[待核]` 交人或模型。
  误报掩盖真实问题是门禁的首要失效原因。
- **豁免必须机器可读**：判断豁免不能靠"文档里写了"，脚本要能读到它。
- **异常退出码必须计入结论**：进程崩溃不能因为"用例都过了"就算通过。为此各脚本入口统一走
  `_common.run(main)`：**脚本自身错误一律退出码 3**，与"门禁抓到真问题"（1）分开——
  否则核查者会把"脚本崩了"读成"项目有问题"。控制台编码装不下的字符降级为替代符，
  **不让一个字符把门禁变成崩溃**。
- **工作区文本一律 UTF-8（无 BOM）**。踩过的坑：Windows PowerShell 5.1 的 `Get-Content` 会按
  ANSI 代码页解码 UTF-8，**数出来的行数是错的**（实测同一文件 Python 算 189 行、PS 算 20 行）。
  **要行数/内容，用脚本读，不要用 `Get-Content` 数。**
