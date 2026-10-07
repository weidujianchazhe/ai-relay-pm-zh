# Empirical Validation Evidence — Cross-set Context-confounded Entity

## Scope

同一条源码实体在两个**任务定义不同**的集合中获得了**不同标签**。
本文件记录该现象与处置口径，**不作标注错误处理**。

## Finding 4: Context-confounded entity example

```json
{
  "entity_key": "Lib/re/_parser.py::module_function._parse",
  "annotations": [
    { "set": "A9", "purpose": "boundary_counterexample", "L1": "REVIEW", "L2": "REVIEW" },
    { "set": "T5", "purpose": "tail_census_random_batch", "L1": "GOOD", "L2": "IGNORE" }
  ],
  "cross_set_note": "same entity, different annotation contexts"
}
```

**Reason**：两个集合的抽样目的不同（边界/反例压力测试 vs 尾部随机批次审查），**标签语义随任务定义变化**。

## Policy（口径定稿）

1. **同一源码实体允许多条带上下文字段的标注**；
2. **标签比较必须在相同任务定义下进行**；
3. 跨任务冲突**不作为标注错误**，而作为**实验变量**记录；
4. 涉及**跨集合一致率 / Kappa 类**计算时，该实体标记为 `context_confounded`：**排除或单独报告**；
5. **集合内部统计保留原标签**（不做覆盖、不做改写）。

**Implication**：跨集合比较前必须先对齐**任务定义**；否则一致率差异可能来自任务框架而非标注质量。


## Evidence revision marker

```yaml
evidence_revision: 2026-10-01-T5
validation_snapshot: T5-complete
note: 内部实验记录编号；本目录不构成版本号的变更依据，也不改变任何阈值或 Core 语义
```
