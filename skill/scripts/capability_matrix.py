# -*- coding: utf-8 -*-
"""capability_matrix.py —— 能力矩阵机检（Declared -> ... -> Verified）

用法：python capability_matrix.py [--root <源码根>] [--ws <管理区>] [--selftest]

**两个层次，不要混**：
  · **契约级（本矩阵主体）**：命令拿得到吗？命令指向的脚本/工具真的在吗？
      —— 专治"注册了 != 生效了"（探针注册却永不被调用、空转即通过）。
  · **结果级（人工/端到端验收）**：真跑一次，产出的是真数据还是 [待核]。
      例：cpp 的 INSPECT **契约级 OK**（走 code_metrics 探针），但**结果级是待核**（MAP 未声明探针）。

三种状态：OK（契约成立）· TBD（已知未接线/缺工具）· FAIL（违反契约，必须修）
编排级能力（AUDIT / VERIFY）**不在 ADAPTERS 里**，由 eng.py 的 main() 路由 -> 记为 CORE。
退出码：0 全符合 · 1 有不符合 · 2 仅待核 · 3 用法错误
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, summary, tbd  # noqa: E402
import eng  # noqa: E402

#: 编排级能力：由 eng.py main() 直接路由，不经 ADAPTERS
CORE_CAPS = ("AUDIT", "VERIFY")

#: 期望表（契约级）。改现状必须同时改这里——这就是"声明要对账"的落点。
EXPECT = {
    ("python", "INSPECT"): "OK", ("python", "BUILD"): "OK", ("python", "TEST"): "OK",
    ("c", "INSPECT"): "OK", ("c", "BUILD"): "TBD", ("c", "TEST"): "TBD",
    ("cpp", "INSPECT"): "OK", ("cpp", "BUILD"): "TBD", ("cpp", "TEST"): "TBD",
}


def probe(verb, lang, root):
    if verb in CORE_CAPS:
        return ("CORE", "由 eng.py main() 路由（不经 ADAPTERS）")
    fn = eng.ADAPTERS.get(lang)
    if fn is None:
        return ("TBD", "语言未注册适配器")
    try:
        cmd, desc = fn(verb, root, lang)
    except Exception as e:
        return ("FAIL", "适配器抛异常：%s" % e)
    if cmd is None:
        return ("TBD", "能力未实现（%s）" % (desc or "无说明"))
    if cmd[0] == "python":
        for x in cmd[1:]:
            if str(x).endswith(".py") and not Path(x).is_file():
                return ("FAIL", "命令指向的脚本不存在：%s" % x)
        return ("OK", desc)
    if eng.has_tool(cmd[0]):
        return ("OK", desc)
    return ("TBD", "工具 %s 不存在（%s）" % (cmd[0], desc))


def selftest():
    """能变红自检：把 INSPECT 改回空转，契约级必须从 OK 掉成 TBD。"""
    orig = eng.ADAPTERS.get("python")
    eng.ADAPTERS["python"] = lambda v, r, l: (None, "")
    st, _ = probe("INSPECT", "python", Path("."))
    eng.ADAPTERS["python"] = orig
    if st == "TBD":
        ok("自检：空转的 INSPECT 被识别为 TBD（与期望 OK 不符 -> 矩阵报红）")
    else:
        problem("自检失败：空转未被识别（state=%s）" % st)
    return summary()


def _mark(l, c, root):
    """单元格判定（自 main() 内层循环抽出，把嵌套 5 层降到 <=4）。

    返回 (标记, bad 增量)。判定语义与原实现逐行一致：整段搬移，未改写任何条件。
    """
    dd = 0
    st, why = probe(c, l, root)
    exp = EXPECT.get((l, c))
    if c in CORE_CAPS:
        mark = "CORE"
    elif exp is None:
        mark = "?"
        note("   未登记期望：(%s, %s) -> %s（请补 EXPECT）" % (l, c, st))
    elif exp != st:
        dd = 1
        mark = "FAIL"
        problem("   (%s, %s)：期望 %s，实际 %s —— %s" % (l, c, exp, st, why))
    else:
        mark = st
    return mark, dd


def main():
    if "--selftest" in sys.argv:
        return selftest()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0]).resolve() if args else Path.cwd()
    ws = root
    for a in sys.argv[1:]:
        if a.startswith("--ws="):
            ws = Path(a.split("=", 1)[1]).resolve()
    eng._WS = ws
    caps = list(eng.VERBS)
    langs = sorted(eng.ADAPTERS)
    print("== 能力矩阵 · 契约级（%s）==" % root)
    print("    " + "%-6s" % "" + " | ".join("%-8s" % c for c in caps))
    bad = 0
    for l in langs:
        cells = []
        for c in caps:
            mk, dd = _mark(l, c, root)
            bad += dd
            cells.append(mk)
        print("    " + "%-6s" % l + " | ".join("%-8s" % x for x in cells))
    print("-" * 60)
    print("   契约级：能力 %d x 语言 %d · 不符合 %d" % (len(caps), len(langs), bad))
    note("   结果级另算：cpp/c 的 INSPECT 契约 OK，但**结果级为待核**（MAP 未声明探针 -> 见 language-adapters.md §6）")
    note("   AUDIT / VERIFY 是编排级：由 eng.py main() 路由到 audit_all.py（不判语言）")
    if bad == 0:
        ok("矩阵全符合预期（TBD 是已知未接线，不是失败）")
    return summary()


if __name__ == "__main__":
    from _common import run  # noqa: E402
    sys.exit(run(main))