# Empirical Validation Evidence — T5 Validation

## Scope

| 项 | 值 |
|---|---|
| 数据集 | T5（population 修正版：排除任意层级 `test` / `tests`） |
| 尾部规模 | eff>50 共 **233** 条（扫描 591 文件 / 排除 7,665 文件） |
| 度量口径 | **v2 函数级**（外层不计内部嵌套函数的分支） |
| 断言 | A1prime `test|tests` 命中 0 · A2 唯一键冲突 0 · A3 每文件≤1 且纯长度 6/6 · A4 元数据无泄漏 · A5 v2 · A6 计数一致 · A7 唯一键集合对称差 0 |
| 盲标批次 | 25 条（6 条纯长度全量枚举 + 19 条分层填充） |
| 标注结果 | L1：GOOD 24 · BAD 1 ／ L2：IGNORE 24 · REVIEW 1 |

## 纯长度小总体（明确小总体的全量枚举）

```text
定义：eff>100 且 ccn<=15 且 nest<=4 —— 全库仅 6 条（非抽样，全量纳入）
结果：GOOD 6 / 6（L2 全为 IGNORE）
读法：该 6 条是该子总体的实际值（无抽样误差）；不得外推为总体接受率
```

## Finding 1: Scale metrics do not capture correctness defects

```text
Entity: Lib/email/feedparser.py::FeedParser._parsegen
```

**Observation**：

- 人工标注识别出一个**真实行为缺陷**：`capturing_preamble` 分支在 `epilogue = []` 之后遍历剩余输入时**未 `append(line)`**，随后 `EMPTYSTRING.join(epilogue)` 使 epilogue 恒为空。
- 该缺陷**无法由 LOC / CCN / 嵌套解释**（它与规模无关）。
- 该实体被归入 **Correctness 域**，而不是可维护性阈值。

**Implication**（措辞收敛版）：

> 该案例提供了一个**经验反例**，显示**规模/复杂度代理指标无法覆盖部分 Correctness 缺陷**，
> 因此**支持**将 **Correctness 作为独立评价维度**（而非证明"必须"如此）。

**反向证据同时存在**：本批中"超阈值"的实体绝大多数为 GOOD —— 见 `rule-capability-comparison.md` 的 T5 表。


## Evidence revision marker

```yaml
evidence_revision: 2026-10-01-T5
validation_snapshot: T5-complete
note: 内部实验记录编号；本目录不构成版本号的变更依据，也不改变任何阈值或 Core 语义
```
