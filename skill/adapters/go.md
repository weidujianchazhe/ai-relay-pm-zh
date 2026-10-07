# 落地附录 · Go

> **状态：未实现（仅说明）** —— 本文件是适配说明，不是已实现能力；语言准入判据与晋升门槛见 references/language-adapters.md 12 与 references/language-quality-adaptation-plan.md。

> ⚠️ **本文件不属技能正文**，是 `references/code-quality.md` 的**按栈落地附录**——只回答「在 Go 栈上用什么工具、配什么参数、接线在哪」。
> 正文条款以 `references/code-quality.md` 为准（下文一律简称「正文」）；文中 `{{config:...}}` 为占位符，落地时由 `config/defaults.yml` 的实值替换。

## 1. 工具映射

| 正文条款 | Go 工具 | 说明 |
| --- | --- | --- |
| 规模三档 | golangci-lint：`funlen`（函数长度）/ `gocyclo`（圈复杂度）/ `nestif`（嵌套） | **默认未全开**：须在 `.golangci.yml` 用 `linters.enable` 显式启用，否则等于没配 |
| 文件长度 | 见下 | **本适配器不提供该门禁**：`scripts/code_metrics.py` **只度量 Python**，非 Python 栈一律 `[待核]`（它不会替你量）。**不要在表格里写「由 code_metrics 度量」**——那是兑现不了的承诺；需要行数门禁请用各栈成熟工具自行接线。 |
| 命名白名单 | `revive` 的 `var-naming` | 由 §4 样例落地，见 §3 |
| 异常红线 | `errcheck` + `revive` 的 `empty-block` | 由 §4 样例落地 |
| 依赖方向 | `depguard`（首选）或 `go list -deps` | 由 §4 样例落地，见 §5 |
| 覆盖率 | `go test -coverprofile` + `go-test-coverage` | 分层阈值见 §5 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
| --- | --- | --- |
| 函数长度 | `funlen.lines = {{config:code_quality.func_lines.blocked}}`，`ignore-comments: true` | **口径警告**：`funlen` 只能忽略注释行，**空行仍计入**——与正文 §1.1「去空行 + 去纯注释」不同源，须择一为准（保持 `ignore-comments: true`，把空行偏差写入适配说明） |
| 圈复杂度 | `gocyclo.min-complexity = {{config:code_quality.cyclomatic_complexity.blocked}}` | **同指标单工具**：不再启用 `cyclop` / `gocognit` 承担同一指标 |
| 嵌套深度 | `nestif.min-complexity = {{config:code_quality.nesting_depth.blocked}}` | **口径警告**：`nestif` 度量的是**嵌套 if 的复杂度**，不是纯嵌套层数，与 `nesting_depth.blocked` 不同源；须择一为准并写入适配说明 |
| 文件长度 | 无对应 linter | **口径警告**：`lll` 的 `line-length` 是**单行字符宽度**，与文件行数无关，**禁止用它承担 `file_lines`**；该指标在 Go 侧由各栈成熟工具自行接线（**本适配器不提供该门禁**）
| 覆盖率 | `go-test-coverage` 的 `.testcoverage.yml` | 键取 `code_quality.coverage.core_business` / `util` |

- **只配拦截线**：上表全部落在 `blocked` 档；推荐线交静态分析平台与人工评审（正文 §1.2）。
- **可机检条款由 §4 样例落地**：规模三档、命名白名单、异常红线、依赖方向。
- **`linters.enable` 必写全**：未显式启用的 linter 不产生任何读数，「退出码 0」只代表没看（正文 §1.4）。

## 3. 命名白名单（`namelist.properties` → Go）

- 默认：导出标识符 `UpperCamelCase`、未导出标识符 `lowerCamelCase`、常量同标识符规则（不用 `UPPER_SNAKE`）；包名全小写单数、无下划线。
- 白名单三类：① 第三方与平台约定（接口实现名、生成代码名）；② 行业通用缩写（`ID`/`URL`/`HTML`/`DTO`/`VO`，Go 侧要求**同词同大小写**：`userID`、`HTTPServer`）；③ 历史遗留文件内部一致性。
- 禁止：拼音与英文混合、直接使用中文命名、完全不规范的缩写。
- **接线方式**：`revive` 的 `var-naming` 已在 golangci-lint 内，**启用即生效**（内置常见缩写表）；本栈白名单的补录条目写入 revive 配置，`namelist.properties` 的「名字 = 豁免原因」与之逐条对应。
- **注释语言**：**注释一律中文、标识符英文**（正文 §4）；**不启用 `misspell`**——它是英文拼写检查，对中文注释只产生噪声；`godot`（注释以句号收尾）对中文同样适用，可按需启用。

## 4. 可直接复制的配置样例

`.golangci.yml`（字段名随主版本变化：v2 用 `linters.default: none`，v1 用 `disable-all: true`）。`{{config:...}}` 落地时由 `config/defaults.yml` 注入，**不写死数值**：

```yaml
# .golangci.yml —— 注释一律中文
linters:
  disable-all: true          # v2 写法：default: none
  enable:                    # golangci-lint 默认未全开，必须逐项列出
    - funlen                 # 函数长度（唯一承担者）
    - gocyclo                # 圈复杂度（唯一承担者）
    - nestif                 # 嵌套（唯一承担者）
    - depguard               # 依赖方向
    - revive                 # 命名与空分支
    - errcheck               # 异常红线
linters-settings:
  funlen:
    lines: {{config:code_quality.func_lines.blocked}}
    # 不设 statements：避免同一指标出现第二个阈值
    ignore-comments: true
  gocyclo:
    min-complexity: {{config:code_quality.cyclomatic_complexity.blocked}}
  nestif:
    min-complexity: {{config:code_quality.nesting_depth.blocked}}
  depguard:                  # 依赖方向：api → services → repositories → models（正文 §5）
    rules:
      api-no-repositories:
        deny:
          - pkg: "example.com/project/repositories"
            desc: "api 层不得直接引用 repositories 层"
      models-no-upward:
        deny:
          - pkg: "example.com/project/services"
            desc: "禁止反向依赖"
  revive:
    rules:
      - name: var-naming
      - name: empty-block
```

## 5. 覆盖率与依赖方向

- **覆盖率**：`go test -covermode=atomic -coverprofile=cover.out ./...` 产出 profile，再由 `go-test-coverage --config .testcoverage.yml` 按 `threshold.package` / `threshold.total` 设线（核心业务 `{{config:code_quality.coverage.core_business}}`、工具包 `{{config:code_quality.coverage.util}}`）。
  **口径警告**：Go 只有**语句覆盖率**，没有分支覆盖率，与 JS/TS 的 `branches` 不同源；跨栈比覆盖率数字无意义，只能同栈纵向比。
- **依赖方向**：首选 `depguard`（§4 已落地）——在配置里直接禁止「某包被某层引用」，违规即非零退出；需要看真实依赖图或排查循环依赖时用 `go list -deps ./...`，它输出**传递闭包**（含标准库与间接依赖），只作分析、不作门禁。
- **读数可信**：`golangci-lint run ./...` 接入 CI 时须上报扫描包范围（正文 §1.4）；静默排除目录属禁止项。

---

**本文件不属技能正文**；正文见 `references/code-quality.md`。


## 附 0. 外部先验（权威来源，接入时须核对版本）

**Go**：Go 官方 Code Review Comments · Effective Go · Google Go Style Guide · golangci-lint 规则集 · Go 官方 race detector 与 pprof 文档 · Uber Go Style Guide

> 纪律（与 references/quality-baseline-design.md 一致）：
> ① 这些规范不是普适权威（大厂的风格指南是对其自身生态的约定）；
> ② 工具默认值不是我们的标准 —— 我们只借它们回答什么值得测，阈值仍由真实样本校准。

## 附 5. 已知缺陷集（取自标准，不含自采样）

> 不自己造缺陷样本；直接用权威标准的编号与规则名当已知缺陷集。
- govet：printf 系列 · shadow · lostcancel（context 取消泄漏）· copylocks
- staticcheck SA 系列 · errcheck（未检查错误）· ineffassign（无效赋值）
- goroutine 泄漏（见 language-adapters 与多语言数据方案的风险矩阵）
- CWE-362 竞态（由 go test -race 承接）· 空指针解引用
- Q6 证据：go test -coverprofile fail-under · govulncheck（依赖漏洞）· pprof（性能）

> 用法：按 Provider 机制接入工具后，用这些条目验证工具是否真能抓到；
> 抓不到的登记为盲区，不假装覆盖。
