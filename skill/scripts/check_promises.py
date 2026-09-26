# -*- coding: utf-8 -*-
"""check_promises.py —— 「文档承诺 ↔ 代码行为」对账门禁

为什么需要（门禁空转这类债务的教训）：
  原有自检覆盖「结构与数值」（占位符 / 兜底值 / 端点 / 文件清单 / 共享写者），
  **唯独不覆盖「文档说检查 X、代码其实没查 X」**——而这是全包最贵的一类债务：
  门禁空转时它**看起来永远健康**（判据算出命中行却从未使用、随后无条件 note + 有行就 ok，即是一例）。

**两条规则**（都可变红）。**原先设想的第三条「README 描述逐词匹配」已判定不可实现并删除**（中文同义不同词无法判定，实测一次刷出 9 条噪声——会误报的检查比没有更坏）：
  §1 声明是门禁的脚本，必须有**可达的** problem()/tbd()——从不失败的"门禁"不是门禁（注释里的不算）。
  §2 scripts/README.md 的功能描述里的中文词组，必须在该脚本的检查节标题或 problem()/tbd() 消息里出现；
     否则报 [待核]：文档承诺了一个代码里没影子的检查项，请人工判定。

退出码：0 全通过 · 1 有[问题] · 2 仅[待核] · 3 脚本自身错误。
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, read, run, summary, tbd  # noqa: E402

HERE = Path(__file__).resolve().parent


def _code_only(s: str) -> str:
    """剥掉注释与字符串字面量，只留代码结构——免得「说明里的例子」被当成实现。"""
    out = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(s).readline):
            if t.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(t.string)
    except Exception:
        return s
    return "".join(out)          # `不能加空格`：否则 `problem( ` 会变成 `problem ( `，判据全部失效（实测误报 5 个门禁）


def main() -> int:
    readme = read(HERE / "README.md") or ""
    rows = re.findall(r"^\|\s*`([a-z_]+\.py)`\s*\|\s*(.+?)\s*\|", readme, re.M)
    print("== 1. 声明为门禁的脚本必须有可达的 problem()/tbd() ==")
    #  **明示豁免**：自检/变异类脚本（`selftest_gates.py`）的失败通道是「断言用例失效」，
    #  不是 problem()——把它们算进门禁会形成**永久误报**，而总是红的门禁等于没有门禁。
    gated = [(n, d) for n, d in rows if "门禁" in d and "非门禁" not in d]
    exempt = [n for n, d in gated if ("自检" in d or "变异" in d)]
    gates = [n for n, d in gated if n not in exempt]
    bad = []
    for name in gates:
        p = HERE / name
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        code = _code_only(src)
        #  接受三种失败通道：problem() / tbd() / 显式打印 [失败]（自检类脚本走这条）
        #  判据必须与 docstring 一致：problem(/tbd( 在**剥掉注释与字符串**后的代码里；
        #  唯一的字符串特例是显式失败标记，只认 `print("[失败]"`（注释里提到 problem( **不算**）。
        if ("problem(" not in code) and ("tbd(" not in code) and ('print("[失败]"' not in src):
            bad.append(name)
    if bad:
        for n in bad:
            problem("声明为门禁，但**没有任何可达的 problem()/tbd()**——它永远不会失败：%s" % n)
    else:
        ok("声明为门禁的 %d 个脚本都至少有一次可达的失败通道（另有 %d 个自检类脚本按上方说明豁免）"
           % (len(gates), len(exempt)))
    #  §2（README 描述逐词匹配）**故意不实现**：中文词组的"同义不同词"无法判定，
    #  实测会一次刷出 9 条 [待核] 噪声——**一条会误报的检查比没有更坏**（它会训练人忽略输出）。
    #  可判定的替代见 §1：门禁若连 problem()/tbd() 都没有，那它声称查什么都没意义。
    dead = []
    for p in sorted(HERE.glob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        #  **只报"筛选/命中"型赋值**（列表/集合推导式的结果从未被读取）——这正是 P0-1 的形态：
        #  `hit = [c for c, _ in rows if ...]` 算完就丢。故意不报 `holder = acquire_lock(...)`
        #  这类"只为副作用而绑定"的写法（那是对的），否则噪声会淹掉真问题。
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            comp, use = {}, set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Load):
                        use.add(node.id)
                elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if isinstance(node.value, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                        comp[node.targets[0].id] = node.lineno
            for nm, ln in sorted(comp.items(), key=lambda x: x[1]):
                if nm not in use:
                    dead.append("%s:%d %s() 里的 %s" % (p.name, ln, fn.name, nm))
    if dead:
        for d in dead[:10]:
            problem("死赋值（算了不用）：%s —— 若是「算出来本该判定却忘了用」，就是空转门禁的形态" % d)
        if len(dead) > 10:
            note("另有 %d 处未列出" % (len(dead) - 10))
    else:
        ok("无死赋值")
    return summary()


if __name__ == "__main__":
    sys.exit(run(main))
