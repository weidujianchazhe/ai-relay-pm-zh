# 落地附录 · JavaScript / TypeScript

> ⚠️ **本文件不属技能正文**，是 `references/code-quality.md` 的**按栈落地附录**——只回答「在 JS/TS 栈上用什么工具、配什么参数、接线在哪」。
> 正文条款以 `references/code-quality.md` 为准（下文一律简称「正文」）；文中 `{{config:...}}` 为占位符，落地时由 `config/defaults.yml` 的实值替换。

## 1. 工具映射

| 正文条款 | JS / TS 工具 | 说明 |
| --- | --- | --- |
| 规模三档 | eslint：`max-lines-per-function` / `max-depth` / `complexity` | 示例配置用一份 `.eslintrc` 承载三档中的拦截线 |
| 类型 | tsc | **注意**：示例未配置 TypeScript 解析器——接入 TS 项目必须先补 `@typescript-eslint/parser` |
| 测试 | jest | `env` 需声明 `jest: true` |
| 覆盖率 | `npm test -- --coverage` | 示例配置流水线写法 |
| 豁免闸门 | 与 Python / Java 共用的 awk 正则步骤 | 机器只拦形式；语义真伪走季度回查 |

## 2. 三档阈值 → 工具参数

| 指标 | 拦截线落点 | 备注 |
| --- | --- | --- |
| 函数长度 | `"max-lines-per-function": ["error", { "max": {{config:code_quality.func_lines.blocked}}, "skipBlankLines": true, "skipComments": true }]` | **`skipBlankLines`/`skipComments` 正是 06 §1.1「有效代码行」口径在工具上的落地**——示例配置三份工具配置里唯一显式实现该口径的一份 |
| 嵌套深度 | `"max-depth": ["error", {{config:code_quality.nesting_depth.blocked}}]` | |
| 圈复杂度 | `"complexity": ["error", {{config:code_quality.cyclomatic_complexity.blocked}}]` | |
| 文件的豁免 | `overrides` 中测试文件关闭 `max-lines-per-function` 与 `complexity` | 分层宽松度的既有实例：测试用例天然长且多分支 |

- **推荐线不落工具**。
- **禁止重复传参**：上述规则已按拦截线配为 `error`，**不得再在命令行重复传阈值**，否则形成两套数值（示例已按此原则只调用 `npx eslint`）。

## 3. 命名白名单（`namelist.properties` → JS / TS）

- 默认：变量与函数 `lowerCamelCase`、类与构造器 `UpperCamelCase`、常量 `UPPER_SNAKE`。白名单三类：① 第三方与平台约定（DOM/框架 API 的平台大小写、`$` 类约定名）；② 行业通用缩写（`HTML`/`URL`/`ID`/`DTO`/`VO`）；③ 历史遗留文件内部一致性。禁止：拼音与英文混合、直接使用中文命名、完全不规范的缩写。
- **接线方式（示例配置缺失，接入时必须补）**：示例只有 `new-cap`（构造器首字母大写）与 `no-var`/`prefer-const`，**没有任何命名风格规则**（如 `camelcase`/`id-match`），`namelist.properties` 也未被加载——接入时需自建接线点。

## 4. 可直接复制的配置样例

以下可整份复制。字面值对应 `code_quality.*`，接入时按 config 替换。

```jsonc
{
  "root": true,
  "env": { "browser": true, "es2022": true, "node": true, "jest": true },
  "parserOptions": { "ecmaVersion": 2022, "sourceType": "module" },
  "extends": ["eslint:recommended"],
  "rules": {
    // 数值取自本包 config（此处以内联值示意；接入时建议由脚本生成 .eslintrc，
    // 避免"文档一套、工具一套"——见正文 §1.2 的「工具只配拦截线」原则）
    "max-lines-per-function": ["error", { "max": {{config:code_quality.func_lines.blocked}}, "skipBlankLines": true, "skipComments": true }],
    "max-depth": ["error", {{config:code_quality.nesting_depth.blocked}}],
    "complexity": ["error", {{config:code_quality.cyclomatic_complexity.blocked}}],
    "no-empty": ["error", { "allowEmptyCatch": false }],
    "no-unused-vars": ["error", { "caughtErrors": "all", "caughtErrorsIgnorePattern": "^(expected|ignore)$" }],
    "no-unsafe-finally": "error",          // 示例配置写作 no-finally——**不是 ESLint 核心规则**，
                                           // 照抄会报 "Definition for rule 'no-finally' was not found"
    "no-console": ["warn", { "allow": ["warn", "error"] }],
    "new-cap": ["error", { "capIsNew": true }]
    // 另含：no-throw-literal / max-classes-per-file / no-nested-ternary / eqeqeq / no-var / prefer-const
  },
  "overrides": [
    { "files": ["tests/**/*.js", "**/*.test.js", "**/*.spec.js"],
      "rules": { "max-lines-per-function": "off", "complexity": "off" } }
  ]
}
```

## 5. 本栈专属提醒

- **有一处待核对项**：`no-finally` **不是 ESLint 核心规则**（核心对应规则是 `no-unsafe-finally`，只禁止在 `finally` 中改变控制流），照抄会报「Definition for rule 'no-finally' was not found」——**接入前须替换为 `no-unsafe-finally`**。
- **空捕获**：`no-empty` 配 `allowEmptyCatch: false`，配合 `no-unused-vars` 的 `caughtErrorsIgnorePattern` 白名单（`expected|ignore`）——与 Java `EmptyCatchBlock` 同源。
- **禁止裸打印调试**：`no-console` 仅告警且放行 `warn`/`error`，工具侧已留出日志通道；生产路径的打印仍按正文判定。
