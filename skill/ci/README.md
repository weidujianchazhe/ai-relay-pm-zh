# CI 接线（`ci/`）

> **本目录不属技能正文**，只是把 `scripts/` 的门禁接到流水线上的样板。

## 1. 为什么能直接接

本包门禁是**确定性函数 + 退出码**，且**只依赖 Python 3 标准库**：无第三方、无编译、无网络。
所以接线只有一件事——**跑脚本，看退出码**。

```
0 = 全通过            → 放行
1 = 有[问题]          → **阻断**
2 = 仅[待核]          → 不阻断（表示"需要人看"，不是"确定有问题"）
3 = 脚本自身错误      → **阻断**（脚本坏了和检查失败一样不能放行）
```

## 2. 顺序：先证明门禁活着，再拿它判别人

```
① python scripts/selftest_gates.py        # 变异自检：注入故障，断言门禁必须变红
② python scripts/audit_all.py .           # 全盘核查：编排门禁 + 机器戳留痕 + 超期自查
③ python scripts/code_metrics.py <源码根> --ws=.   # 代码度量 + 依赖方向
```

**① 必须在 ② 之前。** 一个永远返回 0 的脚本，和一条被删掉的检查，从输出上看不出区别——
不先证明门禁会红，后面的绿就只是"没红过"，不是"查过了"。

## 3. 阈值从哪来（**不要在 CI 里再写一套**）

**工具只配拦截线**（`references/code-quality.md` §1.2）：阈值一律取自**实例 `MAP.md` 规则段**，
缺失才回落 `config/defaults.yml`。在 CI 文件里另写一套数值，立刻产生"文档一套、工具一套"的漂移。

分层与依赖例外同理，写在 **MAP 规则段**，不写在 CI 里：

```
- **分层**：ui > agent > core > llm > config > utils
- **依赖例外**：ui.main_window->ui.mw_parts
```

## 4. 非 Python 项目怎么接（接线板，不自研度量）

**口径**：**各栈用成熟工具，本包只提供接线样板与统一退出码约定**——
自研跨语言度量必然靠行 / 缩进启发式，**误报会掩盖真问题**，而误报正是门禁的首要失效原因。

| 栈 | 拦截线工具 | 接线样板 |
|---|---|---|
| Node / 前端 | ESLint（函数长度 / 嵌套 / 复杂度 / 文件长度）＋ 覆盖率工具 | `ci/github-actions-multilang.yml` 的 `node-gates` |
| Java | Checkstyle（FileLength / MethodLength / NestedIfDepth / CyclomaticComplexity）＋ JaCoCo | 同上 `java-gates` |
| Python | 本包 `scripts/code_metrics.py` | `ci/github-actions.yml` |

**三条纪律**：

1. **只配拦截线**：数值取自实例 MAP 规则段 / `config/defaults.yml`，**不写死在流水线文件里**；
2. **退出码即结论**：外部工具非零即阻断，**不要去看输出里有没有 error 字样**；
3. **口径冲突要择一**：例如 Checkstyle 按物理行算、本包按有效代码行算——
   接入时须择一为准并写进适配说明，**同一指标不得两套数值并存**（见 `adapters/java.md` §2）。

**接线是否真的接上了，可查**（这一步别省）：

```
# CI 汇总作业里加一步（样板见 github-actions-multilang.yml 的 lang-gates-evidence）
python scripts/lang_gates.py . record --results "node=0,python=0,java=1" --summary "各栈退出码"
```
- `record` 把**退出码 + 一行摘要**追加进元数据通道 `REVIEWS.md`——**不管各工具输出长什么样，这里只有一行**（这就是"统一输出契约"）；
- `check` 核这行痕迹：**开关开了却没有新鲜痕迹 → [问题]（假账）；痕迹里有非零 → [问题]（真红）**；
- 于是「样板给了、接没接不知道」变成**看得见**：MAP 写「多语言门禁：开」而 CI 没留痕，下次核查就会红。

> **为什么要有这一节**：包内机检只覆盖 Python。若不给接线样板，"非 Python 项目"就会以为这套规范与自己无关，
> 或者自己造一套弱于成熟工具的实现——**两种结果都比给一块接线板差**。

## 5. 接其他平台

| 平台 | 怎么接 |
|---|---|
| GitHub Actions | 直接用 `ci/github-actions.yml` |
| GitLab CI | `script:` 段里原样写上面三条命令；以退出码判成败 |
| Jenkins | 一个 freestyle job 加三步 shell；**勾选"失败即中断"** |
| pre-commit / husky | 把 `audit_all.py` 挂 `pre-push`（**不要挂 `pre-commit`**：它要跑全套，会把每次提交拖慢到被 `--no-verify` 绕过） |

> **挂在哪一步，取决于它有多贵。** 秒级的（变异自检）可挂提交前；跑全套的挂推送前或流水线。
> **会被绕过门禁比没有门禁更糟**——它制造虚假安全感。
