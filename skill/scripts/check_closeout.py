# -*- coding: utf-8 -*-
"""check_closeout.py —— 提交流程门禁（closeout gate）

用法：python check_closeout.py <管理区>
何时跑：每次提交前（**失败即阻塞提交**）
依据：references/workflow.md §4、references/artifacts.md §4

三查口径：
  · 记录块名（6+1）· 索引行 · 快照时间锚
  · 声明归档任务卡的目标文件是否真实存在（按块内容解析，不看特定字样）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    config, index_rows, iter_cards, newest_handoff, note, ok, problem, read, resolve_under, run,
    summary, tbd,
)

BLOCKS = ["本次需求", "本次涉及工程信息", "改动点", "验证结果", "数据影响", "下一步", "任务卡更新"]

def main():
    if len(sys.argv) < 2:
        print("用法：python check_closeout.py <管理区>")
        return 3
    root = Path(sys.argv[1])
    if not root.is_dir():          #  #13：根不存在必须**明确报错**，不能落进"新工作区正常"
        problem("管理区不存在：%s" % root)
        return 3

    print("== 1. 最新记录 6+1 块齐全 ==")
    rep, no = newest_handoff(root)
    if rep is None:
        tbd("未找到任何交接记录（新工作区正常）")
        return summary()
    txt = read(rep) or ""
    lack = [b for b in BLOCKS if b not in txt]
    if lack:
        problem("最新记录 %s 缺块：%s" % (rep.name, "、".join(lack)))
    else:
        ok("最新记录 %s 的 6+1 块齐全（交接 #%d）" % (rep.name, no))

    print("== 1b. 占位是否补齐（预填≠查证） ==")
    # 为什么查这个：new-record 会预填机械字段、把语义字段留成 [待填]。
    # 若没人拦，预填就会变成"看起来很完整"的假账——**占位留在记录里 = 这份交接没写完**。
    left = txt.count("[待填]")
    if left:
        problem("最新记录仍有 %d 处 [待填] 占位——预填不等于查证，语义字段必须由人补齐" % left)
    else:
        ok("无 [待填] 占位")

    print("== 2. 交接号位置（须在 H1 之下第一行） ==")
    lines = [l for l in txt.splitlines() if l.strip()]
    h1 = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    if h1 is None:
        problem("记录缺 H1 标题")
    elif re.search(r"交接\s*#\d+", lines[h1 + 1] if h1 + 1 < len(lines) else ""):
        ok("交接号位于 H1 之下第一行")
    else:
        note("交接号不在 H1 之下第一行——若正文先引用了他人编号，门禁会取到错误编号")

    print("== 3. 声明的归档任务卡目标是否真的存在 ==")
    moved = re.findall(r"archives[\\/]done[\\/]([^\s；;，,|）)]+\.md)", txt)
    if not moved:
        note("本记录未声明归档任务卡")
    else:
        for name in sorted(set(moved)):
            p = root / "archives" / "done" / name
            (ok if p.exists() else problem)("声明归档任务卡存在：archives/done/%s" % name)

    print("== 4. 索引是否已登记本次提交 ==")
    #  判据必须真的能阻塞：若把命中的行算出来**从未使用**，随后无条件 `note` + 有行就 `ok`，
    #  那么「索引未登记」这条**永不阻塞**——门禁形同虚设。故本项做成**可判定的真检查**：
    #    判据＝本次报告里提到的编号，必须至少有一条出现在索引热区行里（判据已在真工作区验证不误报）。
    rows = index_rows(root / "INDEX.md")
    #  判据（两选一命中即算已登记）：① 索引行里出现**最新报告的文件名**（索引的最后一列就是报告路径）；
    #    ② 或出现该报告提到的任一形如 XX0000 的编号。**只要索引有可解析行却两样都命中不了 → 报问题。**
    ids = sorted({t for t in re.findall(r"\b[A-Z]{2}\d{4}\b", read(rep) or "")}) if rep else []
    joined = [" ".join(cells) for cells, _l in rows]
    by_file = [i for i, j in enumerate(joined) if rep and rep.name in j]
    by_id = [i for i, j in enumerate(joined) if any(t in j for t in ids)]
    if not rep:
        tbd("无交接记录可核 —— 本项无法判定（先写 reports/ 再提交）")
    elif by_file or by_id:
        ok("索引已登记本次提交（按报告名命中 %d 行 / 按编号命中 %d 行）" % (len(by_file), len(by_id)))
    elif rows:
        problem("索引热区 %d 行，但**没有任何一行**登记本次提交（既无报告名 %s，也无报告提到的编号）——未登索引不算提交"
                % (len(rows), rep.name))
    else:
        problem("索引热区无可解析记录行，本次提交未登索引——未登索引不算提交")

    print("== 5. 快照是否已更新（时间 ≥ 最新记录） ==")
    st = root / "STATE.md"
    if not st.exists():
        # 快照是 **standard 起**的能力：light 形态的文件集里没有 STATE.md（见 references/collaboration.md §1）。
        # 若在这里报 [待核]，light 工作区的退出码就**永远到不了 0**——门禁信号随之失效。
        # 这正是本包自己的规矩：设计上恒定成立的项必须降级为 [建议]，不得占用待核通道。
        if str(config(root, "collaboration.mode", "light")) == "light":
            note("模式＝light：文件集不含 STATE.md（快照属 standard 起的能力），本项按设计跳过")
        else:
            tbd("STATE.md 不存在（模式 %s 应有快照），无法核对快照是否已同步" % config(root, "collaboration.mode"))
    elif st.stat().st_mtime >= rep.stat().st_mtime:
        ok("STATE.md 修改时间不早于最新记录（辅证）")
    else:
        note("STATE.md 早于最新记录——疑提交漏同步快照（mtime 仅辅证，非铁证）")


    print("== 6. 并发：租约与卡内容一致性 ==")
    # 两层并发的**检测层**：脚本能拒绝「经由脚本的并发写」，但拦不住「绕过脚本直接改文件」。
    # 拦不住的必须看得见——卡上记的 NORMALIZED-SHA256 与文件实际内容不一致 = 有人绕过脚本改过。
    import lease as _lease
    cards = iter_cards(root)
    if not cards:
        note("tasks/ 下无任务卡（空项目正常）")
    else:
        active, expired, drifted = [], [], []
        #  #14 最小可见性：卡上有**两套"谁持有"真值**——手填「承接」与并发元数据 owner。
        #  两者不一致时**不静默**（本项不做结构性改造；由人核对）——见 references/artifacts.md。
        mismatch = []
        for c in cards:
            st = _lease.lease_state(c)
            _own, _claim = st.get("owner", ""), st.get("claimer", "")
            if _own and _claim and _own != _claim:
                mismatch.append((c, _own, _claim))
            if st["drifted"]:
                drifted.append(c)
            if st["active"]:
                active.append((c, st))
            elif st["expired"]:
                expired.append((c, st))
        if mismatch:
            for c, _own, _claim in mismatch[:5]:
                tbd("两套真值不一致：%s 的「承接」=%s，而并发元数据 owner=%s —— **谁持有以 owner 为准**，请人工核对（本项刻意不做结构性改造）" % (c.name, _claim, _own))
        if drifted:
            for c in drifted[:5]:
                p = _lease.conflict_file(root, c.stem,
                                        "提交门禁发现：卡内容与「并发元数据」记录的哈希不一致；"
                                        "有人绕过脚本直接改了卡——改动本身可能是对的，但它没有留痕。")
                problem("卡 %s 内容与记录哈希不一致（绕过脚本改过）——已生成 %s" % (c.name, p.name))
        else:
            ok("%d 张卡的内容与「并发元数据」记录一致" % len(cards))
        for c, st in active[:5]:
            note("卡 %s 被 %s 持有（租约至 %s）——此时他人写入属并发冲突" % (c.name, st["owner"], st["expires_at"]))
        for c, st in expired[:5]:
            note("卡 %s 租约已过期（原持有 %s，%s）——可安全接手，接手时跑 claim" % (c.name, st["owner"], st["expires_at"]))

    return summary()

if __name__ == "__main__":
    sys.exit(run(main))
