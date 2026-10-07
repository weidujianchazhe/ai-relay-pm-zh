# 落地附录 · TypeScript

> **状态：未实现（仅说明）** —— 本文件是适配说明，不是已实现能力；语言准入判据与晋升门槛见 references/language-adapters.md 12 与 references/language-quality-adaptation-plan.md。

> ⚠️ **本文件不属技能正文**，是 `references/code-quality.md` 的**按栈落地附录**——只回答「在 TypeScript 栈上用什么工具、配什么参数、接线在哪」。
> 正文条款以 `references/code-quality.md` 为准（下文一律简称「正文」）；文中 `{{config:...}}` 为占位符，落地时由 `config/defaults.yml` 的实值替换。

## 1. 工具映射

| 正文条款 | TypeScript 工具 | 说明 |
| --- | --- | --- |
| 规模三档 | typescript-eslint（`@typescript-eslint/parser` + 规则） | 与 `javascript.md` 的分工：**TS 项目必须配 parser**，否则全部 TS 规则形同未开；纯 JS 项目仍走 `javascript.md` |
| 类型 | `tsc --noEmit` | 与 lint 是**两条独立门禁**，类型错误不由三档阈值承担 |
| 命名白名单 | `@typescript-eslint/naming-convention` | 由 §4 样例落地，见 §3 |
| 异常红线 | `no-empty`（`allowEmptyCatch: false`）+ `@typescript-eslint/no-unused-vars` 白名单 | 与 Java / JS 同源的 `expected\|ignore` 约定 |
| 依赖方向 | `import/no-restricted-paths` + `import/no-cycle`（或 dependency-cruiser） | 由 §4 样例落地，见 §5 |
| 覆盖率 | vitest / jest `--coverage` | 分层阈值见 §5 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
| --- | --- | --- |
| 函数长度 | `"max-lines-per-function": ["error", { "max": {{config:code_quality.func_lines.blocked}}, "skipBlankLines": true, "skipComments": true }]` | **`skipBlankLines` 与 `skipComments` 必须同时开**，才是正文 §1.1「有效代码行」；只开其一口径即不同源 |
| 嵌套深度 | `"max-depth": ["error", {{config:code_quality.nesting_depth.blocked}}]` | |
| 圈复杂度 | `"complexity": ["error", {{config:code_quality.cyclomatic_complexity.blocked}}]` | |
| 文件长度 | `"max-lines": ["error", { "max": {{config:code_quality.file_lines.blocked}}, "skipBlankLines": true, "skipComments": true }]` | **口径警告**：`max-lines` 只按整文件统计，**不区分源码与声明/生成物**——`.d.ts`、生成代码若不在 `ignorePatterns` 显式排除，读数不可信（正文 §1.4 禁止静默排除） |
| 覆盖率 | vitest `test.coverage.thresholds` / jest `coverageThreshold` | 取 `code_quality.coverage.core_business` / `util`；`ui` 层不设线 |

- **只配拦截线**：上表全部为 `error` 档；推荐线交静态分析平台与人工评审（正文 §1.2）。
- **可机检条款由 §4 样例落地**：规模三档、命名白名单、异常红线、依赖方向。
- **同指标单工具**：函数长度只由 `max-lines-per-function` 拦，文件长度只由 `max-lines` 拦，圈复杂度只由 `complexity` 拦；**不得在命令行重复传阈值**，否则形成两套数值。

## 3. 命名白名单（`namelist.properties` → TypeScript）

- 默认：变量与函数 `lowerCamelCase`、类/接口/类型别名/枚举 `UpperCamelCase`、常量 `UPPER_SNAKE`。与 `javascript.md` 同源，差异只在 TS 多出 `typeLike` 一类。
- 白名单三类：① 第三方与平台约定（框架注入名、`$` 类约定名）；② 行业通用缩写（`HTML`/`URL`/`ID`/`DTO`/`VO`）；③ 历史遗留文件内部一致性。
- 禁止：拼音与英文混合、直接使用中文命名、完全不规范的缩写。
- **接线方式**：按 selector 分列（`variable` / `function` / `typeLike` / `parameter` / `enumMember`），白名单条目落进 `filter: { regex, match: true }`（§4 已给样例）；`namelist.properties` 的「名字 = 豁免原因」须与 `filter` 逐条对应，否则只是一份注释。
- **注释语言**：本包口径为**注释一律中文、标识符英文**（正文 §4 三层制）；**禁止接入英文拼写检查类规则**（如 `cspell` / `eslint-plugin-spellcheck`）——中文注释在英文词表下全是噪声。

## 4. 可直接复制的配置样例

`.eslintrc.cjs`（TS 项目版本；`{{config:...}}` 落地时由 `config/defaults.yml` 注入，**不写死数值**）：

```js
// .eslintrc.cjs —— 注释一律中文
module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",              // 缺此字段，下述 TS 规则全部失效
  parserOptions: { project: true, tsconfigRootDir: __dirname, sourceType: "module" },
  plugins: ["@typescript-eslint", "import"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended-type-checked"],
  ignorePatterns: ["dist/**", "**/*.d.ts", "**/*.generated.ts"],  // 排除项显式声明（正文 §1.4）
  rules: {
    // 规模三档：只配拦截线
    "max-lines-per-function": ["error", { max: {{config:code_quality.func_lines.blocked}}, skipBlankLines: true, skipComments: true }],
    "max-depth": ["error", {{config:code_quality.nesting_depth.blocked}}],
    "complexity": ["error", {{config:code_quality.cyclomatic_complexity.blocked}}],
    "max-lines": ["error", { max: {{config:code_quality.file_lines.blocked}}, skipBlankLines: true, skipComments: true }],
    // 异常红线
    "no-empty": ["error", { allowEmptyCatch: false }],
    "@typescript-eslint/no-unused-vars": ["error", { caughtErrorsIgnorePattern: "^(expected|ignore)$" }],
    "no-console": ["warn", { allow: ["warn", "error"] }],
    // 命名白名单（缩写白名单用 filter 放行，登记表与之一一对应）
    "@typescript-eslint/naming-convention": [
      "error",
      { selector: "default", format: ["camelCase"], leadingUnderscore: "allow" },
      { selector: "typeLike", format: ["PascalCase"] },
      { selector: "variable", format: ["camelCase", "UPPER_CASE"] },
      { selector: "default", format: null, filter: { regex: "^(HTML|URL|ID|DTO|VO)$", match: true } }
    ],
    // 依赖方向（正文 §5）：api → services → repositories → models，禁止反向与跨层
    "import/no-restricted-paths": ["error", { zones: [
      { target: "./src/api", from: "./src/repositories", message: "api 层不得直接引用 repositories 层" },
      { target: "./src/repositories", from: "./src/services", message: "禁止反向依赖" }
    ] }],
    "import/no-cycle": "error"
  }
};
```

## 5. 覆盖率与依赖方向

- **类型门禁**：`npx tsc --noEmit`，与 lint 并列跑，失败同样阻断合并。
- **覆盖率**：vitest `--coverage`（或 jest `--coverage`），分层设线——核心业务 `{{config:code_quality.coverage.core_business}}`、工具类 `{{config:code_quality.coverage.util}}`、`ui` 层走 E2E 不设线（正文 §7）。阶段门槛按实例配置覆写同一键，**不新增覆盖率字段**。
- **依赖方向**：首选 eslint-plugin-import 的 `no-restricted-paths`（按层 zone 拦跨层与反向，§4 已落地）+ `no-cycle`（拦循环依赖）；需要依赖图可视化时用 dependency-cruiser（`depcruise --config .dependency-cruiser.cjs src`），其 `forbidden` + `no-circular` 与 §4 同义——**二者择一，不得同时拦同一条依赖边**。
- **口径警告**：依赖方向由**静态 import 图**判定；`require()` 拼接路径、运行时才成形的条件化 `import()` 不在图内，属人工评审项（正文 §6.1 第 3 类）。

---

**本文件不属技能正文**；正文见 `references/code-quality.md`。


## 附 0. 外部先验（权威来源，接入时须核对版本）

**TypeScript**：typescript-eslint（strict-type-checked 预设）· TS 官方 handbook 的 strict 家族 · Google TypeScript Style Guide · typescript-eslint 的 no-unsafe-* 规则族文档

> 纪律（与 references/quality-baseline-design.md 一致）：
> ① 这些规范不是普适权威（大厂的风格指南是对其自身生态的约定）；
> ② 工具默认值不是我们的标准 —— 我们只借它们回答什么值得测，阈值仍由真实样本校准。

## 附 5. 已知缺陷集（取自标准，不含自采样）

> 不自己造缺陷样本；直接用权威标准的编号与规则名当已知缺陷集。
- no-unsafe-assignment · no-unsafe-member-access · no-unsafe-call · no-unsafe-return（any 传播链）
- no-explicit-any · no-floating-promises · no-misused-promises · await-thenable
- strict 家族：noImplicitAny · strictNullChecks · exactOptionalPropertyTypes
- CWE-704 类型混淆 · 类型逃逸（断言与 any 滥用）
- Q6 证据：tsc --noEmit + Vitest / Jest 覆盖率 · ts-prune 查死代码

> 用法：按 Provider 机制接入工具后，用这些条目验证工具是否真能抓到；
> 抓不到的登记为盲区，不假装覆盖。
