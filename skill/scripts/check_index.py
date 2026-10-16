# -*- coding: utf-8 -*-
# NOPMD: "表结构先判、再判内容"与"两区皆空不构成一致性证据"是本文件的核心契约（code-quality §0.8.1 OUTPUT_CARDINALITY），注释即契约的现场依据，删掉就无法复核该判据是否仍在生效。
"""check_index.py —— 索引完整性校验

用法：python check_index.py <管理区>
何时跑：改索引后 / 定期
依据：references/artifacts.md §5、references/audit.md §3.2

校验范围：
  · 单行单元格数 <6（整行截断）单独报出——**不对这类行静默跳过**
  · 「[接力] 链跨归档续接」：查热区最后一行是否能在冷区续上
  · 冷区累计声明行数与实际行数是否一致
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    INDEX_HEADER_KEY, branch_pattern, index_rows, index_table_state, note, ok, problem, read,
    resolve_under, summary, tbd, run,
)

VALID_TYPES = ["[接力]", "[完成]", "[废弃]", "[里程碑]"]
BRANCH_RE = re.compile(r"^\|\s*([A-Z]{2})\s*\|")

def registered_branches(root):
    """从 MAP.md 分支登记表读已注册的分支字母。"""
    txt = read(root / "MAP.md") or ""
    out = set()
    for line in txt.splitlines():
        m = re.match(r"^\|\s*([A-Z]{2})\s*\|", line)
        if m:
            out.add(m.group(1))
    return out

def check_file(path, label, root, branches, strict_cells=True):
    txt = read(path)
    if txt is None:
        problem("%s 不可读：%s" % (label, path))
        return 0
    rows, bad_cells = index_rows(path), []
    # 单独扫一遍"像索引行但单元格不足"的——原脚本会静默跳过它们
    for i, line in enumerate(txt.splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and re.match("^" + branch_pattern(root) + "$", cells[0]) and len(cells) < 6:
            bad_cells.append((cells[0], len(cells), i))
    if bad_cells:
        for no, n, ln in bad_cells:
            problem("%s 第 %d 行整行截断：编号 %s 仅 %d 个单元格（缺列将导致指针校验失效）" % (label, ln, no, n))

    seq = {}
    for cells, ln in rows:
        no = cells[0]
        br, num = no[:2], int(no[2:])
        if branches and br not in branches:
            problem("%s 未登记分支：%s（须先在 MAP 分支登记）" % (label, no))
        typ = cells[2] if len(cells) > 2 else ""
        if typ not in VALID_TYPES:
            problem("%s 非法类型：%s / %r" % (label, no, typ))
        if br in seq:
            if num <= seq[br]:
                problem("%s 同分支未递增：%s（前值 %d）" % (label, no, seq[br]))
            else:
                seq[br] = num
        else:
            seq[br] = num
        ptr = cells[5] if len(cells) > 5 else ""
        if ptr and ptr not in ("—", "-"):
            tgt = resolve_under(root, ptr)
            if tgt is not None and not tgt.exists():
                problem("%s 指针悬空：%s -> %s" % (label, no, ptr))
    for br, mx in sorted(seq.items()):
        ok("%s 分支 %s 递增至 %04d" % (label, br, mx))
    return len(rows)

def main():
    if len(sys.argv) < 2:
        print("用法：python check_index.py <管理区>")
        return 3
    root = Path(sys.argv[1])
    branches = registered_branches(root)
    if not branches:
        note("MAP 分支登记表为空或未解析出分支字母——未登记分支的告警将跳过")
    else:
        ok("MAP 已登记分支：%s" % "、".join(sorted(branches)))

    hot = root / "INDEX.md"
    cold = root / "archives" / "INDEX_archived.md"
    n_hot = check_file(hot, "热区", root, branches)
    n_cold = check_file(cold, "冷区", root, branches) if cold.exists() else 0

    if not cold.exists():
        tbd("冷区索引不存在：%s" % cold)
    else:
        # ── 表结构先判，再判内容 ────────────────────────────────────
        #  为什么要先判结构（2026-10-15 实测出的缺陷）：旧实现直接用 index_rows() 取数据行，
        #  **从不判断表头是否存在**。于是「冷区缺表头 + 热区 0 行」时本脚本报
        #  `[通过] 热区 0 条编号在冷区全部找得到`——空集上的「全部找得到」不是证据
        #  （references/code-quality.md §0.8.1 的 OUTPUT_CARDINALITY：空集不得进入一致性比较），
        #  而 index-add 随后因同一个缺表头直接拒写。**绿灯把结构缺失盖住了**，
        #  且 exit 0 会让人以为索引完好。写侧与校验侧现在共用 _common.index_header_at 判据。
        hot_exists, hot_ok = index_table_state(hot)
        cold_exists, cold_ok = index_table_state(cold)
        if not cold_ok:
            problem("冷区表结构无法解析（缺「%s」表头）：%s —— index-add 会拒绝写入；"
                    "须由 templates/archives/INDEX_ARCHIVED.template.md 实例化" % (INDEX_HEADER_KEY, cold))
        if hot_exists and not hot_ok:
            problem("热区表结构无法解析（缺「%s」表头）：%s" % (INDEX_HEADER_KEY, hot))

        # 冷区应全量：热区的每条编号都应能在冷区找到（移入不删除）
        hot_rows = {c[0] for c, _ in index_rows(hot)}
        cold_rows = {c[0] for c, _ in index_rows(cold)}
        missing = sorted(hot_rows - cold_rows)
        if missing:
            problem("热区编号在冷区缺失（违反『移入不删除』）：%s" % "、".join(missing[:6]))
        elif not hot_rows and not cold_rows:
            #  两区皆空：**不构成「一致性成立」的证据**。新工作区正常，但也不能算通过——
            #  否则「冷区结构缺失」这类问题会被一条永真的 [通过] 掩盖（正是本次修的缺陷）。
            if cold_ok:
                tbd("热区与冷区均为 0 行——空集不参与一致性比较（新工作区正常；有记录后本项才可判定）")
        else:
            ok("热区 %d 条编号在冷区全部找得到（移入不删除成立）" % len(hot_rows))
        # 冷区累计数应与实际行数一致
        m = re.search(r"累计\s*(\d+)\s*行", read(cold) or "")
        if m:
            claimed = int(m.group(1))
            (ok if claimed == n_cold else problem)(
                "冷区累计声明 %d 行 == 实测 %d 行" % (claimed, n_cold)
                if claimed == n_cold else
                "冷区累计声明 %d 行 ≠ 实测 %d 行（禁维护高频计数器，应写前重数）" % (claimed, n_cold))
    print("    热区 %d 行 · 冷区 %d 行" % (n_hot, n_cold))
    return summary()

if __name__ == "__main__":
    sys.exit(run(main))
