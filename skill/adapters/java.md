# 落地附录 · Java

> **状态：未实现（仅说明）** —— 本文件是适配说明，不是已实现能力；语言准入判据与晋升门槛见 references/language-adapters.md 12 与 references/language-quality-adaptation-plan.md。

> ⚠️ **本文件不属技能正文**，是 `references/code-quality.md` 的**按栈落地附录**——只回答「在 Java 栈上用什么工具、配什么参数、接线在哪」。
> 正文条款以 `references/code-quality.md` 为准（下文一律简称「正文」）；文中 `{{config:...}}` 为占位符，落地时由 `config/defaults.yml` 的实值替换。

## 1. 工具映射

| 正文条款 | Java 工具 | 说明 |
| --- | --- | --- |
| 规模三档 | checkstyle（函数长度 / 嵌套 / 文件长度）、lizard（通用步骤） | 示例配置两条路径并存，接入时按 §2 的「口径警告」二选一 |
| 圈复杂度 | checkstyle `CyclomaticComplexity` | |
| 静态分析平台 | SonarQube + PMD |；**推荐线交平台与人工评审** |
| 覆盖率 | JaCoCo（`mvn -B jacoco:check`） | 阈值写在项目 pom 的 `<rules>` 中 |
| 异常红线 | checkstyle `EmptyCatchBlock`、`Regexp`（禁 `printStackTrace`） | 示例配置已配置 |
| 命名白名单 | 示例配置无接线点 | 见 §3 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
| --- | --- | --- |
| 函数长度 | `MethodLength` max = `{{config:code_quality.func_lines.blocked}}` | **口径警告**：checkstyle 无 `skipComments`/`skipBlankLines` 开关，按物理行计，与正文 §1.1「有效代码行」不一致；**同一指标只允许一个工具承担拦截**，不要与 lizard 同时拦函数长度，否则注释写得越规范越容易「违规」 |
| 嵌套深度 | `NestedIfDepth` / `NestedForDepth` / `NestedTryDepth` max = `{{config:code_quality.nesting_depth.blocked}}` | 示例配置只覆盖 if/for/try 三类，while、switch 未覆盖，需要时自行补模块 |
| 圈复杂度 | `CyclomaticComplexity` max = `{{config:code_quality.cyclomatic_complexity.blocked}}` | |
| 文件长度 | `FileLength` max = `{{config:code_quality.file_lines.blocked}}` | **三处口径必须一次对齐**：① **数值**只取自本包 config；② **单位**——checkstyle 的 `FileLength` 按**物理行**计，而本包 本文件唯一口径是**有效代码行**（`code_quality.file_lines.unit`），二者不同源，接入时须择一为准并写入适配说明；③ **禁止两套数值并存**（本规范明令禁止的形态） |
| 覆盖率 | JaCoCo `jacoco:check` 的 `<rules>` 阈值 | 取 `code_quality.coverage.core_business` / `util`；示例配置流水线只有 `mvn -B jacoco:check` 一行，具体阈值在项目 pom 中配置 |

## 3. 命名白名单（`namelist.properties` → Java）

- 默认：类 `UpperCamelCase`、方法与变量 `lowerCamelCase`、常量全大写加下划线（；`namelist.properties` 的原生语境即 Java）。白名单三类：① 第三方与平台约定（Windows API 的 `DWORD`、`HANDLE` 等）；② 行业通用缩写（`HTML`/`URL`/`ID`/`DO`/`DTO`/`VO`）；③ 历史遗留文件内部一致性。禁止：拼音与英文混合、直接使用中文命名、完全不规范的缩写。
- **接线方式（必须在接入时补）**：`checkstyle.xml` 不含命名检查模块，`namelist.properties` 也不会被任何工具自动加载；接入时须补 `AbbreviationAsWordInName`（配 `allowedAbbreviations`）或静态分析平台的规则排除表，把「名字 = 豁免原因」的登记表变成真实约束。

## 4. 可直接复制的配置样例

可直接复制的样例。**数值一律用属性占位**——写死数值会立刻产生「文档一套、工具一套」的漂移。

```xml
<module name="Checker">
  <property name="severity" value="error"/>
  <!-- 数值不写死：checkstyle 支持 ${property} 从属性文件取值，
       将 code-config.properties 生成自本包 config/defaults.yml 即可单一来源。
       在此写死数值会与 config 口径冲突，形成两套数值（见 §2）。 -->
  <module name="FileLength">
    <property name="max" value="${code.file_lines.blocked}"/>
  </module>
  <module name="NestedIfDepth">         <!-- 嵌套（示例配置另配 NestedForDepth / NestedTryDepth 同值） -->
    <property name="max" value="${code.nesting_depth.blocked}"/>
  </module>
  <module name="CyclomaticComplexity">  <!-- 拦截线：圈复杂度 -->
    <property name="max" value="${code.cyclomatic_complexity.blocked}"/>
  </module>
  <module name="MethodLength">          <!-- 拦截线：函数长度 -->
    <property name="max" value="${code.func_lines.blocked}"/>
  </module>
  <module name="EmptyCatchBlock">       <!-- 空捕获白名单 -->
    <property name="exceptionVariableName" value="expected|ignore"/>
  </module>
  <module name="Regexp">                <!-- 禁 printStackTrace -->
    <property name="format" value="printStackTrace"/>
    <property name="illegalPattern" value="true"/>
  </module>
</module>
```

## 5. 本栈专属提醒

- **空捕获白名单**：`EmptyCatchBlock` 允许异常变量名为 `expected|ignore`——与 JS 侧 `no-unused-vars.caughtErrorsIgnorePattern` 是同源约定，跨栈保持一致。
- **异常与日志**：禁 `printStackTrace`，必须使用日志框架；核心业务层严格捕获并区分异常类型，顶层入口统一兜底并转友好提示，安全模块（认证/加密）逐行审查。


## 附 0. 外部先验（权威来源，接入时须核对版本）

**Java**：Google Java Style Guide · SpotBugs 官方 Bug Patterns 文档 · PMD 规则集 · Checkstyle · OWASP Dependency-Check 与 find-sec-bugs · Effective Java（条目）

> 纪律（与 references/quality-baseline-design.md 一致）：
> ① 这些规范不是普适权威（大厂的风格指南是对其自身生态的约定）；
> ② 工具默认值不是我们的标准 —— 我们只借它们回答什么值得测，阈值仍由真实样本校准。

## 附 5. 已知缺陷集（取自标准，不含自采样）

> 不自己造缺陷样本；直接用权威标准的编号与规则名当已知缺陷集。
- SpotBugs：NP_NULL_ON_SOME_PATH（空路径解引用）· RV_RETURN_VALUE_IGNORED · DLS_DEAD_LOCAL_STORE · OBL_UNSATISFIED_OBLIGATION（资源未关闭）
- PMD：EmptyCatchBlock · CloseResource · AvoidCatchingGenericException
- find-sec-bugs：SQL 注入 · 路径遍历 · 不安全反序列化
- CWE-476 · CWE-252 · CWE-404 · CWE-89
- Q6 证据：JUnit5 + JaCoCo fail-under · OWASP Dependency-Check（CVE）

> 用法：按 Provider 机制接入工具后，用这些条目验证工具是否真能抓到；
> 抓不到的登记为盲区，不假装覆盖。
