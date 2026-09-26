# -*- coding: utf-8 -*-
"""code_metrics.py —— 代码度量门禁（三档阈值机检）

用法：python code_metrics.py <源码根> [--ws=<工作区根>] [--lang=python]（**本包只度量 Python**；--lang 写 java/javascript 只是显式声明「本栈交给外部工具」，本包会给出 [待核] 指路，不产出读数）
      --ws 省略时按源码根向上找实例 MAP（阈值与分层一律来自实例，不写死在脚本里）
何时跑：每次改代码后 / 提交前
依据：references/code-quality.md §1、§2（三档阈值 = 推荐线 / 预警区 / 拦截线）
      §5 依赖方向 · §1.4 扫描覆盖；风格类条款（references/code-style.md）不机检

设计要点：
  · **工具只配拦截线**——推荐线交人工评审，避免文档与工具两套数值
  · **超限即信号**——超限必须写明原因；空话豁免本身就是设计债探针
  · Python 用 AST 精确测量；其他语言本轮不做（避免行/缩进启发式误报）
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import config, note, ok, problem, read, summary, tbd, run  # noqa: E402


# ── 依赖方向与循环依赖（references/code-quality.md §5）────────────
#: 分层与例外**从实例 MAP 规则段读**，不从脚本里写死——
#  每项目分层不同（这是功能契约，见 references/change-control.md §0）。
#: 反引号常量（用于剥掉 MAP 里值的包裹符号）
BQ = chr(96)

SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".mypy_cache", ".pytest_cache",
             ".ruff_cache", "build", "dist", "venv", ".venv", ".eggs", "site-packages"}


def _map_line(root, keyword):
    """在 MAP **规则段**里找含 keyword 的那一条，返回其值部分。

    只认 **列表项**（以「- 」开头）——否则标题行、说明行里的同名词也会被当成配置，
    实测踩过：MAP 标题写「分层演示」，整个标题被当成分层表。**配置解析必须比"含关键词"更严。**
    """
    for line in (read(Path(root) / "MAP.md") or "").splitlines():
        s = line.strip()
        if not (s.startswith("- ") or s.startswith("* ")) or keyword not in s:
            continue
        v = s.split(keyword, 1)[1]
        v = re.sub(r"^[^：:]*[：:]", "", v)
        return v.strip().strip(BQ).strip()
    return ""


def read_layers(root):
    raw = _map_line(root, "分层") or _map_line(root, "层级")
    if not raw:
        return []
    parts = [x.strip().strip(BQ) for x in re.split(r">|→|›", raw) if x.strip()]
    return parts if len(parts) >= 2 else []


def read_dep_exceptions(root):
    raw = _map_line(root, "依赖例外") or _map_line(root, "例外边")
    if not raw or raw in ("—", "-", "无"):
        return set()
    return {x.strip().strip(BQ) for x in re.split(r"[,，;；]", raw) if x.strip()}


def _modname(rel):
    s = str(rel).replace("\\", "/")
    if s.endswith("/__init__.py"):
        s = s[:-12]
    elif s.endswith(".py"):
        s = s[:-3]
    return s.replace("/", ".")


def _imports(src_text, modname):
    """AST 取 import 目标（含相对导入归一到本包）。"""
    out = set()
    try:
        tree = ast.parse(src_text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                parts = modname.split(".")
                base = parts[: max(1, len(parts) - node.level)]
                if node.module:
                    base = base + node.module.split(".")
                pkg = ".".join(base)
            elif node.module:
                pkg = node.module
            else:
                continue
            out.add(pkg)
            # 「from pkg import mod」里的 mod 可能是子模块——补一条候选取精确匹配，
            # 否则环检测会退化到包粒度，把 ui.panel ↔ ui.viewer 这类子模块环漏掉。
            for a in node.names:
                out.add(pkg + "." + a.name)
    return out


def check_dependencies(root, files):
    """① 分层方向 ② 循环依赖。两者都支持「已登记的例外」。"""
    layers = read_layers(root)
    exceptions = read_dep_exceptions(root)
    mods = {}
    for p in files:
        if p.suffix.lower() != ".py":
            continue
        rel = p.relative_to(root)
        if set(rel.parts) & SKIP_DIRS:
            continue
        mods[_modname(rel)] = p
    if not mods:
        note("无本地 Python 模块——依赖方向检查跳过")
        return
    tops = {m.split(".")[0] for m in mods}
    edges = {}
    for mod, p in mods.items():
        for tgt in _imports(read(p) or "", mod):
            if tgt.split(".")[0] not in tops:
                continue
            if tgt in mods:                       # 精确命中优先（子模块环靠它）
                edges.setdefault(mod, set()).add(tgt)
                continue
            cand = [m for m in mods if m.startswith(tgt + ".")]
            edges.setdefault(mod, set()).add(min(cand, key=len) if cand else tgt.split(".")[0])

    if layers:
        order = {name: i for i, name in enumerate(layers)}
        bad = []
        for src, dsts in sorted(edges.items()):
            s = src.split(".")[0]
            for d in dsts:
                tk = d.split(".")[0]
                if s in order and tk in order and order[s] > order[tk]:
                    k1, k2 = "%s->%s" % (src, d), "%s->%s" % (s, tk)
                    if k1 not in exceptions and k2 not in exceptions:
                        bad.append(k1)
        if bad:
            for k in bad[:12]:
                problem("[依赖方向] 低层引用高层：%s" % k)
        else:
            ok("分层方向无违例（%s）" % " > ".join(layers))
    else:
        note("MAP 规则段未声明「分层」——依赖方向检查跳过"
             "（在 MAP 写一行：- **分层**：ui > agent > core > llm > config > utils 即启用）")

    index, low, stack, on, sccs = {}, {}, [], set(), []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(edges.get(v, ())):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    sys.setrecursionlimit(20000)
    for v in sorted(edges):
        if v not in index:
            strong(v)

    def registered(comp):
        members = set(comp)
        for x in comp:
            for y in edges.get(x, ()):
                if y in members and not (("%s->%s" % (x, y)) in exceptions
                                         or ("%s->%s" % (y, x)) in exceptions):
                    return False
        return True

    for c in sccs:
        if registered(c):
            note("[循环依赖·已登记例外] %s" % " ↔ ".join(c))
    unreg = [c for c in sccs if not registered(c)]
    if unreg:
        for c in unreg[:8]:
            problem("[循环依赖] %s（未登记例外；确属有意为之请在 MAP 写「依赖例外」）" % " ↔ ".join(c))
    elif not sccs:
        ok("本地模块依赖图无环")


def report_scope(root, files, langs):
    """门禁读数可信（code-quality.md §1.4）：报扫描范围，别让退出码 0 等于没看。"""
    all_src = [p for p in root.rglob("*") if p.is_file() and _lang(p) in langs
               and not (set(p.relative_to(root).parts) & SKIP_DIRS)]
    scanned = [p for p in files if not (set(p.relative_to(root).parts) & SKIP_DIRS)]
    total, n = len(all_src), len(scanned)
    pct = (n * 100.0 / total) if total else 100.0
    print("扫描范围：%d / %d 个目标语言文件（%.0f%%）" % (n, total, pct))
    thr = float(config(root, "code_quality.scope_min_percent", 80))
    if total and pct < thr:
        problem("扫描覆盖 %.0f%% 低于阈值 %s%%——退出码 0 不代表全绿，只代表看过的部分没问题" % (pct, thr))
    elif total:
        ok("扫描覆盖达标（阈值 %s%%）" % thr)


# ── 兜底阈值：**只为本脚本脱离技能包单独使用而存在** ──────────────
# 取值顺序仍是「实例 MAP → config/defaults.yml → 本兜底」，所以：
#   · 完整技能包里本表**永远用不到**（defaults.yml 先命中）；
#   · 单独拷走本脚本时，没有 defaults.yml 也能跑——这就是它能独立使用的原因。
# ⚠ 同一数值出现在两处＝漂移起点，故此处**集中声明**，并由 gen_views.py 第 6 节逐键比对
#   config/defaults.yml：漂移会被机器抓到，不靠人记得。
FALLBACKS = {
    "code_quality.func_lines.recommended": 50,
    "code_quality.func_lines.warning": 100,
    "code_quality.func_lines.blocked": 100,
    "code_quality.nesting_depth.recommended": 3,
    "code_quality.nesting_depth.warning": 4,
    "code_quality.nesting_depth.blocked": 4,
    "code_quality.cyclomatic_complexity.recommended": 10,
    "code_quality.cyclomatic_complexity.warning": 15,
    "code_quality.cyclomatic_complexity.blocked": 15,
    "code_quality.file_lines.recommended": 600,
    "code_quality.file_lines.blocked": 600,
    "code_quality.exemption.min_reason_chars": 10,
    "code_quality.comment_density.min_per_function": 1.0,
    "code_quality.comment_density.max_per_function": 1.5,
}
#: 空话词表兜底（同 FALLBACKS 的道理：默认值在 config，兜底只为单独可用）
#  口径：**注释与豁免理由一律中文**（标识符英文）——见 references/code-style.md §S1，故词表只收中文。
FALLBACK_HOLLOW = ["逻辑需要", "性能考虑", "业务需要", "历史原因", "暂时", "先这样",
                   "太复杂", "算法需要", "按需", "不好拆"]


def _exempt_re(root, n_chars):
    """豁免标注正则：NOPMD / noqa 之后必须跟分隔符与原因，**长度取自配置**。

    取配置而非写死：`code_quality.exemption.min_reason_chars` 若只是文档里的一个数，
    就等于**写了没人管**——本包对这种"声明了但没人执行"的形态有专门的名字：假账。
    """
    return re.compile(r"(NOPMD|noqa)[^\n]*?[-—:：]\s*(\S.{%d,})" % max(int(n_chars) - 1, 0), re.I)


def _hollow_re(root):
    """空话判定：忽略首尾标点、空白与括号，**只判"整句就是空话"**。

    为什么要容忍标点：实测理由有各种收尾（"逻辑需要。" / "（逻辑需要）" / "逻辑需要，"）。
    只匹配裸词会漏掉一大片，而漏掉的恰是最常见的敷衍写法。
    **只判整句**：后面接了实义内容的不算空话（"逻辑需要，但已抽成独立函数，见 issue 42" 是有信息量的）。
    """
    words = config(root, "code_quality.exemption.hollow_words", FALLBACK_HOLLOW) or FALLBACK_HOLLOW
    alt = "|".join(re.escape(str(w)) for w in words)
    return re.compile(r"^[\s“”\"'（(]*(" + alt + r")[\s。.,，;；!！?？)）”\"']*$", re.I)

def _lang(path):
    return {"py": "python", "java": "java", "js": "javascript", "ts": "javascript",
            "jsx": "javascript", "tsx": "javascript"}.get(path.suffix.lstrip(".").lower())

def _thresholds(root):
    def g(k):
        return config(root, "code_quality." + k, FALLBACKS["code_quality." + k])
    return {
        "func_lines": (g("func_lines.recommended"), g("func_lines.warning"), g("func_lines.blocked")),
        "nesting": (g("nesting_depth.recommended"), g("nesting_depth.warning"), g("nesting_depth.blocked")),
        "ccn": (g("cyclomatic_complexity.recommended"), g("cyclomatic_complexity.warning"),
                g("cyclomatic_complexity.blocked")),
        "file_lines": (g("file_lines.recommended"), g("file_lines.blocked")),
        "comment": (g("comment_density.min_per_function"), g("comment_density.max_per_function")),
    }

def _eff_lines(lines, node):
    """函数有效行：去空行 / 纯注释 / docstring。"""
    doc = set()
    body = getattr(node, "body", None)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        doc.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    n = 0
    for i in range(node.lineno, (node.end_lineno or node.lineno) + 1):
        s = lines[i - 1].strip()
        if s and not s.startswith("#") and i not in doc:
            n += 1
    return n

def _ccn(node):
    """近似圈复杂度：判定点 + 1。"""
    n = 1
    for x in ast.walk(node):
        if isinstance(x, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                          ast.With, ast.AsyncWith, ast.Assert, ast.IfExp)):
            n += 1
        elif isinstance(x, ast.BoolOp):
            n += len(x.values) - 1
        elif isinstance(x, ast.comprehension):
            n += 1 + len(x.ifs)
        elif hasattr(ast, "Match") and isinstance(x, ast.Match):
            n += len(x.cases)
    return n

#: 会真正增加控制流嵌套的语句节点。
#  为什么要按"语句类别"数而不是按缩进数：
#    缩进启发式会把多行表达式、跨行函数调用、字典/列表字面量、推导式都算成"嵌套"，
#    在 Python 上严重高估（按缩进口径实测报出 188 条，几乎全是假阳性——
#    **误报掩盖真实问题正是门禁的首要失效原因**）。改为 AST 口径：只数真正开块的语句。
_NESTING_STMTS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                  ast.Try, ast.ExceptHandler, ast.FunctionDef, ast.AsyncFunctionDef,
                  ast.ClassDef)
if hasattr(ast, "Match"):
    _NESTING_STMTS = _NESTING_STMTS + (ast.Match,)

def _nest(lines, node):
    """AST 口径的嵌套深度：函数体内"开块语句"的最大层数（函数自身不计）。"""
    best = 0

    def walk(n, depth):
        nonlocal best
        for child in ast.iter_child_nodes(n):
            step = 1 if isinstance(child, _NESTING_STMTS) and not isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else 0
            d = depth + step
            if step:
                best = max(best, d)
            walk(child, d)

    walk(node, 0)
    return best

def _eff_file_lines(lines, tree):
    """文件有效行：去空行 / 纯注释行 / 模块 docstring。

    与函数级 `_eff_lines` **同一套口径**——否则同一指标在文件级与函数级两套算法，
    正是本规范明令禁止的"同一指标两套数值"（正文 §1.1 与 §1.2）。
    """
    doc = set()
    if tree.body and isinstance(tree.body[0], ast.Expr) \
            and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        doc.update(range(tree.body[0].lineno, (tree.body[0].end_lineno or tree.body[0].lineno) + 1))
    n = 0
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s and not s.startswith("#") and i not in doc:
            n += 1
    return n


def _comment_density(lines, tree):
    """注释密度＝函数体内注释行数 ÷ 函数个数，单位**条/函数**（键名 per_function 即此意）。

    口径提醒：**不是"每条代码多少注释"，是"每个函数多少条注释"**——
    首次实现按"条/行"算，结果上限 1.5 永远不可能触发（注释行数不可能超过总行数的 1.5 倍），
    即**一个永远不会红的检查**。这类"恒绿门禁"比没有门禁更坏：它制造"查过了"的错觉。
    docstring 不计入（它是"函数头说明"，是标配，不是密度）。
    """
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not funcs:
        return 0.0, 0, 0
    doc, inside = set(), set()
    for n in funcs:
        inside.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        if n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str):
            doc.update(range(n.body[0].lineno, (n.body[0].end_lineno or n.body[0].lineno) + 1))
    cmts = sum(1 for i in sorted(inside)
               if i <= len(lines) and lines[i - 1].strip().startswith("#") and i not in doc)
    return cmts * 1.0 / len(funcs), len(funcs), cmts


def analyse_python(path, lines, th):
    hits = []
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError as e:
        return [("block", 0, "语法错误 L%s：%s" % (e.lineno, e.msg))]
    r_fl, w_fl, b_fl = th["func_lines"]
    r_n, w_n, b_n = th["nesting"]
    r_c, w_c, b_c = th["ccn"]
    r_fi, b_fi = th["file_lines"]
    _c_min, c_max = th["comment"]

    # ── 文件长度（正文 §1 三档；口径由 config 的 file_lines.unit 声明）──
    eff_file = _eff_file_lines(lines, tree)
    if eff_file > b_fi:
        hits.append(("block", 1, "文件有效行 %d > 拦截线 %d" % (eff_file, b_fi)))
    elif eff_file > r_fi:
        hits.append(("warn", 1, "文件有效行 %d（预警区 %d~%d，须写明未拆分原因）" % (eff_file, r_fi, b_fi)))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        eff, ccn, nest = _eff_lines(lines, node), _ccn(node), _nest(lines, node)
        if eff > b_fl:
            hits.append(("block", node.lineno, "%s() %d 行 > 拦截线 %d" % (node.name, eff, b_fl)))
        elif eff > r_fl:
            hits.append(("warn", node.lineno,
                         "%s() %d 行（预警区 %d~%d，须写明未拆分原因）" % (node.name, eff, r_fl, b_fl)))
        if nest > b_n:
            hits.append(("block", node.lineno, "%s() 嵌套 %d 层 > 拦截线 %d" % (node.name, nest, b_n)))
        elif nest > r_n:
            hits.append(("warn", node.lineno, "%s() 嵌套 %d 层（预警区）" % (node.name, nest)))
        if ccn > b_c:
            hits.append(("block", node.lineno, "%s() 圈复杂度 %d > 拦截线 %d" % (node.name, ccn, b_c)))
        elif ccn > r_c:
            hits.append(("warn", node.lineno, "%s() 圈复杂度 %d（预警区）" % (node.name, ccn)))
    # ── 注释密度（正文 §4：**密度是上限而非下限**，单位 条/函数）──
    # 只查上限：对自解释性好的代码，凑数的注释只能是"翻译式注释"，是噪音。
    # 故这是**预警区**信号（超限须写明理由），不是拦截线——
    # 拿它拦人，等于把"注释写得清楚"判成违规。
    if c_max:
        dens, nf, nc = _comment_density(lines, tree)
        # 函数太少时比值不稳（1 个函数 3 条注释＝密度 3.0）——噪声会掩盖真问题，
        # 故只在函数数达到下限时才判；这是**误报防护**，不是放宽标准。
        if nf >= 3 and dens > float(c_max):
            hits.append(("warn", 1, "注释密度 %.2f 条/函数 > 上限 %s（%d 条注释 / %d 个函数；"
                                    "预警区：翻译式注释嫌疑，须写明理由）" % (dens, c_max, nc, nf)))
    return hits


# ── 豁免清单导出（回查用）：把"全量收集，一条不漏"从要求变成一条命令 ──
def list_exemptions(files, th, exempt_re, hollow_re):
    """导出全部豁免标注与预警区条目，按聚集度排序。

    为什么要有这个模式：正文 §2.3 要求"全量收集，一条不漏"，但**没有工具**——
    靠人 grep 的结果必然是漏的，而漏掉的恰恰是"最不想被看见的那些"。
    机械步骤交给脚本：一次跑出清单 + 聚集度，人只做判断。
    """
    rows, by_file = [], {}
    for p in sorted(files):
        if _lang(p) != "python":
            continue
        lines = (read(p) or "").splitlines()
        for kind, ln, msg in analyse_python(p, lines, th):
            if kind != "warn":
                continue          # 拦截线不是豁免对象：它没得豁免（超线即阻断）
            seg = "\n".join(lines[max(0, ln - 6):ln + 2])
            m = exempt_re.search(seg)
            if m:
                reason = m.group(2).strip()
                verdict = "空话" if hollow_re.match(reason) else "已说明"
            else:
                reason, verdict = "", "未说明"
            rows.append((p, ln, verdict, reason, msg))
            by_file[p] = by_file.get(p, 0) + 1
    print("== 豁免与预警区清单（回查用） ==")
    if not rows:
        print("[通过] 没有需要回查的条目（无预警区、无豁免标注）")
        return summary()
    for p, ln, verdict, reason, msg in rows:
        print("[%s] %s:%d  %s" % (verdict, p.name, ln, msg))
        if reason:
            print("         理由：%s" % reason[:100])
    print("-" * 46)
    print("== 聚集度（同文件条目数，降序）——单条不重要，分布才暴露问题 ==")
    for p, n in sorted(by_file.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        print("   %2d  %s" % (n, p.name))
    cnt = {}
    for _p, _l, v, _r, _m in rows:
        cnt[v] = cnt.get(v, 0) + 1
    print("   合计 %d 条：%s" % (len(rows), " · ".join("%s %d" % (k, v) for k, v in sorted(cnt.items()))))
    print("   判据与处置见 references/code-quality.md §2.3（三选一：真例外 / 设计债 / 敷衍）")
    return summary()

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法：python code_metrics.py <源码根> [--ws=<工作区根>] [--lang=python]（**本包只度量 Python**；--lang 写 java/javascript 只是显式声明「本栈交给外部工具」，本包会给出 [待核] 指路，不产出读数）")
        print("      --exemptions  只导出豁免与预警区清单 + 聚集度（回查用，恒退出 0）")
        return 3
    # 一律解析成绝对路径：相对 src + 绝对 --ws 会让 p.relative_to(root) 直接抛错（实测踩过），
    #  表现为"脚本自身错误"（退出码 3）——而用户只是路径写法不同而已。
    src = Path(args[0]).resolve()
    if not src.is_dir():
        problem("源码根不存在：%s" % src)
        return summary()
    # 配置与 MAP 里的分层声明读**工作区根**，不是源码根——两者物理隔离是本技能的前置设计。
    # 不给 --ws 时退回源码根（兼容只看代码、没有工作区的场景）。
    ws = src
    langs = {"python"}
    for a in sys.argv[1:]:
        if a.startswith("--lang"):
            langs = {x.strip() for x in a.split("=", 1)[-1].split(",") if x.strip()}
        elif a.startswith("--ws="):
            ws = Path(a.split("=", 1)[1]).resolve()
    th = _thresholds(ws)
    # 行数口径：config 声明 unit（默认 effective）。脚本**只实现有效代码行**——
    # 实例若声明了物理行口径，必须当面说出来，不能让两套口径同时存在而不自知。
    unit = str(config(ws, "code_quality.file_lines.unit", "effective"))
    if unit not in ("effective", "有效", "有效代码行", "有效行"):
        note("实例声明 file_lines.unit=%s，但本脚本只按**有效代码行**计算——口径不一致，请择一为准" % unit)
    exempt_re = _exempt_re(ws, config(ws, "code_quality.exemption.min_reason_chars",
                                      FALLBACKS["code_quality.exemption.min_reason_chars"]))
    hollow_re = _hollow_re(ws)
    root = src
    print("阈值（实例 MAP 优先 / 出厂默认兜底）：函数 %s · 嵌套 %s · 圈复杂度 %s"
          % (th["func_lines"], th["nesting"], th["ccn"]))

    files = [p for p in root.rglob("*") if p.is_file() and _lang(p) in langs
             and "__pycache__" not in p.parts and "node_modules" not in p.parts]
    # ── 回查模式：只导出清单与聚集度，不做门禁判定（退出码恒 0）──
    if "--exemptions" in sys.argv:
        return list_exemptions(files, th, exempt_re, hollow_re)
    if not files:
        tbd("未找到目标语言源文件（langs=%s）" % "、".join(sorted(langs)))
        return summary()

    # 只点名了非 Python 语言 → 不许静默通过。
    #  外部评审实测过这个坑，比它说的更严重：--lang=java 会走完全程、报告 0 问题、**退出码 0**，
    #  于是一条「什么都没测」的命令在 CI 里恒绿——正是本包定义的「恒绿门禁」。
    #  本包不度量非 Python（行/缩进启发式误报率高），所以正确行为是 [待核] + 指路，不是沉默。
    _py = [p for p in files if _lang(p) == "python"]
    _other = [p for p in files if _lang(p) != "python"]
    if not _py and _other:
        tbd("目标语言 %s 中没有 Python 文件（%d 个非 Python）——本包不度量非 Python。"
            "请按 adapters/<栈>.md 接线到该栈成熟工具（ESLint / Checkstyle / golangci-lint / clippy…），"
            "再用 scripts/lang_gates.py record 留痕。**保持沉默会让这道门禁恒绿**。"
            % ("、".join(sorted(langs)), len(_other)))
        return summary()

    blocked = warned = 0
    hollow = []
    for p in sorted(files):
        if _lang(p) != "python":
            note("非 Python 文件 %s 本轮不做度量（行/缩进启发式易误报）" % p.name)
            continue
        lines = (read(p) or "").splitlines()
        for kind, ln, msg in analyse_python(p, lines, th):
            loc = "%s:%d" % (p.relative_to(root), ln)
            if kind == "block":
                blocked += 1
                problem("[拦截线] %s %s" % (loc, msg))
            else:
                warned += 1
                seg = "\n".join(lines[max(0, ln - 6):ln + 2])
                m = exempt_re.search(seg)
                if m and not hollow_re.match(m.group(2).strip()):
                    note("[预警区·已说明] %s %s" % (loc, msg))
                elif m:
                    hollow.append("%s 理由空话：%r" % (loc, m.group(2).strip()[:24]))
                else:
                    problem("[预警区·未说明] %s %s" % (loc, msg))

    print("-" * 46)
    report_scope(root, files, langs)
    check_dependencies(ws, files)
    print("-" * 46)
    print("度量 %d 个文件（%s）" % (len(files), "、".join(sorted(langs))))
    print("拦截线命中 %d · 预警区命中 %d" % (blocked, warned))
    for h in hollow:
        problem("豁免理由疑似空话（超限即信号）：%s" % h)
    if warned and not hollow:
        note("预警区均附说明——注意定期回查理由真伪（人发现一次 → 机器永久拦截）")
    return summary()

if __name__ == "__main__":
    sys.exit(run(main))