# Provider 门禁：质量规范总表与接入契约

> 正本 config/providers.json（29 条档案）；本文由脚本从正本渲染，请勿手改。

## 一、唯一契约

每行一个 JSON：file / line / rule / severity(error|warning|info) / message
severity 映射：error -> [问题] 阻断 · warning -> [建议] 观察 · info -> [提示]
工具原生输出不是 JSONL 的，由项目侧薄适配器转换（建议 <=20 行，放项目 tools/，不进本包）。
这样 Core 永远不认识任何工具的原生格式，也就不会退化成第二套分析器。

## 二、怎么跑

    python scripts/provider_gate.py <源码根>
    python scripts/provider_gate.py <源码根> --only=c,cpp
    python scripts/provider_gate.py --list
    python scripts/provider_gate.py --selftest
退出码：0 全通过 · 1 有[问题] · 2 仅[待核] · 3 脚本 / 用法错误

## 三、档案总表（29 条）

| key | 类别 | 工具 | 外部标准（先验） | 已知缺陷集（标准来源） | 薄适配器 |
|---|---|---|---|---|---|
| c | language | cppcheck | SEI CERT C · MISRA C:2012 · ISO C | CERT ARR30-C · CERT MEM30-C · CERT INT30-C · CWE-252 | 需要 |
| cpp | language | clang-tidy | C++ Core Guidelines · SEI CERT C++ · MISRA C++:2023 · AUTOSAR C++14 | CERT MEM50-CPP · GSL R.3 · GSL F.26 · CWE-476 | 需要 |
| javascript | language | eslint | eslint:recommended · eslint-plugin-security · OWASP Node.js Cheat Sheet | detect-eval · detect-child-process · CWE-79 · CWE-1321 | 需要 |
| typescript | language | tsc | typescript-eslint strict-type-checked · TS handbook strict | no-unsafe-assignment · no-floating-promises · CWE-704 | 需要 |
| java | language | spotbugs | SpotBugs Bug Patterns · PMD · Google Java Style | NP_NULL_ON_SOME_PATH · OBL_UNSATISFIED_OBLIGATION · CWE-404 | 需要 |
| go | language | golangci-lint | Go 官方 Code Review Comments · staticcheck · govet | govet.lostcancel · errcheck · CWE-362 | 需要 |
| rust | language | cargo | Rust API Guidelines · Clippy lint groups · RustSec | clippy::unwrap_used · clippy::undocumented_unsafe_blocks · CWE-190 | 不需要 |
| html | asset | htmlhint | HTMLHint · W3C validator · axe (a11y) | a11y-img-alt · CWE-79 | 需要 |
| css | asset | stylelint | Stylelint 标准配置 | no-duplicate-selectors · CWE-79(内联样式) | 需要 |
| scss | asset | stylelint | Stylelint scss 配置 | @extend 滥用 | 需要 |
| xml | asset | xmllint | W3C XML 规范 | 格式非法 · XXE 风险 | 需要 |
| sql | asset | sqlfluff | sqlfluff 规则集 · OWASP SQL 注入防护 | CWE-89 · 全表扫描 · 空值三值逻辑 | 需要 |
| bash | asset | shellcheck | ShellCheck 规则集 · Google Shell Style | SC2086(未加引号) · SC2046 · 危险 rm | 需要 |
| powershell | asset | pwsh | PSScriptAnalyzer 规则集 | PSAvoidUsingInvokeExpression · PSUseDeclaredVarsMoreThanAssignments | 需要 |
| yaml | asset | yamllint | yamllint 默认规则 · actionlint(CI) | truthy · 重复键 · 缩进歧义 | 需要 |
| json | asset | python -m json.tool | RFC 8259 | 格式非法 · 重复键 | 需要 |
| toml | asset | taplo | TOML v1.0.0 | 格式非法 | 需要 |
| dockerfile | asset | hadolint | hadolint 规则集 · Docker 官方最佳实践 | DL3008(未固定版本) · DL3002(非 root) · 密钥硬编码 | 需要 |
| fortran | numeric | gfortran | ISO/IEC 1539 · gfortran -fcheck=all | 越界(-fcheck=bounds) · 未初始化 | 需要 |
| matlab | numeric | mlint | MathWorks Code Analyzer 规则 | 未预分配数组 · 索引从 1 开始 | 需要 |
| r | numeric | Rscript | lintr 规则集 · R 官方风格指南 | lintr.object_usage · 索引从 1 开始 · 因子与字符隐式转换 | 需要 |
| julia | numeric | julia | Julia 官方风格指南 · JET.jl · Aqua.jl | 类型不稳定(JET) · 索引从 1 开始 · 全局变量在热点路径 | 需要 |
| kotlin | pending | detekt | detekt 规则集 · ktlint | 按需补充 | 需要 |
| swift | pending | swiftlint | SwiftLint 规则集 · Swift API Design Guidelines | 按需补充 | 需要 |
| dart | pending | dart | Effective Dart · dart analyze | 按需补充 | 需要 |
| csharp | pending | dotnet | Roslyn 分析器 · Microsoft 设计准则 | 按需补充 | 需要 |
| php | pending | phpstan | PHPStan 规则 · PSR-12 | 按需补充 | 需要 |
| ruby | pending | rubocop | RuboCop 规则集 · Ruby 风格指南 | 按需补充 | 需要 |
| lua | pending | luacheck | luacheck 规则集 | 按需补充 | 需要 |

## 四、数值语言：准入两问的答复

| 语言 | ① 独特工程能力 | ② 我们如何识别其特征缺陷 |
|---|---|---|
| Fortran | 数组语义与列主序性能模型、大规模数值内核 | 越界 / 未初始化 / 精度与隐式类型转换（编译器与运行时检查可承接） |
| MATLAB | 矩阵与工具箱生态、向量化语义 | 未预分配 / 索引基 / 隐式扩展（Code Analyzer 可承接）；专有工具链 -> 未安装即待核 |
| R | 向量化与统计建模语义、公式接口 | 未使用对象 / 索引基 / 隐式强制转换（lintr 与 testthat 可承接） |
| Julia | 多重分派与 JIT 的类型稳定性模型 | 类型不稳定 / 索引基 / 全局变量（JET.jl 可承接） |

## 五、按需新增 —— 六步流程

- 1 收该语言 / 资产的已知缺陷（来自权威标准编号，不自采样）
- 2 选成熟工具（本包不实现解析器）
- 3 写薄适配器：工具原生输出 -> 统一 JSONL（<=20 行，放项目 tools/）
- 4 在 config/providers.json 增一条档案（probe 指向真工具，run 指向适配器命令）
- 5 用 provider_gate.py --selftest 与真实仓库各跑一次，确认能变红
- 6 抓不到的缺陷登记为盲区，不假装覆盖

需要某语言 / 资产时：在 config/providers.json 增一条档案（工具与标准已在本表备好），
再写项目侧薄适配器，即可直接跑 provider_gate.py —— 这就是流程接口。

## 六、当前状态（诚实口径）

- 工具未安装时一律 [待核]（不猜、不静默通过）
- 已自证的只有统一契约与判定路径（--selftest）
- 真接线完成判据：工具就绪 -> 跑出统一 JSONL -> 用标准缺陷集验证能变红
- 未达该判据前，不得声称该语言已受门禁保护
