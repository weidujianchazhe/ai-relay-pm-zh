# NOPMD: 注释密度 1.60 > 上限 1.5 —— 其中 1 条为 G1 审计豁免标记（# noqa: G1 reason=diagnostic-message sha256=…，机器可读的身份绑定证据，非解释性注释）；其余为规则说明与成因注释，非翻译式注释。
# -*- coding: utf-8 -*-
"""validate_workspace.py —— 工作区结构与配置校验

用法：python validate_workspace.py <管理区>
何时跑：初始化后 / 改结构后 / 定期自检
依据：references/artifacts.md §1（文件清单）、§2（冻结区）；references/audit.md §2.1（人检标记）
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import branch_pattern, config, iter_cards, note, ok, problem, read, strip_code, summary, tbd, run  # noqa: E402

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
    for f in REQUIRED_FILES:  # TEMP-DOWNGRADE-INJECT
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
        n = len(re.findall(r"(?m)^\|\s*" + branch_pattern(root) + r"\s*\|", read(idx) or ""))
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
    #  ★ HTML 载体预处理（2026-10-16）：本判据原按 **Markdown** 结构行（`|`/`-`/`*`/`#`/`>`）拆段，
    #  而 v4.0.0 起蓝图载体是 **HTML** —— HTML 行首是 `<`，全部落进 buf，整个 body（含 <style> 的 CSS）
    #  被拼成一段，导致 **出厂 new-card --design 自己产的蓝图过不了自家门禁**（实测最长 1752 字符）。
    #  处置：**CSS/脚本不是散文，先剥**；块级标签当换行；其余标签**剥壳保内容**——
    #  因此**人写的长散文仍会被抓**（负控见 selftest_gates「蓝图里塞长段落」用例）。
    txt = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
    txt = re.sub(r"</(p|div|li|tr|td|th|h[1-6]|section|article|table|ul|ol|blockquote)>", "\n", txt, flags=re.I)
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
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


#  设计骨架**不是设计卡**（references/design.md §0.4）：它是「项目当前工程模型」的两种阅读方式，
#  没有蓝图、也不带「拆分出的任务卡」字段 —— 故从设计卡成对性/字段校验中排除。
SKELETON_NAMES = ("SKELETON.md", "SKELETON.html")


def _check_designs(root: Path):
    """设计区校验：成对性 / 蓝图长度 / 归档成对（references/design.md §1 §4 §6）。"""
    d = root / "designs"
    if not d.is_dir():
        note("无 designs/ —— 不需要设计的项目正常（设计区按需建）")
        return
    specs, bps = [], []
    # **必须由扩展名驱动**：只 glob *.md 会让 .blueprint.html 永不进入 bps →
    # 蓝图长度 / 长段落 / 孤儿蓝图三项检查对 HTML 蓝图全部失效（2026-10 实测：selftest 用例「蓝图塞长段落」报「门禁对这类故障是瞎的」）。
    #
    # ★ 2026-10-16 外部审查修（P1 假红 + P1 假绿）：
    #  ① 假红：旧写法把 designs/ 下**所有** .md 当设计卡 —— 于是 `SKELETON.md`（设计骨架，
    #     design.md §0.4：项目当前工程模型的 AI 读版）被要求配套 SKELETON.blueprint.html 与
    #     「拆分出的任务卡」字段，必然误报；归档成对性又用「`archives/*.md` 个数奇偶」代替配对，
    #     于是**一对合法归档**（1 .md + 1 .blueprint.html）必被判奇数假红。
    #  ② 假绿：design.md §1/§4 允许**板块独立设计** `designs/<模块>/design.md` + `blueprint.html`，
    #     旧写法只扫 designs 根目录 → 嵌套设计**完全不被校验**（缺蓝图也 exit 0）。
    #  新口径：**按目录约定**收集设计单元，**递归但不越界**；骨架与归档都不算活跃设计卡。
    #  安全边界：**只在 designs/ 与其直接板块子目录**内收集根级配对，**不递归进子目录内部**，
    #    避免把模块自己的辅助 .md/.html（如模块 README、素材）误当设计卡（= 不引入新假红）。
    _units = []
    for _dir in [d] + sorted(p for p in d.iterdir() if p.is_dir() and p.name != "archives"):
        _md = [p for p in sorted(_dir.glob("*.md")) if p.name not in SKELETON_NAMES]
        _ht = [p for p in sorted(_dir.glob("*.html")) if p.name not in SKELETON_NAMES]
        if _dir is not d:
            #  板块目录：按 design.md §1「局部/板块设计」的固定名收窄（design.md ↔ blueprint.html），
            #  避免误收模块自有文档（如模块 README、素材）。
            _md = [p for p in _md if p.name == "design.md"]
            _ht = [p for p in _ht if p.name in ("blueprint.html",)]
        #  ★ 蓝图判定**不能只看文件名后缀**：板块约定用固定名 `blueprint.html`（不以 .blueprint.html 结尾）——
        #  旧写法只看后缀会把板块蓝图错收进 specs，于是误报「缺 blueprint.blueprint.html」与「蓝图缺字段」。
        _is_bp = (lambda p: p.name in ("blueprint.html",)) if _dir is not d else (lambda p: p.name.endswith(".blueprint.html"))
        for p in _md + _ht:
            (bps if _is_bp(p) else specs).append(p)
        _units.append((_dir, _md, _ht))
    #  ★ 2026-10-16：早退条件**必须把归档也算进来** —— 否则「活跃区空、但 designs/archives/ 里有半份归档」
    #  会在到达归档成对检查（本函数末尾）之前就 return，**归档缺件永远抓不到**（实测：只有 1 个归档 .md 时 exit 0）。
    _arch_pre = d / "archives"
    if not specs and not bps and not (_arch_pre.is_dir() and any(_arch_pre.rglob("*"))):
        note("designs/ 为空 —— 活跃设计区保持清空是健康状态（走完流程的设计已入 designs/archives/）")
        return
    #  ★ ID 一致性（2026-10-16 外部审查发现）：只查「配套文件存在」不够 ——
    #  同名蓝图可能保留**旧 DESIGN-ID**，而详述是**新的**；两件套引用同一个设计却指向两个身份 = 静默污染。
    _dsn = re.compile(r"DSN-\d{8}-[0-9A-Fa-f]{6}")
    #  配对解析：**同目录内**配对，板块目录用固定名（design.md ↔ blueprint.html，design.md §1）。
    def _blueprint_of(s):
        return s.parent / ("blueprint.html" if s.name == "design.md" else (s.stem + ".blueprint.html"))

    def _spec_of(b):
        return b.parent / ("design.md" if b.name == "blueprint.html" else (b.name[: -len(".blueprint.html")] + ".md"))

    def _rel(p):
        return "designs/" + str(p.relative_to(d)).replace(os.sep, "/")

    for s in specs:
        b = _blueprint_of(s)
        t = read(s) or ""
        #  ★ 2026-10-16 **第二次外部审查修（P1 假红 + P1 假绿，两处同源）**：
        #   依据 `references/design.md` §0.2：`designs/` 根**本来就允许放设计过程资产**
        #   （中间方案 / 局部方案 / 论证材料），它们**不是设计卡**、天然没有蓝图与「拆分出的任务卡」。
        #   旧写法把除 SKELETON 外的**每个 .md 都当设计卡** ⇒ 一份 `research-notes.md` 就假红。
        #   新口径用**身份字段**分界（也是模板的规定）：**有 `DESIGN-ID` 才是设计卡**；
        #   过程资产放行；但「有蓝图却没 ID」要报出来（否则两件套缺 ID 会静默通过）。
        _ids_here = _dsn.findall(t)
        #  ★ 2026-10-16 **第三次外部审查修（规则边界）**：过程资产的判据**不能只看"有没有 ID/蓝图"** ——
        #  否则 `designs/<模块>/design.md`（板块设计的**约定固定名**）只要忘写 ID 就会被当成"过程资产"放行。
        #  正确边界：**板块目录里的 `design.md` 一定是设计卡**（它是约定名，不是随手放的笔记）；
        #  只有**根目录**下、既无 ID 又无配套蓝图的 `.md` 才是过程资产（design.md §0.2 的"中间方案/论证材料"）。
        _is_board_spec = (s.name == "design.md")
        if not _ids_here:
            if b.exists() or _is_board_spec:
                problem("设计卡缺身份字段 `DESIGN-ID`：%s —— %s"
                        % (_rel(s), "同目录已有蓝图，说明它是两件套" if b.exists() else "板块设计的约定文件名是 design.md，不能用缺 ID 绕过"))
            else:
                note("过程资产（根目录、无 `DESIGN-ID`、无配套蓝图，按 design.md §0.2 放行）：%s" % _rel(s))
            continue
        if not b.exists():
            problem("设计缺蓝图：%s 不存在 —— 一份设计＝详述 + 蓝图两件套" % _rel(b))
        if "拆分出的任务卡" not in t:
            problem("设计卡缺冻结字段「拆分出的任务卡」：%s（归档门禁判据）" % _rel(s))
        if b.exists():
            _a = set(_ids_here)
            _b = set(_dsn.findall(read(b) or ""))
            #  ★ 2026-10-16 **第三次外部审查修**：判据必须是**集合相等**，不是"有交集"。
            #  旧写法 `not (_a & _b)` 只要两侧有**一个**共同 ID 就放行 —— 多写 ID、部分不一致都能蒙过去。
            if _a != _b:
                _extra_s = sorted(_a - _b)
                _extra_b = sorted(_b - _a)
                problem("设计两件套 DESIGN-ID 不一致（要求两侧**完全相等**）：%s（%s）↔ %s（%s）"
                        "%s"
                        % (_rel(s), "、".join(sorted(_a)), _rel(b), "、".join(sorted(_b)),
                           ("；仅详述有：%s" % "、".join(_extra_s) if _extra_s else "")
                           + ("；仅蓝图有：%s" % "、".join(_extra_b) if _extra_b else "")))
            elif _a and not _b:
                problem("蓝图缺 `DESIGN-ID`：%s —— 两件套必须指向同一身份（详述为 %s）"
                        % (_rel(b), "、".join(sorted(_a))))
    for b in bps:
        s = _spec_of(b)
        if not s.exists():
            problem("孤儿蓝图（没有对应详述）：%s" % _rel(b))
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
        #  ★ 2026-10-16 修假红：旧判据用「`archives/*.md` 个数奇偶」代替配对 —— 一对合法归档
        #  （1 详述 + 1 蓝图）的 .md 个数是 1（奇数）→ **必然误报**。改为**按 (目录, stem) 双向配对**，
        #  并按板块约定把 design.md ↔ blueprint.html 视作同目录的一对。
        #  ★ 配对键必须**同时**支持两种约定（2026-10-16 实测：只特判 design.md/blueprint.html 会让
        #  `<主题>.md` ↔ `<主题>.blueprint.html` 这一对判不成对，一对合法归档被误报「缺蓝图 + 孤儿蓝图」）：
        #   · 根级/归档：<主题>.md ↔ <主题>.blueprint.html
        #   · 板块：    design.md   ↔ blueprint.html
        #  注意 Path("旧方案.blueprint.html").stem == "旧方案.blueprint"，**必须显式去掉 .blueprint**。
        def _pair_key(p):
            n = p.name
            if n == "design.md" or n == "blueprint.html":
                return (str(p.parent), "design")
            if n.endswith(".blueprint.html"):
                return (str(p.parent), n[: -len(".blueprint.html")])
            if n.endswith(".md"):
                return (str(p.parent), n[: -len(".md")])
            return (str(p.parent), n)

        _am = [p for p in sorted(arch.rglob("*.md")) if p.name not in SKELETON_NAMES]
        #  ★ 归档蓝图扫描必须**两种约定都收**（2026-10-16 实测：只 rglob("*.blueprint.html")
        #  会漏掉板块归档里的固定名 `blueprint.html`，于是刚归档的板块设计被判「缺蓝图」假红）。
        _ah = [p for p in arch.rglob("*.html")
               if p.name == "blueprint.html" or p.name.endswith(".blueprint.html")]
        _mk = {_pair_key(p) for p in _am}
        _hk = {_pair_key(p) for p in _ah}
        _miss_b = [p for p in _am if _pair_key(p) not in _hk]
        _miss_s = [p for p in _ah if _pair_key(p) not in _mk]
        if not _miss_b and not _miss_s:
            ok("设计归档 %d 对（详述 + 蓝图，成对）" % len(_mk))
        else:
            for p in _miss_b:
                problem("归档设计缺蓝图（两件必须一起移）：%s" % str(p.relative_to(root)).replace(os.sep, "/"))
            for p in _miss_s:
                problem("归档孤儿蓝图（没有对应详述）：%s" % str(p.relative_to(root)).replace(os.sep, "/"))

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
