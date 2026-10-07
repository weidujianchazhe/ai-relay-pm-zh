# 多语言质量适配方案（母文档）

> **性质**：本文件是**实施方案**，**不是实现**。本轮**不写 collector、不改 config、不设语言专属阈值**。
> **一句话**：不是给 7 种语言各造一个 collector，而是给每种语言建立一条**从真实工具到可验证质量标准**的**证据链**。

## 0. 边界（四条红线，先于一切）

1. **不自研解析器 / 编译器 / 借用检查器**——成熟工具能做的，**接入并验证那个工具**；
2. **不复制工具默认值当标准**（如 ESLint `complexity` 默认 20、Python 的 50/100/100）——工具默认只是**它自己的**默认；
3. **没有真实项目证据，不固化语言专属阈值**；
4. **Provider 只产证据，不作判定**；判定统一由 `judge` 负责。

## 1. 三级能力矩阵（固定口径）

| 级别 | 含义 |
|---|---|
| **识别级** | 能正确识别这是该语言的项目 / 源码 |
| **测量级** | 有真实工具把质量数据**测出来** |
| **适配级** | **已验证**这些数据该如何用于质量判定 |

**现阶段矩阵（v3.8.0 起）**：

| 语言 | 识别级 | 测量级 | 适配级 |
|---|---|---|---|
| Python | OK | **VERIFIED（已有真实执行）** | **TBD** |
| C | OK | TBD | TBD |
| C++ | OK | TBD | TBD |
| JavaScript | OK | TBD | TBD |
| TypeScript | OK | TBD | TBD |
| Java | OK | TBD | TBD |
| Go | 候选 | TBD | TBD |
| Rust | 候选 | TBD | TBD |

**`TBD → VERIFIED` 的禁止提前晋升理由**：有文档 / 有命令 / 工具能装 / 工具能跑 —— **都不算**。
> **注意**：Python 虽已真实执行，但**未验证阈值**，故其**适配级仍是 TBD**（按本包自己的定义）。

## 2. 十级晋升门槛（L0–L10，任何一级未完成 → 仍是 TBD）

| 级 | 名称 | 完成判据（**须有痕迹**） |
|---|---|---|
| **L0** | 语言登记 | 进入候选列表；**不得表述为「支持」** |
| **L1** | 语言识别 | 扩展名 / 项目结构 / 语言名映射正确 |
| **L2** | 工具发现 | 能确定所需成熟工具是否存在；**不存在 -> `[待核] provider unavailable`，绝不 PASS** |
| **L3** | Provider 接通 | 能调用真实工具并获得原始结果 |
| **L4** | 结果归一化 | 转为统一结果模型（见 §4） |
| **L5** | 指标口径验证 | 确认「这个数字到底是什么」（含注释？空行？宏展开前后？排除生成代码？含测试？） |
| **L6** | 正常样本验证 | 真实正常项目**不因合理结构大量误报** |
| **L7** | 负向样本验证 | 人为制造的明确问题**能真实变红** |
| **L8** | 阈值验证 | 真实数据足够后才定 `recommended / warning / blocked`；**不得从 Python 复制** |
| **L9** | 项目覆盖验证 | 语言默认 -> 项目类型 -> 项目 override 能共存，**且每次覆盖有记录** |
| **L10** | 正式适配 | 证据链完整 -> 矩阵写 `适配级 = VERIFIED` |

**每级晋升必须能指向具体痕迹**（哪次运行 / 哪个样本文件 / 哪个工具与版本 / 哪份误报漏报记录）——
否则没人能区分「真的验证过」与「当时觉得验证过」（同 `references/audit.md` §2.0 锚源原则）。

## 3. 七语言 Provider 与第一阶段指标

| 语言 | Provider（优先接成熟工具） | 第一阶段指标 | 该语言特有风险（重点观察） |
|---|---|---|---|
| **Python** | 现有 `ast`（**不新增**） | 函数行 / 文件行 / 嵌套 / 圈复杂度 | decorator · async · generator · 推导式 · 异常处理 · 嵌套函数 · lambda · 上下文管理器 |
| **C** | 编译器诊断 + Clang 工具链 / Static Analyzer + 项目已有静态分析 | 同上 + 静态诊断 | 指针 · 手动内存 · 数组边界 · 宏 · 条件编译 · 未定义行为 · 整数转换 · 资源释放 · ABI/FFI |
| **C++** | `clang-tidy` + Clang Static Analyzer + 编译器诊断（**须记录编译环境**：`compile_commands.json` / flags / include / defines / 标准） | 同上 + 静态诊断 | RAII · 模板 · 重载 · 继承 · 虚派发 · lambda · 智能指针 · move · 异常 · 生命周期 / 所有权 · ABI |
| **JavaScript** | **ESLint**（官方已覆盖 complexity / max-depth / max-lines / max-lines-per-function / max-nested-callbacks / max-params） | 文件行 / 函数行 / 圈复杂度 / 嵌套 / 回调嵌套 / 参数数 / 静态诊断 | Promise 未处理拒绝 · 深层回调 · 错误处理缺失 · 动态类型 · 模块边界 |
| **TypeScript** | **ESLint + `tsc`（双 Provider）** | 结构质量 + Lint 质量 + **类型系统质量** | 类型错误 · implicit any · return 一致性 · override 正确性 |
| **Java** | Checkstyle（结构/风格）· PMD（质量规则）· SpotBugs（字节码）· **优先用项目已有工具** | 方法/类复杂度 · 异常流 · 资源生命周期 | 异常吞掉 · 资源未关闭 · 过深继承 · null 风险 · 并发 · 依赖误用 |
| **Go** | `go build` / `go test` / **`go vet`** / **`go test -race`** | 结构指标（真实项目后再定）+ 并发证据 | goroutine 生命周期 · channel 误用 · 数据竞争 · context 取消 · 资源回收 · 错误传播 |
| **Rust** | `cargo check` / `cargo test` / **`cargo clippy`** / `cargo fmt --check` | 结构指标 + 编译器/lint/测试证据 | **unsafe** · FFI · panic 策略 · 错误传播 · 并发 · 依赖风险 |

**两条必须记住的边界**：
- **TypeScript 不能当「JavaScript + .ts 扩展名」**——类型系统本身是一个质量维度；
- **`cargo check` PASS ≠ 质量 PASS**、**`go test -race` 没报 ≠ 无并发 bug**——它们只是**证据的一部分**。

## 4. 统一证据模型（Provider -> Judge 的唯一接口）

```text
Provider 产出证据（不判定）：
  { "language": "rust", "metric": "clippy_diagnostics", "value": 3,
    "provider": "cargo-clippy", "tool_version": "…", "scope": "…", "evidence": "…" }

流程：Provider -> Raw evidence -> Normalize -> Judge -> PASS / FAIL / TBD / BLOCKED
```

**语言差异只允许存在于「测量层」与「规则层」；`judge` 与 Core 判定机制不受污染。**

## 5. 阈值策略

**禁止**：`Python=50/100/100 · C 同 · C++ 同 · Go 同 · Rust 同`；**也禁止**「业界一般 100 行，就定 100」。

```text
真实项目 -> 真实 Provider -> 统计分布 -> 正常样本 -> 异常样本
         -> 误报/漏报 -> 语言标准 -> 项目类型标准 -> 阈值
```

**合法中间态**：`measurement = VERIFIED` 而 `adaptation = TBD`。

## 6. 实施顺序（按**技术依赖**，不按市场优先级）

| 批 | 语言 | 在验证什么 |
|---|---|---|
| 一 | **Python · C · C++** | Python 验证现有模型；C/C++ 验证**外部 Provider 模型** |
| 二 | **JavaScript · TypeScript** | 验证**成熟第三方工具 + 双 Provider** |
| 三 | **Java** | 验证**多工具组合** |
| 四 | **Go · Rust** | 验证**并发 / 编译器约束 / 运行时证据** |

## 7. 完成定义（十问，缺一不可）

1. 能识别它吗？ 2. 能真实测量吗？ 3. 口径验证了吗？ 4. 知道它特有的问题吗？ 5. 正常项目会被误拦吗？
6. 明显坏代码能真实变红吗？ 7. 阈值有真实证据吗？ 8. 项目特例能明确覆盖吗？ 9. 结果有工具与版本证据吗？
10. `capability_matrix` 是否**准确反映**上述状态？

> **不能以「所有语言都有 collector」作为完成标准。**

## 8. 本方案阶段明确不做

- 不修改 `config/defaults.yml`；不建立语言专属阈值；
- 不自研 JS/TS/Java/Go/Rust AST 解析器；不实现 Rust borrow checker；不复制编译器能力；
- 不把第三方工具默认阈值变成 Skill 阈值；
- **不因为 `adapters/*.md` 存在就标记语言为已实现**；
- 不为了填满能力矩阵而**制造 PASS**；不因为工具能跑就宣称适配完成。

> **分工**：**工具负责测量 · Provider 负责取证 · Skill 负责归一化 · Judge 负责判定 · 证据让「已适配」成立。**
