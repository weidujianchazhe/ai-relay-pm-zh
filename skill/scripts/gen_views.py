# NOPMD: 本文件是门禁规则的唯一实现处，每条检查必须就地写明判据与反例；注释是规格的一部分，不是复述代码。
# -*- coding: utf-8 -*-
"""gen_views.py —— 派生视图生成 + 版本一致性校验

用法：
    python gen_views.py <技能包根>            # 生成派生视图
    python gen_views.py <技能包根> --check    # 只校验，不写盘

依据：MANIFEST.md §3（派生视图）、§4（版本一致性）

为什么要有这个脚本：
    「同一协议写两遍」与「版本号散在多处」都只能依赖人工同步，实测必然漂移。
    本脚本把派生视图从人工抄写改为生成，并校验版本一致性。

派生视图（不得手改）：
    · 本包 references/README.md 的「协议速览」区段（由 SKILL.md 的「核心不变量」节生成）
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import _load_defaults as _defaults, run  # noqa: E402
from _common import note, ok, problem, read, summary, tbd  # noqa: E402

BEGIN = "<!-- BEGIN:GENERATED-INVARIANTS -->"
END = "<!-- END:GENERATED-INVARIANTS -->"

def manifest_version(pkg: Path):
    txt = read(pkg / "MANIFEST.md") or ""
    m = re.search(r"\*\*版本\*\*[：:]\s*[`\"]?v?([0-9]+\.[0-9]+\.[0-9]+)", txt)
    return m.group(1) if m else None

def skill_invariants(pkg: Path):
    """从 SKILL.md 抽「核心不变量」节（这是协议的高频必读内核）。"""
    txt = read(pkg / "SKILL.md") or ""
    # 按「节名」匹配而不是按序号（序号会随章节增删漂移，是脆弱定位）
    m = re.search(r"(?ms)^##\s*核心不变量.*?(?=^##\s|\Z)", txt)
    if not m:
        return None
    body = m.group(0)
    # 去掉标题行与被引用的 meta 提示行，只留有编号的条目
    items = [l.rstrip() for l in body.splitlines() if re.match(r"^\s*\d+\.\s", l)]
    return "\n".join(items) if items else None

def _atomic_write(path: Path, text: str):
    """原子写：先写同目录临时文件，再 os.replace 覆盖。

    为什么要原子：本套脚本里**只有本脚本会写盘**，而它写的是 references/README.md——
    非原子写在中途崩溃或与另一个进程并发时，会留下被截断的 README。
    os.replace 在同一文件系统上是原子的：读到的要么是旧全文，要么是新全文。
    并发两个 gen_views 也安全：两边内容相同，后写者胜，结果一致。
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def render_section(items: str):
    """派生视图**不带版本号**：版本唯一落点是 MANIFEST.md——副本多一处，就多一处漂移面。"""
    return (BEGIN + "\n"
            + "<!-- 本节由 scripts/gen_views.py 生成，请勿手改；改协议请改 references/ 与 SKILL.md 后重跑 -->\n"
            + "**协议核心不变量（核心 5 条；完整 7 条见 `references/change-control.md` §B）**\n\n"
            + items + "\n"
            + END)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_only = "--check" in sys.argv
    if not args:
        print("用法：python gen_views.py <技能包根> [--check]")
        return 3
    pkg = Path(args[0])

    print("== 1. 版本权威源 ==")
    v = manifest_version(pkg)
    if not v:
        problem("MANIFEST.md 未找到版本声明（版本唯一落点）")
        ok("MANIFEST 版本 = v%s" % v)

    print("== 2. 其他文件不应各自声明版本 ==")
    offenders = []
    for p in sorted(pkg.rglob("*.md")):
        if p.name in ("MANIFEST.md", "BLUEPRINT.md"):
            continue
        if any(part in ("templates", "archives") for part in p.parts):
            continue
        txt = read(p) or ""
        # 两种形态都抓：「版本 v1.2.3」与裸的「技能包 v1.2.3」——
        # 版本副本的危害在于**升级后不更新就撒谎**，而裸形态正是最容易漏网的那种。
        for m in re.finditer(r"(?:版本\s*|技能包\s*)v?([0-9]+\.[0-9]+\.[0-9]+)", txt):
            offenders.append("%s (%s)" % (p.relative_to(pkg), m.group(1)))
    if offenders:
        for o in offenders:
            note("文件内出现版本号：%s —— 版本唯一落点为 MANIFEST，建议改为指针" % o)
    else:
        ok("除 MANIFEST / BLUEPRINT 外无文件各自声明版本")

    print("== 3. 配置占位符校验（{{config:<键>}} 是否都能解到默认值） ==")
    d = _defaults()
    seen, unknown = set(), []
    scan = ([pkg / "SKILL.md"]
            + sorted((pkg / "references").glob("*.md"))
            + sorted((pkg / "adapters").glob("*.md"))
            + sorted((pkg / "templates").rglob("*.md")))
    for p in scan:
        for m in re.finditer(r"\{\{config:([A-Za-z0-9_.]+)\}\}", read(p) or ""):
            key = m.group(1)
            # 纯点号是「格式示意」（如图例里的 {{config:...}}），不是真引用，不校验
            if set(key) <= {"."}:
                continue
            seen.add(key)
            if key not in d:
                unknown.append("%s -> %s" % (p.relative_to(pkg), key))
    if unknown:
        for u in unknown:
            problem("占位符解不到默认值（键名写错或配置缺失）：%s" % u)
    else:
        ok("正文引用的 %d 个配置键全部可在 config/defaults.yml 解到" % len(seen))

    print("== 4. 派生视图生成 ==")
    items = skill_invariants(pkg)
    if not items:
        tbd("未能从 SKILL.md 抽取核心不变量节（派生视图跳过）")
        return summary()
    readme = pkg / "references" / "README.md"
    txt = read(readme) or ""
    block = render_section(items)
    if BEGIN in txt and END in txt:
        new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _m: block, txt, flags=re.S)
    else:
        new = txt.rstrip() + "\n\n---\n\n## 附：协议核心不变量（生成区）\n\n" + block + "\n"
    if check_only:
        if new != txt:
            problem("派生视图已过期——请重跑 gen_views.py（去掉 --check）")
        else:
            ok("派生视图与权威源一致")
    else:
        if new != txt:
            _atomic_write(readme, new)
            ok("已重生成 README 派生视图（%d 条不变量）" % len(items.splitlines()))
        else:
            ok("派生视图无需更新")
    print("== 5. 卡片模板 · 建卡骨架：冻结字段名一致 ==")
    # 为什么查这个：卡字段名是**脚本的功能接口**（references/artifacts.md §2），
    # 模板与 closeout.py 的骨架是同一份契约的两处副本——**漂移了没人会立刻发现**，
    # 直到某天卡里少一个字段、门禁报红才发现。所以此处把它变成机器检查。
    drift = []
    sys.path.insert(0, str(pkg / "scripts"))
    try:
        import closeout as _co
    except Exception as e:  # 脚本被改名/移走时明确报错，不静默跳过
        problem("无法导入 scripts/closeout.py（建卡骨架所在）：%s" % e)
        return summary()
    pairs = [(pkg / "templates" / "tasks" / "TASK_CARD.template.md", _co.CARD_SKELETON_FIELDS, "任务卡"),
             (pkg / "templates" / "designs" / "DESIGN_CARD.template.md", _co.DESIGN_FIELDS, "设计卡")]
    for tpl, fields, label in pairs:
        t = read(tpl)
        if t is None:
            problem("%s模板不可读：%s" % (label, tpl.relative_to(pkg)))
            continue
        have = set(re.findall(r"^- \*\*([^*]+)\*\*", t, flags=re.M))
        for f in fields:
            if f not in have:
                drift.append("%s模板缺字段「%s」（closeout.py 骨架里有）" % (label, f))
        for h in sorted(have):
            if h not in fields and h not in ("文件名",):
                drift.append("%s模板多出字段「%s」（closeout.py 骨架里没有）" % (label, h))
    bpt = pkg / "templates" / "designs" / "DESIGN_BLUEPRINT.template.html"
    bt = read(bpt)
    if bt is None:
        drift.append("设计蓝图模板不可读：%s" % bpt.relative_to(pkg))
    else:
        for sec in _co.BLUEPRINT_SECTIONS:
            if sec not in bt:
                drift.append("蓝图模板缺必备节「%s」（build 骨架里有）" % sec)
    if drift:
        for x in drift:
            problem("%s —— 两处必须同步（字段名与节名是冻结值，见 references/artifacts.md §2 / design.md §6）" % x)
    else:
        ok("任务卡 %d 字段、设计卡 %d 字段、蓝图 %d 节：模板与建卡骨架一致"
           % (len(_co.CARD_SKELETON_FIELDS), len(_co.DESIGN_FIELDS), len(_co.BLUEPRINT_SECTIONS)))

    print("== 6. 脚本兜底值 · config/defaults.yml 逐键一致 ==")
    # 为什么查这个：脚本必须能脱离技能包单独跑（所以要兜底值），
    # 但兜底值与 defaults.yml 是**同一数值的两处副本**——不盯着就会漂移，
    # 而漂移的后果很隐蔽：带着技能包跑一套阈值、单独跑另一套。
    try:
        import code_metrics as _cm
    except Exception as e:
        problem("无法导入 scripts/code_metrics.py（兜底值所在）：%s" % e)
        return summary()
    dd = _defaults()
    mism = []
    for key, val in sorted(_cm.FALLBACKS.items()):
        if key not in dd:
            mism.append("%s 在 defaults.yml 里不存在（脚本有兜底、配置没有 → 用户无处可调）" % key)
        elif dd[key] != val:
            mism.append("%s：脚本兜底 %r ≠ defaults.yml %r" % (key, val, dd[key]))
    hollow = dd.get("code_quality.exemption.hollow_words")
    if hollow is not None and list(hollow) != list(_cm.FALLBACK_HOLLOW):
        mism.append("code_quality.exemption.hollow_words：脚本兜底 %r ≠ defaults.yml %r"
                    % (_cm.FALLBACK_HOLLOW, hollow))
    if mism:
        for m in mism:
            problem("%s —— 同一数值只允许有一处权威（config），脚本兜底必须与之相同" % m)
    else:
        ok("脚本兜底 %d 个数值 + 空话词表，与 config/defaults.yml 完全一致"
           % len(_cm.FALLBACKS))

    print("== 7. 条款 → 执行者映射（规范债务可见化） ==")
    # 为什么要查这个：规范里最危险的形态不是"条款写错"，是**条款没有执行者**——
    # 写着却没人管，与没写等价，但读者会以为有约束（本包称之为假账的一种）。
    # 检查方式：正文引用的每个 code_quality.* 键，都必须在 code-quality.md §9 的映射表里登记执行者。
    def _expand(keys):
        out = set()
        for k in keys:
            m = re.match(r"^(.*)\{([^}]+)\}(.*)$", k)
            if m:
                for alt in m.group(2).split(","):
                    out.add(m.group(1) + alt.strip() + m.group(3))
            else:
                out.add(k)
        return out

    ref_doc = pkg / "references" / "code-quality.md"
    body = read(ref_doc) or ""
    sec9 = body.split("## 9.")[-1].split("## 10.")[0] if "## 9." in body else ""
    if not sec9:
        problem("references/code-quality.md 找不到 §9「配置键清单」——执行者映射表的所在地")
        return summary()
    registered = _expand(set(re.findall(r"`([a-z_]+(?:\.[a-z_{},]+)+)`", sec9)))
    registered = {k for k in registered if k.startswith("code_quality.")}
    referenced = set()
    for p in sorted((pkg / "references").glob("*.md")) + sorted((pkg / "adapters").glob("*.md")):
        referenced |= set(re.findall(r"\{\{config:(code_quality\.[A-Za-z0-9_.]+)\}\}", read(p) or ""))
    orphan = sorted(referenced - registered)
    if orphan:
        for k in orphan:
            problem("条款引用了 `%s` 但 §9 未登记执行者 —— 没有执行者的条款等于没有条款" % k)
    else:
        ok("正文引用的 %d 个 code_quality 键全部登记了执行者" % len(referenced))
    unknown = sorted(k for k in registered if k not in referenced)
    if unknown:
        note("§9 登记但正文未引用（可能是遗留键，出清或补引用）：%s" % "、".join(unknown[:6]))
    # 只认表格行（正文里也会出现「未实现」这个词，那不是在数债务）
    todo = [l.strip() for l in sec9.splitlines() if l.strip().startswith("|") and "**未实现**" in l]
    if todo:
        note("规范债务（执行者＝未实现）%d 条 —— 用得上的补实现、用不上的出清"
             "（见 references/change-control.md 的晋升池）" % len(todo))

    print("== 8. 脚本编译零告警（含无效转义序列） ==")
    # 为什么查这个：非 raw 字符串里的 \s \d \* 之类会触发 DeprecationWarning / SyntaxWarning——
    # 当下不影响运行，但 Python 3.12 起逐步收紧，而且**外部评审会把它当缺陷报出来**。
    # 与其被评审抓到，不如自己抓。（某次外部评审报的正是这一类，此前自检全绿却没发现。）
    import warnings as _w
    warns = []
    for sp in sorted((pkg / "scripts").glob("*.py")):
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            try:
                compile(read(sp) or "", sp.name, "exec")
            except SyntaxError as e:
                warns.append("%s 语法错误：%s" % (sp.name, e))
                continue
            for x in caught:
                warns.append("%s:%s %s：%s" % (sp.name, getattr(x, "lineno", "?"),
                                               x.category.__name__, x.message))
    if warns:
        for x in warns:
            problem("脚本编译告警：%s —— 正则等含转义序列的字符串请写成 r\"...\"" % x)
    else:
        ok("%d 个脚本编译零告警" % len(list((pkg / "scripts").glob("*.py"))))

    print("== 9. 业务写端点登记完整性（唯一入口的契约不漏） ==")
    # 折中方案＝「要 API 的语义，不要 API 的常驻成本」：语义要成立，
    # 就必须保证**每个写端点都被登记过保护方式与失败语义**——
    # 漏登记一个端点，就等于有一个写操作不受任何契约约束，而没人会发现。
    try:
        import closeout as _co
        _sub = [x for x in _co.build_parser()._actions
                if isinstance(x, __import__("argparse")._SubParsersAction)]
        names = list(_sub[0].choices.keys()) if _sub else []
    except Exception as e:
        problem("无法从 scripts/closeout.py 导出端点表：%s" % e)
        return summary()
    missing = [n for n in names if n not in _co.ENDPOINTS]
    extra = [n for n in _co.ENDPOINTS if n not in names]
    if missing:
        for n in missing:
            problem("端点 %s 未在 ENDPOINTS 登记（保护方式与失败语义缺失）——写操作不许有「没契约」的口子" % n)
    if extra:
        for n in extra:
            note("ENDPOINTS 里登记了 %s，但解析器里没有该子命令（改过忘了同步？）" % n)
    if not missing and not extra:
        ok("工作区写端点 %d 个，全部登记了幂等性 / 并发保护 / 失败语义" % len(names))

    print("== 10. 共享文件写路径登记（协议说 CAS，实现就必须走 CAS） ==")
    # 为什么查这个：本包声称「共享文件写前比对哈希」，但实测存在多条直接 os.replace 的写路径
    #  （audit_all / lang_gates / stamp / setup / closeout 归档）——协议一套、实现一套，
    #  两个 Agent 同时写就会丢写。收编后由本节保证**不再长回来**。
    import lease as _lease
    _shared_names = [f.split("/")[-1] for f in _lease.SHARED_FILES]
    _write_call = re.compile(r"(os\.replace\(|\.write_text\(|_atomic_write\()")
    unregistered, stale = [], []
    for sp in sorted((pkg / "scripts").glob("*.py")):
        src = read(sp) or ""
        touches = any(n in src for n in _shared_names)
        writes = bool(_write_call.search(src))
        if touches and writes and sp.name not in _lease.SHARED_WRITERS:
            unregistered.append(sp.name)
    for name in _lease.SHARED_WRITERS:
        sp = pkg / "scripts" / name
        src = read(sp) or ""
        # 注意：**收编成功恰恰意味着它不再直接写**（改为调原语）。
        #  所以这里只判「整份文件已完全不提共享文件」＝登记失效；
        #  直接调原语也算健康。
        if sp.is_file() and not any(n in src for n in _shared_names):
            stale.append(name)
    if unregistered:
        for n in unregistered:
            problem("scripts/%s 写了共享文件但没登记在 lease.SHARED_WRITERS —— 共享写必须走 CAS 原语" % n)
    if stale:
        for n in stale:
            note("lease.SHARED_WRITERS 登记了 %s，但它已完全不提共享文件（改名或功能移除？）" % n)
    if not unregistered:
        ok("共享文件写者 %d 个，全部登记了写原语" % len(_lease.SHARED_WRITERS))
        note("本节是**静态防回归检查**，不是共享写安全证明："
             "动态拼接路径（如 \"IN\"+\"DEX.md\"）可绕过字符串扫描——"
             "真正的保证来自 lease.write_cas 的锁内比对与写后校验")

    print("== 11. 引用完整性（引用到的文件必须存在） ==")
    # 为什么查：拆文件 / 改名最容易出的事是**引用断链**——而断链是沉默的，
    #  读者点不到那个文件，只会以为'没有这份规范'。**功能没丢，但等于丢了。**
    ref_re = re.compile(r"(?:references|adapters|blueprint|templates|scripts|ci|config|tools)/[A-Za-z0-9_./-]+\.(?:md|py|yml|yaml|json)")
    broken = []
    for p in sorted(pkg.rglob("*")):
        if not p.is_file() or p.suffix not in (".md", ".py", ".yml"):
            continue
        rel_self = p.relative_to(pkg)
        for m in ref_re.finditer(read(p) or ""):
            tgt = m.group(0)
            cand = pkg / tgt
            if cand.exists():
                continue
            # 也允许相对本文件目录解析（附录里常这么写）
            if (p.parent / tgt).exists():
                continue
            broken.append("%s → %s" % (rel_self, tgt))
    if broken:
        for b in broken[:8]:
            problem("引用断链：%s（被引用的文件不存在）" % b)
    else:
        ok("正文引用的 %d 处文件路径全部存在" % len([1 for p in pkg.rglob('*.md') for _ in ref_re.finditer(read(p) or '')]))

    print("== 12. 清单完整性（MANIFEST 列的文件 = 磁盘上的文件） ==")
    # 为什么查：拆文件/加文件**忘记登记**，就是组织层面的耦合断裂——
    #  读者按清单找不到东西，或不知道有这个东西。**清单是导航，导航错了比没有更坏。**
    man = read(pkg / "MANIFEST.md") or ""
    listed = set()
    # **只认「缩进清单条目」**（形如 「  overview.py  说明」）：
    #  在整篇里抓文件名会把散文里提到的也算成登记（实测误报：INDEX.md / MAP.md 是工作区文件、
    #  设计蓝图模板名），反而把真问题淹掉。
    in_block, cur_dir = False, ""
    for line in man.splitlines():
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            continue
        md = re.match(r"^([a-z_]+/)\s", line)          # 目录头（references/ scripts/ ci/ …）
        if md:
            cur_dir = md.group(1).rstrip("/")
            continue
        m = re.match(r"^\s{2,}([A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:md|py|yml|yaml|json))\s", line)
        if m:
            listed.add((cur_dir, m.group(1)))          # **按目录记录**：同名文件在不同目录不算同一份

    # 判据要**动态**：MANIFEST 对某些目录是「逐文件列举」（references/ scripts/），
    #  对另一些是「按目录声明」（adapters/ blueprint/ templates/ ci/ …）。
    #  只要求前者列全——否则每次都会刷出一堆'未登记'，把真问题淹掉。
    # listed 是 {(目录, 文件名)} 的集合——按目录比较，避免同名文件互相顶替（README.md 之类）
    missing = sorted(("%s/%s" % (d, n)) if d else n for (d, n) in listed
                     if not (pkg / d / n).exists())
    by_dir_listed, by_dir_disk = {}, {}
    for p in pkg.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        d = str(p.parent.relative_to(pkg))
        d = "" if d == "." else d
        by_dir_disk.setdefault(d, set()).add(p.name)
        if (d, p.name) in listed:
            by_dir_listed.setdefault(d, set()).add(p.name)
    unlisted = []
    for d, names in by_dir_disk.items():
        if not d:
            continue
        listed_here = {n for (dd, n) in listed if dd == d}
        if len(listed_here) >= 1:                 # 该目录被逐文件列举 → 必须列全
            unlisted += ["%s/%s" % (d, n) for n in sorted(names - listed_here)]
    for n in missing[:8]:
        problem("MANIFEST 列了 %s，但磁盘上不存在（删了文件没改清单？）" % n)
    if not missing:
        ok("MANIFEST 列出的文件名全部存在")
    if unlisted:
        for n in unlisted:
            problem("磁盘上有 %s 但 MANIFEST 未列（拆/加文件后忘了登记 → 读者按清单找不到它）" % n)
    else:
        ok("被逐文件列举的目录（%s）全部登记完整" % "、".join(sorted(d for d in by_dir_listed if d != ".")))

    print("== 13. 术语一致性（旧名不得回潮） ==")
    # 为什么查这个：glossary 的标准术语与正文是**双向契约**——只改一处，另一处迟早回潮
    #  （外部评审实测：四个旧名在正文大面积回潮）。本节的旧名来源＝references/glossary.md
    #  两张对照表的旧名列：§二「叙述术语对照」与 §三「旧名对照」。
    #  旧名在**正文**（*.md 与 scripts/*.py）里再出现即报问题；对照表自身与下列登记项除外。
    #: 现役 / 契约保留：这些"旧名"在包内仍是冻结字段、现行术语或通用中文词，判回潮会误报。
    TERM_LIVE = {}   # 已清零：豁免改由 glossary 表内「现役」标记表达（单一来源）
    #: 登记豁免位置：正文里**有意引用旧名**的地方（不能被机检按回潮处理）。
    TERM_EXEMPT = {
        "references/audit.md": {"收工": "旧卡原话引用——存量卡确写该名，删掉读者就认不出旧卡"},
    }
    _SELF = "scripts/gen_views.py"          # 本文件含词表，不得自己判自己
    _OLD_HEADERS = ("原自造词", "更早的叫法")

    def _glossary_old_names(txt):
        """解析 glossary 两张对照表的旧名列 → ([(旧名, 来源行标题)], 需排除的行号集合)。"""
        rows, skip, in_table = [], set(), False
        for i, line in enumerate(txt.splitlines(), 1):
            s = line.strip()
            if not s.startswith("|"):
                in_table = False
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not cells:
                continue
            head = cells[0].strip("*` ")
            if head in _OLD_HEADERS:
                in_table = True
                skip.add(i)
                continue
            if not in_table:
                continue
            skip.add(i)                     # 对照表整行（含分隔行）都不算正文
            if set(head) <= set("-: "):
                continue
            new_term = cells[1] if len(cells) > 1 else ""
            cell = re.sub(r"[（(].*?[）)]", "", head)
            cell = re.sub(r"[「『].*?[」』]", "", cell)
            for part in re.split(r"[/→·]", cell):
                w = part.strip().strip("*` ")
                # 只收含汉字、长度 ≥ 2 的中文词（owner / next 这类不是中文旧名）
                if "现役" in head:   # 表内标记「现役」（字段名/通用词）→ 不参与回潮检查
                    continue
                if len(w) >= 2 and re.search(r"[\u4e00-\u9fff]", w) and w not in new_term:
                    rows.append((w, head))
        return rows, skip

    gloss_txt = read(pkg / "references" / "glossary.md") or ""
    pairs, gloss_skip = _glossary_old_names(gloss_txt)
    terms = sorted({w for w, _src in pairs if w not in TERM_LIVE})
    offenders, scanned = [], 0
    for p in sorted(pkg.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts or p.suffix not in (".md", ".py"):
            continue
        rel = str(p.relative_to(pkg)).replace(os.sep, "/")
        if rel == _SELF:
            continue
        scanned += 1
        exempt_here = TERM_EXEMPT.get(rel, {})
        for i, line in enumerate((read(p) or "").splitlines(), 1):
            if rel == "references/glossary.md" and i in gloss_skip:
                continue
            #  正当引用豁免：该行是在**解释**旧名（含 旧称/旧名/曾用/原叫），不算回潮
            if any(_q in line for _q in ("旧称", "旧名", "曾用", "原叫")):
                continue
            for w in terms:
                if w in line and w not in exempt_here:
                    offenders.append("%s:%d 出现旧名「%s」" % (rel, i, w))
    if offenders:
        for x in offenders[:12]:
            problem("术语回潮：%s —— 正文一律用 glossary 的标准术语（对照表本身除外）" % x)
        if len(offenders) > 12:
            note("另有 %d 处术语回潮未列出（见 references/glossary.md 对照表）" % (len(offenders) - 12))
    else:
        ok("对照表登记 %d 个旧名，扫描 %d 个文件 0 回潮（%d 个现役/契约词已登记豁免）"
           % (len(pairs), scanned, len(TERM_LIVE)))

    #  ── 第二条规则：**当前/历史语义分区**（旧机制术语只允许出现在带历史标注的行里）──
    import ast
    _LEAK = ("LOCK_STALE", "锁龄抢占", "lock-age", "EXCL fallback", "stale takeover", "rename 抢占", "epoch 继承")
    _LABEL = ("已移除", "旧模型", "HISTORICAL", "历史", "原实现", "上一代", "当年")
    _zones = []
    for _p in ("references/concurrency-internals.md", "references/concurrency.md"):
        _hist = False
        for _i, _l in enumerate((read(pkg / _p) or "").splitlines(), 1):
            if _l.startswith("#"):
                _hist = "HISTORICAL" in _l          # 小节标题含 HISTORICAL → 整节视为历史区
            if any(_k in _l for _k in _LEAK):
                _zones.append((_p, _i, _l, _hist or any(_t in _l for _t in _LABEL)))
    _cur = [z for z in _zones if not z[3]]
    _his = [z for z in _zones if z[3]]
    _code = []
    _src = read(pkg / "scripts" / "locks.py") or ""
    _tree = ast.parse(_src)
    _skip = set()
    for _node in ast.walk(_tree):
        if isinstance(_node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _d = ast.get_docstring(_node, clean=False)
            if _d:
                for _ln in range(_node.body[0].lineno, (_node.body[0].end_lineno or _node.body[0].lineno) + 1):
                    _skip.add(_ln)
    for _i, _l in enumerate(_src.splitlines(), 1):
        if _i in _skip or _l.strip().startswith("#"):
            continue
        if any(_k in _l for _k in _LEAK):
            _code.append((_i, _l.strip()[:60]))
    if _cur or _code:
        for _p, _i, _l, _f in _cur[:6]:
            problem("当前/历史语义泄漏：%s:%d 出现旧机制术语但未标注历史：%s" % (_p, _i, _l.strip()[:56]))
        for _i, _l in _code[:4]:
            problem("旧机制术语出现在可执行代码里：locks.py:%d %s" % (_i, _l))
    else:
        ok("当前/历史语义分区：Current 区命中 0 · Historical 标注 %d 处 · 代码行为引用 0" % len(_his))
    print("== 14. 可发现性（references/ 每个文件都必须能从首读入口找到） ==")
    #  为什么查：§11 只查「被引用的文件是否存在」，抓不到「存在但无人引用」——
    #  删/改路由时，正文会**静默从入口不可达**（恢复篇、审计篇尤其致命），而门禁全绿。
    _skill = read(pkg / "SKILL.md") or ""
    _refs = sorted(p.name for p in (pkg / "references").glob("*.md"))
    _orphan = [n for n in _refs if n not in _skill]
    if _orphan:
        for n in _orphan:
            problem("可发现性：references/%s 没有出现在 SKILL.md 里——读者从首读入口找不到它" % n)
    else:
        ok("references/ 的 %d 个文件都能从 SKILL.md 找到" % len(_refs))

    print("== 15. 发布卫生（未登记根条目 · 缓存/测试残留） ==")
    if not (pkg / "MANIFEST.md").is_file():
        note("非完整包（缺 MANIFEST.md）——跳过发布卫生检查")
    else:
        allow = {'blueprint', 'tools', 'LEGACY_ONBOARDING.md', 'config', 'adapters', 'locales', 'BLUEPRINT.md', 'examples', 'scripts', 'ci', 'archives', 'MANIFEST.md', 'templates', 'SKILL.md', 'references'}
        junk = []
        for p in sorted(pkg.iterdir()):
            if p.name not in allow:
                junk.append("根目录未登记：%s" % p.name)
        for d in pkg.rglob("*"):
            rel = str(d.relative_to(pkg))
            if d.is_dir() and d.name in (".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__"):
                junk.append("缓存目录：%s" % rel)
            elif d.is_file() and d.suffix == ".lock":
                junk.append("残留文件：%s" % rel)
        for d in pkg.iterdir():
            if d.is_dir() and (d.name.startswith("matrix_") or d.name.startswith("crash_") or d.name.startswith("gate_selftest_")):
                junk.append("测试残留目录：%s" % d.name)
        if junk:
            for j in sorted(set(junk)):
                problem("发布卫生：" + j)
        else:
            ok("根目录无未登记条目 · 无缓存/测试残留（根条目 %d 个）" % len(list(pkg.iterdir())))

    print("== 16. 配置面 ASCII 与全角空格（F9：机器字段必须可被工具读） ==")
    #   为什么查：机器用的字段混入全角（尤其**全角空格**）会让命令/键**静默失配**——不报错、只出错。
    #   口径刻意收窄到**零误报**：只查 ① providers 的机器字段 ② yml 的**键** ③ **全角空格**（任何地方都错）。
    _fw = chr(0x3000)          # 全角空格：连中文文案里也不该出现
    _bad_fw = []
    _cfg = pkg / "config"
    if _cfg.is_dir():
        for _jf in sorted(_cfg.glob("*.json")):
            try:
                _jd = json.loads(_jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            for _p in (_jd.get("providers", []) if isinstance(_jd, dict) else []):
                for _k in ("key", "kind", "tool", "probe", "run", "standards", "defects"):
                    _v = _p.get(_k)
                    if _v is None:
                        continue
                    _s = json.dumps(_v, ensure_ascii=False)
                    if _fw in _s or any(ch in "，。；：（）【】「」" for ch in _s):
                        _bad_fw.append("%s: providers[%s].%s 含全角字符" % (_jf.name, _p.get("key", "?"), _k))
        for _yf in sorted(_cfg.glob("*.yml")):
            for _i, _l in enumerate((read(_yf) or "").splitlines(), 1):
                _s = _l.split("#", 1)[0]
                _m = re.match(r"^\s*([^:\s]+):", _s)
                if _m and (_fw in _m.group(1) or any(ch in "，。；：（）【】「」" for ch in _m.group(1))):
                    _bad_fw.append("%s:%d 键含全角字符：%s" % (_yf.name, _i, _m.group(1)))
    for _sub in ("scripts", "references", "config", "adapters"):
        _sd = pkg / _sub
        if not _sd.is_dir():
            continue
        for _f2 in _sd.rglob("*"):
            if not _f2.is_file() or "__pycache__" in _f2.parts or _f2.suffix.lower() not in (".py", ".yml", ".json", ".md"):
                continue
            if _fw in (read(_f2) or ""):
                _bad_fw.append("%s 含全角空格（U+3000）" % _f2.relative_to(pkg))
    if _bad_fw:
        for _b in sorted(set(_bad_fw)):
            problem("配置面 ASCII：" + _b)
    else:
        ok("配置面 ASCII：机器字段与键无全角字符 · 无全角空格（扫 %s）" % "scripts/references/config/adapters")

    print("== 17. 载体契约一致性（规范 → 模板 → 生成器 → 验证器） ==")
    #   为什么查：四层换轨时**任一层留在旧载体**都会静默漂移（门禁全绿、事实上没接通）。
    #   唯一真值＝**规范声明**（design.md）：其余三层只许与它一致，不得各说各话。
    _spec = read(pkg / "references" / "design.md") or ""
    _mm = re.search(r"blueprint\.([A-Za-z0-9]+)`.{0,40}?（\*\*人看", _spec) or re.search(r"blueprint\.([A-Za-z0-9]+)`", _spec)
    _want = _mm.group(1) if _mm else None
    if not _want:
        note("载体契约：规范未声明蓝图扩展名，跳过（无法判定，不猜）")
    else:
        _bad = []
        _dir = pkg / "templates" / "designs"
        if not any(t.suffix == ("." + _want) for t in _dir.glob("DESIGN_BLUEPRINT.template.*")):
            _bad.append("模板层：templates/designs/DESIGN_BLUEPRINT.template.%s 缺失" % _want)
        # 旧写法只查 closeout.py 与 gen_views.py 自己 —— **漏了真正的验证器 validate_workspace.py 与自检夹具 selftest_gates.py
        # （2026-10 实测：官方 new-card --design 产出 .html，而 validate_workspace 找 .md → 必然报红；三处互相掩护长期存活）。
        # 根修：覆盖面【由磁盘驱动】—— 扫描 scripts/ 下**所有** .py，任一脚本引用旧载体即报红；且必须至少有一个脚本引用新载体。
        _scripts = sorted((pkg / "scripts").glob("*.py"))
        _hit_new = False
        for _sp in _scripts:
            _txt = read(_sp) or ""
            _e = set(re.findall(r"blueprint\.([A-Za-z0-9]+)", _txt))
            _bad_e = sorted(x for x in _e if x != _want)
            if _bad_e:
                _bad.append("脚本层：%s 仍出现旧载体 .blueprint.%s" % (_sp.name, "、".join(_bad_e)))
            if ("blueprint." + _want) in _txt:
                _hit_new = True
        if not _hit_new:
            _bad.append("脚本层：scripts/ 下没有任何脚本引用 .blueprint.%s" % _want)
        for _b in _bad:
            problem("载体契约不一致（规范＝.%s）：%s" % (_want, _b))
        if not _bad:
            ok("载体契约一致：规范 .%s ＝ 模板 ＝ 生成器 ＝ 验证器" % _want)

    return summary()

if __name__ == "__main__":
    sys.exit(run(main))
