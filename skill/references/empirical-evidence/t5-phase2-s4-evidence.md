# Empirical Validation Evidence — T5 Phase 2（S4 CCN/nesting 分层抽样）

## Scope

| 项 | 值 |
|---|---|
| 目标层 | S4 = eff 51-100 且（ccn>15 或 nest>4）；总体 **155 条** |
| 抽样 | **分层随机**：C 20 / CN 15 / N 8 = **43 条** · seed=20261003 |
| 源码量 | 3886 行（样本内） |
| 标注来源 | **人类 40 条** · **AI 代理 3 条（单独文件，排除于人类统计）** |
| 触发分布 | {"CN": 15, "C": 20, "N": 8} |
| 落点 | human：labels_t5s4.json · agent：labels_t5s4_agent.json（同目录） |

## 分布（人类 40 条 + 代理 3 条覆盖 43/43）

```text
人类 L1：{"ACCEPTABLE": 38, "GOOD": 2}
代理 L1：{"ACCEPTABLE": 3}
```

## Finding B1: 历史批次 GOOD 与分层复核 ACCEPTABLE 的**同向偏移**

```text
冲突（dual + context_confounded）：
  T5S4-016  T5-C14  GOOD/IGNORE -> ACCEPTABLE/OBSERVE
  T5S4-025  T5-C10  GOOD/IGNORE -> ACCEPTABLE/OBSERVE
  T5S4-045  T5-C12  GOOD/IGNORE -> ACCEPTABLE/OBSERVE
  T5S4-056  T5-C16  GOOD/IGNORE -> ACCEPTABLE/OBSERVE
  T5S4-135  T5-C13  GOOD/IGNORE -> ACCEPTABLE/OBSERVE
  => 5/5 同向，无一例反向、无一例保持 GOOD

对照（carry，标签一致）：
  T5S4-001 A9#5 · T5S4-013 A9#7 · T5S4-026 T5-C11 · T5S4-153 T5-C17
  => 4/4 无偏移
```

**Implication（收敛表述）**：在**本样本**中，历史 T5-25 批次的 5 条键一致实体全部出现同向标签偏移，
而 A9 来源与同批次的另外 2 条未偏移。**这提示批次语境作为实验变量值得单独控制**；
**本证据不解释成因**（不做 A/B/C/D 归因），也不改变任何历史标签。

## Finding B2: 触发类型与人工判断的关系（本样本，不外推）

```text
C 组 20 条 / CN 组 15 条 / N 组 8 条 -> 人类判定中 REVIEW 0 条、BAD 0 条
唯一非 ACCEPTABLE 的人类标签是 2 条 GOOD（均为历史 carry）
```

**Implication**：在本样本中，**CCN / nesting 触发本身未产生任何 REVIEW/BAD**；
指标触发与「需要人工动作」之间**仍未观察到稳定映射**（与 Phase 1 一致）。
**不得外推**：43 条为分层抽样，且 C/CN/N 为构造分层（非自然分布比例）。

## Finding B3: 重复与近名实体的处理

```text
字节相同对：T5S4-045 = T5S4-047（sha256[:12]=70da956c2646）-> 047 记 label_inherited_from
同文件同名簇：T5S4-034（已现代化改写，sha=2c68bc934e29）与 045/047 不同源
近名对：T5S4-048 parse_makefile vs T5S4-121 _parse_makefile -> 两个独立实体，无 carry
嵌套父子对：T5S4-015 consume_optional 的父实体 = Phase 1 的 T5S5-05（不继承标签）
```

## 字段协议偏差史（透明化，均原样保留）

本阶段记录 8 类偏差，其中最重要的一次是：**L1/L2 曾被填入非受控域值**（T5S4-107/116/117）；
该次**未写入主标签**，而是暂存 l1_raw_supplied / l2_raw_supplied，待人类补正后才入库。
`metric_visibility` 共出现 5 次词表变体（数值 / high-medium / visible / low），均归一为 yes/no 并保留原值。
`cause_domain` 由 7 值扩至 24 值（6 次扩展，均经人类裁定「甲」）。

## Evidence revision marker

```yaml
evidence_revision: 2026-10-02-T5-S4
validation_snapshot: T5-P2-complete
human_ground_truth_items: 40
agent_labeled_items_excluded: 3
note: 内部实验记录编号；本文件不构成版本号变更依据，也不改变任何阈值或 Core 语义
```
