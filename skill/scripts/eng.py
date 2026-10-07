# -*- coding: utf-8 -*-
"""eng.py —— 能力接口层（Capability Layer / 能力路由器）

用法：python eng.py <源码根> <INSPECT|BUILD|TEST|AUDIT|VERIFY> [--ws=<管理区>] [--lang=python,cpp]

分层（见 references/language-adapters.md §2）：
  eng.py          = 能力路由器（只说动词，不写语言分支）
  ADAPTERS        = 唯一的语言相关落点（Adapter Registry）
  audit_all.py    = 审计编排（成员清单 / 聚合退出码 / 机器戳留痕）
  code_metrics.py = 度量实现（含外部取数探针钩子）

三条硬约束：
  ① 核心流程不出现 if python / elif cpp——新增语言 = 注册一个 adapter；
  ② AUDIT 不判语言：它调编排器，语言判断由各门禁的 COLLECTORS 承担；
  ③ 绝不"空转即通过"：拿不到结果就是 [待核] 或 [问题]，不许 note 一句就算过。
退出码：0 通过 · 1 问题 · 2 仅待核 · 3 用法/脚本错误
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, summary, tbd  # noqa: E402

BIN = Path(__file__).resolve().parent
VERBS = ("INSPECT", "BUILD", "TEST", "AUDIT", "VERIFY")

_WS = None


def run_script(script, args):
    """调包内脚本并逐段透传输出（不吞输出）。返回其退出码。"""
    cmd = [sys.executable, "-B", str(BIN / script)] + args
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
    out = (r.stdout or b"").decode("utf-8", "replace")
    for line in out.splitlines():
        print(line)
    return r.returncode


ADAPTERS = {}


def adapter(lang):
    def deco(fn):
        ADAPTERS[lang] = fn
        return fn
    return deco


def has_tool(name):
    return shutil.which(name) is not None


@adapter("python")
def py_adapter(verb, root, lang):
    if verb == "INSPECT":
        return ["python", str(BIN / "code_metrics.py"), str(root),
                "--ws=" + str(_WS or root), "--lang=" + lang], "code_metrics.py（真跑，不再空转）"
    if verb == "BUILD":
        return ["python", "-m", "compileall", "-q", str(root)], "python -m compileall"
    if verb == "TEST":
        return ["python", "-m", "pytest", "-q"], "pytest"
    return None, ""


@adapter("c")
@adapter("cpp")
def c_cpp_adapter(verb, root, lang):
    if verb == "INSPECT":
        return ["python", str(BIN / "code_metrics.py"), str(root),
                "--ws=" + str(_WS or root), "--lang=" + lang], "code_metrics.py（走外部探针；未声明 -> 待核）"
    if verb == "BUILD":
        return ["cmake", "--build", "build"], "cmake --build build"
    if verb == "TEST":
        return ["ctest", "--test-dir", "build", "--output-on-failure"], "ctest --test-dir build"
    return None, ""


def langs_of(ws, arg):
    if arg:
        return [x.strip() for x in arg.split(",") if x.strip()]
    try:
        import code_metrics as cm
        decl = cm._map_line(ws, "语言") or ""
        out = [x.strip().strip(chr(96) + "[]") for x in decl.replace("，", ",").split(",") if x.strip()]
        if out:
            return out
    except Exception:
        pass
    return ["python"]


def one(verb, lang, root):
    fn = ADAPTERS.get(lang)
    if fn is None:
        tbd("%s：语言 %s 未注册适配器（已注册：%s）——见 references/language-adapters.md §4"
            % (verb, lang, "、".join(sorted(ADAPTERS))))
        return False
    cmd, desc = fn(verb, root, lang)
    if cmd is None:
        tbd("%s / %s：该能力未实现（适配器未提供命令）" % (verb, lang))
        return False
    if cmd[0] == "python":
        cmd = [sys.executable, "-B"] + cmd[1:]
    elif not has_tool(cmd[0]):
        tbd("%s / %s：工具 %s 不存在（命令 %s）——装上该工具即可，本步不伪装成功"
            % (verb, lang, cmd[0], desc))
        return False
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
    out = (r.stdout or b"").decode("utf-8", "replace")
    for line in out.splitlines():
        print(line)
    if r.returncode == 0:
        ok("%s / %s：通过（%s）" % (verb, lang, desc))
        return True
    problem("%s / %s：失败 rc=%d（%s）" % (verb, lang, r.returncode, desc))
    return False


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("用法：python eng.py <源码根> <%s> [--ws=<管理区>] [--lang=python,cpp]" % "|".join(VERBS))
        return 3
    root = Path(args[0]).resolve()
    verb = args[1].upper()
    global _WS
    ws = root
    lang_arg = ""
    for a in sys.argv[1:]:
        if a.startswith("--ws="):
            ws = Path(a.split("=", 1)[1]).resolve()
        elif a.startswith("--lang="):
            lang_arg = a.split("=", 1)[1]
    _WS = ws
    if verb not in VERBS:
        problem("未知动词：%s（可用：%s）" % (verb, " / ".join(VERBS)))
        return summary()
    langs = langs_of(ws, lang_arg)
    print("== eng.py %s · 语言 %s · 根 %s ==" % (verb, "、".join(sorted(langs)), root))
    if verb == "AUDIT":
        print("-- AUDIT = 审计编排（audit_all.py：成员清单 / 聚合退出码 / 机器戳留痕）；本层不判语言 --")
        rc = run_script("audit_all.py", [str(ws), "--code", str(root)])
        if rc == 0:
            ok("AUDIT：编排器聚合退出码 0（全通过）")
        else:
            note("AUDIT：编排器聚合退出码 %d（1 有问题 · 2 仅待核 · 3 脚本错误）——已原样透传" % rc)
        return rc if rc in (0, 1, 2, 3) else 3
    if verb == "VERIFY":
        print("-- VERIFY = BUILD + TEST + AUDIT（三者皆过才算）--")
        done = all(one("BUILD", l, root) for l in sorted(langs))
        done = all(one("TEST", l, root) for l in sorted(langs)) and done
        arc = run_script("audit_all.py", [str(ws), "--code", str(root)])
        if arc != 0:
            note("VERIFY：AUDIT 聚合退出码 %d —— 不计通过" % arc)
            done = False
        if done:
            ok("VERIFY：构建 + 测试 + 审计都过")
        return summary()
    for l in sorted(langs):
        one(verb, l, root)
    return summary()


if __name__ == "__main__":
    from _common import run  # noqa: E402
    sys.exit(run(main))