# 落地附录 · C++

> **状态：未实现（仅说明）** —— 本文件是适配说明，不是已实现能力；语言准入判据见 references/language-adapters.md §12。
> ⚠️ **本文件不属技能正文**，是 references/code-quality.md 的**按栈落地附录**：只回答「在 C++ 栈上用什么工具、配什么参数、接线在哪」。
> **外部依据全部来自公开标准与大厂实践，不来自本包自采样。**

## 0. 外部先验（权威来源，接入时须核对版本）

| 来源 | 提供什么 |
|---|---|
| **C++ Core Guidelines（ISO C++ 基金会）** | 现代 C++ 的权威实践与"不要做什么"（带编号 GSL / F / C / R / ES 等） |
| **SEI CERT C++ Coding Standard** | C++ 专有缺陷规则集（带编号） |
| **MISRA C++:2023 · AUTOSAR C++14** | 高约束行业规则（汽车 / 工业） |
| **Google C++ Style Guide · LLVM Coding Standards** | 大厂工程约定与危险构造限制 |
| **ISO/IEC 14882（C++ 标准）+ 实现 UB 清单** | 未定义行为 / 生命周期 / 求值顺序 |
| **Clang 诊断树与 Sanitizer 文档** | 可机检证据（含 lifetime、UB） |

## 1. 工具映射

| 正文条款 | C++ 工具 | 说明 |
|---|---|---|
| 规模三档 | `lizard`（支持 C++）· `clang-tidy readability-function-size` | 沿用通用步骤 |
| 复杂度 / 模板复杂度 | `lizard --CCN` · `clang-tidy readability-cognitive-complexity` | 模板复杂度另见语言差异表 |
| 命名与风格 | `clang-format`（Google / LLVM 预设） | 强制门禁 |
| 正确性 | `-Wall -Wextra -Werror` · `clang-tidy` · `cppcheck` | |
| **生命周期 / 所有权** | `clang-tidy cppcoreguidelines-*` · `-Wdangling` · C++ 生命期分析 | **C++ 的核心指标**，非规模问题 |
| 未定义行为 | `-fsanitize=undefined,address` · MSan · TSan | 运行时证据（Q6） |
| 不安全转换 / 资源 | `cppcoreguidelines-pro-type-*` · `modernize-*` · `bugprone-*` | |
| 头文件依赖 | `include-what-you-use` · `clang-tidy llvm-include-order` | |
| 测试与覆盖率 | `ctest` · `llvm-cov` + `gcovr` | Q6 证据门槛 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
|---|---|---|
| 函数有效行 | `lizard --length {{config:code_quality.func_lines.blocked}}` | |
| 圈复杂度 | `lizard --CCN {{config:code_quality.cyclomatic_complexity.blocked}}` | |
| 嵌套深度 | `clang-tidy readability-function-size` 或 lizard 计数 | |
| 覆盖率 | `gcovr --fail-under={{config:code_quality.coverage.core_business}}` | |

- **模板 / 泛型代码**：其复杂度可能由问题本身决定（见 code-quality §0）→ **允许专业复杂度，但必须显式声明来源** ✓
- **规模类为观察**：不得拿 50 行 / CCN 15 去拆 C++ 的状态机、解析器或模板库 ✓

## 3. 命名白名单

- 默认：函数/变量 `snake_case`（或项目统一前缀）· 宏与常量 `UPPER_SNAKE` · 类型 `PascalCase`（项目约定优先）
- 白名单三类：① 第三方库 API 约定（POSIX / OpenSSL / STL 等）② 行业通用缩写 ③ 历史遗留文件内部一致性
- **接线**：`.clang-tidy` 的 `readability-identifier-naming` 按上述配置；**未接线则它只是一份注释** ✓

## 4. 可直接复制的配置样例

```text
.clang-format      基于 Google 或 LLVM 预设，只改缩进/列宽/命名，不逐条手写
.clang-tidy        Checks 单一来源；WarningsAsErrors 只对"确定性强"的检查组开启
cppcheck           --enable=warning,performance,portability --error-exitcode=1
构建                -Wall -Wextra -Werror（CI 全量；本地可降级但不得长期）
运行时证据          ASan + UBSan（CI 必跑）· TSan（并发路径）· valgrind（可选深度）
覆盖率              gcov/llvm-cov -> gcovr --fail-under=<核心业务线>
```

## 5. 已知缺陷集：**取自外部标准，不用自采样**

> 这是本附录最重要的一节：**不自己造缺陷样本**，直接用权威标准的规则编号当"已知缺陷集"。

| 编号来源 | 缺陷类 | 我们的工具承接 |
|---|---|---|
| CERT C++ MEM50-CPP | 释放后使用（UAF） | ASan · scan-build |
| CERT C++ MEM51-CPP | 资源未正确释放（RAII 缺失） | clang-tidy cppcoreguidelines-owning-memory |
| C++ Core Guidelines R.3 / R.5 | 裸指针所有权不清 / 未 RAII | cppcoreguidelines-* |
| C++ Core Guidelines F.26 / ES.60 | 资源获取未用 RAII | modernize-* |
| C++ Core Guidelines R.11 | `new` 后未 `delete` / 未用智能指针 | modernize-make-unique |
| CWE-476 | 空指针解引用 | scan-build |
| CWE-190 | 整数溢出 | UBSan |

> **用法同上**：这些编号**就是"已知缺陷集"**；先接工具，再用它们验证工具真能抓到，抓不到的登记为盲区 ✓
