# 质量基准设计：外部先验 + 项目校准（母文档）

> **先把话说清**：本包**没有**私有的大规模代码统计库，**不伪造任何统计量**。
> 这里给出的是 **① 外部先验来自哪些公开规范与成熟工具**、**② 如何用真实数据把先验校准成阈值**。
> **外部资料告诉我们「什么值得测」；真实数据告诉我们「怎么测、阈值在哪里」。**

## 0. 两个数据源（不可互相替代）

```text
公开规范 / 成熟工具  ->  外部先验  ->  候选规则（含来源）
                                          |
                          正常样本 + 负向样本（本项目）
                                          |
                            TP / FP / FN / TN  ->  阈值与严重度
                                          |
                                     L0 -> L10  ->  正式门禁
```

**禁止**：`大厂说 100 行 -> 我们也是 100 行`。
**允许**：`大厂说这个指标值得看 -> 我们用真实样本定它的门槛`。

## 1. 外部先验的来源类别（实施时**须核对官方文档与版本**）

| 类别 | 代表 | 最适合提供什么 |
|---|---|---|
| 语言官方规范 / 代码评审文档 | Go 官方 code review 文档 · Rust 官方 API 指南 | **语言特有风险**（错误处理 · Context · goroutine 生命周期 · unsafe 边界） |
| 大型工程风格指南 | Google 的 C++ / Java / JS / TS / Go 指南 | **工程原则与危险构造**（可读性 · 复杂度控制 · 危险特性限制） |
| 成熟静态分析工具 | `clang-tidy` · Clippy · ESLint · `tsc` · `go vet` · SpotBugs · Checkstyle · PMD | **可机检的规则集合 + 分级** |
| 质量平台规则体系 | Sonar 的规则与质量门 | **多维度质量指标**（可靠性 / 安全 / 可维护性 / 覆盖率 / 重复） |
| 平台分析器 | Microsoft 的分析器与 CI 分层 | **项目级规则分层** |

> ⚠️ **两条纪律**：① 这些规范**不是普适权威**（各家的风格指南是对其自身代码生态的约定）；
> ② **工具默认值不是我们的标准**（例：ESLint `complexity` 默认、Clippy 各 lint 组默认等级）。

## 2. 七类质量数据（替代「只看 LOC」）

| 类 | 名称 | 例 |
|---|---|---|
| **A** | 结构指标 | 函数/文件长度 · 圈复杂度 · 认知复杂度 · 嵌套 · 参数数 · 重复 |
| **B** | 正确性指标 | 编译/类型错误 · 静态分析 correctness · 未处理错误 · 不可达 · 危险 API 误用 |
| **C** | 安全指标 | 缓冲区 · UAF · 空解引用 · 整数问题 · UB · 注入 · 动态执行 · 不安全反序列化 |
| **D** | 并发 / 资源指标 | 数据竞争 · goroutine 生命周期 · context 取消 · 资源泄漏 · 生命周期/所有权 |
| **E** | 架构指标 | 循环依赖 · 层级违反 · 依赖深度 · 耦合 · 公共 API 面 |
| **F** | 测试证据 | 测试是否存在 / 执行 / 通过 · 关键路径 · 覆盖率证据 · race/sanitizer 证据 |
| **G** | 工具证据 | 工具是否运行 · 版本 · 扫描与排除清单 · 退出码 · 原始输出引用 |

## 3. 八语言「从哪里找质量证据」的优先级

| 语言 | 第一优先 | 第二优先 | 第三优先 |
|---|---|---|---|
| Python | 正确性 | 可维护性 | 安全 |
| **C** | **安全 / UB** | 正确性 | 可维护性 |
| C++ | 正确性 / 安全 | 生命周期 / 所有权 | 复杂度 |
| JavaScript | 正确性 | 安全 | 可维护性 |
| TypeScript | **类型正确性** | 正确性 | 架构 |
| Java | 正确性 | 安全 | 架构 |
| Go | 正确性 | **并发** | 可维护性 |
| Rust | 正确性 | **unsafe / FFI** | 可维护性 |

（这不是「哪个语言更重要」，而是**该语言该去哪儿找证据**。）

## 4. 规则 ID 草案（可机检 · 只列骨架，实施时按工具实际名称映射）

| 语言 | 规则 ID 草案 |
|---|---|
| Python | `PY-001` 未定义名/未用导入 · `PY-002` 不可达/可疑控制流 · `PY-003` 动态执行 · `PY-004` 危险 subprocess · `PY-005` 不安全反序列化 · `PY-006` 圈复杂度 · `PY-007` 函数/文件长度 · `PY-008` 循环导入 · `PY-009` 测试执行与结果 · `PY-010` 覆盖率证据 |
| C | `C-001` 未处理编译器警告 · `C-002` 静态分析 correctness · `C-003` 缓冲区越界 · `C-004` 释放后使用/重复释放 · `C-005` 空解引用 · `C-006` 整数转换/溢出 · `C-007` 资源未释放 · `C-008` 未定义行为 · `C-009` 危险 API · `C-010` sanitizer/测试证据 |
| C++ | `CPP-001` 编译器诊断 · `CPP-002` clang-tidy correctness · `CPP-003` 生命周期/悬垂 · `CPP-004` 危险 cast · `CPP-005` 所有权误用 · `CPP-006` 模板复杂度 · `CPP-007` 类大小 · `CPP-008` include 依赖/循环 · `CPP-009` sanitizer · `CPP-010` 测试证据 |
| JavaScript | `JS-001` 未处理 Promise · `JS-002` 动态执行 · `JS-003` 危险 DOM/注入 · `JS-004` 依赖风险 · `JS-005` 复杂度 · `JS-006` 嵌套/回调深度 · `JS-007` 函数/文件长度 · `JS-008` 循环依赖 · `JS-009` 测试执行与结果 · `JS-010` 覆盖率 |
| TypeScript | `TS-001` tsc 编译错误 · `TS-002` strict 配置状态 · `TS-003` any 滥用 · `TS-004` 不安全断言 · `TS-005` nullability · `TS-006` 未使用声明 · `TS-007` 公共 API 类型质量 · `TS-008` 复杂度 · `TS-009` 测试 + 类型测试 |
| Java | `JV-001` 编译器 · `JV-002` 静态分析 · `JV-003` 异常吞掉 · `JV-004` 资源未关闭 · `JV-005` 注入 · `JV-006` 不安全反序列化 · `JV-007` 方法/类复杂度 · `JV-008` 继承深度 · `JV-009` 包循环/层级违反 · `JV-010` 测试与覆盖率 |
| Go | `GO-001` ignored_error · `GO-002` goroutine_lifetime · `GO-003` context_propagation · `GO-004` race_test_executed · `GO-005` data_race_found · `GO-006` resource_leak · `GO-007` package_cycle · `GO-008` complexity · `GO-009` function_size · `GO-010` test_coverage |
| Rust | `RS-001` unsafe 块（须有 justification）· `RS-002` FFI 边界 · `RS-003` clippy correctness · `RS-004` clippy suspicious · `RS-005` panic 策略 · `RS-006` 错误传播（unwrap/expect 滥用）· `RS-007` crate/feature 耦合 · `RS-008` API 复杂度 · `RS-009` 测试与文档测试 · `RS-010` unsafe 专项测试证据 |

**工具输出必须保留分组**（例：Clippy 的 `correctness / suspicious / style / complexity / perf / pedantic / restriction`）——
**不得**把「工具输出 warning」直接当成 FAIL；也**不得整体启用**限制型分组（官方自己提示会误伤合理代码）。

## 5. 每条规则的证据等级 E0–E6（**进入阻断规则的门槛**）

| 级 | 含义 |
|---|---|
| **E0** | 只有理论依据 |
| **E1** | 成熟工具已有该规则 |
| **E2** | **多个**公开工程规范支持 |
| **E3** | 有**真实项目样本** |
| **E4** | **正常 + 负向样本**验证 |
| **E5** | **误报 / 漏报**已验证 |
| **E6** | 已进入正式门禁 |

**硬性规定**：`E0` / `E1` **不得**成为**阻断**规则（可以是提示或 warning）；**阻断需要 E4 以上**。

## 6. 规则分类 A/B/C（**决定它能不能是硬规则**）

| 类 | 内容 | 处置 |
|---|---|---|
| **A** | 编译失败 · 明确正确性问题 · 严重安全问题 · 明确违反语言安全模型 | **可作为候选硬规则** |
| **B** | 函数/类长度 · 复杂度 · 参数数 · 依赖深度 | **必须经项目数据验证**才定门槛 |
| **C** | 命名偏好 · 某种格式 · 某种 idiom · 个人风格 | **只做建议**，不进阻断 |

## 7. 参考基准数据集（**本设计最值得做的部分**）

**目录结构（草案）**：

```text
references/quality-baseline/
  python/  c/  cpp/  javascript/  typescript/  java/  go/  rust/
    01-normal/        正常代码（不应误报）
    02-borderline/    边界代码（临界）
    03-negative/      明确问题（必须能变红）
    04-security/      安全问题
    05-complexity/    复杂度问题
    06-concurrency-or-resource/
    07-architecture/  循环依赖 / 层级违反
    08-test/          测试证据正例与反例（含「未执行」样本）
```

**每个样本目录包含**：

```text
source/            样本代码（本包**不**附带真实第三方代码，自行准备或最小自造）
expected.yml       期望结果：
                     expected_findings / expected_domain / expected_severity
                     provider / provider_version / expected_evidence / expected_judgement
README.md          这个样本为什么这样设计、它验证哪一条规则
```

**运行与统计**：

```text
Provider -> 实际结果 -> 与 expected 比较 -> TP / FP / FN / TN
        -> FPR = FP / (FP + TN)      （误报率）
        -> DR  = TP / (TP + FN)      （检出率）
        -> 才决定 severity：建议 / warning / high / blocker
```

**这一层比「再写一个 collector」高一级**：它让阈值来自统计，而不是来自两个人的直觉。

## 8. 输出形态（长什么样才算合格）

```text
QUALITY GATE

Language   Go

Evidence
  gofmt              EXECUTED / PASSED
  go vet             EXECUTED / PASSED
  go test            EXECUTED / PASSED
  go test -race      EXECUTED / PASSED

Correctness        findings: 0
Safety             findings: 0
Concurrency        findings: 2 HIGH
                     - goroutine lifecycle unclear
                     - race evidence unavailable
Maintainability    functions above validated threshold: 3
Architecture       package cycle: 0
Testing            tests executed: YES / coverage: VERIFIED

Conclusion         GRAY
```

> **`race evidence unavailable` 不得变成 `PASS`** —— 这就是本包 Evidence 原则的落地。

## 9. 与既有条款的接口（不重复定义）

- **归因**走 `references/multi-language-quality-gate-data-schema.md` §10.3 的 **A/B/C/D + 前置门**；
- **分叉**走同文件 §10.2 的**参数分叉硬规则**；
- **晋升**走 `references/language-quality-adaptation-plan.md` 的 **L0–L10**；
- **结论四档**（GREEN / YELLOW / RED / **GRAY**，且 **GRAY ≠ GREEN**）见同文件 §6；
- **Finding 字段**见同文件 §2（统一 Schema）。

## 10. 本设计明确不做

- ❌ **不伪造**统计量（没有私有大规模语料就不假装有）；
- ❌ 不把公开规范的数字当成本包阈值；
- ❌ 不让 `E0` / `E1` 的规则进入**阻断**；
- ❌ 不把工具 warning 数量直接当 FAIL；❌ 不整体启用限制型 lint 分组；
- ❌ 不附带真实第三方代码样本（基准数据集按需自备，避免许可与体积问题）。
