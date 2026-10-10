# NOPMD: 注释密度 1.60 > 上限 1.5 —— 其中 1 条为 G1 审计豁免标记（# noqa: G1 reason=diagnostic-message sha256=…，机器可读的身份绑定证据，非解释性注释）；其余为规则说明与成因注释，非翻译式注释。
# -*- coding: utf-8 -*-
"""validate_workspace.py —— 工作区结构与配置校验

用法：python validate_workspace.py <管理区>
何时跑：初始化后 / 改结构后 / 定期自检
依据：references/artifacts.md §1（文件清单）、§2（冻结区）；references/audit.md §2.1（人检标记）
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import config, iter_cards, note, ok, problem, read, strip_code, summary, tbd, run  # noqa: E402

REQUIRED_FILES = ["MAP.md", "STATE.md", "INDEX.md", "REVIEWS.md", "SKILL.md"]
REQUIRED_DIRS = ["tasks", "reports", "archives", "archives/done"]
REQUIRED_ARCHIVE = "archives/INDEX_archived.md"

# 2.x 工作区随带（见 references/artifacts.md §1）。
# 判据用「有没有 MANIFEST.md」而不是版本号：1.x 工作区没有这个文件，
# 于是旧工作区判为 legacy、只提示不报错（存在 1.x 实例是事实，不能判它不合法）。
V2_FILES = ["MANIFEST.md", "config.yml"]
V2_DIRS = ["references", "scripts"]

# 冻结区（改名即破坏功能）——抽查最关键的几个
REQUIRED_CARD_FIELDS = ["承接", "进度锚点", "上次交接", "已提炼", "代码根路径", "涉及"]
HANDOVER_BLOCKS = ["本次需求", "本次涉及工程信息", "改动点", "验证结果", "数据影响", "下一步", "任务卡更新"]

def main():
    if len(sys.argv) < 2:
        print("用法：python validate_workspace.py <管理区>")
        return 3
    root = Path(sys.argv[1])
    if not root.is_dir():
        problem("管理区不存在：%s" % root)
        return 3

    print("== 1. 必需文件 / 目录 ==")
    for f in REQUIRED_FILES:
        (ok if (root / f).exists() else problem)("文件 %s" % f)
    for d in REQUIRED_DIRS:
        (ok if (root / d).is_dir() else problem)("目录 %s/" % d)
    (ok if (root / REQUIRED_ARCHIVE).exists() else problem)("文件 %s" % REQUIRED_ARCHIVE)

    print("== 1b. 2.x 随带件（references/ / scripts/ / config.yml） ==")
    if (root / "MANIFEST.md").exists():
        for f2 in V2_FILES:
            (ok if (root / f2).exists() else problem)("文件 %s" % f2)
        for d2 in V2_DIRS:
            (ok if (root / d2).is_dir() else problem)("目录 %s/" % d2)
        refs = root / "references"
        if refs.is_dir() and not list(refs.glob("*.md")):
            problem("references/ 下没有协议正文（空目录＝协议正文无法从工作区还原）")
    else:
        # noqa: G1 reason=diagnostic-message sha256=cf8b612e6349
        note("无 MANIFEST.md —— 判定为 1.x 工作区；建议按 references/artifacts.md §1 补齐 "
             "MANIFEST.md / references/ / scripts/ / config.yml"
             "（缺 references/ 时协议正文无法从工作区逐字还原）")

    print("== 2. MAP 规则段配置项 ==")
    map_txt = read(root / "MAP.md") or ""
    if not map_txt:
        tbd("MAP.md 不可读，配置项校验跳过")
    else:
        for label in ("INDEX 主文件行数", "STATE 字数上限", "reports 归档阈值", "协作模式"):
            (ok if label in map_txt else problem)("MAP 规则段含「%s」" % label)

    print("== 3. 冻结字段名抽查（任务卡） ==")
    cards = iter_cards(root)
    if not cards:
        note("tasks/ 下暂无任务卡（空项目正常）")
    else:
        miss = {}
        for c in cards:
            t = read(c) or ""
            for f in REQUIRED_CARD_FIELDS:
                if f not in t:
                    miss.setdefault(f, []).append(c.name)
        if miss:
            for f, names in miss.items():
                problem("字段「%s」缺失于 %d 张卡：%s" % (f, len(names), "、".join(names[:3])))
        else:
            ok("%d 张卡均含 %d 个必需字段" % (len(cards), len(REQUIRED_CARD_FIELDS)))

    print("== 3b. 设计区（designs/）—— 成对性 / 蓝图长度 / 归档成对 ==")
    _check_designs(root)

    print("== 4. 交接块名（模板抽查） ==")
    tpl = root / "reports" / "HANDOVER.template.md"
    if tpl.exists():
        t = read(tpl) or ""
        lack = [b for b in HANDOVER_BLOCKS if b not in t]
        (ok if not lack else problem)("交接模板 6+1 块齐全" if not lack else "交接模板缺块：%s" % "、".join(lack))
    else:
        note("无 reports/HANDOVER.template.md（模板未随工作区复制时正常）")

    print("== 5. 容量口径（实例 MAP 优先） ==")
    print("    索引热区行数 = %s" % config(root, "capacity.index_hot_rows"))
    print("    STATE 字数上限 = %s" % config(root, "capacity.state_max_chars"))
    print("    reports 归档阈值 = %s" % config(root, "capacity.report_archive_threshold"))
    print("    REVIEWS 热区行数上限 = %s" % config(root, "capacity.reviews_hot_lines"))
    print("    协作模式 = %s" % config(root, "collaboration.mode"))
    idx = root / "INDEX.md"
    if idx.exists():
        n = len(re.findall(r"(?m)^\|\s*[A-Z]{2}[0-9]{4,5}\s*\|", read(idx) or ""))
        cap = config(root, "capacity.index_hot_rows", 20)
        (ok if n <= cap else problem)("索引热区 %d 行（上限 %s）" % (n, cap))
    st = root / "STATE.md"
    if st.exists():
        n = len(read(st) or "")
        cap = config(root, "capacity.state_max_chars", 15000)
        (ok if n <= cap else problem)("STATE %d 字符（上限 %s）" % (n, cap))
    rv = root / "REVIEWS.md"
    if rv.exists():
        # 留痕只增不删，但**读取面有界**（references/artifacts.md §8）：
        # 超限不是错，是"该滚动了"——修复动作由 closeout.py reviews-archive 给出。
        n = len((read(rv) or "").rstrip("\n").split("\n"))
        cap = config(root, "capacity.reviews_hot_lines", 200)
        (ok if n <= cap else problem)(
            "REVIEWS 热区 %d 行（上限 %s）——跑 closeout.py reviews-archive 滚入 archives/REVIEWS_archived.md"
            % (n, cap))

    print("== 6. \u4eba\u68c0\u6807\u8bb0\u683c\u5f0f\u4e0e\u5230\u671f\uff08\u673a\u5668\u6233\uff09 ==")
    _check_human_marks(root)

    return summary()

MARK_RE = re.compile(r"#\u4eba\u68c0\s*\(([^)]*)\)")
STAMP_RE = re.compile(
    r"^(git|host):[0-9a-fA-F]{4,40}@\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)$"
)


def _long_paragraphs(txt: str, cap: int):
    """蓝图里超过 cap 字符的**段落**（结构行——表格 / 清单 / 引用 / 标题 / 代码块——不算段落）。

    为什么要查这个：蓝图是"一屏能看明白的结构视图"。出现长段落，说明**详述的内容被搬过来了**，
    两份文件从此各写一份、迟早漂移（references/design.md §1）。
    """
    out, buf, fence = [], [], False
    for ln in txt.split("\n"):
        s = ln.strip()
        if s.startswith("```"):
            fence = not fence
            if buf:
                out.append("".join(buf)); buf = []
            continue
        if fence or not s:
            if buf:
                out.append("".join(buf)); buf = []
            continue
        if s[0] in "|-*#>":
            if buf:
                out.append("".join(buf)); buf = []
            continue
        buf.append(s)
    if buf:
        out.append("".join(buf))
    return [p for p in out if len(p) > cap]


def _check_designs(root: Path):
    """设计区校验：成对性 / 蓝图长度 / 归档成对（references/design.md §1 §4 §6）。"""
    d = root / "designs"
    if not d.is_dir():
        note("无 designs/ —— 不需要设计的项目正常（设计区按需建）")
        return
    specs, bps = [], []
    # **必须由扩展名驱动**：只 glob *.md 会让 .blueprint.html 永不进入 bps →
    # 蓝图长度 / 长段落 / 孤儿蓝图三项检查对 HTML 蓝图全部失效（2026-10 实测：selftest 用例「蓝图塞长段落」报「门禁对这类故障是瞎的」）。
    for p in sorted(list(d.glob("*.md")) + list(d.glob("*.html"))):
        (bps if p.name.endswith(".blueprint.html") else specs).append(p)
    if not specs and not bps:
        note("designs/ 为空 —— 活跃设计区保持清空是健康状态（走完流程的设计已入 designs/archives/）")
        return
    for s in specs:
        if not (d / (s.stem + ".blueprint.html")).exists():
            problem("设计缺蓝图：designs/%s.blueprint.html 不存在 —— 一份设计＝详述 + 蓝图两件套" % s.stem)
        t = read(s) or ""
        if "拆分出的任务卡" not in t:
            problem("设计卡缺冻结字段「拆分出的任务卡」：designs/%s.md（归档门禁判据）" % s.stem)
    for b in bps:
        if not (d / (b.name[: -len(".blueprint.html")] + ".md")).exists():
            problem("孤儿蓝图（没有对应详述）：designs/%s" % b.name)
    cap_lines = int(config(root, "capacity.blueprint_max_lines", 100))
    cap_para = int(config(root, "capacity.blueprint_max_para_chars", 160))
    for b in bps:
        t = read(b) or ""
        n = len(t.rstrip("\n").split("\n"))
        if n <= cap_lines:
            ok("蓝图 %s %d 行（上限 %s）" % (b.name, n, cap_lines))
        else:
            note("蓝图 %s %d 行（提醒线 %s）—— 超线不阻断；若已影响直观，把叙述移回详述" % (b.name, n, cap_lines))
        bad = _long_paragraphs(t, cap_para)
        if bad:
            problem("蓝图 %s 含 %d 个超过 %d 字符的段落（最长 %d）—— 结构视图不放散文，请移回详述"
                    % (b.name, len(bad), cap_para, max(len(x) for x in bad)))
    arch = d / "archives"
    if arch.is_dir():
        an = len(list(arch.glob("*.md")))
        if an % 2 == 0:
            ok("设计归档 %d 个 .md 文件（成对）" % an)
        else:
            problem("设计归档 %d 个 .md 文件（奇数＝有设计只移了一半，详述与蓝图必须成对）" % an)

def _parse_marker(body):
    """#人检(slot=x, by=y) -> dict。刻意不认 owner= / next=（见 audit.md §2.1）。"""
    d = {}
    for seg in body.split(","):
        if "=" in seg:
            k, v = seg.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def _check_human_marks(root):
    """扫 MD 里的人检标记：只查格式与到期——**不查真伪**（真伪是人工分诊的事）。

    到期 = 戳的时间 + 周期。因为标记里没有 next 字段，到期是算出来的，
    所以「忘了复检」会自己变红，不需要任何人记账。
    """
    period = config(root, "audit.human_check.period_days", 90)
    # 标记字面量刻意**不**走 config()：那套取值器是为数值设计的（见 _common.config），
    # 对字符串键会抓到 MAP 里的引号等噪声。标记字面量固定为 #人检（改它要过 §A 门禁）。

    found, bad, stale = 0, [], []
    now = datetime.now().astimezone()
    for p in sorted(root.rglob("*.md")):
        parts = set(p.parts)
        if parts & {"archives", ".git", "__pycache__"}:
            continue
        # **先剥代码块与行内代码再扫**：规范文档会把旧格式当反例写在代码里
        #  （audit.md §2.1 就写着 #人检(owner=…, next=…)），
        #  不剥的话，机器检查器会把自己的规范说明当成真实数据报错——**门禁自污染**。
        for m in MARK_RE.finditer(strip_code(read(p) or "")):
            found += 1
            d = _parse_marker(m.group(1))
            rel = p.relative_to(root)
            if "owner" in d or "next" in d:
                bad.append("%s \u5199\u4e86 owner/next\uff08\u5e94\u6539\u4e3a slot + by \u673a\u5668\u6233\uff0c\u89c1 audit.md \u00a72.1\uff09" % rel)
                continue
            if "slot" not in d or "by" not in d:
                bad.append("%s \u7f3a slot \u6216 by" % rel)
                continue
            if not STAMP_RE.match(d["by"]):
                bad.append("%s \u7684 by \u683c\u5f0f\u975e\u6cd5\uff1a%s" % (rel, d["by"][:60]))
                continue
            kind, rest = d["by"].split(":", 1)
            ts = rest.split("@", 1)[1]
            try:
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                dt = datetime.fromisoformat(ts)
            except Exception:
                bad.append("%s \u65f6\u95f4\u4e0d\u53ef\u89e3\u6790\uff1a%s" % (rel, ts))
                continue
            age = (now - dt).total_seconds() / 86400
            if age > period:
                stale.append("%s\uff08\u8d85\u671f %.0f \u5929\uff0c\u8f7d\u4f53=%s\uff09" % (rel, age - period, kind))

    if not found:
        note("\u672a\u53d1\u73b0\u4eba\u68c0\u6807\u8bb0\uff08\u672a\u542f\u7528\u65f6\u6b63\u5e38\uff09")
    else:
        (ok if not bad else problem)("%d \u5904\u4eba\u68c0\u6807\u8bb0\u683c\u5f0f\u5408\u6cd5" % found
                                     if not bad else "\u4eba\u68c0\u6807\u8bb0\u683c\u5f0f\u95ee\u9898\uff1a" + "\uff1b".join(bad[:5]))
        (ok if not stale else problem)("\u4eba\u68c0\u5747\u672a\u8d85\u671f\uff08\u5468\u671f %s \u5929\uff09" % period
                                       if not stale else "\u4eba\u68c0\u8d85\u671f\uff1a" + "\uff1b".join(stale[:5]))

if __name__ == "__main__":
    sys.exit(run(main))
