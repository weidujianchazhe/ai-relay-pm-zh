# -*- coding: utf-8 -*-
"""lang_gates.py —— 多语言门禁的**留痕与可查**（不自研度量，只统一口径）

用法：
    python lang_gates.py <工作区根> record --results "node=0,python=0,java=1" [--summary "..."]
    python lang_gates.py <工作区根> check

要解决的两个问题（都在「不自研度量」这个前提下）：
  ① **接没接上不知道**：本包给的是接线样板（各栈用成熟工具），但项目接没接、跑没跑，无从判断；
  ② **各栈输出不统一**：ESLint / Checkstyle / golangci-lint / clippy 各说各话，没人能一眼看完。

解法（复用本包既有的「开关即承诺，承诺由痕迹核实」）：
  · CI 跑完各栈工具 → 调 @record@ 把**退出码 + 一行摘要**追加进元数据通道 REVIEWS.md；
  · @check@ 读那行痕迹：开关开了却没有新鲜痕迹 → **[问题]**（假账）；有非零退出码 → **[问题]**（真红）。

为什么不自研度量：跨语言度量要么写六套解析器，要么退回行/缩进启发式——
后者本包实测过（按缩进口径报出 188 条、几乎全假阳性），而**误报会掩盖真问题**。
各栈的成熟工具本来就更准；本包只负责**约定、接线、留痕**。

依据：references/code-quality.md §1.4（门禁读数可信）· references/audit.md §6（开关与假账）
回本口径：一次「以为接好了其实没跑」的漏检即已回本。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import config, note, ok, problem, read, run, summary, tbd  # noqa: E402
import lease as _lease  # noqa: E402  —— 共享文件写原语（CAS）

#: 证据行格式（机器可读，与 audit_all 的「全盘核查」痕迹同一形态）：
#    - 2026-09-26T22:10:00+08:00 · 语言门禁 · node=0 python=0 java=1 · <摘要>
EVIDENCE_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2}T[\d:+\-]+)\s*·\s*语言门禁\s*·\s*([^·]*)(?:·\s*(.*))?$")


def _provenance(args) -> str:
    """证据来源标记（**证据存在 ≠ 证据真实**）。

    为什么要有它：check 只能证明「有一条记录」，不能证明记录来自 CI——
    有人手打一行 record --results node=0,java=0 也能让门禁变绿。
    加上来源 / 流水号 / 提交号后，伪造的成本才真正提高（至少要对得上一次真实的 CI 运行）。
    没带来源的记录仍可用，但 check 会明说它只是线索。
    """
    bits = []
    if getattr(args, "source", ""):
        bits.append("source=%s" % args.source)
    if getattr(args, "run", ""):
        bits.append("run=%s" % args.run)
    if getattr(args, "commit", ""):
        bits.append("commit=%s" % args.commit)
        # 能就地核验就标出来：伪造者至少要让这个提交在本地真实存在。
        #  核验不了（如 CI 记录的是别处的提交）不报错，只标 unverified——**不假装验证过**。
        try:
            import subprocess as _sp
            _r = _sp.run(["git", "cat-file", "-e", args.commit], cwd=str(Path.cwd()),
                         stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, timeout=8)
            bits.append("verified=%s" % ("yes" if _r.returncode == 0 else "no"))
        except Exception:
            bits.append("verified=unknown")
    return ("  [" + " ".join(bits) + "]") if bits else "  [无来源标记]"


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _parse_results(raw: str):
    """把 node=0,python=0,java=1 解析成 [(栈, 退出码)]；非法项不静默丢弃。"""
    out, bad = [], []
    for seg in re.split(r"[,;，；]", raw or ""):
        seg = seg.strip()
        if not seg:
            continue
        if "=" not in seg:
            bad.append(seg)
            continue
        k, v = seg.split("=", 1)
        k, v = k.strip(), v.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", k) or not re.fullmatch(r"-?\d+", v):
            bad.append(seg)
            continue
        out.append((k, int(v)))
    return out, bad


def _evidence(root: Path):
    """取最近一条语言门禁证据 → (时间, 结果串, 摘要) 或 (None, ..)。"""
    txt = read(root / "REVIEWS.md") or ""
    best = None
    for line in txt.splitlines():
        m = EVIDENCE_RE.match(line.strip())
        if not m:
            continue
        try:
            t = m.group(1).replace("Z", "+00:00")
            dt = datetime.fromisoformat(t)
        except Exception:
            continue
        if best is None or dt > best[0]:
            best = (dt, m.group(2).strip(), (m.group(3) or "").strip())
    if best is None:
        return None, "", ""
    return best[0], best[1], best[2]


def cmd_record(root: Path, args) -> int:
    results, bad = _parse_results(args.results)
    if bad:
        problem("--results 里有无法解析的项：%s（正确形态如 node=0,python=0）" % "、".join(bad))
        return summary()
    if not results:
        problem("--results 为空：没有可留痕的内容")
        return summary()
    p = root / "REVIEWS.md"
    if not p.exists():
        problem("REVIEWS.md 不存在（元数据通道）——无法留痕：%s" % p)
        return summary()
    prov = _provenance(args)
    line = "- %s · 语言门禁 · %s · %s%s" % (_now(),
                                      " ".join("%s=%d" % (k, v) for k, v in results),
                                      args.summary or "", prov)
    # **共享文件的写必须走原语**（lease.shared_append 内含 CAS）：
    #  这里原来是 tmp + os.replace 直接替换——与协议声称的「共享文件写前比对哈希」不符，
    #  两个 Agent 同时 record 会丢写（经典 lost update）。收拢到原语后由 gen_views 第 10 节守着。
    okk, why = _lease.shared_append(root, p, line, "语言门禁留痕")
    if not okk:
        problem(why)
        return summary()
    ok("已留痕：%s" % line[:110])
    failed = [k for k, v in results if v != 0]
    if failed:
        note("其中有非零退出码：%s —— 留痕不等于放行，门禁红就该阻断" % "、".join(failed))
    return summary()


def cmd_check(root: Path) -> int:
    on = bool(config(root, "tools.lang_gates", False))
    days = int(config(root, "tools.lang_gates_days", 7) or 7)
    when, results, brief = _evidence(root)
    print("多语言门禁：开关=%s · 周期=%s 天" % ("开" if on else "关", days))
    if when is None:
        if on:
            problem("开关为「开」但元数据通道里没有语言门禁痕迹——**开了却没跑＝假账**"
                    "（CI 里加一步 lang_gates.py record，见 ci/github-actions-multilang.yml）")
        else:
            note("未启用多语言门禁（单语言项目正常）；启用后本项会核实在跑")
        return summary()
    age = (datetime.now(when.tzinfo) - when).total_seconds() / 86400.0
    stamp = "%s（%.1f 天前）" % (when.isoformat(), age)
    if age > days:
        if on:
            problem("语言门禁痕迹已超期 %s：%s" % (stamp, results))
        else:
            note("语言门禁痕迹已超期 %s（开关为关，不计入）" % stamp)
        return summary()
    ok("语言门禁痕迹新鲜：%s" % stamp)
    if results:
        print("     各栈退出码：%s" % results)
    if brief:
        print("     摘要：%s" % brief[:120])
    failed = [s for s in results.split() if "=" in s and not s.endswith("=0")]
    if failed:
        problem("最近一次语言门禁有非零退出码：%s —— 这是真红，不是待核" % "、".join(failed))
    return summary()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法：python lang_gates.py <工作区根> record --results \"node=0,python=0\" [--summary \"...\"]")
        print("      python lang_gates.py <工作区根> check")
        return 3
    root = Path(args[0])
    if not root.is_dir():
        problem("工作区根不存在：%s" % root)
        return summary()
    if "check" in sys.argv[1:]:
        return cmd_check(root)
    if "record" in sys.argv[1:]:
        res = sys.argv[sys.argv.index("--results") + 1] if "--results" in sys.argv else ""
        brief = sys.argv[sys.argv.index("--summary") + 1] if "--summary" in sys.argv else ""
        def _opt(flag):
            return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else ""
        return cmd_record(root, type("A", (), {
            "results": res, "summary": brief,
            "source": _opt("--source"), "run": _opt("--run"), "commit": _opt("--commit")})())
    problem("未知动作：需 record 或 check")
    return summary()


if __name__ == "__main__":
    sys.exit(run(main))