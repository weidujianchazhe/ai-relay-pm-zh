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
MAP_TXT = ("# 夹具 · 项目地图（MAP）\n\n## 一、环境\n\n- 平台：win\n\n## 二、规则\n\n"
           "- INDEX 主文件行数：20\n- STATE 字数上限：15k\n- reports 归档阈值：20\n"
           "- 定期排查：关\n- 协作模式：light\n")
RECORD = ("# 夹具记录\n\n> 交接 #001\n\n## 本次需求\n\n- x\n\n## 本次涉及工程信息\n\n- x\n\n"
          "## 改动点\n\n- x\n\n## 验证结果\n\n- x\n\n## 数据影响\n\n- 本轮无设计级取舍、未核设计文档\n\n"
          "## 下一步\n\n- 无\n\n## 任务卡更新\n\n- 已更新\n")
CARD = ("# 卡\n\n- **编号**：EN0002\n- **状态**：[进行中]\n- **承接**：win-t\n"
        "- **进度锚点**：—\n- **上次交接**：reports\\2026-09-20_一_win-t.md\n"
        "- **已提炼**：—\n- **代码根路径**：—\n- **涉及**：—\n"
        "- **并发元数据**：owner=win-t；lease=—；claimed_at=—；expires_at=—；revision=0；"
        "NORMALIZED-SHA256=—；写入方式=atomic rename；冲突文件=—\n")


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


def _mut_del(path):
    path.unlink()


def _mut_edit(path, old, new):
    t = path.read_text(encoding="utf-8")
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


def _mk_spec_only(d):
    """只写详述、不写蓝图 —— 一份设计＝两件套，缺一份必须报红。"""
    (d / "designs" / "方案.md").write_text(
        "# 方案 设计卡\n\n- **状态**：草案\n- **拆分出的执行卡**：—\n", encoding="utf-8")


def _mk_long_blueprint(d):
    """蓝图里塞一段长散文 —— 详述被搬进蓝图，两份文件开始漂移。"""
    _mk_spec_only(d)
    (d / "designs" / "方案.blueprint.md").write_text(
        "# 方案 · 设计蓝图\n\n## 一、现状 → 目标（改什么）\n\n"
        + "这是一段本该写在详述里、却被搬进蓝图的散文。" * 12 + "\n",
        encoding="utf-8")


def _mk_long_file(d):
    """单文件有效行超拦截线（600）——文件级三档必须和函数级一样会红。"""
    (d / "src" / "mod.py").write_text("".join("x%d = %d\n" % (i, i) for i in range(620)), encoding="utf-8")


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
    p = subprocess.run([sys.executable, str(HERE / script), *args],
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
        ("code_metrics", "注入超拦截线的长文件（620 有效行）", "code_metrics.py", ["{r}/src", "--ws={r}"],
         _mk_long_file),
        ("code_metrics", "注入注释密度超限（3.0 条/函数）", "code_metrics.py", ["{r}/src", "--ws={r}"],
         _mk_comment_heavy),
        ("code_metrics", "注入超拦截线的长函数（120 行）", "code_metrics.py", ["{r}/src", "--ws={r}"],
         lambda d: (d / "src" / "mod.py").write_text(
             "def big():\n" + "".join("    x%d = %d\n" % (i, i) for i in range(120)) + "    return 0\n",
             encoding="utf-8")),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="门禁变异自检：注入故障，断言门禁必须变红")
    usage_exit(ap)
    ap.add_argument("--keep", action="store_true", help="保留临时夹具（排查用）")
    ap.add_argument("--only", default="", help="只跑匹配的用例（逗号分隔子串）")
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="gate_selftest_"))
    todo = cases()
    if a.only:
        want = [x.strip() for x in a.only.split(",") if x.strip()]
        todo = [c for c in todo if any(w in c[0] or w in c[1] for w in want)]

    print("=" * 58)
    print("门禁变异自检 · 逐门禁对射（gate_i 只在故障 f_i 下跑自己）")
    print("=" * 58)
    fails, ran = [], 0
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
            if rc == 0:
                fails.append("%s / %s：注入故障后**仍然退出 0** —— 门禁对这类故障是瞎的" % (gate, desc))
                print("  [未变红]   %-18s %s" % (gate, desc))
            else:
                print("  [已变红]   %-18s %s（exit=%d）" % (gate, desc, rc))
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
