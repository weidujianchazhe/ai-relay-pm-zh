# 多语言质量门禁 · 数据方案（母文档）

> **性质**：**数据协议基线**，不是实现，**不是阈值**。
> **本文件成立的前提**：`config/defaults.yml` 的阈值**不动**；语言专属阈值继续等真实项目数据。

## 0. 三条原则（先于一切）

1. **成熟工具负责「发现问题」，本包负责「组织证据 + 决定门禁」** —— 不自研 ESLint / Clang / Clippy / `go vet` / `tsc`；
2. **工具默认值不是我们的质量标准** —— `tool default -> candidate evidence -> 真实项目验证 -> skill rule`，**不能反过来**；
3. **阈值永远是最后一步** —— 先是「定义风险 → 找 Provider → 定字段 → 正常样本 → 负向样本 → 测量误差 → 误报漏报」，**然后才**是阈值与项目覆盖。

## 1. 七个质量域（Q1–Q7 · 全语言固定）

| ID | 质量域 | 核心问题 | 默认重要性 |
|---|---|---|---|
| **Q1** | **Correctness** 正确性 | 代码是不是可能是错的？ | 极高 |
| **Q2** | **Safety** 安全性 | 有没有危险行为？ | 极高 |
| **Q3** | **Maintainability** 可维护性 | 将来是不是难改？ | 高 |
| **Q4** | **Architecture** 工程结构 | 结构是不是正在腐化？（循环依赖 / 层级违反 / 耦合） | 高 |
| **Q5** | **Testing** 测试证据 | 有没有真实的测试证据？ | 高 |
| **Q6** | **Evidence** 证据完整性 | 这个结论有没有真实证据？ | 极高 |
| **Q7** | **Performance** 性能与复杂度 | 成长路径上是不是做得不够好？（时间 / 空间 / 误差界） | 高 |

**为什么升级成六域**：`质量 = 行数 + 圈复杂度` 太窄。**一个潜在 use-after-free 比一个 110 行的函数严重得多。**

## 2. 【表 1】统一 Finding Schema（Provider 到底交什么）

```text
Language Provider -> Raw Evidence -> Normalized Finding -> Quality Domain -> Severity -> Judge
                                                    ^ 全多语言质量门禁的核心
```

**必填字段**（所有语言**只用这一种结构**）：

```json
{
  "language": "go",
  "provider": "go-vet",
  "provider_version": "1.x",
  "rule_id": "GO-CORRECTNESS-001",
  "domain": "correctness",
  "category": "error_handling",
  "severity": "high",
  "scope": { "type": "function", "file": "internal/server/server.go", "line": 128 },
  "metric": { "name": "ignored_error", "value": 1 },
  "evidence": { "source": "tool_output", "command": "...", "exit_code": 1 },
  "status": "detected",
  "confidence": "verified",
  "exception_status": "none",
  "judgement": { "state": "TBD", "reason": "threshold_not_validated" }
}
```

**铁律**：**Provider 不负责说 PASS / FAIL** —— 它只说「我在这里发现了什么」；**是否阻断由统一 Judge 决定**。

## 3. 【表 2】八语言质量矩阵（采什么 · 谁提供 · 什么可阻断）

| 语言 | Q1 正确性 | Q2 安全性 | Q3 可维护性 | Q4 结构 | Q5 测试 |
|---|---|---|---|---|---|
| **Python** | AST · 类型检查（若启用） | 动态执行 · 危险 subprocess · 注入 · 不安全反序列化 | 复杂度 · 长度 · 嵌套 · 重复 | 循环导入 · 依赖方向 | pytest 执行 + 结果 |
| **C** | 编译器诊断 · 静态分析 | **内存 / UB / 指针**（buffer overflow · OOB · UAF · double free · 空解引用 · 整数问题） | 复杂度 · 长度 | include 依赖 | 单测 · sanitizer |
| **C++** | 编译器 · `clang-tidy` | **lifetime · 悬垂引用 · 不安全转换 · 所有权 · UB** | 复杂度 · **模板复杂度** · 类大小 | include 依赖 · 循环 · 公共 API 面 | 单测 · sanitizer |
| **JavaScript** | ESLint · 明显逻辑错误 · Promise 误用 | **eval / 动态执行 · 危险 DOM · 注入 · 依赖风险** | 复杂度 · 嵌套 · 重复 · 回调复杂度 | import 图 · 循环 · 包边界 | Jest 执行 + 结果 |
| **TypeScript** | **`tsc`** + ESLint | JS 风险 **+ 类型逃逸**（any 滥用 · 不安全断言） | 复杂度 · 类型复杂度 | 模块依赖 | Jest/Vitest + 类型测试 |
| **Java** | 编译器 · SpotBugs | 注入 · 不安全反序列化 · 资源生命周期 | 方法/类复杂度 · 重复 · 参数数 · 继承深度 | 包循环 · 层级违反 · API 面 | JUnit 执行 + 结果 |
| **Go** | 编译器 · `go vet` · 静态分析 | **数据竞争 · goroutine 生命周期 · 资源泄漏 · unsafe** | 复杂度 · **错误处理** · 过度抽象 | 包循环 · 包耦合 | `go test` + **`-race`** + 覆盖率 + benchmark 证据 |
| **Rust** | `rustc` · Clippy `correctness` | **unsafe · FFI · 裸指针 · panic 行为 · unsafe 边界** | 复杂度 · 类型/API 复杂度 | crate 依赖 · workspace · feature 耦合 | `cargo test` + 集成 + 文档测试 |

**各语言的重点差异（不是所有域等权）**：

| 语言 | 权重画像 | 一句话 |
|---|---|---|
| Python | 正确性★★★ · 可维护性★★★★ · 安全★★★ · 结构★★★★ · 测试★★★★ | 重点在**错误处理 / 复杂度 / 动态类型风险 / 异步 / 资源** |
| **C** | **正确性×极高 · 安全×极高** · 可维护性高 | **100 行的 C 函数不一定严重；一个潜在 use-after-free 才严重** |
| C++ | 正确性 · 安全 · 可维护性 · **复杂度** · API 设计 | 语言能力越强 → 复杂度与风险越高；**但不自造 C++ AST 分析器** |
| JavaScript | 动态行为 · 异步 · 依赖 · 安全 · 复杂度 | 重点不在 LOC，在**动态性与异步** |
| TypeScript | **类型正确性** + JS 运行时安全 + 可维护性 | **TS ≠ JS + .ts**；Provider 至少 `ESLint + tsc` |
| Java | 架构 · 类复杂度 · 异常流 · 资源 · 依赖 | 编译器已挡掉低级问题 → **找编译器没告诉你的工程问题** |
| Go | 并发 · 错误处理 · 资源 · 结构 | **`go test -race` 没报 ≠ 无并发 bug**（只证明本次路径未被检出） |
| Rust | **unsafe / FFI** · 错误传播 · panic · API · 并发 | **编译器已做 ownership/lifetime → 本包不重复**；`unsafe != FAIL`，而是**需要证据与边界管理的风险源** |

## 4. 【表 3】Severity / Blocking Matrix

| 级 | 名称 | 默认处置 |
|---|---|---|
| **S0** | INFORMATION | 纯信息，不影响门禁 |
| **S1** | STYLE | 风格，**默认不阻断** |
| **S2** | MAINTAINABILITY | 默认不阻断；**达到经过验证的阈值**后才可能阻断 |
| **S3** | WARNING | 进入质量报告 |
| **S4** | HIGH | 严重质量问题，**可阻断** |
| **S5** | BLOCKER | correctness / safety 类严重问题，**原则上阻断** |

**但 `S5 = 永远 FAIL` 不写死** —— 项目可以有：生成代码 · 遗留代码 · 平台特定代码 · **有意为之的 unsafe** · 测试夹具。
所以完整链是：`Finding -> Severity -> Scope -> Exception Policy -> Judge`。

**目标不是 0 warnings**，而是：

```text
0 未解释的 Blocker · 0 未处理的 High · 可接受的 Warning · 所有例外都有证据
```

## 5. 【表 4】Evidence / Exception Schema（区分「没检查」与「真的通过」）

| 状态 | 含义 | **绝不允许** |
|---|---|---|
| `executed_passed` | 工具真跑了且通过 | — |
| `executed_failed` | 工具真跑了且失败 | — |
| **`not_executed`** | **工具没跑 / 不存在** | ❌ 绝不能当通过 |
| `tool_error` | 工具自身报错（rc=3 类） | ❌ 绝不能当通过 |
| `unavailable` | 能力缺失（provider unavailable） | ❌ 绝不能当通过 |
| **`not_applicable`** | 该语言/项目类型**明确不适用** | 必须写明理由 |
| `exception_granted` | **允许的例外**（生成/遗留/平台/有意 unsafe） | **必须留下：理由 + 范围 + 放行依据** |

**必录证据字段**：工具是否运行 · 工具版本 · 扫描了哪些文件 · **排除了哪些文件与原因** · 是否编译 · 测试是否执行 · 真实输出引用 · 退出码。

## 6. 结论四档（替代单纯 PASS/FAIL）

| 档 | 含义 |
|---|---|
| **GREEN** | 无阻断问题 |
| **YELLOW** | 有可维护性 / 复杂度问题，**不阻断** |
| **RED** | 存在严重 correctness / safety 问题 |
| **GRAY** | **没有执行 / 工具缺失 / 证据不足** |

**铁律：`GRAY` 绝对不能自动转换成 `GREEN`。** —— 这才能让 `TBD` / `BLOCKED` / 未执行 具有工程意义。

## 7. 配置形态（**不要**长成 per-language 阈值表）

**避免**：`languages: {python: {function_lines: 100}, cpp: {function_lines: 80}, …}` —— 那是配置垃圾场的起点。

```text
quality_gate:
  domains:
    correctness:      policy: blocker
    safety:           policy: blocker
    maintainability:  policy: evidence_required
    architecture:     policy: evidence_required
    testing:          policy: evidence_required
    evidence:         policy: mandatory
```

**结构**：`通用质量域（策略） <- 语言规则（rule_id） <- Provider 数据 <- 成熟工具`。

## 8. 八语言落地路线（四批 · 按技术依赖）

| 批 | 语言 | 在验证什么 |
|---|---|---|
| 一 | Python · C · C++ | 现有架构能否统一不同底层模型？C/C++ 重点验证 **Provider** |
| 二 | JavaScript · TypeScript | **动态语言 + 类型超集**能否共存？重点验 `ESLint + tsc` **双证据** |
| 三 | Java | **企业级强类型 + 大型模块架构**如何进入门禁？ |
| 四 | Go · Rust | **并发模型**与**编译器安全模型**如何进入统一门禁？ |

## 9. 本文件明确不做

- ❌ 不把本文档里的任何「建议采集项」变成 `defaults.yml` 的阈值；
- ❌ 不把工具默认值（ESLint complexity 20、Clippy 各类别等）当成本包标准；
- ❌ 不整体启用限制型 lint（如 Clippy `restriction`）——**官方自己都提醒会对合理代码误伤**；
- ❌ 不追求 0 warnings；❌ 不为了填满矩阵制造 PASS。

> **一句话**：**成熟工具负责发现问题，本包负责组织证据并决定门禁；阈值永远是最后一步。**
## 10. 治理基线（v3.9.0 固定 · 四项 · 落地后不再因规则性补充升版本号）

### 10.1 ① 内容准入：什么能进质量门禁、什么必须排除

**能进**：有 Provider 证据的 Finding —— 属于六域之一 · 有 `rule_id` · 有严重级 · 有工具与版本 · 有真实输出引用。

**必须排除**（**排除必须记录原因，不得静默忽略**）：

生成代码 · 第三方 / vendor 代码 · 构建产物 · 测试夹具（除非项目明确纳入）· 平台或工具链不适用的文件 · 该语言不适用的检查项。

**排除记录字段**：`excluded: { path, reason, decided_by, evidence }` —— **没有记录 = 不允许排除**。

> 内容该进 **Core** 还是 **Adapter**，是另一件事，见 `references/language-adapters.md` §12（软件工程本身 / 新工程维度 / 某语言编程知识）。

### 10.2 ② 参数分叉判据（**硬规则**）

> **语言不同本身不是分叉理由。**
> **只有当真实证据证明通用规则不能正确表达该语言的工程风险时，才允许语言级参数。**

**分叉前置证据链（顺序不可颠倒）**：

```text
该语言的真实数据
  -> 通用规则产生「系统性」误判（不是个案）
  -> 确认不是 Provider 问题
  -> 确认不是统计口径问题
  -> 确认不是项目特殊情况
  -> 才允许语言级参数（并在 version-boundaries 留下开版记录）
```

**明确禁止**：`C++ ≠ Python -> 所以 C++ 要一套阈值`。

### 10.3 ③ A/B/C/D 误报漏报分类 + **前置验证门**

| 类 | 问题所在 | 修哪一层 |
|---|---|---|
| **A** | Provider 识别错（函数识别错 / 文件漏扫） | 修 **Provider** |
| **B** | 统计口径错（这个数字到底是什么：含注释？空行？宏展开前后？） | 修 **Provider / 指标定义** |
| **C** | 统计对，但阈值产生**系统性**误判 | **阈值治理**（走 10.2） |
| **D** | 阈值合理，但项目**确有例外** | **项目级覆盖** + 记录理由 |

**前置验证门**：**未排除 A 与 B，不得进入 C**；**未排除 C，不得走到 D**。

> 否则最常见的一种错误就会发生：**«这个项目经常触发 100 行限制，所以把 100 改成 200»**
> —— 那很可能是在**掩盖 Provider 或口径的问题**。

### 10.4 ④ 三维能力矩阵 + L0–L10

- 三格**独立**记录：**识别级 / 测量级 / 适配级**；
- 晋升按 `references/language-quality-adaptation-plan.md` 的 **L0–L10** 走，**每级都必须有痕迹**；
- **未完成即保持 TBD**，**不得**因"有文档 / 有命令 / 工具能装 / 工具能跑"而晋升；
- **落地要求**：矩阵里任何 `OK` 都必须能一眼看出**是哪一级**（**禁止**单格 `OK` 被读成"已适配"）。

## 11. 3.9.0 的准确定义（避免误读）

```text
3.9.0 = 多语言质量门禁的「治理 + 数据协议」基线
      ≠ 8 种语言已完成质量适配
```

**完整治理闭环（本版已闭合）**：

```text
内容准入 -> 语言识别 -> 测量 -> 适配 -> L0–L10
        -> 误报归因(A/B/C/D) -> 参数分叉判据 -> 阈值治理 -> Quality Gate
```

**下一阶段的版本变化，必须来自「真实 Provider + 真实项目验证」产生的实质能力变化，而不是再增加一份文档。**
