# 证据：尺度指标 vs 结构模式（Python 判定分两层）

> 证据版本 `2026-10-02-structure-layer` · 落盘 `3.9.2` · 面向：代码质量门禁的**动作分级**决策

## 一、结论（本页支撑的两个决定）

1. **规模类指标降为「观察」**（长度 / 圈复杂度 / 嵌套 / 文件行）：数值未改、检查未删、信号仍逐条打印，但**不再阻断**。
2. **新增结构模式规则为「阻断」层**（Correctness 域）：判定的是**形状**（能指向具体变量与位置），不是数值大小。

## 二、为什么规模类降为观察（实测依据）

```text
S5 全量 42 条：GOOD 14 · ACCEPTABLE 21 · REVIEW 6 · BAD 1
S4 抽样 40 条（人类）：ACCEPTABLE 38 · GOOD 2 · REVIEW 0 · BAD 0
触发分档（C / CN / N）：人工判定中「需要动作」= 0 条
唯一那条 BAD（email/feedparser.py::FeedParser._parsegen）与规模完全无关
```

**推论**：规模线拦到的多是已达标代码，而真缺陷在它之外。把它当阻断线 = 高误报、零召回。

## 三、结构模式规则（首版，Python 最小集）

| 规则 | 动作 | 判据 |
|---|---|---|
| C1 循环漏收集 | 阻断 | 空容器就地建立 → 紧邻 `for` 循环**未写入**该容器 → 循环后仍被使用 |
| C2 异常被吞 | 裸 `except: pass` 阻断；有类型但仅 `pass` 观察 | `except` 分支仅 `pass` |
| C3 句柄未关 | 观察 | `x = open(...)` 后未见 `close()`/`with`，且未交给调用方 |

**召回证明（夹具，2026-10-02）**：复刻 `_parsegen` 形态（`epilogue = []` → 循环体只 `continue` → 循环后 `join`）→
规则精确报出 `mod.py:3 「epilogue」… 疑似漏写收集语句`，**exit=1**；
三个对照（下标赋值构建字典 / `append` 收集 / 循环后未使用）**全部放过**。

## 四、误报收窄过程（必须留档的教训）

```text
首版（只认 Name 存储 / .append 等 / 作实参传出）扫本包 scripts/：
   阻断 9 条 —— 逐条人工核对后判定【9/9 全是误报】
   共同形态：d[k] = v（下标赋值），首版未把它算作写入通道
收窄：补 Subscript 存储 / Attribute 存储两条写入通道后：
   本包 scripts/ 阻断 9 -> 0（误报清零），夹具召回仍为 1（未损召回）
```

**教训**：新规则上线前**必须做精度抽检**（逐条看真假），否则就是用新噪声替换旧噪声。

## 五、可复跑命令

```bash
python scripts/correctness_rules.py scripts        # 本包自扫：期望 阻断 0 · 观察 17
python scripts/code_metrics.py scripts             # 规模度量：拦截线 0 · 观察逐条打印
python scripts/selftest_gates.py                   # 变异自检：含「注入循环漏收集必须变红」用例
```

## 六、3.9.2 的行为变更点（升级必读）

- 规模类超限**不再阻断**（`code_metrics.py` 的 `_is_scale_msg()` 决定；改回 `return False` 即恢复阻断）。
- **新增阻断层**：`scripts/correctness_rules.py`（C1 阻断 · C2 裸 except 阻断 · C3 观察）。
- `ci/github-actions.yml` 已接入结构模式步骤，首版设 `continue-on-error: true`（先看噪声，稳定后转阻断）。
