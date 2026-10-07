# Empirical Validation Evidence — T5 Phase 1（S5 长度层级清查）

## Scope

| 项 | 值 |
|---|---|
| 数据集 | T5（population：任意层级 `test`/`tests` 排除 + 顶层 idlelib/lib2to3/tkinter/site-packages 排除） |
| 目标层 | **S5 = eff>100 行**，全库 **42 条全量枚举**（非抽样） |
| 度量口径 | v2 函数级（外层不计内部嵌套函数的分支）；键 =（文件路径, 限定名） |
| 标注字段 | L1 · L2 · cause_domain（13 值扩展词表）· metric_visibility（yes/no）· metric_level（high/medium/low，可选）· reason |
| 落点 | 数据：`ground_truth_T5/labels_t5_233.json`（证据层，包外实验目录） |

## 分布（42/42 完成，字段完整性：metric_visibility 空缺 = 0）

```text
L1：GOOD 14 · ACCEPTABLE 21 · REVIEW 6 · BAD 1
L2：IGNORE 14 · OBSERVE 22 · REVIEW 6
配对：GOOD-IGNORE 14/14 · REVIEW-REVIEW 5 · REVIEW-OBSERVE 1 · BAD-REVIEW 1
标注来源：carry 13 · new 27 · independent 2
```

**metric_visibility 分布（42 条）**：length yes 38 / no 4 · ccn yes 27 / no 15 · nesting yes 25 / no 17
（`ccn` 与 `nesting` 各有 15/17 条被判为 `no` —— 人工认为这两个指标**不足以表达**该条目的风险来源）

**cause_domain 高频**：io_serialization · data_transform · maintainability · implementation_logic · error_handling · interface_orchestration
（这 6 个值中有 4 个属于 2026-10-01 新扩展进词表的维度）

## Finding A1: 长度层级的主体不是缺陷，而是「可观察复杂」

```text
S5 42 条中：BAD 1 条（2.4%）· REVIEW 6 条（14.3%）· ACCEPTABLE 21 条（50%）· GOOD 14 条（33.3%）
```

**Implication（收敛表述）**：在**本层级的全量枚举**下，**长度条件本身不与缺陷状态强相关**；
长度层级可作为「观察层」的候选池，但不构成「动作层」的充分条件。

**不得外推**：S5 是全库该层级的全量枚举，**不是自然分布抽样**；上述比例不适用于其它层级或其它代码库。

## Finding A2: 唯一 BAD 与规模无关（承接 T5-25 的 C22）

```text
Entity: Lib/email/feedparser.py::FeedParser._parsegen
缺陷：capturing_preamble 分支 epilogue=[] 后遍历输入未 append(line) -> epilogue 恒为空
```

该实体在 S5 中被独立复核（carry 自 T5-C22），结论一致。**规模/复杂度代理指标无法表达该缺陷**，
它属于 Correctness 域 —— 与 `t5-validation.md` 的 Finding 1 为同一证据链。

## Finding A3: 嵌套父子对会同时进入同一层级

```text
T5S5-18 module_function._simple_enum  /  T5S5-19 module_function._simple_enum.convert_class
T5S5-33 module_function.dis          /  T5S5-34 module_function.dis.dis_
```

**事实**：两对父子实体**都**满足 eff>100 并进入 S5；长度只计外层时，内层实体仍会被单独计入自己的 eff。
**Implication**：长度类门禁在存在嵌套函数的代码上会**对同一段实现产生重复计数候选**；
统计与门禁设计需明确「是否对父子对去重」。（本证据不结论、只记录。）

## Finding A4: 跨集上下文混淆实体的第三次独立判断

```text
Entity: Lib/re/_parser.py::module_function._parse
A9#3   : REVIEW / REVIEW        （boundary_counterexample 框架）
T5-C25 : GOOD / IGNORE          （tail random batch 框架）
T5S5-35: ACCEPTABLE / OBSERVE   （S5 长度层级框架 -> 独立判断，不 carry）
```

**Implication**：同一实体在三个任务框架下得到三种标签 —— 支持 `cross-set-context-confounded.md` 的口径：
**标签比较必须在相同任务定义下进行**；跨框架冲突作为实验变量记录，而非标注错误。

## Schema 修订史（本阶段发生，均属证据层字段规范）

```yaml
cause_domain:           24 值？否 —— 2026-10-01 由 7 值扩展为 13 值
  新增：data_transform / io_serialization / data_initialization /
        implementation_logic / error_handling / interface_orchestration
  依据：15 次实际使用落在原声明域之外，属稳定缺失维度而非偶发描述词
metric_visibility:      2026-10-02 归一为 yes/no
  语义：yes = 该指标可直接反映该问题维度；no = 不足以表达该维度
  历史值（指标数值 / high-medium）不删除，分别保留于
  metric_values_supplied 与 metric_level（独立字段，避免一字段两语义）
```

## 标注协议偏差记录（透明化）

本阶段共记录 4 类字段层偏差，均在落库时**原样保留 + 标记**，未擅自改写：
metric_visibility 词表三次变体 · cause_domain 非声明域值（已由词表扩展解决）·
L1/L2 非常规配对（GOOD-OBSERVE 经确认为笔误并修正；REVIEW-OBSERVE 经确认为有意设定）·
疑似指标污染（经用户裁定为误填，未置 non_blind）。

## Evidence revision marker

```yaml
evidence_revision: 2026-10-02-T5-S5
validation_snapshot: T5-P1-complete
note: 内部实验记录编号；本文件不构成版本号变更依据，也不改变任何阈值或 Core 语义
```
