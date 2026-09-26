# -*- coding: utf-8 -*-
"""overview.py —— 一屏项目全貌（只读视图，不是门禁）

用法：python overview.py <工作区根> [--full]

为什么要有这个脚本：
    「这个项目现在是什么状态」原本要靠人依次打开 MAP / STATE / INDEX / tasks 四处才能回答。
    本脚本把这几处的**摘要**一次输出，用于接手前 10 秒的定位，以及管理者的定期扫视。

与门禁的区别（重要）：
    本脚本是**视图**，不是**门禁**——它恒返回 0，不阻塞任何操作。
    缺文件时按要求降级显示为「无」，而不是报错——只有 MAP 的项目也能跑。

依据：references/onboarding.md §7（一屏查看）、§6（交付话术：任务卡靠人派发）、references/workflow.md §7（人眼查看视图）
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import config, index_rows, iter_cards, iter_reports, read, run  # noqa: E402

SEP = "-" * 52


def _sections(txt: str) -> dict:
    """把 Markdown 按 ## 标题切段（标题去序号前缀）。"""
    out, cur, buf = {}, "", []
    for line in (txt or "").splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            if cur:
                out[cur] = buf
            cur = re.sub(r"^[一二三四五六七八九十\d]+[、.]\s*", "", m.group(1).strip())
            buf = []
        elif cur:
            buf.append(line)
    if cur:
        out[cur] = buf
    return out


def _bullets(lines):
    return [l.strip()[1:].strip() for l in lines if l.strip().startswith("- ")]


def _table_rows(lines):
    return [l.strip() for l in lines
            if l.strip().startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", l.strip())][1:]


def show_map(root: Path):
    txt = read(root / "MAP.md")
    if not txt:
        print("[地图] 无 MAP.md —— 本工作区未登记项目地图（卡片模式下属正常）")
        return
    title = next((l[2:].strip() for l in txt.splitlines() if l.startswith("# ")), "（无标题）")
    secs = _sections(txt)
    print("[地图] %s" % title)
    for name, lines in secs.items():
        if "环境" in name:
            for b in _bullets(lines)[:8]:
                print("        " + b[:110])
        elif "规则" in name:
            # 权限档位单独显示：本包约束「路径」不约束「能力」（artifacts.md §9.3）——
            # 有人绕过唯一入口直接改文件时，**先要能回答他为什么能**。
            tier = config(root, "environment.sandbox", "unknown")
            if str(tier).lower() in ("unknown", "", "—", "未登记"):
                # 视图只 print，不 note：overview 是恒返 0 的视图，不参与三态计分
                print("        [权限档位] 未登记 —— 建议在 MAP 规则段写一行"
                      "「权限档位：完全权限 / 工作区可写 / 只读」")
            else:
                print("        [权限档位] %s（登记值：本包约束路径，不约束能力）" % tier)
            picks = [b for b in _bullets(lines) if any(
                k in b for k in ("INDEX", "STATE", "reports", "排查", "协作模式", "ID 注册", "单写者"))]
            for b in picks[:6]:
                print("        " + b[:110])
        elif "路径" in name:
            rows = _table_rows(lines)
            print("        [路径注册表] %d 条" % len(rows))


def show_state(root: Path):
    txt = read(root / "STATE.md")
    if not txt:
        print("[快照] 无 STATE.md")
        return
    secs = _sections(txt)
    upd = next((l for l in txt.splitlines() if "最近更新" in l), "")
    print("[快照] %s" % upd.strip("> ").strip()[:100])
    for name, lines in secs.items():
        items = _bullets(lines)
        if "当前进展" in name and items:
            print("        进展：" + items[0][:100])
        elif "进行中" in name:
            print("        进行中任务：%d 条" % len(items))
            for b in items[:5]:
                print("          · " + b[:100])
        elif "决策点" in name:
            rows = _table_rows(lines)
            if rows:
                print("        待确认决策点：%d 条" % len(rows))
                for r in rows[:5]:
                    print("          · " + r[:110])
        elif "限制" in name and items:
            print("        已知限制：%d 条" % len(items))


def show_index(root: Path, full: bool):
    rows = index_rows(root / "INDEX.md")
    cold = root / "archives" / "INDEX_archived.md"
    ncold = len(index_rows(cold)) if cold.exists() else 0
    limit = config(root, "capacity.index_hot_rows", 20)
    print("[索引] 热区 %d 行（上限 %s）· 冷区 %d 行" % (len(rows), limit, ncold))
    show = rows if full else rows[-5:]
    for cells, _ in show:
        print("        " + " | ".join(c[:22] for c in cells[:4]))


def show_cards(root: Path):
    """任务卡板：按分支分组、标出在途/空闲、超阈值时给合并提示。"""
    show_card_board(root, iter_cards(root))




# ── 任务卡板与合并提示（references/workflow.md §2 认领 / §4.1 分派）────
#: 卡上这几个字段非「—」即表示**有人正在动它**——合并前必须查，否则会把两张在途的卡并成一张。
FIELD_RE = re.compile(r"\*\*(承接|进度锚点|状态|编号)\*\*\s*[：:]\s*(.+?)\s*$")


def _card_fields(path):
    d = {}
    txt = read(path) or ""
    for line in txt.splitlines():
        m = FIELD_RE.search(line.strip())
        if m:
            d[m.group(1)] = m.group(2).strip().strip("[]").strip()
    return d


def _inflight(path, minutes):
    try:
        age = (time.time() - path.stat().st_mtime) / 60.0
    except OSError:
        return False, -1
    return age <= minutes, age


def _branch_of(card):
    """分组依据：编号的两位分支码；无编号时用文件名首段。"""
    d = _card_fields(card)
    m = re.match(r"([A-Z]{2})[0-9]{4,5}", d.get("编号", "")) or re.match(r"([A-Z]{2})[0-9]{4,5}", card.stem)
    return m.group(1) if m else "—"


def show_card_board(root, cards):
    """把任务卡排成一块板：按分支分组，标出在途/空闲。"""
    limit = int(config(root, "cards.merge_hint_threshold", 8))
    inflight_min = int(config(root, "cards.inflight_minutes", 30))
    print("[任务卡板] 活跃 %d 张（合并提示阈值 %d）" % (len(cards), limit))
    if not cards:
        # 没有卡时不能说"正常"，要说**怎么建**：任务卡由人开口、AI 落卡，
        # 用户不知道有这个功能，卡就永远是 0（说明话术见 references/onboarding.md §6）。
        print("     暂无任务卡。建卡不用记命令，对 AI 说一句即可："
              "「新建任务：<要做的事>」——AI 跑 closeout.py new-card 生成骨架；"
              "要先定方案时先说「这件事先出个设计卡」（未批准的设计不生成执行卡）。")
        return
    groups = {}
    info = {}
    for c in cards:
        d = _card_fields(c)
        # 在途判据**只看声明字段**（承接 / 进度锚点）。
        # mtime 只作提示附在后面：它分不清"刚被写过"与"正在被写"（见 audit.md §3.4），
        # 拿它当判据会把刚建的空卡全判成在途——**近似即不可靠，故不作裁决**。
        busy_field = [k for k in ("承接", "进度锚点") if d.get(k, "—") not in ("—", "-", "", "[]")]
        _, age = _inflight(c, inflight_min)
        info[c] = {"f": d, "why": busy_field, "busy": bool(busy_field), "age": age}
        groups.setdefault(_branch_of(c), []).append(c)

    for br in sorted(groups):
        print("  ── 分支 %s（%d 张）" % (br, len(groups[br])))
        for c in sorted(groups[br], key=lambda p: p.stem):
            g = info[c]
            flag = "在途" if g["busy"] else "空闲"
            why = "；".join(g["why"])
            if g["age"] is not None and 0 <= g["age"] <= inflight_min:
                why = (why + "；" if why else "") + "文件 %d 分钟前被改（仅提示）" % int(g["age"])
            st = g["f"].get("状态", "?")
            print("     [%s] %-34s 状态=%-8s %s" % (flag, c.stem[:34], st[:8], why))

    if len(cards) <= limit:
        return
    print("  ── 合并提示（卡数 %d > 阈值 %d）" % (len(cards), limit))
    print("     可考虑把同一分支的**空闲**卡合并成一张连续做——减少切换成本与接手次数。")
    print("     ⚠ 合并前必须查并发冲突：**在途的卡不得合并**（会踩掉别人正在写的进度）。")
    for br in sorted(groups):
        free = [c for c in groups[br] if not info[c]["busy"]]
        busy = [c for c in groups[br] if info[c]["busy"]]
        if len(free) >= 2:
            print("     · 分支 %s：可合并候选 %d 张 —— %s" % (br, len(free), "、".join(c.stem[:22] for c in free)))
        if busy:
            print("     · 分支 %s：**排除** %d 张在途卡 —— %s" % (br, len(busy), "、".join(c.stem[:22] for c in busy)))



# ── 接手包：把「上手成本恒定」从一句话变成一行数字 ──────────────
# 为什么量字符而不是数文件：「一份卡 + 一篇记录」说的是**读哪些**，不是**读多少**。
# 实测某真实项目：卡中位 5,445 字符、记录中位 3,505 字符，即"两份文件"≈ 8,900 字符，
# 而单张卡最大 22,002 字符。**文件数恒定 ≠ 成本恒定**——能被控制的只有字符数。
def _chars(p: Path) -> int:
    return len(read(p) or "")


#: 「上次交接」是**指针链**，与卡板上那四个字段不是一回事——
#  card_fields 只取卡板要用的字段（承接/进度锚点/状态/编号），拿它读指针会永远读空。
POINTER_RE = re.compile(r"^-\s*\*\*上次交接\*\*\s*[：:]\s*(.*)$", re.M)


def _ref_reports(card: Path, root: Path):
    """卡「上次交接」指向的记录（可能多篇，逗号分隔或分行）。"""
    txt = read(card) or ""
    m = POINTER_RE.search(txt)
    raw = m.group(1).strip() if m else ""
    out = []
    for m in re.finditer(r"reports[\\/][^\s,，、;；|）)]+?\.md", raw):
        p = root / m.group(0).replace("/", "\\")
        if p.exists():
            out.append(p)
    return out


def show_onboarding_cost(root: Path, cards):
    print("[接手包] 接手一项工作实际要读多少（字符，不是文件数）")
    cap = int(config(root, "capacity.onboarding_max_chars", 12000))
    card_cap = int(config(root, "capacity.card_max_chars", 3000))
    if not cards:
        hist = sorted((root / "archives" / "done").glob("*.md"),
                      key=lambda p: p.stat().st_mtime, reverse=True) if (root / "archives" / "done").is_dir() else []
        if not hist:
            print("     当前无任务卡 —— 卡片模式下上手成本＝一个卡片文件的字数。")
            return
        # 无在途卡时用最近归档的一张做**历史样本**：它回答的是
        # "这个项目里，一张卡实际上长到多大"——正是"成本会不会随规模膨胀"的证据。
        c = hist[0]
        cc = _chars(c)
        print("     （无在途卡）历史样本：最近归档 %s —— 卡 %d 字符%s"
              % (c.stem[:30], cc, "" if cc <= card_cap else "  ← 超建议上限 %d" % card_cap))
        refs = _ref_reports(c, root)
        if refs:
            rc = sum(_chars(p) for p in refs)
            print("     连同其指针记录 %d 篇 %d 字符 → 那份工作的上手成本 ≈ %d 字符（上限 %d）"
                  % (len(refs), rc, cc + rc, cap))
        return
    # 选目标：优先在途的卡（承接/进度锚点非空），否则最近改过的那张
    def pick():
        busy = [c for c in cards if any(_card_fields(c).get(k, "—") not in ("—", "-", "", "[]")
                                       for k in ("承接", "进度锚点"))]
        pool = busy or cards
        return sorted(pool, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    card = pick()
    c_chars = _chars(card)
    refs = _ref_reports(card, root)
    r_chars = sum(_chars(p) for p in refs)
    total = c_chars + r_chars
    state = root / "STATE.md"
    print("     目标卡：%s" % card.stem[:40])
    print("     · 卡 %d 字符%s" % (c_chars, "" if c_chars <= card_cap else
                                  "  ← 超建议上限 %d：卡是**定位与指针**，不是档案（把内容写回记录）" % card_cap))
    print("     · 指针记录 %d 篇 %d 字符" % (len(refs), r_chars))
    print("     · 接手最小集 = %d 字符（上限 %d）%s"
          % (total, cap, "" if total <= cap else "  ← 超限：先写回（把增量压进卡）再交接"))
    if state.exists():
        print("     · 需要全局判断时再 ＋ STATE %d 字符 = %d"
              % (_chars(state), total + _chars(state)))
    print("     ⚠ 读进来的东西会**留在上下文里**：成本不是「读了几份」，是「带了多少字符走完整场对话」。")


# ── 人检：把「到点了」放进每次都会看的那一屏 ────────────────────
# 为什么要有这一段：人检标记已有机器戳与周期，到期也由 validate_workspace.py 判——
# 但那要人主动去跑它。**提示出现在「每次都会看的那一屏」，才叫提醒。**
# 到期＝戳的时间 + 周期：标记里没有 next 字段，**忘了复检会自己浮上来**，不需要谁记账。
HUMAN_MARK_RE = re.compile(r"#人检\s*\(([^)]*)\)")
STAMP_LIKE_RE = re.compile(r"^(git|host):[0-9a-fA-F]{4,40}@")


def show_human_checks(root: Path):
    """列出人检标记与（算出来的）账龄；超期的直接点名。"""
    period = float(config(root, "audit.human_check.period_days", 90))
    now = datetime.now().astimezone()
    rows, stale = [], 0
    for p in sorted(root.rglob("*.md")):
        if set(p.parts) & {"archives", "scripts", ".git", "__pycache__"}:
            continue
        _t = read(p) or ""
        try:              #  与 validate_workspace 同口径：先剥围栏块与行内代码，免得把示例计成标记
            from _common import strip_code as _sc
            _t = _sc(_t)
        except Exception:
            pass
        for i, line in enumerate(_t.splitlines(), 1):
            m = HUMAN_MARK_RE.search(line)
            if not m:
                continue
            d = {}
            for seg in m.group(1).split(","):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    d[k.strip()] = v.strip()
            age = None
            by = d.get("by", "—")
            if STAMP_LIKE_RE.match(by):
                ts = by.split("@", 1)[1]
                try:
                    if ts.endswith("Z"):
                        ts = ts[:-1] + "+00:00"
                    age = (now - datetime.fromisoformat(ts)).total_seconds() / 86400.0
                except Exception:
                    age = None
            over = age is not None and age > period
            stale += 1 if over else 0
            rows.append((over, p.relative_to(root), i, d.get("slot", "—"), by, age))
    print("[人检] 标记 %d 条 · 周期 %d 天" % (len(rows), int(period)))
    if not rows:
        print("     无 #人检 标记（未启用该机制时正常）")
        return
    rows.sort(key=lambda r: (-(r[5] or 0)))
    for over, rel, ln, slot, by, age in rows[:5]:
        print("     %s %s:%d  槽位=%s  %s"
              % ("[超期]" if over else "      ", rel, ln, slot,
                 ("账龄 %.0f 天" % age) if age is not None else by[:40]))
    if len(rows) > 5:
        print("     ……（其余 %d 条）" % (len(rows) - 5))
    print("     %s" % ("⚠ 有 %d 条超过复核周期——跑 validate_workspace.py 看完整报告" % stale
                      if stale else "均在复核周期内（到期由戳推导，不需要谁记账）"))

def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full = "--full" in sys.argv
    if not args:
        print("用法：python overview.py <工作区根> [--full]")
        return 0
    root = Path(args[0])
    if not root.is_dir():
        print("[地图] 目录不存在：%s（若为卡片模式，直接读卡片文件即可）" % root)
        return 0
    print(SEP)
    print("项目全貌 · %s" % root)
    print(SEP)
    show_map(root)
    print(SEP)
    show_state(root)
    print(SEP)
    show_index(root, full)
    print(SEP)
    show_cards(root)
    print(SEP)
    show_onboarding_cost(root, iter_cards(root))
    print(SEP)
    show_human_checks(root)
    n = len(iter_reports(root))
    print(SEP)
    print("[记录] reports %d 篇" % n)
    if not (root / "MAP.md").exists() and not (root / "STATE.md").exists():
        print()
        print("[建议] 既无 MAP 也无 STATE：本目录可能只是卡片模式的落点。")
        print("       若要升级为工作区，见 references/onboarding.md §1 的判定问句与 §3 初始化清单。")
    print(SEP)
    return 0


if __name__ == "__main__":
    sys.exit(run(main))
