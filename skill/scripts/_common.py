# -*- coding: utf-8 -*-
"""_common.py —— 脚本套件共用设施（标准库实现，无第三方依赖）

设计约定（全套脚本统一，见 references/audit.md §4）：
  输出三态：[通过] / [问题] / [待核]
  退出码：0 = 全通过；1 = 有[问题]；2 = 仅[待核]；3 = 脚本自身错误
  取值顺序：实例 MAP 规则段 → 缺失才回落 config/defaults.yml（禁止只读技能包默认值）
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ── 三态输出 ──────────────────────────────────────────────────
_p = _q = _t = 0

def ok(msg):
    global _p
    _p += 1
    print("[通过] " + msg)

def problem(msg):
    global _q
    _q += 1
    print("[问题] " + msg)

def tbd(msg):
    global _t
    _t += 1
    print("[待核] " + msg)

def note(msg):
    """提示：不计数、不影响退出码——用于"设计上永久如此"的项。

    存在理由：常量 [待核] 会让"退出码 0"永不可达，门禁信号失效（见 references/audit.md §4）。
    """
    print("[建议] " + msg)


def _harden_stdout():
    """让输出永不因「控制台编码装不下某个字符」而崩。

    实测（中文 Windows，控制台 GBK）：打印 ↔ ／ ━ ／ ✓ 这类字符会抛 UnicodeEncodeError，
    Python 随即以**退出码 1** 结束——与「门禁发现真问题」同码，
    核查者会把「脚本崩了」读成「项目有问题」。这是**信号污染**，必须堵住。
    处置：只把不可编码字符降级为替代符（errors="replace"），**不改控制台编码**——
    改编码会打乱用户既有终端的显示，代价比收益大。
    """
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def usage_exit(parser):
    """把 argparse 的**用法错误**统一成退出码 3（脚本自身错误）。返回该 parser，便于链式调用。

    为什么必须改：argparse 默认 `sys.exit(2)`，而本包口径里 **2 = 「仅[待核]」**——
    **CI 把 2 视作不阻断**。于是「命令根本没跑对」（参数拼错 / 缺子命令）会看起来通过；
    用法错误是**脚本没被执行**，不是「需要人看的结论」，必须与门禁结论区分开。
    """

    def _error(message):
        print("[问题] 用法错误：%s" % message)
        try:
            parser.print_usage(sys.stderr)
        except Exception:
            pass
        raise SystemExit(3)

    parser.error = _error
    return parser


def run(main):
    """统一入口包装：把**脚本自身错误**与「有 [问题]」区分开（退出码 3 vs 1）。

    为什么必须区分：未捕获异常时 Python 的退出码也是 1，
    于是「脚本崩溃」与「门禁抓到真问题」在机器看来完全一样——结论会被读反。
    统一约定（scripts/README.md）：0 全通过 · 1 有[问题] · 2 仅[待核] · 3 脚本自身错误。
    """
    try:
        return main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("[待核] 执行被中断（KeyboardInterrupt）——本轮结论不成立")
        return 3
    except Exception as e:  # noqa: BLE001 —— 这里就是要兜住一切
        import traceback
        traceback.print_exc()
        print("[待核] 脚本自身错误：%s: %s —— **不计入项目结论**（退出码 3）" % (type(e).__name__, e))
        return 3


_harden_stdout()

def alias_notes():
    """报出配置项用了历史别名的情形（口径收敛用）。"""
    for s in sorted(_ALIAS_USED):
        note("配置项别名：" + s)

def summary() -> int:
    alias_notes()
    print("-" * 46)
    print("[通过] %d  |  [问题] %d  |  [待核] %d" % (_p, _q, _t))
    if _q:
        return 1
    if _t:
        return 2
    return 0

def read(path):
    """读文本。用 utf-8-sig：带 BOM 的文件不会把 \ufeff 混进首行（无 BOM 时与 utf-8 等价）。

    BOM 会让「以 | 开头的行」「以 key: 开头的行」判定整体失效——实测踩过，故统一加防护。
    """
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None

# ── 配置取值：实例优先，出厂默认兜底 ─────────────────────────
_DEFAULTS_CACHE = {}

def _load_defaults():
    """读技能包出厂默认值 config/defaults.yml（极简 YAML 子集解析，不引依赖）。

    支持任意层嵌套（用缩进栈维护路径），并支持行内列表 [a, b, c]。
    之所以自己解析：本套脚本的硬约束是**只用标准库**，不引入 PyYAML。
    """
    if _DEFAULTS_CACHE:
        return _DEFAULTS_CACHE
    here = Path(__file__).resolve().parent.parent
    txt = read(here / "config" / "defaults.yml")
    if not txt:
        return _DEFAULTS_CACHE
    stack = []  # [(indent, key)]
    for line in txt.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^([A-Za-z_][\w]*):\s*(.*)$", line.strip())
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2).strip()
        # 行内注释：取第一个 '#' 之前的部分；若 '#' 打头则视为"无值"（是个节，不是叶子）
        # ⚠ 必须**引号感知**：值本身可能含 '#'（如 marker: "#人检"），
        #   朴素 split("#") 会把它截成半个引号，静默产出一个错值。
        val = "" if raw_val.startswith("#") else _strip_comment(raw_val)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([k for _, k in stack] + [key])
        if val:
            _DEFAULTS_CACHE[path] = _coerce(val)
        else:
            stack.append((indent, key))
    return _DEFAULTS_CACHE

def _strip_comment(raw_val):
    """去掉行内注释，但引号内的 '#' 不生效。"""
    out, quote = [], ""
    for ch in raw_val:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


def _coerce(v):
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_coerce(x.strip()) for x in inner.split(",") if x.strip()] if inner else []
    if v in ("true", "false"):
        return v == "true"
    if v in ("null", "~", ""):
        return None
    m = re.match(r'^"(.*)"$', v) or re.match(r"^'(.*)'$", v)
    if m:
        return m.group(1)
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v

#: MAP 规则段里配置项的中文标签 → 配置键（含历史别名，容忍旧实例）
#  为什么容忍别名：实测各实例对同一配置项的叫法并不统一
#  （规范写「协作模式」，实例写「运行模式」）——口径漂移的样本。
#  脚本接受别名，但把用了别名的情形作为 [建议] 提示出来，供逐步收敛。
MAP_KEYS = {
    "INDEX 主文件行数": "capacity.index_hot_rows",
    "STATE 字数上限": "capacity.state_max_chars",
    "reports 归档阈值": "capacity.report_archive_threshold",
    "协作模式": "collaboration.mode",
    "定期排查": "tools.periodic_audit",
    "多语言门禁": "tools.lang_gates",
}
#: **开关类**的配置键：MAP 里写「开 / 关」，不是数字。
#  为什么要单独列：`config()` 原来只认数字与模式名——
#  于是「定期排查：开」这类**写了却读不到**的开关，实际真值一直来自出厂默认。
#  这不是"少读一个值"，是**开关承诺没人核实**（本包称之为假账）。
BOOL_KEYS = {"tools.periodic_audit", "tools.lang_gates"}
#  **不登记这三个键**：tools.closeout_gate / auto_archive / auto_index_write。
#  理由：它们**读不到**（缺 MAP 别名）**也不生效**（唯一读者只打一句 note 就继续执行），
#  属于「开关是承诺」的反面——宁可不承诺，也不要一个兑现不了的开关。
#: **枚举类**配置键：MAP 里写已知词表里的一个词。
#  权限档位为什么要登记：本包约束的是「路径」不是「能力」（artifacts.md §9.3）——
#  有人绕过入口直接改文件时，**必须先能回答「他为什么能」**。登记过的取舍叫决定，没登记的叫意外。
ENUM_KEYS = {
    "environment.sandbox": {
        "danger-full-access": "danger-full-access", "完全权限": "danger-full-access", "全权": "danger-full-access",
        "workspace-write": "workspace-write", "工作区可写": "workspace-write", "限工作区": "workspace-write",
        "read-only": "read-only", "只读": "read-only",
    },
}
MAP_ALIASES = {
    "capacity.index_hot_rows": ["INDEX 主文件行数", "INDEX 行数"],
    "capacity.state_max_chars": ["STATE 字数上限", "STATE 上限"],
    "capacity.report_archive_threshold": ["reports 归档阈值", "报告归档阈值"],
    "collaboration.mode": ["协作模式", "运行模式"],
    "tools.periodic_audit": ["定期排查", "定期审计"],
    "tools.lang_gates": ["多语言门禁", "语言门禁"],
    "environment.sandbox": ["权限档位", "沙箱档位", "运行权限"],
}
#: 模式名的历史别名 → 规范名。实测源包写 light/standard/coordination，
#  而实例写「轻量／标准／统筹」——同一套东西两套名字，正是口径漂移的样本。
MODE_ALIASES = {
    "light": "light", "轻量": "light",
    "standard": "standard", "标准": "standard",
    "coordination": "coordination", "统筹": "coordination",
}
_ALIAS_USED = set()

def config(root, key, fallback=None):
    """取值顺序：实例 MAP 规则段 → 出厂默认 config/defaults.yml → fallback。

    为什么先读实例：每项目阈值不同（这是功能契约，见 references/change-control.md §0）。
    """
    root = Path(root)
    map_txt = read(root / "MAP.md") or ""
    labels = MAP_ALIASES.get(key, [])
    for label in labels:
        if key == "collaboration.mode":
            # 模式名单独处理：必须命中已知词表，避免抓到括号里的解释文字
            pat = re.escape(label) + r"[^0-9A-Za-z]{0,8}(light|standard|coordination|轻量|标准|统筹)"
        elif key in ENUM_KEYS:
            # 枚举类：只认词表里的写法；认不出就当没配（**不猜**——猜错比没有更糟）
            pat = re.escape(label) + r"[^0-9A-Za-z]{0,8}(" + "|".join(
                re.escape(k) for k in sorted(ENUM_KEYS[key], key=len, reverse=True)) + ")"
        elif key in BOOL_KEYS:
            # 开关类：认「开 / 关 / 启用 / 关闭 / on / off / true / false」
            #  不认的写法不静默取默认——那会让「没配」看起来像「配好了」
            pat = re.escape(label) + r"[^0-9A-Za-z]{0,8}(开|关|启用|停用|on|off|true|false|yes|no)"
        else:
            pat = re.escape(label) + r"[^0-9A-Za-z]{0,8}([0-9]+\s*k?)"
        m = re.search(pat, map_txt, re.I)
        if m:
            raw = m.group(1).strip().lower()
            if key in ENUM_KEYS:
                if label != labels[0]:
                    _ALIAS_USED.add("%s（实例写作「%s」，规范用词「%s」）" % (key, label, labels[0]))
                return ENUM_KEYS[key].get(raw, raw)
            if key in BOOL_KEYS:
                if label != labels[0]:
                    _ALIAS_USED.add("%s（实例写作「%s」，规范用词「%s」）" % (key, label, labels[0]))
                return raw in ("开", "启用", "on", "true", "yes")
            if label != labels[0]:
                _ALIAS_USED.add("%s（实例写作「%s」，规范用词「%s」）" % (key, label, labels[0]))
            if raw.endswith("k"):
                return int(float(raw[:-1]) * 1000)
            if raw.isdigit():
                return int(raw)
            canon = MODE_ALIASES.get(raw, raw)
            if canon != raw:
                _ALIAS_USED.add("模式名别名（实例写作「%s」，规范名「%s」）" % (raw, canon))
            return canon
    d = _load_defaults()
    if key in d:
        return d[key]
    return fallback

# ── 登记/声明类取值（自由文本）────────────────────────────────
#  与 config() 的分工：config 只认数字 / 模式 / 开关 / 枚举（**有界的配置**）；
#  这里取**无界的声明**（例如底座登记的模型名）。放在 _common 是为了**只有一条读取路径**，
#  否则每个脚本各写一遍正则，迟早漂移成两套口径。
def map_line_value(root, labels):
    """按标签从 MAP 规则段取自由文本值；取不到返回空串。"""
    txt = read(Path(root) / "MAP.md") or ""
    for label in labels:
        # 分隔符只允许**标点与空白**，不吃汉字：
        #  用 [^0-9A-Za-z] 会把「：某底座-」整段当分隔符，把值截成后半截（实测踩过）。
        sep = r"[\s：:；;·,，\-—]{0,8}"
        m = re.search(re.escape(label) + sep + r"([^\n|]{1,60})", txt)
        if m:
            v = m.group(1).strip().strip("`*_ \u3000").strip()
            # 去掉括号注释：登记写法常带解释（「qwen-max（2026-09 换的）」），值只取名字
            v = re.split(r"[（(]", v, 1)[0].strip()
            if v and v not in ("—", "-", "待填", "[待填]"):
                return v
    return ""

# ── 扫描前归一化：**文档里的示例不是数据** ──────────────────────────
#  为什么需要：规范文档为了说明「旧格式为什么错」，会把错误写法当**反例**写进来
#  （例如 audit.md 里的旧人检标记）。若不剥掉代码块与行内代码，
#  机器检查器就会把**自己的规范说明**当成真实数据去报错——门禁自污染。
def strip_code(text):
    """剥掉围栏代码块与行内代码，返回仅剩正文的文本（行数不变，便于报行号）。"""
    if not text:
        return text
    out, in_fence = [], False
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            out.append("")
            continue
        if in_fence:
            out.append("")
            continue
        # 行内代码：成对反引号的内容置空（保留两侧正文）
        out.append(re.sub(r"`[^`\n]*`", "", line))
    return "\n".join(out)

# ── 磁盘扫描 ──────────────────────────────────────────────────
def list_md(d):
    p = Path(d)
    return sorted(p.glob("*.md")) if p.is_dir() else []

IS_TEMPLATE = re.compile(r"\.template\.md$", re.I)

def iter_cards(root):
    """任务卡：tasks\\*.md，排除模板。"""
    return [p for p in list_md(Path(root) / "tasks") if not IS_TEMPLATE.search(p.name)]

def iter_reports(root):
    """交接记录：reports\\*.md，排除模板。"""
    return [p for p in list_md(Path(root) / "reports") if not IS_TEMPLATE.search(p.name)]

def index_rows(path):
    """解析索引表行 → [(cells, lineno)]；只看形如 | XX0000 | 开头的行。"""
    txt = read(path)
    if not txt:
        return []
    rows = []
    for i, line in enumerate(txt.splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and re.match(r"^[A-Z]{2}[0-9]{4,5}$", cells[0]):
            rows.append((cells, i))
    return rows

def newest_handoff(root):
    """取"最新记录"：优先交接号最大者，否则文件名倒序第一篇。

    口径与引用它的门禁一致——只在**已存在**的记录里选，不臆造。
    """
    reports = iter_reports(root)
    if not reports:
        return None, -1
    best, best_no = None, -1
    for p in reports:
        m = re.search(r"交接\s*#(\d+)", read(p) or "")
        if m:
            n = int(m.group(1))
            if n > best_no:
                best_no, best = n, p
    # 全部记录都没有交接号时，取**最新**一篇（文件名含日期前缀，正序末位即最新）。
    # 旧写法在循环里兜底会取到**最旧**一篇——方向反了。
    return (best if best is not None else reports[-1]), best_no

def resolve_under(root, raw):
    """把指针字段（MAP / 索引 / 记录里写的路径）解析为绝对路径，**并约束在工作区内**。

    为什么必须约束：指针字段的内容可能来自被修改过的文件（或被人误写）。
    不约束的话，`resolve_under(root, "C:/Windows/...")` 会把**工作区外**的路径当合法目标去核对——
    工作区的边界就成了软的。本包既然声称「工作区是外部记忆的边界」，这条就必须硬。

    例外：**项目代码根**（`代码根路径` / `涉及`）本来就可以在工作区外（源码常在别处），
    那些位置**不走本函数**，由调用方各自处理——所以这里可以放心收紧。

    返回：解析后的绝对路径；越界或非法返回 None。
    """
    if not raw or raw in ("—", "-"):
        return None
    s = raw.strip().strip("`").replace("\\", os.sep).replace("/", os.sep)
    p = Path(s)
    base = Path(root).resolve()
    cand = p.resolve() if p.is_absolute() else (base / p).resolve()
    try:
        cand.relative_to(base)
    except ValueError:
        # 越界：**不在这里报错**（本函数是工具函数，报错该由门禁做），返回 None 让调用方按"取不到"处理
        return None
    return cand
