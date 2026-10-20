# NOPMD: 用例的变异意图与判据必须就地写明——用例名看不出它证明的是哪个故障形态，删掉注释即失去可复核性。
# -*- coding: utf-8 -*-
"""selftest_gates.py —— 门禁的变异自检（证明门禁真的会红）

用法：
    python selftest_gates.py [--keep] [--only check_index,reconcile]

为什么要有这个脚本：
    门禁退出码 0 只有在**门禁真的会因故障变红**时才说明问题。一个永远返回 0 的脚本
    和一条被删掉的检查，从输出上看不出区别。本脚本用**变异检验**把这件事变成可验证的：
    在临时副本里**注入一个已知故障**，跑对应门禁，**断言它必须变红**。

口径（三条，都是踩过的坑）：
    ① **逐门禁对射**：gate_i 只需在故障 f_i 下变红，就跑 gate_i 自己——
       全套一起跑是回归测试，不是变异检验，混在一起既慢又分不清是谁失效。
    ② **不手造边界样本**：故障按"确定性违规"程序化注入（删文件、截断行、改字段），
       不靠人凭感觉造——造得太温和就是假绿演示。
    ③ **不依赖真实工作区**：用临时夹具，秒级，可反复跑。

依据：references/audit.md §4（判定口径）· scripts/README.md（统一约定）
回本口径：一次「门禁已失效但没人发现」的漏检即已回本；本脚本秒级，可在每次改门禁后跑。
踩坑记录：
    · 断言的是**退出码非 0**，不是输出里有没有某句话——匹配文案会随改词而失效；
    · 夹具必须自建自删：**不得指向真实工作区**，否则自检本身就成了破坏源；
    · 每个用例都先跑一次**基线**：夹具不注入故障时必须为 0，否则用例本身无效。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import run, usage_exit  # noqa: E402  —— 统一入口包装（退出码 3 = 脚本自身错误）

HERE = Path(__file__).resolve().parent

INDEX_HEAD = "# 夹具 · 记录索引（INDEX）\n\n| 编号 | 日期 | 类型 | 主题 | AI | 交接文件 |\n|---|---|---|---|---|---|\n"
MAP_TXT = ((Path(__file__).resolve().parent / "templates" / "selftest_map_text.txt").read_text(encoding="utf-8"))
RECORD = ((Path(__file__).resolve().parent / "templates" / "selftest_record_text.txt").read_text(encoding="utf-8"))
CARD = ((Path(__file__).resolve().parent / "templates" / "selftest_card_text.txt").read_text(encoding="utf-8"))


def build_fixture(root: Path):
    for d in ("tasks", "reports", "archives/done", "scripts", "designs", "src"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "MAP.md").write_text(MAP_TXT, encoding="utf-8")
    (root / "STATE.md").write_text("# 夹具 · 当前状态（STATE）\n\n## 当前进展\n\n- 无\n", encoding="utf-8")
    (root / "INDEX.md").write_text(
        INDEX_HEAD + "| EN0001 | 2026-09-20 | [接力] | 一 | win-t | reports\\2026-09-20_一_win-t.md |\n",
        encoding="utf-8")
    # 冷区必须含同一行：热区编号在冷区找不到会直接报红，夹具基线就不干净
    (root / "archives" / "INDEX_archived.md").write_text(
        INDEX_HEAD + "| EN0001 | 2026-09-20 | [接力] | 一 | win-t | reports\\2026-09-20_一_win-t.md |\n",
        encoding="utf-8")
    (root / "REVIEWS.md").write_text("# 元数据通道\n\n", encoding="utf-8")
    (root / "SKILL.md").write_text("k\\n", encoding="utf-8")
    # 规范文档会把旧格式当**反例**写在代码里；门禁不得把它当数据（防自污染）。
    #  这份文件放在夹具里，基线必须照常全绿——若哪天扫描器不再剥代码块，这里会立刻变红。
    BT = chr(96)
    (root / "REFERENCES_EXAMPLE.md").write_text(
        "# 规范示例\n\n旧格式 " + BT + "#人检(owner=某人, next=某日)" + BT + " 是错的。\n\n" +
        BT * 3 + "\n#人检(slot=<角色槽>, by=<机器戳>)\n" + BT * 3 + "\n", encoding="utf-8")
    (root / "reports" / "2026-09-20_一_win-t.md").write_text(RECORD, encoding="utf-8")
    (root / "tasks" / "EN0002_卡.md").write_text(CARD, encoding="utf-8")
    (root / "src" / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    for p in HERE.glob("*.py"):
        shutil.copy2(p, root / "scripts" / p.name)
        _rd = HERE / "README.md"
        if _rd.is_file():
            shutil.copy2(_rd, root / "scripts" / "README.md")
            _td = HERE / "templates"
            if _td.is_dir():
                shutil.copytree(_td, root / "scripts" / "templates", dirs_exist_ok=True)
                _fd = HERE / "fixtures"
                if _fd.is_dir():
                    shutil.copytree(_fd, root / "scripts" / "fixtures", dirs_exist_ok=True)


def _mut_del(path):
    path.unlink()


def _mut_edit(path, old, new):
    t = path.read_text(encoding="utf-8")
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


def _mk_spec_only(d):
    """只写详述、不写蓝图 —— 一份设计＝两件套，缺一份必须报红。

    ★ 2026-10-16 **第二次外部审查修**：`validate_workspace` 现在以**身份字段**分界——
    无 `DESIGN-ID` 且无配套蓝图的 .md 按 `design.md §0.2` 当作**设计过程资产放行**；
    **例外**：板块目录里的 `design.md` 是约定固定名，**必为设计卡**（缺 ID 即报，不能以"过程资产"绕过）。
    因此本夹具必须**写上 `DESIGN-ID`**，才能真实代表「设计卡缺蓝图」这一故障形态。
    """
    (d / "designs" / "方案.md").write_text(
        "# 方案 设计卡\n\n- **状态**：草案\n- **DESIGN-ID**：DSN-20260101-CCCCCC\n"
        '- **拆分出的任务卡**：—\n', encoding="utf-8")


def _mk_long_blueprint(d):
    """蓝图里塞一段长散文 —— 详述被搬进蓝图，两份文件开始漂移。"""
    #  ★ 必须用**真实 HTML**（2026-10-16 外部审查发现）：蓝图载体自 v4.0.0 起是 .html，
    #  而 `_long_paragraphs` 对 HTML 有专门处理（剥 <style>/<script>/标签）。夹具若写成 Markdown 内容，
    #  就**绕过了那条路径** —— 「HTML 剥壳写坏了」也不会有人发现（假绿）。
    #  本夹具因此**双向盯**：① <style> 里的长 CSS **不得**被误报；② 人写的长散文**必须**被抓。
    _mk_spec_only(d)
    (d / "designs" / "方案.blueprint.html").write_text(
        #  ★ 用**显式 +** 拼接而非隐式拼接：AST 会把隐式相邻字面量**合并成一个 Constant**，
        #  那样 `correctness_rules` 的 G1（超长字符串片段）仍会命中（实测 288 字符阻断）。
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
        + "<style>body{font-family:PingFang SC,Microsoft YaHei,sans-serif;background:#F4F3EE;"
        + "color:#1A1B1C;line-height:1.7;padding:24px}</style>\n"
        + "</head><body>\n<h1>方案 · 设计蓝图</h1>\n<h2>一、现状 → 目标（改什么）</h2>\n"
        "<p>" + "这是一段本该写在详述里、却被搬进蓝图的散文。" * 12 + "</p>\n"
        "</body></html>\n",
        encoding="utf-8")


def _mk_id_mismatch(d):
    """两件套 DESIGN-ID 不一致 —— 详述与蓝图指向两个身份（同名蓝图保留旧 ID 被沿用的形态）。

    ★ 2026-10-16 **第二次外部审查修**：本夹具此前调用 `_mk_spec_only()` —— 那份详述**没有 DESIGN-ID、
    也不建蓝图**，于是该用例实际因「**缺蓝图**」变红，**完全没碰到 ID 一致性检查**（= 假负控：
    「用例变红」不等于「判据被触发」）。现改为：**建成对的两件套，且两侧 ID 不同**。
    """
    p = d / "designs"
    (p / "方案.md").write_text(
        "# 方案 设计卡\n\n- **状态**：草案\n- **DESIGN-ID**：DSN-20260101-AAAAAA\n"
        '- **拆分出的任务卡**：—\n', encoding="utf-8")
    (p / "方案.blueprint.html").write_text(
        "<!DOCTYPE html><html><head><style>body{margin:0}</style></head><body>\n"
        "<div>DESIGN-ID：DSN-20260101-BBBBBB</div></body></html>\n", encoding="utf-8")


def _mk_board_missing_bp(d):
    """板块目录里只有 design.md、缺 blueprint.html —— ② 的假绿形态（只扫根目录时完全不被校验）。"""
    p = d / "designs" / "模块A"
    p.mkdir(parents=True, exist_ok=True)
    (p / "design.md").write_text(
        "# 板块设计\n\n- **DESIGN-ID**：DSN-20260101-AAAAAA\n\n- **拆分出的任务卡**：—\n", encoding="utf-8")


def _mk_half_archive(d):
    """归档里只有详述、缺蓝图 —— 两件必须一起移；旧判据「.md 数奇偶」抓不到这种半份。"""
    p = d / "designs" / "archives"
    p.mkdir(parents=True, exist_ok=True)
    (p / "旧方案.md").write_text(
        "# 归档设计\n\n- **DESIGN-ID**：DSN-20260101-BBBBBB\n\n- **拆分出的任务卡**：—\n", encoding="utf-8")


def _mk_pair_no_id(d):
    """两件套但详述**缺 DESIGN-ID** —— 有蓝图说明它是设计卡，却拿不出身份字段。

    ★ 2026-10-16 第二次外部审查的 P1 假绿：旧判据只在**双方都提取到 ID** 时才比较，
    于是「一方没有 ID」静默通过。现以身份字段分界并双向检查，本夹具锁住该口径。
    """
    p = d / "designs"
    (p / "方案.md").write_text(
        "# 方案 设计卡\n\n- **状态**：草案\n- **拆分出的任务卡**：—\n", encoding="utf-8")
    (p / "方案.blueprint.html").write_text(
        "<!DOCTYPE html><html><head><style>body{margin:0}</style></head><body><h1>x</h1></body></html>\n",
        encoding="utf-8")


def _mk_long_file(d):
    """单文件有效行超拦截线（600）——文件级三档必须和函数级一样会红。"""
    (d / "src" / "mod.py").write_text("".join("x%d = %d\n" % (i, i) for i in range(620)), encoding="utf-8")


def _mk_index_incomplete(d):
    """夹具里的 scripts/README.md 只列 1 个脚本 —— §3 必须报「一览表缺登记」。

    为什么用这种写法：§3 查的是【包自身】的文件集合，无法靠改工作区夹具触发；
    因此由变异函数【就地写一份不完整的一览表】，再让 check_promises 用 --scripts-dir 指向夹具，
    这样既保持夹具隔离，又让 §3 进入自动回归。
    """
    (d / "scripts" / "README.md").write_text(
        "| 脚本 | 作用 | 何时跑 |\n|---|---|---|\n| `overview.py` | 一屏全貌 | 随时 |\n",
        encoding="utf-8")


def _mk_comment_heavy(d):
    """注释密度超上限（3 个函数各 3 条注释 = 3.0 条/函数 > 1.5）。"""
    body = "".join("def f%d():\n    # 一\n    # 二\n    # 三\n    return %d\n\n" % (i, i) for i in range(3))
    (d / "src" / "mod.py").write_text(body, encoding="utf-8")


def _mk_others_lease(d):
    """让 win-other 持有一张有效租约——此时别人归档该卡必须被拒。"""
    import sys as _s
    _s.path.insert(0, str(HERE))
    import lease as _lease
    card = d / "tasks" / "EN0002_卡.md"
    okk, why = _lease.claim(d, card, "win-other", 30)
    assert okk, why


def _run(script, *args):
    #  -B：自检跑的是包内脚本，不得在包里留下 .pyc（口径见 scripts/README.md；
    #      这不是"用有利环境替包打掩护"——gen_views §15 仍会把 __pycache__ 判为残留，本节的干净 = 运行一律加 -B）
    p = subprocess.run([sys.executable, "-B", str(HERE / script), *args],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=180, check=False)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def cases():
    r = "reports\\2026-09-20_一_win-t.md"
    return [
        ("validate_workspace", "删掉必需文件 INDEX.md", "validate_workspace.py", ["{r}"],
         lambda d: _mut_del(d / "INDEX.md")),
        ("validate_workspace", "卡片缺冻结字段（上次交接）", "validate_workspace.py", ["{r}"],
         lambda d: _mut_edit(d / "tasks" / "EN0002_卡.md", "- **上次交接**", "- **XX交接**")),
        ("check_closeout", "最新记录的块名被改坏", "check_closeout.py", ["{r}"],
         lambda d: _mut_edit(d / "reports" / "2026-09-20_一_win-t.md", "## 本次涉及工程信息", "## 涉及")),
        ("lang_gates", "多语言门禁开关开了却没痕迹（假账）", "lang_gates.py", ["{r}", "check"],
         lambda d: (d / "MAP.md").write_text(
             (d / "MAP.md").read_text(encoding="utf-8") + "- 多语言门禁：开\n", encoding="utf-8")),
        ("check_closeout", "记录里留着 [待填] 占位（预填未补齐）", "check_closeout.py", ["{r}"],
         lambda d: _mut_edit(d / "reports" / "2026-09-20_一_win-t.md", "## 下一步", "## 下一步\n\n- [待填]")),
        ("check_closeout", "记录缺 H1 标题", "check_closeout.py", ["{r}"],
         lambda d: _mut_edit(d / "reports" / "2026-09-20_一_win-t.md", "# 夹具记录", "夹具记录")),
        #  P0-1 的回归覆盖（最重要的修复必须有变异用例）：
        #  把索引行里的报告名换成别的 → 「索引未登记本次提交」必须让 check_closeout 变红。
        ("check_closeout", "索引未登记本次提交（P0-1 回归）", "check_closeout.py", ["{r}"],
         lambda d: _mut_edit(d / "INDEX.md", r, "reports\\别人.md")),
        ("check_index", "索引行被截断成 4 列", "check_index.py", ["{r}"],
         lambda d: _mut_edit(d / "INDEX.md",
                             "| EN0001 | 2026-09-20 | [接力] | 一 | win-t | " + r + " |",
                             "| EN0001 | 2026-09-20 | [接力] | 一 |")),
        ("check_index", "同分支编号回跳（大号在前、小号在后）", "check_index.py", ["{r}"],
         lambda d: (d / "INDEX.md").write_text(
             INDEX_HEAD + "| EN0005 | 2026-09-21 | [接力] | 甲 | win-t | " + r + " |\n"
             "| EN0002 | 2026-09-22 | [接力] | 乙 | win-t | " + r + " |\n", encoding="utf-8")),
        ("reconcile", "卡上次交接指向不存在的记录", "reconcile.py", ["{r}"],
         lambda d: _mut_edit(d / "tasks" / "EN0002_卡.md", r, "reports\\不存在.md")),
        ("reconcile", "索引交接文件指向不存在的记录", "reconcile.py", ["{r}"],
         lambda d: _mut_edit(d / "INDEX.md", r, "reports\\不存在.md")),
        ("closeout", "别人持有租约时归档该卡（并发强制）", "closeout.py",
         ["{r}", "card-archive", "EN0002_卡.md", "--ai", "win-intruder"], _mk_others_lease),
        ("validate_workspace", "设计缺配套蓝图（只写了详述）", "validate_workspace.py", ["{r}"],
         _mk_spec_only),
        ("validate_workspace", "蓝图里塞长段落（详述被搬进蓝图）", "validate_workspace.py", ["{r}"],
         _mk_long_blueprint),
        ("validate_workspace", "两件套 DESIGN-ID 不一致（详述↔蓝图指两个身份）", "validate_workspace.py", ["{r}"],
         _mk_id_mismatch),
        ("validate_workspace", "板块设计缺蓝图（designs/模块/design.md 无 blueprint.html）", "validate_workspace.py", ["{r}"],
         _mk_board_missing_bp),
        ("validate_workspace", "归档半份（只有详述、缺蓝图）", "validate_workspace.py", ["{r}"],
         _mk_half_archive),
        ("validate_workspace", "两件套但详述缺 DESIGN-ID（身份字段缺失）", "validate_workspace.py", ["{r}"],
         _mk_pair_no_id),
        # 【2026-10-02】规模类（长文件 / 长函数 / 嵌套 / CCN）已降为「观察」不再阻断，
        # 故不再作为"必须变红"的变异用例。此处改为验证**仍然阻断**的非规模类信号：
        # 注释密度超限 · 预警区未说明 · 豁免理由空话。
        ("code_metrics", "注入注释密度超限（3.0 条/函数）", "code_metrics.py", ["{r}/src", "--ws={r}"],
         _mk_comment_heavy),
        # §3（scripts/*.py 与一览表集合一致）：夹具隔离的变异 —— 见 _mk_index_incomplete 的说明
        ("check_promises", "一览表缺登记（夹具 README 少列脚本）", "check_promises.py",
         ["{r}", "--scripts-dir={r}/scripts"], _mk_index_incomplete),
        # 结构模式规则（Correctness 域）：注入 feedparser 那条真缺陷的形态
        # （循环前建空容器、循环体只 continue、循环后直接使用）——必须变红。
        ("correctness_rules", "注入循环漏收集（真缺陷形态）", "correctness_rules.py", ["{r}/src"],
         lambda d: (d / "src" / "mod.py").write_text(
             (Path(__file__).resolve().parent / "fixtures" / "selftest_fixture_src.txt").read_text(encoding="utf-8"),
             encoding="utf-8")),
        # 说明：规模类（长文件/长函数/嵌套/CCN）自 2026-10-02 起为「观察」不阻断，
        # 且其"豁免理由空话"检查一并跳过（观察项无需豁免）——故不再设"必须变红"用例。
        # code_metrics 仍能阻断的类别：注释密度超限未说明（上一用例）· 扫描覆盖不足 · 依赖方向。
        # 数学/数值域规则（M1/M4）：注入必须变红
        ("correctness_rules", "注入浮点判等（与 0.1 比较）", "correctness_rules.py", ["{r}/src"],
         lambda d: (d / "src" / "mod.py").write_text(
             "def f(x):\n"
             "    if x == 0.1:\n"
             "        return 1\n"
             "    return 0\n",
             encoding="utf-8")),
        # 2026-10-16 外部评审（Claude）：退出判定的作用域边界 —— 以下两个注入都必须变红。
        # 修前漏报（rc=0）：内层循环的 break、嵌套函数的 return 被误当成外层 while True 的退出。
        ("correctness_rules", "注入 嵌套 break（外层 while 仍无退出）", "correctness_rules.py", ["{r}/src"],
         lambda d: (d / "src" / "mod.py").write_text(
             (HERE / "fixtures" / "nested_break_src.txt").read_text(encoding="utf-8"),
             encoding="utf-8")),
        ("correctness_rules", "注入 嵌套函数 return 冒充退出", "correctness_rules.py", ["{r}/src"],
         lambda d: (d / "src" / "mod.py").write_text(
             (HERE / "fixtures" / "nested_def_return_src.txt").read_text(encoding="utf-8"),
             encoding="utf-8")),
        # 已知限制（不设"必须变红"用例）：句柄泄漏是【观察级】（rc=2），不是阻断。
        # 修后行为：不再被无关的 `with g` 掩盖，能定位到真正的 `f` —— 级别不变，故不进阻断用例。
        ("correctness_rules", "注入 while True 无 break", "correctness_rules.py", ["{r}/src"],
         lambda d: (d / "src" / "mod.py").write_text(
             "def f(tol):\n"
             "    while True:\n"
             "        tol = tol / 2\n",
             encoding="utf-8")),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="门禁变异自检：注入故障，断言门禁必须变红")
    usage_exit(ap)
    ap.add_argument("--keep", action="store_true", help="保留临时夹具（排查用）")
    ap.add_argument("--only", default="", help="只跑匹配的用例（逗号分隔子串）")
    a = ap.parse_args()

    #  否则 `--only 拼错` 会在退出前**留下一个临时夹具目录**（实测残留 gate_selftest_*）。
    todo = cases()
    if a.only:
        want = [x.strip() for x in a.only.split(",") if x.strip()]
        todo = [c for c in todo if any(w in c[0] or w in c[1] for w in want)]
        if not todo:
            print("[问题] --only 没有匹配到任何用例：%s" % a.only)
            print("       可用筛选词示例：validate_workspace / check_index / reconcile / 蓝图 / DESIGN-ID")
            return 1
    tmp = Path(tempfile.mkdtemp(prefix="gate_selftest_"))

    print("=" * 58)
    print("门禁变异自检 · 逐门禁对射（gate_i 只在故障 f_i 下跑自己）")
    print("=" * 58)
    fails, ran = [], 0

    # ── ★ 正控段（该绿必须绿）──────────────────────────────────────────
    #  为什么必须有：19 条变异用例**只证明「必须变红」**——若某条命令在**干净夹具上就 exit 3**，
    #  那不是「门禁变红」，而是「脚本坏了」，变异矩阵会把它**整体放行**。
    #  2026-10 实测过一次真 P0：index-add 在干净工作区对合法短号 ValueError -> exit 3 -> 19/19 全绿。
    #  同 references/self-gate-debt.md §5 ⑮「验证方向完整性」：只验红不验绿 = 方向不全。
    _r = "reports\\2026-09-20_一_win-t.md"
    pbase = tmp / "t00_posbase"
    pbase.mkdir(parents=True)
    build_fixture(pbase)
    prc, pout = _run("closeout.py", str(pbase), "index-add", "--id", "EN0007", "--type", "[接力]",
                     "--topic", "正控", "--record", _r, "--ai", "win-t")
    if prc == 0:
        print("  [正控通过] index-add 在干净工作区 exit 0 —— 该绿确实会绿 ✓")
    else:
        _msg = "正控 / index-add 成功路径：应为 0 实为 %d —— 这不是门禁变红，是命令坏了，而变异矩阵对它是瞎的" % prc
        fails.append(_msg)
        print("  [正控失败] index-add exit=%d（应为 0）" % prc)
        for _ln in pout.splitlines()[-6:]:
            print("      " + _ln.strip())

    # ★ 正控第二面：**判据还灵不灵**（不是「命令能不能跑」）──────────────────
    #  夹具预置 EN0050（大号）→ 登记更小的 EN0001 → **必须被「同分支未递增」拒绝（非 0）**。
    #  为什么必须有：2026-10 的 closeout.py:183 缺陷正是「端点跑通、判据空转」——
    #  上面那条正控只跑干净工作区（索引空 → 递增循环不执行 → 根本碰不到该判据）。
    pbase2 = tmp / "t00_posbase2"
    pbase2.mkdir(parents=True)
    build_fixture(pbase2)
    (pbase2 / "INDEX.md").write_text(
        INDEX_HEAD + "| EN0050 | 2026-09-20 | [接力] | 一 | win-t | reports\\2026-09-20_一_win-t.md |\n",
        encoding="utf-8")
    (pbase2 / "archives" / "INDEX_archived.md").write_text(
        INDEX_HEAD + "| EN0050 | 2026-09-20 | [接力] | 一 | win-t | reports\\2026-09-20_一_win-t.md |\n",
        encoding="utf-8")
    irc, iout = _run("closeout.py", str(pbase2), "index-add", "--id", "EN0001", "--type", "[接力]",
                     "--topic", "正控2", "--record", _r, "--ai", "win-t")
    if irc != 0:
        print("  [正控通过] 已有 EN0050 时登记 EN0001 → 被拒（exit %d）—— 递增判据仍在生效 ✓" % irc)
    else:
        _msg2 = "正控2 / 同分支递增判据：已有 EN0050 时登记 EN0001 应被拒，实为 exit 0 —— 判据空转（静默失效）"
        fails.append(_msg2)
        print("  [正控2失败] 判据空转：EN0001 被接受了")
        for _ln in iout.splitlines()[-6:]:
            print("      " + _ln.strip())

    # ★ 正控第三面：**card-update 成功路径**（该绿必须绿）─────────────────
    #  为什么必须有：card-update 是 2026-10-16 新增端点（补 workflow §3.1/§3.2/§4 的「写回卡」缺口）。
    #  若它在干净卡上就 exit 3（例如字段定位写错），变异矩阵对「端点根本不可用」是瞎的——同 index-add 那次的教训。
    pbase3 = tmp / "t00_posbase3"
    pbase3.mkdir(parents=True)
    build_fixture(pbase3)
    _card3 = pbase3 / "tasks" / "EN0002_卡.md"
    urc, uout = _run("closeout.py", str(pbase3), "card-update", "EN0002_卡.md",
                     "--ai", "win-t", "--field", "状态", "--value", "已阻塞")
    _txt3 = _card3.read_text(encoding="utf-8") if _card3.exists() else ""
    if urc == 0 and "- **状态**：已阻塞" in _txt3:
        print("  [正控通过] card-update 干净卡改「状态」exit 0 且值已落盘 —— 写回通道可用 ✓")
    else:
        _msg3 = "正控3 / card-update 成功路径：应为 0 且字段落盘，实为 exit %d、字段命中 %s —— 端点不可用，变异矩阵对它瞎" % (
            urc, "- **状态**：已阻塞" in _txt3)
        fails.append(_msg3)
        print("  [正控3失败] card-update exit=%d（应为 0）" % urc)
        for _ln in uout.splitlines()[-6:]:
            print("      " + _ln.strip())

    # ★ 正控第四面：**漂移态不得被洗白**（该红必须红）──────────────────────
    #  为什么必须有：2026-10-15 实测的缺陷——越界手改卡触发漂移后，release 无条件重算哈希把改动洗白；
    #  card-update 若不查漂移同理会把脏内容固化成新哈希。这里同时钉住两个端点的漂移前置检查。
    pbase4 = tmp / "t00_posbase4"
    pbase4.mkdir(parents=True)
    build_fixture(pbase4)
    _card4 = pbase4 / "tasks" / "EN0002_卡.md"
    _run("closeout.py", str(pbase4), "claim", "EN0002_卡.md", "--ai", "win-t")   # 建租约（刷新哈希，此刻干净）
    _mut_edit(_card4, "- **进度锚点**：—", "- **进度锚点**：越界手改")            # 绕过脚本手改 → 制造漂移
    _st4 = _card4.read_text(encoding="utf-8")
    crc, _cout = _run("closeout.py", str(pbase4), "card-update", "EN0002_卡.md", "--ai", "win-t",
                      "--field", "已提炼", "--value", "x")
    rrc, _rout = _run("closeout.py", str(pbase4), "release", "EN0002_卡.md", "--ai", "win-t")
    #  判据：两个端点都必须**非 0**（漂移被拦）；且手改内容不得被刷新成「干净哈希」而消失
    if crc != 0 and rrc != 0:
        print("  [正控通过] 漂移态 card-update(exit %d) 与 release(exit %d) 均被拒 —— 越界改动不被洗白 ✓" % (crc, rrc))
    else:
        _msg4 = "正控4 / 漂移前置：card-update 应非0实为%d，release 应非0实为%d —— 有一者把越界改动洗白了" % (crc, rrc)
        fails.append(_msg4)
        print("  [正控4失败] card-update=%d release=%d（均应非 0）" % (crc, rrc))
        for _ln in (_cout + _rout).splitlines()[-6:]:
            print("      " + _ln.strip())
    #  release --accept-drift 必须放行（显式认领是人的判断，不能被误拦）
    arc, _aout = _run("closeout.py", str(pbase4), "release", "EN0002_卡.md", "--ai", "win-t", "--accept-drift")
    if arc == 0:
        print("  [正控通过] release --accept-drift 在漂移态放行（exit 0）—— 显式认领通道未被误拦 ✓")
    else:
        fails.append("正控4b / --accept-drift：应放行(0)实为 %d —— 显式认领通道被误拦" % arc)
        print("  [正控4b失败] release --accept-drift exit=%d（应为 0）" % arc)

    # ★ 正控第六面：**SKELETON 是设计骨架、不是设计卡**（该绿必须绿）──────────────
    #  为什么必须有：旧校验器把 designs/ 下所有 .md 当设计卡，于是 `SKELETON.md`
    #  （design.md §0.4：项目当前工程模型）被要求配套 SKELETON.blueprint.html 与「拆分出的任务卡」
    #  —— **任何建了骨架的项目都会被误报**（2026-10-16 外部审查 P1 假红）。
    pbase5 = tmp / "t00_posbase5"
    pbase5.mkdir(parents=True)
    build_fixture(pbase5)
    (pbase5 / "designs" / "SKELETON.md").write_text("# 骨架\n", encoding="utf-8")
    (pbase5 / "designs" / "SKELETON.html").write_text(
        "<!DOCTYPE html><html><head><style>body{font-family:sans-serif}</style></head>\n"
        "<body><h1>骨架</h1></body></html>\n", encoding="utf-8")
    src_s, sout = _run("validate_workspace.py", str(pbase5))
    if src_s == 0:
        print("  [正控通过] SKELETON.md+.html 在场 exit 0 —— 骨架未被误当设计卡 ✓")
    else:
        fails.append("正控5 / SKELETON 不被误当设计卡：应为 0 实为 %d —— 骨架被当成了设计卡（假红）" % src_s)
        print("  [正控5失败] SKELETON 在场却 exit=%d" % src_s)
        for _ln in sout.splitlines()[-6:]:
            print("      " + _ln.strip())

    # ★ 正控第七面：**设计过程资产必须放行**（该绿必须绿）──────────────────────
    #  为什么必须有：`design.md §0.2` 明写 `designs/` 根可放**设计过程资产**（中间/局部方案、论证材料），
    #  它们不是设计卡、天然没有蓝图和「拆分出的任务卡」。旧校验器把除 SKELETON 外每个 .md 都当设计卡 ⇒ 假红。
    pbase6 = tmp / "t00_posbase6"
    pbase6.mkdir(parents=True)
    build_fixture(pbase6)
    (pbase6 / "designs" / "research-notes.md").write_text(
        "# 调研笔记\n\n- 方案 A 的取舍\n- 待验证的假设\n", encoding="utf-8")
    arc, aout = _run("validate_workspace.py", str(pbase6))
    if arc == 0:
        print("  [正控通过] 过程资产 research-notes.md 在场 exit 0 —— 未被误当设计卡 ✓")
    else:
        fails.append("正控6 / 过程资产放行：应为 0 实为 %d —— 过程笔记被当成设计卡（假红）" % arc)
        print("  [正控6失败] 过程资产被误报 exit=%d" % arc)
        for _ln in aout.splitlines()[-6:]:
            print("      " + _ln.strip())

    # ★ 正控第七面：crash_matrix 的 --help 守卫（该绿必须绿）──────────────────────
    #  为什么必须有：2026-10 实测缺陷——`--help` 曾直接启动破坏性崩溃测试，AI 遇到异常输出反复重试会形成执行循环。
    #  守卫删掉后，`--help` 会落到「不接受任何参数」分支（返回 3）；判据即：--help 必须 0 且不进矩阵。
    _hc = subprocess.run([sys.executable, "-B", str(HERE / "crash_matrix.py"), "--help"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, check=False)
    _hout = _hc.stdout.decode("utf-8", "replace")
    _uc = subprocess.run([sys.executable, "-B", str(HERE / "crash_matrix.py"), "--bogus"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, check=False)
    _uout = _uc.stdout.decode("utf-8", "replace")
    if _hc.returncode == 0 and "== 崩溃注入矩阵" not in _hout and "不接受任何参数" not in _hout \
            and _uc.returncode != 0 and "== 崩溃注入矩阵" not in _uout:
        print("  [正控通过] crash_matrix --help exit 0 且未启动破坏性测试；未知参数被拒 ✓")
    else:
        fails.append("正控7 / crash_matrix 守卫：--help 应 exit 0 且不进矩阵（实为 %d），未知参数应被拒且不进矩阵（实为 %d）—— 「想查用法」会启动破坏性测试"
                     % (_hc.returncode, _uc.returncode))
        print("  [正控7失败] crash_matrix --help exit=%d · --bogus exit=%d" % (_hc.returncode, _uc.returncode))

    # ★ 正控第八面：句柄泄漏观察项不被无关 with 掩盖（该观察必须出现）──────────────
    #  为什么必须有：2026-10 修前的漏报——只要函数里有任意 `with open()`，所有未关闭的 open() 都被豁免。
    #  夹具：f 未关闭，同函数另有 with open(os.devnull)。判据：泄漏观察项必须报出 f。
    pbase7 = tmp / "t00_posbase7"
    pbase7.mkdir(parents=True)
    build_fixture(pbase7)
    (pbase7 / "src" / "mod.py").write_text(
        (HERE / "fixtures" / "open_leak_masked_src.txt").read_text(encoding="utf-8"), encoding="utf-8")
    hrc, hout7 = _run("correctness_rules.py", str(pbase7 / "src"))
    if "「f」= open(...)" in hout7 and "句柄可能泄漏" in hout7:
        print("  [正控通过] 未关闭的 f 即使与无关 with 同处也被报出（观察级，rc=%d）—— 豁免不再全局生效 ✓" % hrc)
    else:
        fails.append("正控8 / 句柄泄漏观察：未关闭的 f 应被报出，实为 rc=%d 且未命中 —— 被无关 with 掩盖（全局豁免回潮）" % hrc)
        print("  [正控8失败] 句柄泄漏未被报出（rc=%d）" % hrc)
        for _ln in hout7.splitlines()[-6:]:
            print("      " + _ln.strip())

    # ★ 正控第九面：new-record 并发创建同名记录，必须恰好一个成功（该绿必须绿）──────
    #  为什么必须有：2026-10 实测竞态——修前 16 进程并发时多个进程都报「已生成」、目录里只剩 1 个文件（静默覆盖丢写）。
    #  顺序执行的「同名被拒」证明不了并发安全；判据必须是并发：成功数 == 1 且文件数 == 1。
    pbase8 = tmp / "t00_posbase8"
    pbase8.mkdir(parents=True)
    build_fixture(pbase8)
    _procs = [subprocess.Popen([sys.executable, "-B", str(HERE / "closeout.py"), str(pbase8), "new-record",
                                "并发同名", "--ai", "win-t", "--date", "2026-10-20", "--no-prefill"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
              for _ in range(16)]
    _rcs = [_p.wait(timeout=180) for _p in _procs]
    _ok = sum(1 for _r in _rcs if _r == 0)
    _files = sorted((pbase8 / "reports").glob("2026-10-20_并发同名_win-t.md"))
    if _ok == 1 and len(_files) == 1:
        print("  [正控通过] 16 进程并发建同名记录：恰好 1 个成功、1 个文件 —— 并发创建不丢写 ✓")
    else:
        fails.append("正控9 / new-record 并发：应恰好 1 个成功且 1 个文件，实为成功 %d、文件 %d —— 并发覆盖（静默丢写）" % (_ok, len(_files)))
        print("  [正控9失败] 并发成功 %d · 文件 %d（应为 1 与 1）" % (_ok, len(_files)))

    for gate, desc, script, extra, mutate in todo:
        ran += 1
        try:
            base = tmp / ("t%02d_base" % ran)
            base.mkdir(parents=True)
            build_fixture(base)
            base_rc, _ = _run(script, *[x.replace("{r}", str(base)) for x in extra])
            if base_rc != 0:
                fails.append("%s / %s：**基线非 0**（%d）——用例本身无效" % (gate, desc, base_rc))
                print("  [基线非 0] %-18s %s（base=%d）" % (gate, desc, base_rc))
                continue

            fx = tmp / ("t%02d" % ran)
            fx.mkdir(parents=True)
            build_fixture(fx)
            mutate(fx)
            rc, _ = _run(script, *[x.replace("{r}", str(fx)) for x in extra])
            #  判据收紧：**只认门禁抓到问题**（1 阻断 / 2 仅待核）。
            #  rc=3 是脚本/用法错误——把脚本跑崩了不等于门禁有效，不能拿来当自证。
            if rc == 0:
                fails.append("%s / %s：注入故障后**仍然退出 0** —— 门禁对这类故障是瞎的" % (gate, desc))
                print("  [未变红]   %-18s %s" % (gate, desc))
            elif rc == 3:
                fails.append("%s / %s：注入故障后退出 **3（脚本/用法错误）**——这是把脚本跑崩了，"
                             "不是门禁抓到问题，不算自证" % (gate, desc))
                print("  [退出3]    %-18s %s（崩溃不算自证）" % (gate, desc))
            elif rc == 2:
                #  旧写法 `else: 已变红` 会把 2 当"门禁抓到了"——于是「把 problem 降级成 tbd」
                #  这种**抑制阻断而不失自检**的动作永远发现不了（与 1 的区别正是本包注册的退出码四值）。
                #  判据收紧：**只认阻断码 1**；2 单列报告并判自检失败。
                fails.append("%s / %s：注入故障后退出 **2（仅待核，不阻断）**——不是阻断码 1；"
                             "把 problem 降级成 tbd 不得算「门禁抓到了」" % (gate, desc))
                print("  [仅待核]   %-18s %s（exit=2 · 不算变红）" % (gate, desc))
            elif rc == 1:
                print("  [已变红]   %-18s %s（exit=1 阻断）" % (gate, desc))
            else:
                fails.append("%s / %s：退出码 %d 不属于约定四值（0/1/2/3）——判据失效，请查夹具" % (gate, desc, rc))
                print("  [异常码]   %-18s %s（exit=%d 不在 0/1/2/3）" % (gate, desc, rc))
        except Exception as e:
            fails.append("%s / %s：自检自身异常 %s" % (gate, desc, e))
            print("  [自检异常] %-18s %s（%s）" % (gate, desc, e))

    print("-" * 58)
    print("用例 %d · 通过 %d · 失败 %d" % (ran, ran - len(fails), len(fails)))
    for f in fails:
        print("[问题] " + f)
    if a.keep:
        print("夹具保留在：%s" % tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run(main))
