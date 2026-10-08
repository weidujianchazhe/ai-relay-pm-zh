# -*- coding: utf-8 -*-
"""closeout.py —— 提交流程的机械步骤（把"手改共享文件"换成"跑脚本"）

用法：
    python closeout.py <管理区> new-record "<主题>" [--ai <标识>]
    python closeout.py <管理区> index-add --id <编号> --type <类型> --topic <主题> --record <路径> [--ai <标识>] [--date YYYY-MM-DD]
    python closeout.py <管理区> archive-reports
    python closeout.py <管理区> card-archive <卡文件名>
    python closeout.py <管理区> new-card "<卡名>" [--design] [--project P] [--module M] [--design-id DSN-... | --skip-design]
    python closeout.py <管理区> reviews-archive [--keep N] [--dry-run]
    python closeout.py <管理区> design-archive "<设计卡名>" [--dry-run]
    python closeout.py <管理区> claim   "<卡名>" --ai <标识> [--minutes N] [--steal "<理由>"]
    python closeout.py <管理区> release "<卡名>" --ai <标识> [--force]
    python closeout.py <管理区> repair [--dry-run]   # 半事务补偿（可重放、幂等）

为什么要有这个脚本：
    提交流程里有一半是**机械动作**——索引镜像写、溢出移行、滚动归档、交接号自增、记录骨架。
    这些动作手改的代价有两重：**烧 token**（模型逐字重写共享文件）与**写错**（实测：整行截断、
    冷热计数对不上、归档后索引指向没同步）。
    机械动作交给脚本：**零上下文成本、可重复、原子写**。人只做语义部分（写记录内容、判断下一步）。

依据：references/workflow.md §4（提交流程）、references/artifacts.md §5（索引 schema）
回本口径：每次提交省下"重写 INDEX 两处 + 数行数 + 移行 + 归档 + 查下一个交接号"的手工动作；
         一次写错导致索引截断的返工成本即已回本。
踩坑记录：
    · 冷区必须先写成功再动热区——反过来会出现"热区少了、冷区没有"的丢行；
    · 两个 4 位数分支号比较必须按**数值**，不能按字符串（EX9999 → EX10000）；
    · 溢出移行只移 [完成]/[废弃]，**[接力] 行留驻**，否则接手链断；
    · REVIEWS 滚动归档同理：**冷区先写成功再截热区**，且只按 `## ` 条目边界切——按行硬切会切碎一条记录。
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    config, index_rows, iter_cards, iter_reports, note, ok, problem, read, run, summary, tbd,
    usage_exit,  # noqa: E402
)
import lease  # noqa: E402  —— 任务租约与 CAS 原语（并发强制层，见 references/concurrency.md）

ID_RE = re.compile(r"^([A-Z]{2})([0-9]{4,5})$")
TYPES = ("[接力]", "[完成]", "[废弃]", "[里程碑]")
ROW_RE = re.compile(r"^\|\s*([A-Z]{2}[0-9]{4,5})\s*\|")


def _atomic_write(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


def _create_new(path: Path, text: str) -> bool:
    """**原子创建新文件**：文件已存在则失败，**绝不覆盖**；且**不产生半份文件**。

    为什么不用「先 exists() 再写」：那是 check-then-act——两个并发建卡能同时通过检查，
    后写者静默覆盖先写者。为什么也不直接 `O_EXCL` 后就写：那样**崩溃会留下半份卡**。

    做法（两步都是系统原子操作，且都不是新机制）：
      ① 唯一临时名 `O_EXCL` 写入并 flush（写坏只坏临时文件）；
      ② `os.link(tmp, path)` —— 目标已存在即失败（不覆盖），成功即**一步可见**（无半份）。
    `os.link` 不可用时（个别文件系统）退化为 `O_EXCL` 直写，并在返回值里如实降级。
    """
    tmp = path.with_name("%s.tmp.%d.%s" % (path.name, os.getpid(), secrets.token_hex(4)))
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        return False
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        os.link(str(tmp), str(path))      # 目标已存在 → FileExistsError（不覆盖）
        return True
    except FileExistsError:
        return False
    except OSError:
        # 文件系统不支持 link → 退化为 O_EXCL 直写（有半份窗口，已在文档声明）
        try:
            fd2 = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return False
        try:
            os.write(fd2, text.encode("utf-8"))
        finally:
            try:
                os.close(fd2)
            except OSError:
                pass
        return True
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
def _cas_write(root: Path, path: Path, text: str, expected: str, what: str) -> bool:
    """CAS 写入：把「比对 + 写」交给 lease.write_cas（同一临界区）。返回是否写入成功。

    为什么不能「读了自己算的那份就直接写」：脚本的读—改—写之间有窗口，
    另一个 AI 可能正好在这段窗口里写了同一文件——直接写下去就是**静默覆盖别人的改动**。
    冲突时：拒绝写入 + 生成 CONFLICT 文件（**拦不住的也要看得见**）。
    """
    okk, why, _h = lease.write_cas(path, text, expected)
    if not okk:
        p = lease.conflict_file(root, path.name,
                                "**写入被拒（CAS 失败）**：%s 的目标 %s 在读取之后被改动。\n\n- %s\n"
                                "- 处置：重新读取该文件 → 重新生成内容 → 再次提交" % (what, path.name, why))
        problem("%s 写入被拒：%s —— 已生成 %s，请重读后重做" % (what, why, p.name))
    return okk


# ── 索引表读写 ────────────────────────────────────────────────
def _split_index(txt: str):
    """→ (前段, 表头行, 分隔行, [数据行], 后段)。表结构保持原样，只动数据行。"""
    lines = (txt or "").splitlines()
    head = next((i for i, l in enumerate(lines) if l.strip().startswith("|") and "编号" in l), None)
    if head is None or head + 1 >= len(lines):
        return None
    sep = head + 1
    data, i = [], sep + 1
    while i < len(lines) and lines[i].strip().startswith("|"):
        data.append(lines[i])
        i += 1
    return lines[:head], lines[head], lines[sep], data, lines[i:]


def _row_id(line: str):
    m = ROW_RE.match(line.strip())
    return m.group(1) if m else None


def _sort_key(row_id: str):
    m = ID_RE.match(row_id)
    return (m.group(1), int(m.group(2))) if m else ("ZZ", 0)


def cmd_index_add(root: Path, a) -> int:
    idx = root / "INDEX.md"
    cold = root / "archives" / "INDEX_archived.md"
    if not idx.exists():
        problem("INDEX.md 不存在：%s" % idx)
        return summary()
    if not ID_RE.match(a.id):
        problem("编号格式非法（应为两位大写字母 + 4~5 位数字）：%s" % a.id)
        return summary()
    if a.type not in TYPES:
        problem("类型标记非法（应为 %s）：%s" % (" / ".join(TYPES), a.type))
        return summary()

    # 幂等：已在热区或冷区出现即拒绝——重复登记比漏登记更难查
    for p in (idx, cold):
        for cells, ln in index_rows(p):
            if cells and cells[0] == a.id:
                problem("编号已存在（%s:%d）：%s" % (p.name, ln, a.id))
                return summary()

    # 同分支严格递增（按数值）
    branch, num = ID_RE.match(a.id).groups()
    mx = 0
    for p in (idx, cold):
        for cells, _ in index_rows(p):
            m = ID_RE.match(cells[0])
            if m and m.group(1) == branch:
                mx = max(mx, int(m.group(2)))
    if int(num) <= mx:
        problem("同分支编号未递增：%s 的当前最大值为 %s%04d" % (a.id, branch, mx))
        return summary()

    row = "| %s | %s | %s | %s | %s | %s |" % (
        a.id, a.date, a.type, a.topic, a.ai, a.record)

    # ① 先写冷区（全量），成功后再动热区——顺序不可颠倒，否则丢行
    ctxt = read(cold)
    if ctxt is None:
        problem("冷区不存在：%s" % cold)
        return summary()
    _cold_hash = lease.norm_hash_text(ctxt)   # CAS 基准：读的那一刻的内容
    cparts = _split_index(ctxt)
    if cparts is None:
        problem("冷区表结构无法解析（缺「编号」表头）：%s" % cold)
        return summary()
    chead, cheadline, csep, cdata, ctail = cparts
    cdata = sorted(cdata + [row], key=lambda l: _sort_key(_row_id(l) or "ZZ"))
    if not _cas_write(root, cold, "\n".join(chead + [cheadline, csep] + cdata + ctail) + "\n",
                      _cold_hash, "冷区追加"):
        return summary()
    ok("冷区已追加：%s（现 %d 行）" % (a.id, len(cdata)))

    # ② 更新热区（同样 CAS：读的那一刻的哈希为基准）
    _hot_txt = read(idx) or ""
    _hot_hash = lease.norm_hash_text(_hot_txt)
    parts = _split_index(_hot_txt)
    if parts is None:
        problem("热区表结构无法解析：%s" % idx)
        return summary()
    head, headline, sep, data, tail = parts
    data = sorted(data + [row], key=lambda l: _sort_key(_row_id(l) or "ZZ"))

    # ③ 溢出移行：只移 [完成]/[废弃]，[接力] 留驻
    limit = config(root, "capacity.index_hot_rows", 20)
    moved = []
    while len(data) > limit:
        victim = next((l for l in data if "[完成]" in l or "[废弃]" in l), None)
        if victim is None:
            note("热区 %d 行超过上限 %s，但余下全是 [接力] 行——**按契约留驻，不移出**" % (len(data), limit))
            break
        data.remove(victim)
        moved.append(_row_id(victim))
    if not _cas_write(root, idx, "\n".join(head + [headline, sep] + data + tail) + "\n",
                      _hot_hash, "索引热区更新"):
        return summary()   # 冷区已写成功、热区失败：下次重跑会因为"编号已存在"被幂等拦下，可人工对齐
    ok("热区已更新：%d 行（上限 %s）" % (len(data), limit))
    if moved:
        ok("溢出移行（移入不删除）：%s" % "、".join(moved))
    note("下一步：跑 check_closeout.py 与 check_index.py 复核")
    return summary()


# ── 交接预填：机械字段自动、语义字段留白（见 references/workflow.md §4.3）──
def _git_lines(root: Path, args, limit: int = 12):
    """跑一条 git 命令取行；不可用/失败返回 None（**不伪造**）。"""
    try:
        p = subprocess.run(["git"] + list(args), cwd=str(root), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=10)
        if p.returncode != 0:
            return None
        out = p.stdout.decode("utf-8", "replace").strip().splitlines()
        return [l for l in out if l.strip()][:limit]
    except Exception:
        return None


CARD_LINE_RE = re.compile(r"^-\s*\*\*([^*]+)\*\*\s*[：:]\s*(.*)$", re.M)
CARD_ITEMS_RE = re.compile(r"^-\s*\*\*要点\*\*\s*[：:]\s*\n((?:[ \t]+[-*].*\n)+)", re.M)


def _card_fields(card: Path) -> dict:
    """卡的字段字典（只认 `- **字段**：值` 形）。

    与 overview.py 的同名函数**不是一回事**：那个只取卡板要用的四个字段（承接/进度锚点/状态/编号），
    这里取交接预填需要的（描述/要点/涉及/承接）。**两边的字段集合不同，不能互相顶替。**
    """
    txt = read(card) or ""
    out = {}
    for m in CARD_LINE_RE.finditer(txt):
        k = m.group(1).strip()
        if k not in out:
            out[k] = m.group(2).strip()
    m = CARD_ITEMS_RE.search(txt)
    if m:
        items = [re.sub(r"^[ \t]+[-*]\s*", "", l).strip() for l in m.group(1).splitlines()]
        items = [i for i in items if i and i not in ("—", "-")]
        if items:
            out["要点"] = items[0]
    return out


def _card_prefill(root: Path, card_name: str):
    """从任务卡取机械可派生的字段。返回 (卡路径或 None, 字段字典)。"""
    card = _find_card(root, card_name) if card_name else None
    if card is None:
        # 没指定就自动挑：优先「在途」（有有效租约或承接非空），否则最近改过的
        cards = iter_cards(root)
        if not cards:
            return None, {}
        busy = [c for c in cards if str(lease.lease_state(c)["owner"]) not in ("", "—", "-")]
        card = sorted(busy or cards, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    d = _card_fields(card)
    return card, d

def cmd_new_record(root: Path, a) -> int:
    rep = root / "reports"
    if not rep.is_dir():
        problem("reports/ 不存在：%s" % rep)
        return summary()
    ai = a.ai or "AI标识"
    title = a.topic.strip()
    if not title:
        problem("主题不能为空")
        return summary()
    name = "%s_%s_%s.md" % (a.date, re.sub(r'[\\/:*?"<>|]', "_", title), ai)
    dest = rep / name
    if dest.exists():
        problem("同名记录已存在：%s" % dest.name)
        return summary()

    # 交接号 = 现有最大值 + 1
    mx = 0
    for p in iter_reports(root):
        for m in re.finditer(r"交接\s*#(\d+)", read(p) or ""):
            mx = max(mx, int(m.group(1)))
    no = mx + 1

    # ── 预填：**只填机械可派生的，语义字段一律留 [待填]** ──────────────
    #  依据 change-control §A 第 4 条「写路径恒定」：提交流程上的字段必须机械派生
    #  （本地列举 / 单行查找 / 首句截取）。填不了的不许编——那违反数据诚实边界。
    TBD = "[待填]"
    card, cd = (None, {})
    if not a.no_prefill:
        card, cd = _card_prefill(root, a.card or "")

    def _v(key, default=TBD):
        v = str(cd.get(key, "") or "").strip()
        return default if v in ("", "—", "-", "[]") else v

    need = _v("描述")
    files = _v("涉及")
    nxt = _v("要点")
    if nxt != TBD:
        nxt = nxt.splitlines()[0].strip().lstrip("①②③④⑤ ").strip() or TBD

    git_ready = _git_lines(root, ["rev-parse", "--short", "HEAD"], 1) is not None
    changed, commits = None, None
    if git_ready:
        changed = _git_lines(root, ["diff", "--name-only", "HEAD"], 12)
        commits = _git_lines(root, ["log", "--oneline", "-n", "5"], 5)
    chg = TBD if not changed else "\n".join("- %s" % f for f in changed)
    if commits:
        chg += "\n\n最近提交：\n" + "\n".join("- %s" % c for c in commits)
    elif not git_ready:
        chg = "%s（未启用版本控制：改动点需人补，建议启用 git 以自动带 commit 哈希）" % TBD

    src = []
    if card is not None:
        src.append("任务卡 tasks/%s" % card.name)
    src.append("git" if git_ready else "无版本控制")
    body = (Path(__file__).resolve().parent / "templates" / "closeout_record.md").read_text(encoding="utf-8") % (title, no, " + ".join(src), need, files, chg, TBD,
       "%s（若本轮无设计级取舍，改写为「本轮无设计级取舍、未核设计文档」）" % TBD,
       nxt, "更新 tasks/%s 的要点与锚点，并同步 STATE" % (card.name if card else "（对应卡）"))
    _atomic_write(dest, body)
    ok("已生成记录骨架：reports/%s（交接 #%03d）" % (name, no))
    filled = sum(1 for x in (need, files, nxt) if x != TBD)
    note("机械字段预填 %d/3（需求 / 涉及 / 下一步）；**语义字段（验证结果 / 数据影响）留 [待填]**——"
         "它们要判断，自动填就是编" % filled)
    note("提交门禁会拦住仍含 [待填] 的记录：check_closeout.py 视为未提交完成")
    note("登记索引：python closeout.py <管理区> index-add --id <编号> --type [接力] --topic \"%s\" --record reports\\%s" % (title, name))
    return summary()


def cmd_archive_reports(root: Path, a) -> int:
    reports = iter_reports(root)
    limit = a.keep if a.keep is not None else config(root, "capacity.report_archive_threshold", 20)
    if len(reports) <= limit:
        ok("reports %d 篇，未达归档阈值 %s —— 无需归档" % (len(reports), limit))
        return summary()
    move = reports[: len(reports) - limit]
    arch = root / "archives"
    arch.mkdir(parents=True, exist_ok=True)
    done = []
    for p in move:
        tgt = arch / p.name
        if tgt.exists():
            note("目标已存在，跳过（不覆盖）：%s" % p.name)
            continue
        os.replace(p, tgt)
        done.append(p.name)
    ok("已归档 %d 篇至 archives/（保留最近 %s 篇）" % (len(done), limit))

    # 同步索引「交接文件」列：指向新位置，否则指针悬空
    fixed = 0
    for p in (root / "INDEX.md", arch / "INDEX_archived.md"):
        txt = read(p)
        if not txt:
            continue
        out = []
        for line in txt.splitlines():
            n = line
            for name in done:
                if ("reports\\" + name) in n or ("reports/" + name) in n:
                    n = n.replace("reports\\" + name, "archives\\" + name)
                    n = n.replace("reports/" + name, "archives/" + name)
                    fixed += 1
            out.append(n)
        if not _cas_write(root, p, "\n".join(out) + "\n", lease.hash_of_text(txt),
                          "归档后同步索引指向"):
            return summary()
    (ok if fixed else note)("索引「交接文件」列已同步指向 archives/（%d 处）" % fixed
                            if fixed else "索引中未出现被归档文件的指向（可能是存量写法）")
    note("归档后跑 check_index.py 复核冷热一致")
    return summary()


def cmd_card_archive(root: Path, a) -> int:
    src = _find_card(root, a.name)
    if src is None:
        problem("任务卡不存在：tasks/%s" % a.name)
        return summary()
    # 租约守卫：归档＝移动这张卡，属于"写它"。别人持有租约时必须先让出或等过期。
    #  带 --token 时额外做 fencing 判断（挡住"租约已被抢占、旧进程仍在写"的僵尸写者）。
    aired = getattr(a, "ai", "") or ""
    dst_dir = root / "archives" / "done"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        problem("目标已存在，不覆盖：archives/done/%s" % src.name)
        return summary()
    # **守卫与移动整体进临界区**
    #  若写成「guard → 复核哈希 → replace」：两步之间仍有窗口，只能缩小不能消除。
    #  现在两者在同一把锁里——与 write_cas 同级：对**守规矩的写者**（claim / 写卡同样走锁）是线性化的；
    #  对绕过入口直接改文件的写者，仍只能事后由漂移检测发现（边界表见 concurrency-internals.md §2）。
    # **业务侧只用唯一原语入口**（层界）：不碰 acquire/release 细节
    with lease.exclusive_resource(src) as _lock:
        if _lock is None:
            problem("拒绝归档：该卡正被其他写者持有——请稍后重试")
            return summary()
        gok, gwhy = lease.guard(root, src, aired, token=getattr(a, "token", None))
        if not gok:
            problem("拒绝归档：%s" % gwhy)
            return summary()
        if gwhy:
            note(gwhy)
        os.replace(src, dst)
    ok("已归档任务卡：tasks/%s → archives/done/%s（**不删卡**）" % (src.name, src.name))
    return summary()


# ── 建卡：用户说一句话 → 字段齐全的卡（任务卡 / 设计卡）────────────
# 字段名是**冻结值**（references/artifacts.md §2）：改这里的 CARD_SKELETON_FIELDS 必须同时改
# templates/tasks/TASK_CARD.template.md，否则 gen_views.py --check 会报红。
CARD_SKELETON_FIELDS = ["TASK-ID", "DESIGN-ID", "EVENT-ID", "状态", "描述", "要点", "代码根路径",
               "涉及", "承接", "进度锚点", "上次交接", "已提炼", "设计偏离", "派发摘录",
               "验收状态", "并发元数据"]
DESIGN_FIELDS = ["DESIGN-ID", "状态", "提议人", "定稿人", "定稿 EVENT-ID", "影响模式",
                 "范围与不变式", "角色/权限变化", "迁移与回滚", "验证证据", "拆分出的任务卡"]


def _serial() -> str:
    """6 位随机尾号。只用于唯一性，**不承担防伪职责**（防伪锚见 audit.md §2）。"""
    return "%06X" % int.from_bytes(os.urandom(3), "big")


def _render_task_card(name: str, project: str, module: str, design_id: str, day: str) -> str:
    L = [
        "# %s 任务卡" % name,
        "",
        "> 由 `scripts/closeout.py new-card` 生成。字段语义与质量门槛见 `references/artifacts.md` §3。",
        "",
        "━━━ 人读定位 ━━━",
        "项目：%s · 模块：%s" % (project, module),
        "任务：%s" % name,
        "状态：待认领 · 下一步：—",
        "━━━━━━━━━━━━━━━━",
        "",
        "- **TASK-ID**：TASK-%s-%s" % (day.replace("-", ""), _serial()),
        "- **DESIGN-ID**：%s" % (design_id or "—"),
        "- **EVENT-ID**：—",
        "- **状态**：待认领",
        "- **描述**：%s" % name,
        "- **要点**：",
        "  - ① —",
        "- **代码根路径**：[绝对工程路径，如 F:\\code\\project]",
        "- **涉及**：[文件路径列表，逗号分隔]",
        "- **承接**：—",
        "- **进度锚点**：—",
        "- **上次交接**：—",
        "- **已提炼**：—",
        "- **设计偏离**：—",
        "- **派发摘录**：—",
        "- **验收状态**：—",
        "- **并发元数据**：owner=—；revision=0；NORMALIZED-SHA256=—；写入方式=atomic rename；冲突文件=—",
        "",
        "---",
        "",
        "> **人读区由 AI 区机械派生**：任务行 ← 描述首句 · 状态行 ← 状态字段 · 下一步 ← 要点①。",
    ]
    return "\n".join(L) + "\n"


def _render_design_card(topic: str, mode: str, day: str, ds_id: str = "") -> str:
    L = [
        "# %s 设计卡" % topic,
        "",
        "> 由 `scripts/closeout.py new-card --design` 生成（**草案态**）。字段语义见 `references/artifacts.md`。",
        "",
        "- **DESIGN-ID**：%s" % (ds_id or ("DSN-%s-%s" % (day.replace("-", ""), _serial()))),
        "- **状态**：草案",
        "- **提议人**：[`scripts/stamp.py --ai-id` 产出的标识]",
        "- **定稿人**：—",
        "- **定稿 EVENT-ID**：—",
        "- **影响模式**：%s" % mode,
        "- **范围与不变式**：[目标 / 非目标 / 必须保持的协议约束]",
        "- **角色/权限变化**：[新增 owner、审计或裁决责任；无则「—」]",
        "- **迁移与回滚**：[文件集、兼容策略、失败处理]",
        "- **验证证据**：[检查 / fixture / 命令及结果]",
        "- **拆分出的任务卡**：—",
        "",
        "> **配套蓝图**：同目录 `<主题>.blueprint.html` 必须存在（结构视图，给人看）。",
        "> **归档**：全部拆完或作废后跑 `closeout.py <管理区> design-archive <主题>`，两份文件一起移入 `designs\\archives\\`。",
        "",
        "## 生命周期门禁",
        "",
        "1. 草案 → 评审中：补齐范围、权限、迁移与验证证据。",
        "2. 评审中 → 已定稿/已拒绝：管理者写定稿或拒绝 EVENT-ID；**未定稿不得生成任务卡**。",
        "3. 已定稿 → 任务卡：每张任务卡填写本 DESIGN-ID，并生成新的 TASK-ID。",
        "3b. **已定稿 → 暂不实施·基线保留**：设计**有效但不立即实施**（未来规划 / 架构基线 / 设计库存）——**合法状态**，不产生任务、不归档。",
        "3c. **设计变更传播**：设计变更（v1→v2 / 废弃）必须登记「受影响结构」与「受影响任务」并写 EVENT-ID——不得只改 Markdown。",
        "3d. **任务完成 ≠ 设计失效**：任务全部完成不使设计失效；它可能仍是当前工程基线，继续作为对照依据。",
        "4. 已定稿 → 已废弃：管理者写废弃 EVENT-ID；已生成的任务卡不回写历史，只按新决策处理。",
    ]
    return "\n".join(L) + "\n"



#: 蓝图的必备节（与 templates/designs/DESIGN_BLUEPRINT.template.md 同源；gen_views.py 会核对）
BLUEPRINT_SECTIONS = ["现状 → 目标", "结构与依赖", "改动点清单", "数据与调用流",
                      "拆分出的执行任务", "风险与未决"]


def _render_blueprint(topic: str, mode: str, day: str, ds_id: str) -> str:
    """设计蓝图 = 人读结构视图，载体为 HTML（契约见 references/design.md §0/§1）。

    必备节与 templates/designs/DESIGN_BLUEPRINT.template.html 同源（gen_views.py 会核对）。
    """
    secs = ["现状 → 目标","结构与依赖","改动点","数据与调用流","拆分出的执行任务","风险与未决","实施依据"]
    body = []
    for i, s in enumerate(secs, 1):
        body.append("  <div class=card><h2>%d、%s</h2>" % (i, s))
        if s == secs[2]:
            body.append("    <table><tr><th>#</th><th>文件 / 位置</th><th>动作</th><th>一句话</th></tr><tr><td>1</td><td></td><td></td><td></td></tr></table>")
        elif s == secs[4]:
            body.append("    <table><tr><th>顺序</th><th>TASK-ID</th><th>任务</th><th>依赖</th></tr><tr><td>1</td><td>—</td><td></td><td></td></tr></table>")
        elif s == secs[5]:
            body.append("    <ul><li>[ ] 未决问题 / 需要用户拍板的选择</li></ul>")
        elif s == secs[6]:
            body.append("    <ul><li>① 这项工作在<strong>项目整体结构中的位置</strong>：</li><li>② 实施时<strong>依据什么结构</strong>（落点 / 影响面 / 顺序与依赖 / 可独立与不可独立）：</li></ul>")
        else:
            body.append("    <pre>（填写：%s）</pre>" % s)
        body.append("  </div>")
    head = [
        "<!DOCTYPE html>",
        chr(60) + "html lang=zh-CN" + chr(62),
        chr(60) + "head" + chr(62) + chr(60) + "meta charset=UTF-8" + chr(62),
        chr(60) + "title" + chr(62) + topic + " · 设计蓝图" + chr(60) + "/title" + chr(62),
        chr(60) + "style" + chr(62) + "body{font-family:PingFang SC,Microsoft YaHei,Segoe UI,Arial,sans-serif;background:#F4F3EE;color:#1A1B1C;line-height:1.7;padding:24px}",
        ".wrap{max-width:980px;margin:0 auto}.card{background:#FFF;border:1px solid #E4E3DD;border-radius:12px;padding:16px 20px;margin-bottom:14px}",
        "h2{font-size:15.5px;margin-bottom:8px}table{width:100%;border-collapse:collapse}",
        "th,td{border:1px solid #E4E3DD;padding:6px 9px;font-size:12.5px;text-align:left;vertical-align:top}th{background:#F1F0EB}",
        "pre{background:#F7F6F2;border:1px solid #E4E3DD;border-radius:8px;padding:10px 12px;font-size:12.5px}" + chr(60) + "/style" + chr(62) + chr(60) + "/head" + chr(62),
        chr(60) + "body" + chr(62) + chr(60) + "div class=wrap" + chr(62),
        chr(60) + "div class=hd" + chr(62) + chr(60) + "h1" + chr(62) + "设计蓝图 · " + topic + chr(60) + "/h1" + chr(62),
        chr(60) + "div class=meta" + chr(62) + "DESIGN-ID：" + ds_id + " ｜ 状态：草案 ｜ 日期：" + day + " ｜ 影响模式：" + mode + " ｜ 配套详述：同目录 " + topic + ".md" + chr(60) + "/div" + chr(62),
        chr(60) + "div class=meta" + chr(62) + "人读的结构视图：不放长段落（上限 {{config:capacity.blueprint_max_para_chars}} 字符）；总行数上限 {{config:capacity.blueprint_max_lines}}（<strong>超限仅提醒</strong>）。" + chr(60) + "/div" + chr(62) + chr(60) + "/div" + chr(62),
    ]
    return "\n".join(head + body + [chr(60) + "/div" + chr(62) + chr(60) + "/body" + chr(62), ""])

# ── 任务认领（租约）：把「请遵守单写者」变成「脚本会拒绝」──────────
def _find_card(root: Path, name: str):
    """按文件名或卡名（stem）找活跃任务卡；找不到返回 None。"""
    src = root / "tasks" / name
    if src.exists():
        return src
    cand = [c for c in iter_cards(root) if c.stem == Path(name).stem]
    return cand[0] if cand else None


def cmd_claim(root: Path, a) -> int:
    """认领任务：写 owner + 租约 + 到期时间（字段落在既有的「并发元数据」行里）。"""
    if not a.ai:
        problem("需要 --ai <标识>（由 scripts/stamp.py --ai-id 产生；**不得自报姓名**）")
        return summary()
    card = _find_card(root, a.name)
    if card is None:
        problem("任务卡不存在：tasks/%s" % a.name)
        return summary()
    minutes = a.minutes or int(config(root, "collaboration.lease_minutes", 30))
    if a.steal is not None and not str(a.steal).strip():
        problem("--steal 必须写明理由（抢占会留痕，理由不能空）")
        return summary()
    okk, why = lease.claim(root, card, a.ai, minutes, a.steal or "")
    (ok if okk else problem)(why)
    if okk:
        note("离开或让出前跑 release；忘了也没关系——租约到期后别人可自动接手")
        note("建议顺手留一条运行证据（谁在什么运行时/模型上接手）："
             "python scripts/stamp.py --evidence --append --root <管理区>")
    return summary()


def cmd_release(root: Path, a) -> int:
    """释放租约（保留「承接」：认领关系是历史，租约是当下的占用）。"""
    if not a.ai:
        problem("需要 --ai <标识>")
        return summary()
    card = _find_card(root, a.name)
    if card is None:
        problem("任务卡不存在：tasks/%s" % a.name)
        return summary()
    okk, why = lease.release(root, card, a.ai, a.force)
    (ok if okk else problem)(why)
    return summary()

def cmd_new_card(root: Path, a) -> int:
    #  值类口径（机检）：任务卡必须显式表态——--design-id DSN-… 或 --skip-design；
    #  跳过设计必须显式表态，不许留空或「—」（见 references/design.md「先跳过」）。
    if not getattr(a, "design", False):
        if getattr(a, "skip_design", False) and getattr(a, "design_id", ""):
            problem("--design-id 与 --skip-design 只能给一个（二选一）"); return 3
        if getattr(a, "skip_design", False):
            a.design_id = "先跳过"
        elif getattr(a, "design_id", ""):
            if not str(a.design_id).startswith("DSN-"):
                problem("--design-id 必须是 DSN-YYYYMMDD-XXXXXX（见 references/design.md）；收到：%s" % a.design_id); return 3
        else:
            problem("建任务卡必须显式表态：给 --design-id DSN-… 或 --skip-design（跳过设计）")
            note("例：closeout.py <管理区> new-card <卡名> --skip-design"); return 3
    name = (a.name or "").strip()
    if not name:
        problem("卡名不能为空")
        return summary()
    safe = re.sub(r'[\\/:*?"<>|]', "_", name)
    if a.design:
        d = root / "designs"
        d.mkdir(parents=True, exist_ok=True)
        dest = d / ("%s.md" % safe)
        bp = d / ("%s.blueprint.html" % safe)
        mode = a.mode or str(config(root, "collaboration.mode", "light"))
        ds_id = "DSN-%s-%s" % (a.date.replace("-", ""), _serial())
        # **两份文件一起建**：一份设计就是两件套（references/design.md §1）。
        # 用原子创建（O_EXCL）：同名已存在即失败，**不会静默覆盖**（并发建同名也不再互相覆盖）。
        if not _create_new(dest, _render_design_card(name, mode, a.date, ds_id)):
            problem("同名设计卡已存在（或无法创建），不覆盖：designs/%s.md" % safe)
            return summary()
        if not _create_new(bp, _render_blueprint(name, mode, a.date, ds_id)):
            note("蓝图未创建（同名已存在）：designs/%s.blueprint.html" % safe)
        ok("已建设计卡：designs/%s.md（详述）+ designs/%s.blueprint.html（蓝图）（状态＝草案）" % (safe, safe))
        note("**先填蓝图**（结构：现状→目标 / 改动点 / 拆分）给用户确认方向；确认后再补详述")
        note("补齐详述的「范围与不变式 / 迁移与回滚 / 验证证据」；定稿后按定稿结论建任务卡（未定稿不生成任务卡）")
        return summary()
    t = root / "tasks"
    if not t.is_dir():
        problem("tasks/ 不存在：%s" % t)
        return summary()
    dest = t / ("%s.md" % safe)
    if not _create_new(dest, _render_task_card(name, a.project, a.module, a.design_id, a.date)):
        problem("同名任务卡已存在（或无法创建），不覆盖：tasks/%s.md" % safe)
        return summary()
    ok("已建任务卡：tasks/%s.md（状态＝待认领）" % safe)
    note("下一步：补齐「要点」（可执行动作：做什么 + 在哪文件）与「代码根路径」；认领时填「承接」")
    return summary()


# ── REVIEWS 滚动归档：留痕只增不删，但读取面有界（artifacts.md §8）────
def cmd_reviews_archive(root: Path, a) -> int:
    p = root / "REVIEWS.md"
    if not p.exists():
        problem("REVIEWS.md 不存在：%s" % p)
        return summary()
    txt = read(p)
    if txt is None:
        problem("REVIEWS.md 不可读（编码或权限问题）")
        return summary()
    lines = txt.rstrip("\n").split("\n")
    keep = a.keep if a.keep else int(config(root, "capacity.reviews_hot_lines", 200) or 200)
    if len(lines) <= keep:
        ok("REVIEWS.md %d 行，未超热区上限 %s——无需归档" % (len(lines), keep))
        return summary()
    starts = [i for i, l in enumerate(lines) if l.startswith("## ")]
    cut = None
    for i in starts:
        if len(lines) - i <= keep:
            cut = i
            break
    if not starts or cut is None or cut <= starts[0]:
        problem("找不到可切的条目边界（需保留 %s 行）——**拒绝按行硬切**，避免切碎一条记录" % keep)
        return summary()
    head, move, stay = lines[:starts[0]], lines[starts[0]:cut], lines[cut:]
    if not move:
        ok("REVIEWS.md 无可归档条目（仅有标题与前言）")
        return summary()
    cold = root / "archives" / "REVIEWS_archived.md"
    if a.dry_run:
        ok("预览：将移出 %d 行 → archives/REVIEWS_archived.md；热区保留 %d 行" % (len(move), len(head) + len(stay)))
        return summary()
    cold.parent.mkdir(parents=True, exist_ok=True)
    prev_orig = read(cold)
    prev = prev_orig
    if not prev:
        prev = ((Path(__file__).resolve().parent / "templates" / "closeout_cmd_reviews_archive.md").read_text(encoding="utf-8"))
    if not prev.endswith("\n"):
        prev += "\n"
    # **冷区先写成功，再截热区**——反过来会出现「热区少了、冷区没有」的丢行。
    #  两处都是共享文件 → 都走 CAS；**这不是事务**：冷区成功而热区冲突时，
    #  结果是「两处都有」（重复但不丢失），重跑 reviews-archive 可收敛（见 api 端点表的原子性列）。
    if not _cas_write(root, cold, prev + "\n".join(move).rstrip("\n") + "\n",
                      lease.hash_of_text(prev_orig if prev_orig else prev), "REVIEWS 冷区归档"):
        return summary()
    if not _cas_write(root, p, "\n".join(head + stay).rstrip("\n") + "\n",
                      lease.hash_of_text(txt), "REVIEWS 热区截断"):
        return summary()
    ok("REVIEWS 滚动归档：移出 %d 行 → archives/REVIEWS_archived.md（未删除任何内容）" % len(move))
    ok("热区保留 %d 行（上限 %s）" % (len(head + stay), keep))
    return summary()



# ── 设计归档：走完流程的设计卡移入 designs/archives/ ──────────────
# 触发条件（references/design.md §4，满足其一）：
#   ① 已定稿 **且**「拆分出的任务卡」非空 **且** 每个 TASK-ID 都能在 tasks/ 或 archives/done/ 找到
#   ② 状态 ∈ {已废弃, 已拒绝}
# 判据取自**痕迹**不是声明：用户说"拆完了"不算数，"列出的任务卡确实存在"才算（audit.md §2.0）。
DESIGN_STATES = ("草案", "评审中", "已定稿", "已拒绝", "已废弃")
DESIGN_VOID = ("已废弃", "已拒绝")


def _field_of(txt: str, name: str):
    m = re.search(r"^-\s*\*\*%s\*\*\s*[：:]\s*(.*?)\s*$" % re.escape(name), txt, re.M)
    return None if m is None else m.group(1).strip()


def _task_id_exists(root: Path, tid: str) -> bool:
    for base in (root / "tasks", root / "archives" / "done"):
        if not base.is_dir():
            continue
        for p in base.glob("*.md"):
            if tid in (read(p) or ""):
                return True
    return False


def cmd_design_archive(root: Path, a) -> int:
    d = root / "designs"
    if not d.is_dir():
        problem("designs/ 不存在：%s" % d)
        return summary()
    stem = Path((a.name or "").strip()).stem
    if not stem:
        problem("设计卡名不能为空")
        return summary()
    src = d / ("%s.md" % stem)
    if not src.exists():
        cand = [p for p in d.glob("*.md") if p.stem == stem]
        if not cand:
            problem("活跃设计区里没有这份设计：designs/%s.md" % stem)
            return summary()
        src = cand[0]
        stem = src.stem
    bp = d / ("%s.blueprint.html" % stem)
    txt = read(src)
    if txt is None:
        problem("设计详述不可读：designs/%s.md" % stem)
        return summary()
    state = _field_of(txt, "状态") or ""
    if state not in DESIGN_STATES:
        problem("状态字段读不出或不在五态内（读到「%s」）—— 设计卡结构见 references/design.md §6" % state)
        return summary()

    if state in DESIGN_VOID:
        ok("触发条件②：设计%s" % state)
    elif state == "已定稿":
        raw_ids = _field_of(txt, "拆分出的任务卡")
        if raw_ids is None:
            problem("缺少「拆分出的任务卡」字段——它是归档门禁判据，不能省（见 references/design.md §4）")
            return summary()
        if raw_ids in ("—", "-", ""):
            problem("状态＝已定稿，但「拆分出的任务卡」仍是「—」：触发条件①不成立（设计尚未拆完）")
            note("若这份设计最终不做了，应先把状态改为「已废弃」再归档——**不要用归档掩盖未拆完**")
            return summary()
        ids = re.findall(r"TASK-[0-9]{8}-[0-9A-Z]{6}", raw_ids)
        if not ids:
            problem("「拆分出的任务卡」里没有合法 TASK-ID：%s" % raw_ids[:60])
            return summary()
        missing = [t for t in ids if not _task_id_exists(root, t)]
        if missing:
            problem("声明拆出的任务卡在工作区里找不到：%s" % "、".join(missing))
            note("声明与痕迹不符 —— 拒绝归档（先建卡，或把该 ID 从字段里去掉）")
            return summary()
        ok("触发条件①：已定稿，且列出的 %d 张任务卡均存在" % len(ids))
    else:
        problem("状态「%s」不在归档触发条件内（需：已定稿且拆完 / 已废弃 / 已拒绝）" % state)
        return summary()

    if not bp.exists():
        problem("配套蓝图缺失：designs/%s.blueprint.html —— **两份文件必须一起移**，缺一份不算完整设计" % stem)
        return summary()
    dst_dir = d / "archives"
    if a.dry_run:
        ok("预览：designs/%s.md + designs/%s.blueprint.html → designs/archives/" % (stem, stem))
        return summary()
    for p in (src, bp):
        if (dst_dir / p.name).exists():
            problem("归档目标已存在，不覆盖：designs/archives/%s" % p.name)
            return summary()
    dst_dir.mkdir(parents=True, exist_ok=True)
    for p in (src, bp):
        os.replace(p, dst_dir / p.name)
    ok("已归档设计：designs/%s{.md, .blueprint.html} → designs/archives/（两份一起移，**未删除**）" % stem)
    note("设计卡不进 INDEX / 不动快照 —— 设计区的进出不产生索引维护成本")
    return summary()


# ── 端点契约：工作区写操作的 API surface（从实现导出，不手抄）──────
#  为什么要有这张表：折中方案＝「要 API 的语义，不要 API 的常驻成本」。
#  语义要成立，必须能回答三个问题：**有哪些写操作 / 每个受什么保护 / 失败是什么样**。
#  元数据放在这里，随实现一起改；打印由 api 子命令做，登记完整性由 gen_views 检查。
#  **原子性列**（评审要求写明，也是使用者最容易误解的一处）：
#    · atomic      —— 单文件、CAS 保护：读到的要么旧要么新，不会半成品
#    · best-effort —— 多文件操作：**不是事务**。可能"部分成功"，重跑可收敛（幂等或跳过）
#    · new-file    —— 只创建新文件：没有竞争者，天然安全
#    · read-only   —— 不写盘
#  **CAS 解决"覆盖"，不解决"事务"**——把这两件事混起来，使用者会以为多文件操作是全或无的。
ENDPOINTS = {
    "new-record":     ("生成 6+1 交接记录骨架（预填机械字段）", "追加（新文件）", "—", "[待填] 未补齐则提交门禁拦", "new-file"),
    "index-add":      ("索引镜像写：冷区追加 + 热区按序插入 + 溢出移行", "否（编号重复即拒）", "CAS（冷区 + 热区各一次）", "冷区已写而热区冲突 → 幂等拦重复，人工对齐", "best-effort"),
    "archive-reports":("滚动归档 reports 并同步索引指向", "否", "移动时同名跳过 + 索引 CAS", "目标同名则跳过，不覆盖", "best-effort"),
    "card-archive":   ("完成任务卡移入 archives/done/", "否", "**锁内**租约守卫（--ai）＋ fencing（--token）", "他人持租约即拒", "atomic"),
    "new-card":       ("建任务卡 / 设计卡骨架（--design 一次建两件套）", "追加（新文件）", "—", "同名即拒，不覆盖", "new-file"),
    "reviews-archive":("REVIEWS 溢出滚动归档（只增不删）", "否", "CAS（冷区 + 热区各一次）", "切点非条目边界则拒", "best-effort"),
    "design-archive": ("设计卡归档（详述 + 蓝图一起移）", "否", "触发条件校验（拆完 / 作废）", "条件不成立即拒", "best-effort"),
    "claim":          ("认领任务（写 owner + 租约 + 到期 + fencing）", "否（重复 claim = 续约，令牌自增）", "租约 + 漂移检测 + CAS", "他人持有效租约即拒；--steal 需理由", "atomic"),
    "release":        ("释放租约（保留「承接」）", "是", "租约归属校验 + CAS", "非持有者即拒（--force 留痕）", "atomic"),
    "repair":         ("半事务补偿：索引冷热 / 指向 / 崩溃残留", "**是**（跑第二遍报无需修复）", "CAS（每处写入前比对）", "CAS 冲突即停并留痕", "best-effort"),
    "api":            ("打印本表（只读，视图）", "是", "—", "恒退出 0", "read-only"),
}


def cmd_api(a) -> int:
    """打印端点契约表：命令名与参数取自解析器（实现），保护与失败语义取自 ENDPOINTS。"""
    ap = build_parser()
    # 从解析器里取子命令：走 _actions 找 _SubParsersAction，比 _subparsers 私有属性稳
    sub_actions = [x for x in ap._actions if isinstance(x, argparse._SubParsersAction)]
    subs = list(sub_actions[0].choices.items()) if sub_actions else []
    print("== 工作区业务写端点（唯一入口：scripts/closeout.py）==")
    print("%s" % "-" * 124)
    print("%-17s %-30s %-10s %-24s %-30s %s" % ("端点", "作用", "幂等", "并发保护", "失败语义", "原子性"))
    print("%s" % "-" * 124)
    for name, p in subs:
        meta = ENDPOINTS.get(name)
        if meta is None:
            print("%-17s %-30s %-10s %-24s %-30s %s" % (name, (p.description or "")[:30], "?", "**未登记**", "—", "?"))
            continue
        print("%-17s %-30s %-10s %-24s %-30s %s" % (name, meta[0][:30], meta[1], meta[2], meta[3], meta[4]))
    print("%s" % "-" * 124)
    print("原子性：atomic＝单文件 CAS（不会半成品）· best-effort＝多文件（**不是事务**，可能部分成功、重跑可收敛）· new-file · read-only")
    print("%s" % "-" * 108)
    print("退出码：0 全通过 · 1 有[问题] · 2 仅[待核] · 3 脚本自身错误")
    print("调用方式：python closeout.py <管理区> <端点> [参数] —— 任何语言可调，看退出码")
    print("写操作一律经此入口；直接编辑共享文件＝绕过，由 check_closeout.py 的哈希漂移检测抓（见 references/concurrency.md §0）")
    return 0


# ── 半事务补偿（可重放，幂等）：把「仅事后检测」提到「最终一致」──────
#  为什么放在 closeout 里而不是独立脚本：它要**写共享文件**——
#  一旦独立成第二个脚本，「唯一写入口」就成了空话（第 10 节也会把它当未登记写者抓出来）。
def _repair_index(root: Path, dry: bool) -> int:
    idx, cold = root / "INDEX.md", root / "archives" / "INDEX_archived.md"
    itxt, ctxt = read(idx), read(cold)
    if itxt is None or ctxt is None:
        note("缺 INDEX.md 或冷区——跳过索引一致性补偿")
        return 0
    hot = {c[0]: c for c, _ in index_rows(idx)}
    cl = {c[0]: c for c, _ in index_rows(cold)}
    # 冷区有、热区没有：只有 [接力] 该回热区；[完成]/[废弃] 不在热区是**溢出移行的正常结果**，补了反而破坏契约
    to_hot = [cells for i, cells in cl.items() if i not in hot and "接力" in (cells[2] if len(cells) > 2 else "")]
    to_cold = [cells for i, cells in hot.items() if i not in cl]
    if not to_hot and not to_cold:
        ok("索引冷热一致（热 %d 行 / 冷 %d 行）——无需修复" % (len(hot), len(cl)))
        return 0
    if dry:
        note("预览：需补回热区 %d 行、补入冷区 %d 行" % (len(to_hot), len(to_cold)))
        return 0
    for path, txt, rows, what in ((idx, itxt, to_hot, "补回热区"), (cold, ctxt, to_cold, "补入冷区")):
        if not rows:
            continue
        parts = _split_index(txt)
        if parts is None:
            problem("%s 表结构无法解析——拒绝改写" % path.name)
            return -1
        head, headline, sep, data, tail = parts
        add = ["| %s |" % " | ".join(c) for c in rows]
        data = sorted(data + add, key=lambda l: _sort_key(_row_id(l) or "ZZ"))
        if not _cas_write(root, path, "\n".join(head + [headline, sep] + data + tail) + "\n",
                          lease.hash_of_text(txt), "半事务补偿：%s" % what):
            return -1
    note("[已修复] 索引一致性：补回热区 %d 行、补入冷区 %d 行（重跑本命令应报无需修复）"
         % (len(to_hot), len(to_cold)))
    return len(to_hot) + len(to_cold)


def _repair_pointers(root: Path, dry: bool) -> int:
    arch = root / "archives"
    if not arch.is_dir():
        return 0
    moved = {p.name for p in arch.glob("*.md")}
    fixed = 0
    for p in (root / "INDEX.md", arch / "INDEX_archived.md"):
        txt = read(p)
        if not txt:
            continue
        out, hit = [], 0
        for line in txt.splitlines():
            n = line
            for name in moved:
                if ("reports\\" + name) in n:
                    n = n.replace("reports\\" + name, "archives\\" + name)
                    hit += 1
                if ("reports/" + name) in n:
                    n = n.replace("reports/" + name, "archives/" + name)
                    hit += 1
            out.append(n)
        if hit:
            if dry:
                note("预览：%s 需修正 %d 处指向" % (p.name, hit))
                continue
            if not _cas_write(root, p, "\n".join(out) + "\n", lease.hash_of_text(txt),
                              "半事务补偿：修正指向"):
                return -1
            fixed += hit
    note("[已修复] 索引指向：修正 %d 处（指向已归档的记录）" % fixed) if fixed else ok("索引指向无需修复")
    return fixed


def _repair_temp(root: Path, dry: bool) -> int:
    if dry:
        n, _ = lease.sweep_temp(root, older_than=0)
        note("预览：可清理崩溃残留 %d 个" % n)
        return 0
    n, names = lease.sweep_temp(root)
    if n:
        note("[已修复] 清理崩溃残留临时文件 %d 个：%s" % (n, "、".join(names[:5])))
    else:
        ok("无崩溃残留临时文件")
    return n


def cmd_repair(root: Path, a) -> int:
    """半事务的**可重放补偿**：幂等地把不一致补齐（跑第二遍报「无需修复」）。"""
    dry = bool(getattr(a, "dry_run", False))
    print("== 半事务补偿（可重放，幂等）%s ==" % ("（预览）" if dry else ""))
    for fn, label in ((_repair_index, "索引冷热一致性"),
                      (_repair_pointers, "索引指向"),
                      (_repair_temp, "崩溃残留")):
        print("-- " + label)
        try:
            fn(root, dry)
        except Exception as e:
            problem("%s 补偿异常：%s: %s" % (label, type(e).__name__, e))
    return summary()

def build_parser():
    """构造命令行解析器。

    **抽出来是为了让「端点契约」可以从实现导出**：`closeout.py api` 与
    `gen_views.py` 的端点登记检查都调用它——契约不能是手抄的第二份副本。
    """
    ap = argparse.ArgumentParser(description="工作区业务写操作唯一入口（索引镜像写 / 归档 / 建卡 / 设计归档 / 任务认领 / 半事务补偿）")
    ap.add_argument("root")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("new-record", help="生成 6+1 骨架记录（自动取下一个交接号）")
    p1.add_argument("topic")
    p1.add_argument("--ai", default="")
    p1.add_argument("--date", default=date.today().isoformat())
    p1.add_argument("--card", default="", help="要交接的任务卡（不给则自动挑在途/最近的卡）")
    p1.add_argument("--no-prefill", action="store_true", help="只出空骨架，不预填机械字段")

    p2 = sub.add_parser("index-add", help="索引镜像写：冷区追加 + 热区按序插入 + 溢出移行")
    p2.add_argument("--id", required=True)
    p2.add_argument("--type", required=True, dest="type")
    p2.add_argument("--topic", required=True)
    p2.add_argument("--record", required=True)
    p2.add_argument("--ai", default="AI标识")
    p2.add_argument("--date", default=date.today().isoformat())

    p3 = sub.add_parser("archive-reports", help="滚动归档 reports 并同步索引指向")
    p3.add_argument("--keep", type=int, default=None)

    p4 = sub.add_parser("card-archive", help="完成任务卡移入 archives/done/（不删卡）")
    p4.add_argument("name")
    p4.add_argument("--ai", default="", help="操作者标识；填了才做租约守卫（别人持有租约时拒绝归档）")
    p4.add_argument("--token", default=None, help="claim 时回显的 fencing 令牌；带上可挡住僵尸写者")

    p5 = sub.add_parser("new-card", help="建任务卡 / 设计卡骨架（用户说一句话，AI 落卡）")
    p5.add_argument("name")
    p5.add_argument("--design", action="store_true", help="建的是设计卡（草案态，进 designs/）")
    p5.add_argument("--project", default="[项目名称]")
    p5.add_argument("--module", default="[模块]")
    p5.add_argument("--design-id", default="", help="任务卡关联的设计卡 ID（已定稿的设计卡）")
    p5.add_argument("--skip-design", action="store_true", help="显式跳过设计：任务卡 DESIGN-ID 写「先跳过」（与 --design-id 二选一）")
    p5.add_argument("--mode", default="", help="设计卡的影响模式；默认取实例 MAP 的协作模式")
    p5.add_argument("--date", default=date.today().isoformat())

    p6 = sub.add_parser("reviews-archive", help="REVIEWS 溢出滚动归档（只增不删，热区留尾部）")
    p6.add_argument("--keep", type=int, default=None, help="热区保留行数；默认取 capacity.reviews_hot_lines")
    p6.add_argument("--dry-run", action="store_true", help="只预览，不写盘")

    p8 = sub.add_parser("claim", help="认领任务（写 owner + 租约 + 到期时间，落到「并发元数据」行）")
    p8.add_argument("name")
    p8.add_argument("--ai", default="", help="认领者标识（stamp.py --ai-id 产生）")
    p8.add_argument("--minutes", type=int, default=None, help="租约时长；默认取 collaboration.lease_minutes")
    p8.add_argument("--steal", default=None, help="抢占他人有效租约；**必须写明理由**（会留痕）")

    pr = sub.add_parser("repair", help="半事务补偿（可重放、幂等）：索引冷热 / 指向 / 崩溃残留")
    pr.add_argument("--dry-run", action="store_true", help="只预览，不写盘")

    pa = sub.add_parser("api", help="打印业务写端点契约表（从实现导出，非手抄）")
    pa.add_argument("root", nargs="?", default=".")

    p9 = sub.add_parser("release", help="释放租约（保留「承接」）")
    p9.add_argument("name")
    p9.add_argument("--ai", default="")
    p9.add_argument("--force", action="store_true", help="释放他人持有的租约（会留痕）")

    p7 = sub.add_parser("design-archive", help="走完流程的设计卡移入 designs/archives/（详述+蓝图一起移）")
    p7.add_argument("name")
    p7.add_argument("--dry-run", action="store_true", help="只预览，不写盘")

    return ap


def main() -> int:
    a = usage_exit(build_parser()).parse_args()
    if a.cmd == "api":
        return cmd_api(a)
    root = Path(a.root)
    if not root.is_dir():
        problem("管理区不存在：%s" % root)
        return summary()
    #  这里**不放开关**：任何「若为假只打一句 note 就继续执行」的分支都是
    #  「声称跳过而实际执行」。三个读不到也不生效的开关**不登记**（见 _common.BOOL_KEYS 的说明）。
    return {"new-record": cmd_new_record, "index-add": cmd_index_add,
            "archive-reports": cmd_archive_reports, "card-archive": cmd_card_archive,
            "new-card": cmd_new_card, "reviews-archive": cmd_reviews_archive,
            "design-archive": cmd_design_archive,
            "claim": cmd_claim, "release": cmd_release,
            "repair": cmd_repair}[a.cmd](root, a)


if __name__ == "__main__":
    sys.exit(run(main))
