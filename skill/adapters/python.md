# 落地附录 · Python

> **状态：未实现（仅说明）** —— 本文件是适配说明，不是已实现能力；语言准入判据与晋升门槛见 references/language-adapters.md 12 与 references/language-quality-adaptation-plan.md。

> ⚠️ **本文件不属技能正文**，是 `references/code-quality.md` 的**按栈落地附录**——只回答「在 Python 栈上用什么工具、配什么参数、接线在哪」。
> 正文条款以 `references/code-quality.md` 为准（下文一律简称「正文」）；文中 `{{config:...}}` 为占位符，落地时由 `config/defaults.yml` 的实值替换。

## 1. 工具映射

| 正文条款 | Python 工具 | 说明 |
| --- | --- | --- |
| 规模三档 | lizard（函数长度 + 圈复杂度）、pylint R1702（嵌套） | Python 分支只需启用这两项专用检查 |
| 命名与风格 | ruff check + ruff format | ruff 强制门禁，全库 format 一次性对齐 |
| 类型 | mypy（渐进：core/llm/config 先行，ui 暂缓） | 阶段门禁 |
| 测试 | pytest（核心管线三条：context_manager / config manager / paths） | 阶段门禁 |
| 覆盖率 | coverage（或 pytest-cov） | `coverage report --fail-under=…` |
| 豁免闸门 | awk 正则步骤（见 §4） | 机器只拦形式；语义真伪走季度回查 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
| --- | --- | --- |
| 函数长度 | `lizard --length {{config:code_quality.func_lines.blocked}}` | Python 侧没有函数长度 lint 规则，沿用通用 lizard 步骤 |
| 圈复杂度 | `lizard --CCN {{config:code_quality.cyclomatic_complexity.blocked}}` | 同上 |
| 嵌套深度 | `pylint --max-nested-blocks={{config:code_quality.nesting_depth.blocked}} --disable=all --enable=R1702` | 只启用嵌套一项，其余交 ruff |
| 覆盖率 | `coverage report --fail-under={{config:code_quality.coverage.core_business}}` | 核心业务线；阶段门槛按实例配置覆写，不新增字段 |

- **推荐线不落工具**：lizard 与 pylint 都只配拦截线。
- **行数口径提醒**：`ruff` 的 `line-length` 是**字符宽度**（格式化用），**不是**函数行数口径，两者不可混用承担同一门禁；Python 侧的函数长度以 lizard `--length` 为准。
- **分工**：函数长度与圈复杂度由通用 lizard 步骤承担；Python 专用检查只补 R1702（嵌套）与覆盖率两项。

## 3. 命名白名单（`namelist.properties` 的思路 → Python）

- 默认：函数与变量 `snake_case`、类 `UpperCamelCase`、常量 `UPPER_SNAKE`（PEP8）。
- 白名单三类：① 第三方库与框架约定（如界面框架的信号/槽名沿用上游大小写）；② 行业通用缩写（`HTML`/`URL`/`ID`/`DTO`/`VO`/`DO`）；③ 历史遗留文件内部一致性。
- 禁止：拼音与英文混合、直接使用中文命名、完全不规范的缩写。
- **接线方式（必须在接入时补）**：`namelist.properties` 的「名字 = 豁免原因」格式作为登记表保留，同时在 ruff 配置中把对应名字写进 `lint.pep8-naming.ignore-names`（或按文件 `per-file-ignores`）。
  **注意**：`namelist.properties` **不会被任何工具自动加载**——不显式接线，它只是一份注释。

## 4. 可直接复制的配置样例

示例来源见 §4（字面值对应 `code_quality.nesting_depth.blocked` 与 `code_quality.coverage.core_business`，接入时按 config 替换）。

```yaml
      - name: Block on nesting depth (Python)
        if: contains(split(env.STACKS, ','), 'python')
        run: |
          pip install --quiet pylint
          pylint --max-nested-blocks=4 --disable=all --enable=R1702 "$SOURCE_DIR"

      - name: Coverage gate (Python)
        if: contains(split(env.STACKS, ','), 'python')
        run: |
          pip install --quiet coverage
          coverage report --fail-under=80
```

## 5. 本栈专属提醒

- **断言载体**：`assert` 在 `-O/-OO` 下被完全剥离——对外接口、数据层入口、权限与路径边界的前置校验必须显式 `raise`。
- **异常**：禁裸 `except:`；捕获必落日志（loguru）；界面层与库层禁 `print` 调试，命令行入口的功能性输出豁免须以显式路径登记。
- **依赖**：`requirements.txt` 全部 `==` 钉死版本，升级须在任务卡上写明原因。
- **界面框架（PySide6）**：耗时操作必须离开主线程；文件必 `with`；动态信号销毁时断连；交互须在响应预算内给出可见反馈。

---

**本文件不属技能正文**；正文见 `references/code-quality.md`。


## 附 0. 外部先验（权威来源，接入时须核对版本）

**Python**：PEP 8 / PEP 20（Zen）· PEP 484 / 561（类型标注）· Google Python Style Guide · ruff 规则集（源自 pycodestyle / pyflakes / pylint / bugbear / bandit）· mypy 严格度档 · pytest 官方文档

> 纪律（与 references/quality-baseline-design.md 一致）：
> ① 这些规范不是普适权威（大厂的风格指南是对其自身生态的约定）；
> ② 工具默认值不是我们的标准 —— 我们只借它们回答什么值得测，阈值仍由真实样本校准。

## 附 5. 已知缺陷集（取自标准，不含自采样）

> 不自己造缺陷样本；直接用权威标准的编号与规则名当已知缺陷集。
- CERT Python 编码标准（CWE 映射）
- Bandit B1xx：B301 pickle · B307 eval · B602 subprocess shell=True · B608 SQL 字符串拼接
- pyflakes：未使用变量 / 未定义名字
- ruff S 系（安全组）· CWE-89 注入 · CWE-78 命令注入 · CWE-502 不安全反序列化 · CWE-476 空指针
- Q6 证据：pytest 执行 + coverage fail-under

> 用法：按 Provider 机制接入工具后，用这些条目验证工具是否真能抓到；
> 抓不到的登记为盲区，不假装覆盖。
