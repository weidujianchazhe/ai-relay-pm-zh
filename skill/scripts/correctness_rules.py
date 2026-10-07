# NOPMD: 规则的就地说明是可校验的判据来源；删掉注释即失去复核依据。
# -*- coding: utf-8 -*-
"""correctness_rules.py —— Correctness 域结构模式规则（Python）

为什么要有这个脚本：
  实测（见 references/empirical-evidence）表明规模指标（长度/CCN/嵌套）**不预测缺陷**；
  唯一被人工发现的真缺陷与规模无关，其形态是「循环里少一句收集」
  （email/feedparser.py::FeedParser._parsegen：epilogue = [] 后循环未 append，随后直接 join）。
  本脚本用 **AST 结构模式匹配**（不是数值比较）去找这一类形状 —— 它能指向具体位置。

规则（Python 最小集，先做高精度、低误报的三条）：
  C1 阻断  空容器就地建立 -> 紧邻 for 循环未收集 -> 循环后仍被使用（漏写收集语句）
  C2 阻断  裸 except 且仅 pass（异常被吞）；非裸但仅 pass -> 观察
  C3 观察  open(...) 赋值后未见 close() 或 with，且未交给调用方

退出码：0 通过 · 1 有[问题]（阻断）· 2 仅[建议] · 3 脚本/用法错误
依赖：仅 Python 标准库（ast / sys / pathlib）
"""
import ast
import hashlib
import re
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, tbd  # noqa: E402

MUTATORS = ("append", "extend", "insert", "add", "update", "setdefault", "appendleft")


def _empty_name(node):
    """若 node 是「赋值为空字面量」，返回目标名；否则 None。"""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    t = node.targets[0]
    if not isinstance(t, ast.Name):
        return None
    v = node.value
    if isinstance(v, ast.List) and not v.elts:
        return t.id
    if isinstance(v, ast.Dict) and not v.keys:
        return t.id
    if isinstance(v, ast.Set) and not v.elts:
        return t.id
    return None


def _loop_touches(loop, name):
    """循环体内是否可能写入 name，或把它作为实参传出（两种都保守放过）。"""
    for n in ast.walk(loop):
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store):
            return True
        # 下标赋值 d[k] = v —— 这是最常用的字典构建方式，必须算作写入通道
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == name:
            return True
        # 属性赋值 d.a = v
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == name and isinstance(n.ctx, ast.Store):
            return True
        # 增量赋值 d += x（AugAssign 的目标是 Name，已在上面 Store 分支覆盖）
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr in MUTATORS:
                if isinstance(f.value, ast.Name) and f.value.id == name:
                    return True
            for a in list(n.args) + [k.value for k in n.keywords]:
                if isinstance(a, ast.Name) and a.id == name:
                    return True
    return False


def _used_after(fn, name, lineno):
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load) and n.lineno > lineno:
            return True
    return False


def check_function(fn):
    out = []
    body = fn.body
    for i, stmt in enumerate(body):
        name = _empty_name(stmt)
        if not name:
            continue
        loop = None
        for s in body[i + 1:i + 3]:
            if isinstance(s, (ast.For, ast.AsyncFor)):
                loop = s
                break
            if isinstance(s, ast.Assign):
                continue
            break
        if loop is None:
            continue
        if _loop_touches(loop, name):
            continue
        if not _used_after(fn, name, loop.end_lineno):
            continue
        out.append(("block", loop.lineno,
                    "「%s」在循环前建立为空，循环体 L%d-%d 内未见收集，循环后仍被使用 —— 疑似漏写收集语句" % (name, loop.lineno, loop.end_lineno)))
    # M1 浮点判等：与【非整数】浮点字面量比较（0.1 / 1.5 类；== 0.0 属精确值，放过）
    for n in ast.walk(fn):
        if not isinstance(n, ast.Compare):
            continue
        for op, _c in zip(n.ops, n.comparators):
            if not isinstance(op, (ast.Eq, ast.NotEq)):
                continue
            for side in [n.left] + list(n.comparators):
                if not (isinstance(side, ast.Constant) and isinstance(side.value, float)):
                    continue
                if not (-1e300 < side.value < 1e300 and side.value != int(side.value)):
                    continue
                # 收窄（2026-10-02 外部抽检发现）：0.5 / 1.5 / 0.25 这类【十进制可精确表示】的值
                # 判等是安全的，不该报（外部样本误报率曾达 44%）。判据：十进制分母是否为 2 的幂。
                try:
                    _den = Fraction(repr(side.value)).denominator
                    if (_den & (_den - 1)) == 0:
                        continue
                except Exception:
                    pass
                if True:
                    out.append(("block", n.lineno,
                                "浮点判等：与 %r 用 ==/!= 比较 —— 二进制浮点不精确，应用容差比较（math.isclose）" % side.value))
                    break
    # M4 无上限迭代：while True 且体内无 break / return / raise
    for n in ast.walk(fn):
        if isinstance(n, ast.While) and isinstance(n.test, ast.Constant) and n.test.value is True:
            has_exit = any(isinstance(x, (ast.Break, ast.Return, ast.Raise)) for x in ast.walk(n))
            if not has_exit:
                out.append(("block", n.lineno,
                            "while True 且无 break/return/raise —— 无退出条件的迭代（疑似死循环）"))
    for n in ast.walk(fn):
        if isinstance(n, ast.ExceptHandler):
            only_pass = all(isinstance(s, ast.Pass) for s in n.body)
            if not only_pass:
                continue
            if n.type is None:
                out.append(("block", n.lineno, "裸 except 且仅 pass —— 异常被吞（失败原因不可定位）"))
            else:
                out.append(("warn", n.lineno, "except 分支仅 pass —— 异常被吞，须写明为何可忽略"))
    opened = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = n.value
            if isinstance(v, ast.Call):
                f = v.func
                nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                if nm == "open":
                    opened[n.targets[0].id] = n.lineno
    for name, ln in sorted(opened.items(), key=lambda x: x[1]):
        handed = False
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and n.attr == "close" and isinstance(n.value, ast.Name) and n.value.id == name:
                handed = True
            if isinstance(n, ast.Call):
                for a in list(n.args) + [k.value for k in n.keywords]:
                    if isinstance(a, ast.Name) and a.id == name:
                        handed = True
            if isinstance(n, ast.With):
                for it in n.items:
                    c = it.context_expr
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "open":
                        handed = True
        if not handed:
            out.append(("warn", ln, "「%s」= open(...) 未见 close() 或 with，且未交给调用方 —— 句柄可能泄漏" % name))
    return out


def _is_inline_json(v):
    """G2 判据：值长度 > 60 且能被 json.loads 解析为对象/数组（真正的 JSON 数据形态）。"""
    if len(v) <= 60:
        return False
    try:
        o = json.loads(v)
    except Exception:
        return False
    return isinstance(o, (dict, list))

def _is_exempt(src, node, val):
    """G1 豁免：仅当【理由合法 + 内容指纹匹配】时成立（豁免针对内容，不是位置）。"""
    lines = src.splitlines()
    want = hashlib.sha256(val.encode("utf-8")).hexdigest()[:12]
    for ln in (node.lineno, node.lineno - 1):
        if not (1 <= ln <= len(lines)):
            continue
        m = re.search("# noqa: G1 reason=([a-z-]+) sha256=([0-9a-f]{12})", lines[ln - 1])
        if m and m.group(1) in _G1_REASONS and m.group(2) == want:
            return m.group(1)
    return ""


_G1_REASONS = ("diagnostic-message", "audit-kept-in-source")


def _literal_rules(src, path):
    """G1/G2/G3：内联复杂内容（生成阶段高风险写法）。first-match：一个字面量最多报一条。"""
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    ds = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = getattr(node, "body", [])
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant):
                ds.add(id(b[0].value))
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)) or id(n) in ds:
            continue
        seg = ast.get_source_segment(src, n) or ""
        val = n.value
        q = seg.count(chr(34)) + seg.count(chr(39))
        if len(seg) > 160:
            _ex = _is_exempt(src, n, val)
            if _ex:
                out.append(("EXEMPT", "G1 已审计豁免（%s） %d 字符（%s:%d）" % (_ex, len(seg), path.name, n.lineno)))
            else:
                out.append(("BLOCK", "G1 超长字符串片段 %d 字符（%s:%d）" % (len(seg), path.name, n.lineno)))
        elif _is_inline_json(val):
            out.append(("BLOCK", "G2 疑似内联 JSON（值 %d 字符，%s:%d）" % (len(val), path.name, n.lineno)))
        elif q > 10:
            out.append(("BLOCK", "G3 引号密集（源码 %d 个引号，%s:%d）" % (q, path.name, n.lineno)))
    return out

def check_file(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    # 父级感知遍历：只扫描【父节点是 Module 或 ClassDef】的函数
    #   —— 跳过嵌套函数（避免重复报告，外部抽检发现 6% 重复）
    #   —— 但【保留类方法】（早先只取 tree.body 会漏掉类里的方法，导致漏报）
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    out = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(parents.get(node), (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for hit in check_function(node):
            k = (hit[1], hit[2])
            if k in seen:
                continue
            seen.add(k)
            out.append(hit)
    return out


def main(argv):
    if len(argv) < 2:
        print("[用法] python correctness_rules.py <源码根>")
        return 3

    # F7：[_common 未导入 summary；也不该为此新增依赖] —— 本地记录 [待核]，
    #   原实现只按 blocked/warned 出退出码，**把 tbd 丢弃了 -> 该红的地方恒绿**。
    _tbds = []

    def _tbd(msg):
        _tbds.append(msg)
        tbd(msg)
    root = Path(argv[1]).resolve()
    if not root.exists():
        problem("路径不存在：%s" % root)
        return 3
    files = sorted(p for p in root.rglob("*.py") if p.is_file())
    # 非 Python 源码：**不许静默略过**（否则读者会把"没查"当成"已通过"）。
    # 与 code_metrics 的 PENDING 口径一致：未接线就是 [待核]，不猜。
    _other = sorted({p.suffix.lower() for p in root.rglob("*")
                     if p.is_file() and p.suffix.lower() in (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp",
                                                             ".go", ".java", ".js", ".jsx", ".ts", ".tsx",
                                                             ".rs", ".cs", ".rb", ".php",
                                                             # 数值/科学计算（已准入 L0–L2；未接线 -> [待核]）
                                                             ".f90", ".f95", ".f03", ".f08", ".for", ".r", ".jl",
                                                             # .m 同时是 MATLAB 与 Objective-C：**显式点名、不猜**
                                                             ".m")})
    if _other:
        _tbd("本目录含未接线语言 %s —— 本脚本只查 Python，其余语言尚无检查器（不猜）"
              % "、".join(x.lstrip(".") for x in _other))
    # Q6 证据门槛：数学/数值代码跑通什么都不能证明 —— 无证据只能报 [待核]。
    _MATH = ("numpy", "scipy", "cmath", "decimal", "fractions", "statistics")
    _tests = [q for q in root.rglob("*") if q.is_file()
              and (q.name.startswith("test_") or q.name.endswith("_test.py"))]
    _tref = "".join(q.read_text(encoding="utf-8", errors="replace") for q in _tests[:200])
    _gated = 0
    blocked = warned = 0
    for p in files:
        _src = p.read_text(encoding="utf-8", errors="replace")
        if not any(("import " + m) in _src or ("from " + m) in _src for m in _MATH):
            continue
        if p.stem not in _tref:
            _gated += 1
            _tbd("Q6 证据门槛：%s 疑似数学/数值代码，未见测试引用（无证据不得报通过）"
                  % p.relative_to(root))
    if _gated:
        _tbd("证据门槛命中 %d 个模块 —— 结论应为未验证，不是通过" % _gated)
    blocked = warned = 0
    _lit_classified = 0
    _lit_emitted = 0
    _lit_exempt = 0
    _lit_blocked = 0
    for p in files:
        for _lv, _g in _literal_rules(p.read_text(encoding="utf-8", errors="replace"), p):
            _lit_classified += 1
            if _lv == "EXEMPT":
                note("[结构模式·豁免] " + _g)
                _lit_exempt += 1
                _lit_emitted += 1
                continue
            problem("[结构模式·阻断] " + _g)
            _lit_blocked += 1
            blocked += 1
            _lit_emitted += 1
        for kind, ln, msg in check_file(p):
            loc = "%s:%d" % (p.relative_to(root), ln)
            if kind == "block":
                blocked += 1
                problem("[结构模式·阻断] %s %s" % (loc, msg))
            else:
                warned += 1
                note("[结构模式·观察] %s %s" % (loc, msg))
    print("---")
    if _lit_classified != _lit_emitted or (_lit_blocked + _lit_exempt) != _lit_classified:
        problem("[结果完整性] 分类 %d · 发射 %d · 阻断 %d · 豁免 %d —— 语义链断裂，不得视为通过" % (_lit_classified, _lit_emitted, _lit_blocked, _lit_exempt))
        blocked += 1
    print("文件 %d 个 · 阻断 %d · 观察 %d" % (len(files), blocked, warned))
    if blocked:
        return 1
    if warned:
        return 2
    # F7 修复：**[待核] 必须计入退出码**（原先 `return 2 if warned else 0` 把它丢弃 -> 该红的地方恒绿）。
    #   基线保持 0：无 blocked / 无 warned / 无 _tbd 时仍返回 0（否则 selftest 的基线用例会失效）。
    return 2 if _tbds else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
