# -*- coding: utf-8 -*-
# NOPMD: 核查编排器的聚合四档（3>1>2>0）、成员退出码口径与"部分核查不得冒充全盘"的留痕规则必须就地写明——它们是判据本身，删注释即失去复核入口，且 rc=3 与 rc=1 的区分全靠这几行。
"""audit_all.py —— 全盘核查入口（编排器 + 留痕）

用法：
    python audit_all.py <管理区> [--code <源码根>] [--only a,b,c] [--no-record]

为什么要有这个脚本：
    ① 门禁分多路（结构 / 提交 / 索引 / 一致性 / 代码度量），逐个手跑既费事又容易只跑一半就宣布通过——
       **编排器把"跑全套"变成一条命令**；成员清单见下方 MEMBERS（**数量不写死在注释里**，免得与实现漂移）。
    ② 更重要的：**开关不能只是配置里的一个"开"字**。MAP 写「定期排查：开」而没人真跑，
       就是**假账**——账面上有这项控制，实际不存在。所以本脚本每跑一次就往元数据通道
       追加一行**机器戳证据**，并自查"距上次核查多久"。**开了却没跑，机器自己会红。**

开关口径（与 audit.md 一致）：
    开关不是**许可**，是**承诺**。承诺由 REVIEWS.md 里的核查记录核实，不由 MAP 里那个字核实。

依据：references/audit.md §2.0（锚源原则：声明 vs 痕迹）、references/audit.md §6（开关的假账风险）
回本口径：把"逐个手跑各门禁 + 手工汇总 + 手工记录"压成一条命令；
         一次"只跑了一半就说通过"的漏检即已回本。
踩坑记录：
    · 子脚本返回 2（仅待核）不得被当成失败——本脚本按 1 → 1、否则 2 → 2 的次序聚合；
    · **不把子脚本输出整段吞进内存后一起打印**会丢失"哪个门禁红了"的定位，故逐段透传；
    · 证据行必须带**机器戳**，否则它自己也是"声明"而不是"痕迹"。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import config, note, ok, problem, read, summary, tbd, run, usage_exit  # noqa: E402
from stamp import ai_id  # noqa: E402
import lease as _lease  # noqa: E402  —— 共享文件写原语（CAS）

HERE = Path(__file__).resolve().parent
#: 全盘核查的成员（顺序即运行顺序；overview 是视图不是门禁，恒 0）
MEMBERS = ["overview.py", "validate_workspace.py", "check_closeout.py",
           "check_index.py", "reconcile.py",
           # 2026-10-02 纳入：此前只在 CI 跑，本地全盘核查跑不到（CI 与本地必须一致）
           "correctness_rules.py", "check_size_budget.py", "provider_gate.py"]
EVIDENCE_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2}T[\d:+\-]+)\s*·\s*全盘核查")


def _last_audit(root: Path):
    """从元数据通道里取最近一次核查的机器戳时间。"""
    txt = read(root / "REVIEWS.md") or ""
    best = None
    for line in txt.splitlines():
        m = EVIDENCE_RE.match(line.strip())
        if m:
            try:
                t = m.group(1).replace("Z", "+00:00")
                dt = datetime.fromisoformat(t)
                best = dt if best is None or dt > best else best
            except Exception:
                continue
    return best


def _append_evidence(root: Path, text: str):
    """往元数据通道追加一行机器戳证据。

    走 `lease.shared_append`（**带 CAS**）：原来是自己 tmp + os.replace——
    与协议声称的「共享文件写前比对哈希」不符，两个 Agent 同时核查会丢写。
    """
    p = root / "REVIEWS.md"
    if not p.exists():
        note("无 REVIEWS.md —— 核查证据未留痕（这会使「定期排查：开」变成假账）")
        return False
    okk, why = _lease.shared_append(root, p, text, "全盘核查留痕")
    if not okk:
        note("留痕被拒：%s" % why)
    return okk


def main() -> int:
    ap = argparse.ArgumentParser(description="全盘核查：编排门禁 + 留痕 + 新鲜度自查")
    usage_exit(ap)
    ap.add_argument("root")
    ap.add_argument("--code", default="", help="源码根（给了才跑 code_metrics.py）")
    ap.add_argument("--only", default="", help="只跑指定成员（逗号分隔的脚本名或短名）")
    ap.add_argument("--no-record", action="store_true", help="不写证据行（只用于排查脚本本身）")
    a = ap.parse_args()

    root = Path(a.root)
    if not root.is_dir():
        problem("管理区不存在：%s" % root)
        return 3

    print("=" * 52)
    print("全盘核查 · %s" % root)
    print("=" * 52)

    # ── 0. 新鲜度自查：开关开了却没跑，就是假账 ──
    on = config(root, "tools.periodic_audit", True)
    period = config(root, "tools.periodic_audit_days", 7)
    last = _last_audit(root)
    print("== 0. 核查新鲜度（开关不是许可，是承诺） ==")
    if not on:
        note("定期排查开关为「关」——本项不计入（但请注意：关也不等于免检，只是不承诺周期）")
    elif last is None:
        tbd("开关为「开」但元数据通道里**查不到任何核查记录**——这是假账的第一种形态：账面上有控制，实际没跑过")
    else:
        age = (datetime.now(last.tzinfo) - last).days
        if age > period:
            problem("上次全盘核查在 %d 天前（周期 %s 天）——已超期" % (age, period))
        else:
            ok("上次全盘核查在 %d 天前（周期 %s 天）——在周期内" % (age, period))

    # ── 1. 编排成员 ──
    members = MEMBERS[:]
    if a.code:
        members.append("code_metrics.py")
    if a.only:
        want = [x.strip() for x in a.only.split(",") if x.strip()]
        members = [m for m in members if m in want or m[:-3] in want]
        if not members:
            print("[问题] --only 没有匹配到任何成员：%s" % a.only)
            return summary()

    worst = 0
    results = []
    for m in members:
        script = HERE / m
        if not script.exists():
            problem("成员脚本不存在：%s" % m)
            worst = max(worst, 1)
            continue
        # -B：编排跑全部门禁时不落地 .pyc（口径见 scripts/README.md；非掩盖红灯，见 references/self-gate-debt.md）
        args = [sys.executable, "-B", str(script), str(root if m != "code_metrics.py" else a.code)]
        print()
        print("---- %s " % m + "-" * max(0, 46 - len(m)))
        try:
            p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=600, check=False)
            out = p.stdout.decode("utf-8", "replace")
            sys.stdout.write(out if out.endswith("\n") else out + "\n")
            rc = p.returncode
        except subprocess.TimeoutExpired:
            print("[问题] %s 超时（600s）" % m)
            rc = 3
        results.append((m, rc))
        #  聚合四档，**3 单独成档、不折进 1**（2026-10-15 实测出的缺陷）：
        #    旧实现 `worst = 1 if (rc == 1 or rc == 3 or worst == 1) else ...` 把「成员脚本自己崩了」(3)
        #    折成「项目有问题」(1)。后果：每 7 天的定期全盘核查在**健康工作区**上永久 exit 1，
        #    而各成员汇总里 `[问题] 0`——红灯无从归因（实测成因：check_size_budget 只认
        #    config/defaults.yml，而实例工作区按 README ② 实例化成 config.yml → 恒返回 3）。
        #    这违反 scripts/README.md 的明文约定：「脚本自身错误一律退出码 3，与『门禁抓到真问题』(1)
        #    分开——否则核查者会把『脚本崩了』读成『项目有问题』」。
        #  优先级 **3 > 1 > 2 > 0**：核查工具自身失效时，它给出的「项目有问题」结论同样不可信，
        #    故 3 覆盖 1。两者都必须在下面的「成员结果」行里逐成员可见，不能只靠聚合码归因。
        if rc == 3:
            worst = 3
        elif rc == 1 and worst != 3:
            worst = 1
        elif rc == 2 and worst not in (1, 3):
            worst = 2

    # ── 2. 留痕 ──
    print()
    print("=" * 52)
    print("成员结果：" + "  ".join("%s=%d" % (m[:-3], rc) for m, rc in results))
    print("聚合退出码：%d（0 全通过 · 1 有问题 · 2 仅待核 · 3 脚本错误）" % worst)
    #  归因行：**把红灯落到具体成员**，避免「聚合 1 但看不出是谁」的排查成本。
    #  两类分开点名——「项目有问题」与「脚本自身错误」的处置完全不同：
    #    前者去修工作区，后者去修本包脚本（或它依赖的布局），**不要拿它当项目缺陷去查**。
    bad = [m[:-3] for m, rc in results if rc == 1]
    broken = [(m[:-3], rc) for m, rc in results if rc == 3]
    if bad:
        problem("门禁判出问题：%s —— 去修工作区" % "、".join(bad))
    if broken:
        problem("成员脚本自身错误：%s —— **不是项目有问题**，是核查工具失效（先修脚本/布局，再重跑核查）"
                % "、".join("%s(rc=%d)" % (m, rc) for m, rc in broken))
    if not a.no_record:
        now = datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()
        #  新鲜度自查用的 EVIDENCE_RE 正是认「· 全盘核查」这个字样；若部分运行也写它，
        #  就会**把部分审计冒充完整审计，并刷新完整审计的新鲜度**（后续定期排查变假账）。
        #  处置：部分运行的痕迹用不同字样（**不匹配 EVIDENCE_RE**），因此不刷新全盘新鲜度。
        _scope = "部分核查（--only: %s）" % a.only if a.only else "全盘核查"
        line = "- %s · %s · %s · 聚合退出码 %d（%s）" % (
            now, _scope, ai_id(), worst, " ".join("%s=%d" % (m[:-3], rc) for m, rc in results))
        if _append_evidence(root, line):
            if a.only:
                note("部分核查痕迹已留痕（REVIEWS.md 一行）——它不满足「全盘核查」证据，新鲜度不会被它刷新")
            else:
                ok("核查证据已留痕（REVIEWS.md 一行，带机器戳）")
    return worst


if __name__ == "__main__":
    sys.exit(run(main))
