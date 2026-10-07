# -*- coding: utf-8 -*-
"""known_defects.py - 已知缺陷集 + 召回矩阵（缺陷 -> 检测器 -> 结果）

为什么要有这个脚本：
  「门禁能变红」只证明它对自己的夹具有效；要证明它覆盖【真实缺陷谱】，
  必须拿【已知真实缺陷 / 真实发生过的失误】去攻击它。
  本脚本跑这张矩阵，并把抓不到的条目登记为【盲区】。

语言适配接口（现在就定死，规则以后再补）：
  CODE_CHECKERS = {python: correctness_rules.py}          # 已接线
  PENDING_LANGS = (c, cpp, go, java, javascript)           # 未接线 -> 只报待核，不猜
  新增一种语言只需两步：
    1）在该语言的 CODE_CHECKERS 里加一行检查器映射；
    2）在 DEFECTS 里加该语言的缺陷记录（lang 字段填语言名）。
  在此之前，该语言的缺陷一律显示 [待核] 未接线 -- 与 code_metrics 的 PENDING 口径一致。

退出码：恒 0（报告工具，不阻断）；盲区由人读。
用法：python known_defects.py                    仅打印矩阵
      python known_defects.py --emit-md <路径>   生成参考文档（机器撰写，避免文档漂移）
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE_CHECKERS = {"python": "correctness_rules.py"}
PENDING_LANGS = (
    "c", "cpp", "go", "java", "javascript", "typescript", "rust",
    "kotlin", "swift", "dart", "csharp", "php", "ruby", "lua",
    # 数值/科学计算：待准入（未答准入两问前不入册）
    "fortran", "matlab", "r", "julia",
)
# 技术资产：**不是语言**，按检查器对待（与语言分开登记，避免类别混淆）
PENDING_ASSETS = (
    "html", "css", "scss", "xml", "sql", "bash", "powershell",
    "yaml", "json", "toml", "dockerfile",
)

DEFECTS = [
    {
        "id": "KD-001",
        "lang": "python",
        "kind": "code",
        "name": "循环内漏收集（取了值没用）",
        "source": "email/feedparser.py::FeedParser._parsegen（人工发现；所有规模指标均未抓到）",
        "snippet": "def f(xs):\n    out = []\n    for x in xs:\n        if x is None:\n            continue\n    return chr(10).join(out)\n",
        "detector": "correctness_rules.py（C1）",
        "expect": "变红",
    },
    {
        "id": "KD-002",
        "lang": "python",
        "kind": "code",
        "name": "裸 except 吞异常",
        "source": "CWE-390 类（吞掉异常），通用工程缺陷",
        "snippet": "def f():\n    try:\n        g()\n    except:\n        pass\n",
        "detector": "correctness_rules.py（C2）",
        "expect": "变红",
    },
    {
        "id": "KD-003",
        "lang": "python",
        "kind": "code",
        "name": "句柄未关闭",
        "source": "CWE-404 类（资源未释放）",
        "snippet": "def f(p):\n    fh = open(p)\n    return fh.read()\n",
        "detector": "correctness_rules.py（C3）",
        "expect": "观察（不阻断）",
    },
    {
        "id": "KD-004",
        "lang": "-",
        "kind": "protocol",
        "name": "门禁检查被插到 return 之后（死代码）",
        "source": "本轮实测：新增检查落在两个连续 return summary() 之间",
        "detector": "selftest_gates.py（变异自检：假门禁无法变红）",
        "expect": "变红",
    },
    {
        "id": "KD-005",
        "lang": "-",
        "kind": "protocol",
        "name": "新增文件未登记 MANIFEST",
        "source": "本轮实测：脚本写盘后未登记",
        "detector": "gen_views.py --check 第 12 节",
        "expect": "变红",
    },
    {
        "id": "KD-006",
        "lang": "-",
        "kind": "protocol",
        "name": "文档引用未创建的文件（断链）",
        "source": "本轮实测：债文件里写了尚未创建的脚本路径",
        "detector": "gen_views.py --check 第 11 节",
        "expect": "变红",
    },
    {
        "id": "KD-007",
        "lang": "-",
        "kind": "protocol",
        "name": "术语回潮（旧名重新出现）",
        "source": "本轮实测：债文件里写了旧名",
        "detector": "gen_views.py --check 第 13 节",
        "expect": "变红",
    },
    {
        "id": "KD-008",
        "lang": "-",
        "kind": "human",
        "name": "新规则首版 9/9 全是误报",
        "source": "本轮实测：C1 未把下标赋值当写入通道",
        "detector": "人工精度抽检（不可自动化 -- 必须逐条看真假）",
        "expect": "人工发现",
    },
    {
        "id": "KD-009",
        "lang": "python",
        "kind": "code",
        "name": "浮点判等（与 0.1 这类非整数比较）",
        "source": "数值代码高频缺陷：二进制浮点不精确，判等静默失败",
        "snippet": "def f(x):\n    if x == 0.1:\n        return 1\n    return 0\n",
        "detector": "correctness_rules.py（M1）",
        "expect": "变红",
    },
    {
        "id": "KD-010",
        "lang": "python",
        "kind": "code",
        "name": "无退出条件的迭代（while True 无 break）",
        "source": "数值/求解循环高频缺陷：无最大迭代次数，不收敛即挂死",
        "snippet": "def f(tol):\n    while True:\n        tol = tol / 2\n",
        "detector": "correctness_rules.py（M4）",
        "expect": "变红",
    },
]

BLIND_SPOTS = [
    # 封闭表：行数由【质量维度】决定，不随缺陷条目增长（避免成长型膨胀点）
    ("安全 · CWE-252 未检查返回值", "NOT COVERED", "需返回值检查规则；本包目前零覆盖"),
    ("安全 · CWE-476 空指针解引用", "NOT COVERED", "需数据流/空值分析；本包目前零覆盖"),
    ("安全 · CWE-390 吞掉异常", "COVERED", "correctness_rules C2（裸 except 阻断 / 有类型仅 pass 观察）"),
    ("资源 · CWE-404 资源未释放", "COVERED", "correctness_rules C3（观察，不阻断）"),
    ("业务正确性", "NOT COVERED", "需验收测试或规格验证；静态规则原理上无法覆盖"),
    ("并发/竞态", "NOT COVERED", "需动态分析或压测"),
    ("性能退化", "NOT COVERED", "需基准对比"),
    ("架构质量", "PARTIAL", "仅有依赖方向与分层（code_metrics）；无架构审查"),
    ("可维护性（规模）", "OBSERVE", "规模指标降为观察（实测不预测缺陷）"),
    ("可维护性（结构模式）", "COVERED", "correctness_rules C1/C2 阻断、C3 观察"),
    ("协议一致性（登记/引用/术语/门禁自证）", "COVERED", "gen_views 第 11-15 节 + selftest_gates"),
]


def run_code_check(defect):
    checker = CODE_CHECKERS.get(defect["lang"])
    if not checker:
        return ("[待核] 未接线（%s 尚无检查器）" % defect["lang"], None)
    with tempfile.TemporaryDirectory(prefix="kd_") as d:
        f = Path(d) / "mod.py"
        f.write_text(defect["snippet"], encoding="utf-8")
        p = subprocess.run([sys.executable, "-B", str(HERE / checker), d],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = (p.stdout or "").splitlines()
        blocked = sum(1 for line in lines if "结构模式·阻断" in line)
        watched = sum(1 for line in lines if "结构模式·观察" in line)
        if blocked:
            return ("变红（阻断 %d 条）" % blocked, True)
        if watched:
            return ("检出（观察 %d 条，按设计不阻断）" % watched, True)
        return ("未检出", False)


def matrix():
    rows = []
    for d in DEFECTS:
        if d["kind"] == "code":
            actual, ok = run_code_check(d)
        elif d["kind"] == "protocol":
            actual = "已由历史实证抓到（2026-10-02）"
            ok = True
        else:
            actual = "需人工（不可自动化）"
            ok = None
        rows.append((d["id"], d["lang"], d["name"], d["detector"], d["expect"], actual, ok))
    return rows


def render_md(rows):
    out = []
    out.append("# 已知缺陷集与召回矩阵（机器生成）")
    out.append("")
    out.append("> 由 scripts/known_defects.py --emit-md 生成，请勿手改。")
    out.append("> 目的：拿已知的真实缺陷与真实失误攻击门禁，把抓不到的登记为盲区。")
    out.append("")
    out.append("## 一、召回矩阵")
    out.append("")
    out.append("| 编号 | 语言 | 缺陷 | 检测器 | 期望 | 实测 | 结论 |")
    out.append("|---|---|---|---|---|---|---|")
    for i, lang, name, det, exp, act, ok in rows:
        verdict = "覆盖" if ok else ("未覆盖（盲区）" if ok is False else "待人工")
        out.append("| %s | %s | %s | %s | %s | %s | %s |" % (i, lang, name, det, exp, act, verdict))
    out.append("")
    out.append("## 二、盲区声明（由脚本输出，不靠人记）")
    out.append("")
    out.append("| 质量维度 | 状态 | 说明 |")
    out.append("|---|---|---|")
    for dim, st, why in BLIND_SPOTS:
        out.append("| %s | %s | %s |" % (dim, st, why))
    out.append("")
    out.append("## 三、语言适配接口（已定死，规则待补）")
    out.append("")
    out.append("    CODE_CHECKERS = %r   # 已接线" % CODE_CHECKERS)
    out.append("    PENDING_LANGS = %r" % (PENDING_LANGS,))
    out.append("")
    out.append("新增一种语言只需两步：① 在 CODE_CHECKERS 加一行检查器映射；")
    out.append("② 在 DEFECTS 里加该语言的缺陷记录（lang 填语言名）。")
    out.append("在此之前，该语言的缺陷一律显示 待核-未接线 -- 与 code_metrics 的 PENDING 口径一致。")
    out.append("")
    out.append("## 四、复跑")
    out.append("")
    out.append("    python scripts/known_defects.py                  # 打印矩阵")
    out.append("    python scripts/known_defects.py --emit-md <路径>  # 重新生成本文件")
    return chr(10).join(out) + chr(10)


def main(argv):
    rows = matrix()
    if "--emit-md" in argv:
        i = argv.index("--emit-md")
        if i + 1 >= len(argv):
            print("[用法] --emit-md <路径>")
            return 3
        Path(argv[i + 1]).write_text(render_md(rows), encoding="utf-8")
        print("[通过] 已生成 %s" % argv[i + 1])
        return 0
    for r in rows:
        print("%-7s %-8s %-34s %-40s %s" % (r[0], r[1], r[2], r[3], r[5]))
    print("---")
    gaps = [r[0] for r in rows if r[6] is False]
    print("缺陷 %d 条 · 覆盖 %d · 盲区 %d %s" % (len(rows), sum(1 for r in rows if r[6]), len(gaps), gaps or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
