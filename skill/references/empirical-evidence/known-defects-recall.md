# 已知缺陷集与召回矩阵（机器生成）

> 由 scripts/known_defects.py --emit-md 生成，请勿手改。
> 目的：拿已知的真实缺陷与真实失误攻击门禁，把抓不到的登记为盲区。

## 一、召回矩阵

| 编号 | 语言 | 缺陷 | 检测器 | 期望 | 实测 | 结论 |
|---|---|---|---|---|---|---|
| KD-001 | python | 循环内漏收集（取了值没用） | correctness_rules.py（C1） | 变红 | 变红（阻断 1 条） | 覆盖 |
| KD-002 | python | 裸 except 吞异常 | correctness_rules.py（C2） | 变红 | 变红（阻断 1 条） | 覆盖 |
| KD-003 | python | 句柄未关闭 | correctness_rules.py（C3） | 观察（不阻断） | 检出（观察 1 条，按设计不阻断） | 覆盖 |
| KD-004 | - | 门禁检查被插到 return 之后（死代码） | selftest_gates.py（变异自检：假门禁无法变红） | 变红 | 已由历史实证抓到（2026-10-02） | 覆盖 |
| KD-005 | - | 新增文件未登记 MANIFEST | gen_views.py --check 第 12 节 | 变红 | 已由历史实证抓到（2026-10-02） | 覆盖 |
| KD-006 | - | 文档引用未创建的文件（断链） | gen_views.py --check 第 11 节 | 变红 | 已由历史实证抓到（2026-10-02） | 覆盖 |
| KD-007 | - | 术语回潮（旧名重新出现） | gen_views.py --check 第 13 节 | 变红 | 已由历史实证抓到（2026-10-02） | 覆盖 |
| KD-008 | - | 新规则首版 9/9 全是误报 | 人工精度抽检（不可自动化 -- 必须逐条看真假） | 人工发现 | 需人工（不可自动化） | 待人工 |
| KD-009 | python | 浮点判等（与 0.1 这类非整数比较） | correctness_rules.py（M1） | 变红 | 变红（阻断 1 条） | 覆盖 |
| KD-010 | python | 无退出条件的迭代（while True 无 break） | correctness_rules.py（M4） | 变红 | 变红（阻断 1 条） | 覆盖 |

## 二、盲区声明（由脚本输出，不靠人记）

| 质量维度 | 状态 | 说明 |
|---|---|---|
| 安全 · CWE-252 未检查返回值 | NOT COVERED | 需返回值检查规则；本包目前零覆盖 |
| 安全 · CWE-476 空指针解引用 | NOT COVERED | 需数据流/空值分析；本包目前零覆盖 |
| 安全 · CWE-390 吞掉异常 | COVERED | correctness_rules C2（裸 except 阻断 / 有类型仅 pass 观察） |
| 资源 · CWE-404 资源未释放 | COVERED | correctness_rules C3（观察，不阻断） |
| 业务正确性 | NOT COVERED | 需验收测试或规格验证；静态规则原理上无法覆盖 |
| 并发/竞态 | NOT COVERED | 需动态分析或压测 |
| 性能退化 | NOT COVERED | 需基准对比 |
| 架构质量 | PARTIAL | 仅有依赖方向与分层（code_metrics）；无架构审查 |
| 可维护性（规模） | OBSERVE | 规模指标降为观察（实测不预测缺陷） |
| 可维护性（结构模式） | COVERED | correctness_rules C1/C2 阻断、C3 观察 |
| 协议一致性（登记/引用/术语/门禁自证） | COVERED | gen_views 第 11-15 节 + selftest_gates |

## 三、语言适配接口（已定死，规则待补）

    CODE_CHECKERS = {'python': 'correctness_rules.py'}   # 已接线
    PENDING_LANGS = ('c', 'cpp', 'go', 'java', 'javascript', 'typescript', 'rust', 'kotlin', 'swift', 'dart', 'csharp', 'php', 'ruby', 'lua', 'fortran', 'matlab', 'r', 'julia')

新增一种语言只需两步：① 在 CODE_CHECKERS 加一行检查器映射；
② 在 DEFECTS 里加该语言的缺陷记录（lang 填语言名）。
在此之前，该语言的缺陷一律显示 待核-未接线 -- 与 code_metrics 的 PENDING 口径一致。

## 四、复跑

    python scripts/known_defects.py                  # 打印矩阵
    python scripts/known_defects.py --emit-md <路径>  # 重新生成本文件
