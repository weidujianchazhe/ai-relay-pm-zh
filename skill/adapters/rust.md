# 落地附录 · Rust

> ⚠️ **本文件不属技能正文**，是 `references/code-quality.md` 的**按栈落地附录**——只回答「在 Rust 栈上用什么工具、配什么参数、接线在哪」。
> 正文条款以 `references/code-quality.md` 为准（下文一律简称「正文」）；文中 `{{config:...}}` 为占位符，落地时由 `config/defaults.yml` 的实值替换。

## 1. 工具映射

| 正文条款 | Rust 工具 | 说明 |
| --- | --- | --- |
| 规模三档 | clippy：`too_many_lines`（函数长度）/ `cognitive_complexity`（复杂度）/ `excessive_nesting`（嵌套） | 三个 lint **默认并非全部 deny**，须在 `Cargo.toml` 的 `[lints.clippy]` 显式 `deny` |
| 版面 | `cargo fmt`（rustfmt） | rustfmt 只管格式，**不承担任何规模口径** |
| 命名白名单 | rustc 的 `non_snake_case` / `non_camel_case_types` + `clippy::upper_case_acronyms` | 由 §4 样例落地，见 §3 |
| 异常红线 | clippy `unwrap_used` / `expect_used` / `panic` | 按 §3 分层宽松度在模块上放行并写原因；安全模块最严 |
| 依赖方向 | `cargo modules dependencies --acyclic` + workspace crate 切分 | `cargo-deny` 不承担分层方向，见 §5 |
| 覆盖率 | `cargo llvm-cov` | 分层阈值见 §5 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
| --- | --- | --- |
| 函数长度 | `clippy.toml` 的 `too-many-lines-threshold = {{config:code_quality.func_lines.blocked}}`，并在 `[lints.clippy]` 置 `too_many_lines = "deny"` | **口径警告**：clippy **不支持忽略空行与注释**，按物理行计——与正文 §1.1「有效代码行」不同源，须择一为准并写入适配说明 |
| 圈复杂度 | `cognitive-complexity-threshold = {{config:code_quality.cyclomatic_complexity.blocked}}`，`cognitive_complexity = "deny"` | **口径警告**：该 lint 属 restriction 类、**默认 allow**，且需对应的 clippy 版本；不可用时降级为「`too_many_lines` 拦截 + 人工评审」并登记为规范债务 |
| 嵌套深度 | `excessive-nesting-threshold = {{config:code_quality.nesting_depth.blocked}}`，`excessive_nesting = "deny"` | **口径警告**：该 lint 需较新 clippy，旧工具链上不产生读数——「退出码 0」不等于合格（正文 §1.4） |
| 文件长度 | 见下 | **本适配器不提供该门禁**：`scripts/code_metrics.py` **只度量 Python**，非 Python 栈一律 `[待核]`（它不会替你量）。**不要在表格里写「由 code_metrics 度量」**——那是兑现不了的承诺；需要行数门禁请用各栈成熟工具自行接线。 |
| 覆盖率 | `cargo llvm-cov` | 键取 `code_quality.coverage.core_business` / `util` |

- **只配拦截线**：上表全部落在 `blocked` 档；推荐线交静态分析平台与人工评审（正文 §1.2）。
- **可机检条款由 §4 样例落地**：规模三档、命名白名单、异常红线、依赖方向。
- **同指标单工具**：函数长度只由 `too_many_lines` 拦，复杂度只由 `cognitive_complexity` 拦，嵌套只由 `excessive_nesting` 拦，**不得叠加其它度量工具**。

## 3. 命名白名单（`namelist.properties` → Rust）

- 默认：类型/枚举/特质/变体 `UpperCamelCase`、函数与变量/模块 `snake_case`、常量与静态量 `UPPER_SNAKE`、生命周期短名 `'a`。
- 白名单三类：① 第三方与平台约定（`#[no_mangle]` 导出的 C ABI 名、crate 单复数惯例、FFI 侧原名）；② 行业通用缩写（`ID`/`URL`/`HTML`/`DTO`/`VO`——Rust 惯例是缩写首字母大写，如 `HttpUrl`，特例由 `upper_case_acronyms` 放行）；③ 历史遗留文件内部一致性。
- 禁止：拼音与英文混合、直接使用中文命名、完全不规范的缩写。
- **接线方式**：`non_snake_case` / `non_camel_case_types` 是 rustc 内建 lint、**默认 warn**，须提升为 deny（§4 的 `[lints.rust]`）；白名单条目用 `#[allow(...)]` 行内豁免，**登记项 = 名字 + 豁免原因**写入 `namelist.properties`。
- **注释语言**：**注释一律中文、标识符英文**（正文 §4）；rustfmt / clippy **不提供**注释语言检查，**不得**引入英文拼写类工具（如 `typos` 的英文词表）——中文注释对它是纯噪声。

## 4. 可直接复制的配置样例

`clippy.toml` 与 `Cargo.toml` 的 `[lints]` 段（需支持 lints 表与对应 lint 的工具链；`{{config:...}}` 落地时由 `config/defaults.yml` 注入，**不写死数值**）：

```toml
# clippy.toml —— 阈值是全局单值；注释一律中文
too-many-lines-threshold = {{config:code_quality.func_lines.blocked}}
cognitive-complexity-threshold = {{config:code_quality.cyclomatic_complexity.blocked}}
excessive-nesting-threshold = {{config:code_quality.nesting_depth.blocked}}
```

```toml
# Cargo.toml 追加段
[lints.rust]
non_snake_case = "deny"          # 命名白名单：rustc 内建，默认 warn，须提升
non_camel_case_types = "deny"

[lints.clippy]
too_many_lines = "deny"          # 函数长度：唯一承担者
cognitive_complexity = "deny"    # 圈复杂度：唯一承担者
excessive_nesting = "deny"       # 嵌套：唯一承担者
upper_case_acronyms = "deny"     # 缩写大小写一致性
unwrap_used = "deny"             # 异常红线；按 §3 分层宽松度在模块上 allow 并写原因
```

命令接线（CI 一行跑全）：

```bash
cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings && cargo test
```

## 5. 覆盖率与依赖方向

- **覆盖率**：`cargo llvm-cov --fail-under-lines {{config:code_quality.coverage.core_business}} -p core`（核心 crate），`-p utils` 取 `{{config:code_quality.coverage.util}}`；`ui` crate 走 E2E 不设线（正文 §7）。
  **口径警告**：`--fail-under-lines` 是**行覆盖**口径，与 JS/TS 的 `branches`、Go 的语句覆盖都不同源，跨栈比数字无意义。
- **依赖方向**：分层由 **workspace crate 切分**承载（如 `api` / `services` / `repositories` / `models` 四个 crate），方向靠 Cargo 依赖图天然单向；用 `cargo modules dependencies --acyclic` 检查是否成环，成环即非零退出（正文 §5 禁止循环依赖），传递依赖用 `cargo tree --edges normal` 查看。
- **`cargo-deny` 的边界**：它管**许可证 / 重复版本 / 安全公告 / 源**，**不判分层方向**——`bans` 是全局的，拦不住「低层引用高层」，分层必须落到 crate 切分与 `cargo-modules`，不得用它冒充。
- **读数可信**：CI 须上报扫描 crate 范围与是否启用 `--all-features`（正文 §1.4）；静默排除模块属禁止项。

---

**本文件不属技能正文**；正文见 `references/code-quality.md`。
