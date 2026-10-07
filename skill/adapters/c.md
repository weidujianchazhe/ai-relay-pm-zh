# 落地附录 · C

> **状态：未实现（仅说明）** —— 本文件是适配说明，不是已实现能力；语言准入判据见 references/language-adapters.md §12。
> ⚠️ **本文件不属技能正文**，是 references/code-quality.md 的**按栈落地附录**：只回答「在 C 栈上用什么工具、配什么参数、接线在哪」。
> **外部依据全部来自公开标准与大厂实践，不来自本包自采样。**

## 0. 外部先验（权威来源，接入时须核对版本）

| 来源 | 提供什么 |
|---|---|
| **SEI CERT C Coding Standard** | 安全与缺陷规则集（**带编号，可直接当已知缺陷集**） |
| **MISRA C:2012（含 Amendment / Dir 4.x）** | 安全相关系统的高约束规则（汽车 / 工业 / 医疗） |
| **ISO/IEC 9899（C 标准）+ 实现 UB 清单** | 未定义行为的权威边界 |
| **Google C++ Style Guide**（C 相关部分） | 工程风格与危险构造限制 |
| **Clang / GCC 诊断与 Sanitizer 官方文档** | 可机检的正确性证据 |

## 1. 工具映射

| 正文条款 | C 工具 | 说明 |
|---|---|---|
| 规模三档 | `lizard`（原生支持 C）· `clang-tidy readability-function-size` | 沿用通用 lizard 步骤 |
| 圈复杂度 / 嵌套 | `lizard --CCN` · `clang-tidy readability-cognitive-complexity` | |
| 命名与风格 | `clang-format`（.clang-format） | 强制门禁 |
| 正确性 | `-Wall -Wextra -Werror` · `clang-tidy` · `cppcheck` | |
| 未定义行为 | `-fsanitize=undefined,address`（UBSan / ASan）· MSan · TSan | 运行时证据（Q6） |
| 内存与资源 | `clang static analyzer`（scan-build）· `valgrind` · `cppcheck --enable=all` | |
| 头文件依赖 | `include-what-you-use`（IWYU） | |
| 测试与覆盖率 | `ctest`（CMake）· `gcov` / `llvm-cov` + `gcovr` | Q6 证据门槛 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
|---|---|---|
| 函数有效行 | `lizard --length {{config:code_quality.func_lines.blocked}}` | C 无函数长度 lint，沿用通用步骤 |
| 圈复杂度 | `lizard --CCN {{config:code_quality.cyclomatic_complexity.blocked}}` | 同上 |
| 嵌套深度 | `clang-tidy readability-function-size` 或 lizard 嵌套计数 | |
| 覆盖率 | `gcovr --fail-under={{config:code_quality.coverage.core_business}}` | 核心业务线 |

- **规模类在本包为「观察」**（见 code-quality §1 动作分级）→ C 侧同样只作观察，**不阻断** ✓
- **不自己定数值**：先沿用通用出厂阈值；**只有真实项目数据证明"同一数字在 C 下判错了"**，才按语言覆盖（并在 version-boundaries 记录理由）✓

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
| CERT C MEM30-C | 释放后使用（UAF） | ASan · scan-build |
| CERT C MEM31-C | 双重释放 | ASan |
| CERT C ARR30-C | 数组越界 | ASan · UBSan |
| CERT C INT30-C | 无符号整数回绕 | UBSan · clang-tidy bugprone |
| CERT C EXP34-C | 空指针解引用 | UBSan · scan-build |
| CWE-252 | 未检查返回值 | clang-tidy bugprone-unused-return-value |
| CWE-476 | 空指针解引用 | scan-build |

> **用法**：这些编号**就是"已知缺陷集"**。按 Provider 机制接入工具后，
> 用它们验证**工具是否真能抓到**；抓不到的**登记为盲区**，不假装覆盖 ✓
