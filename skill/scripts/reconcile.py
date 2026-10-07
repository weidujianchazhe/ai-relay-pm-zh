# -*- coding: utf-8 -*-
"""reconcile.py —— 三方一致性校验（快照 ↔ 记录 ↔ 索引）

用法：python reconcile.py <管理区>
何时跑：定期 / 怀疑账实不符时
依据：references/audit.md §3.3

设计要点：**每条声明要有第二读者**——单方说法一律不算数。
校验范围：快照 / 记录 / 索引三方互证 + 命名 + 指针 + 时间锚 + 容量口径。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    config, index_rows, iter_cards, iter_reports, note, ok, problem, read,
    resolve_under, run, summary, tbd,
)

def main():
    if len(sys.argv) < 2:
        print("用法：python reconcile.py <管理区>")
        return 3
    root = Path(sys.argv[1])

    print("== 1. 记录文件名合规（YYYY-MM-DD_主题_AI标识.md） ==")
    bad = [p.name for p in iter_reports(root)
           if not re.match(r"^\d{4}-\d{2}-\d{2}_.+_[A-Za-z\u4e00-\u9fff][\w\u4e00-\u9fff@-]*\.md$", p.name)]
    (ok if not bad else tbd)(
        "记录命名全部合规（%d 篇）" % len(iter_reports(root)) if not bad
        else "记录命名可疑（存量历史可豁免）：%s" % "、".join(bad[:5]))

    print("== 2. 任务卡指针有效性（卡「上次交接」→ 记录存在） ==")
    dangling = []
    for c in iter_cards(root):
        txt = read(c) or ""
        m = re.search(r"\*\*上次交接\*\*[：:]\s*(.+)", txt)
        if not m:
            continue
        val = m.group(1).strip()
        if val in ("—", "-", ""):
            continue
        for tok in re.split(r"[，,;；\s]+", val):
            if not tok or tok in ("—", "-"):
                continue
            tgt = resolve_under(root, tok)
            if tgt is not None and not tgt.exists():
                dangling.append("%s -> %s" % (c.name, tok))
    if dangling:
        for d in dangling:
            problem("卡指针悬空：%s" % d)
    else:
        ok("活跃任务卡指针全部有效（%d 张卡）" % len(iter_cards(root)))

    print("== 3. 索引指针有效性（索引「交接文件」→ 记录存在） ==")
    miss = 0
    for f, label in ((root / "INDEX.md", "热区"), (root / "archives" / "INDEX_archived.md", "冷区")):
        for cells, ln in index_rows(f):
            ptr = cells[5] if len(cells) > 5 else ""
            if ptr and ptr not in ("—", "-"):
                tgt = resolve_under(root, ptr)
                if tgt is not None and not tgt.exists():
                    problem("%s 索引指针悬空：%s -> %s" % (label, cells[0], ptr))
                    miss += 1
    if not miss:
        ok("索引指针无悬空")

    print("== 4. 时间锚（快照 ≥ 最新记录） ==")
    reps = iter_reports(root)
    st = root / "STATE.md"
    if reps and st.exists():
        newest = max(reps, key=lambda p: p.stat().st_mtime)
        (ok if st.stat().st_mtime >= newest.stat().st_mtime else note)(
            "快照时间不早于最新记录" if st.stat().st_mtime >= newest.stat().st_mtime
            else "快照早于最新记录 %s（辅证，非铁证）" % newest.name)
    else:
        tbd("记录或快照缺失，时间锚跳过")

    print("== 5. 容量口径（实例 MAP 优先） ==")
    for key, path, label, unit in (
        ("capacity.state_max_chars", st, "STATE", "字符"),
        ("capacity.index_hot_rows", root / "INDEX.md", "索引热区", "行"),
    ):
        if not path.exists():
            continue
        txt = read(path) or ""
        n = len(re.findall(r"(?m)^\|\s*[A-Z]{2}[0-9]{4,5}\s*\|", txt)) if unit == "行" else len(txt)
        cap = config(root, key)
        (ok if (cap is None or n <= cap) else problem)("%s %d %s（上限 %s）" % (label, n, unit, cap))

    print("== 6. 冷区累计数 vs 实测 ==")
    cold = root / "archives" / "INDEX_archived.md"
    if cold.exists():
        m = re.search(r"累计\s*(\d+)\s*行", read(cold) or "")
        actual = len(index_rows(cold))
        if m:
            claimed = int(m.group(1))
            (ok if claimed == actual else problem)(
                "冷区累计 %d == 实测 %d" % (claimed, actual) if claimed == actual
                else "冷区累计 %d ≠ 实测 %d（应写前重数，禁维护高频计数器）" % (claimed, actual))
        else:
            note("冷区未声明累计行数")
    return summary()

if __name__ == "__main__":
    sys.exit(run(main))
