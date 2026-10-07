# -*- coding: utf-8 -*-
"""provider_gate.py —— 通用 Provider 门禁：把成熟工具的判定接成本包的三态门禁

设计红线（与 references/language-adapters.md 第 12 节一致）：
  1) 本包【不实现】任何解析器 / 分析器 —— 只调用成熟工具；
  2) 工具未安装 -> [待核] 工具未安装（不猜、不静默通过）；
  3) 工具输出必须经【薄映射】转成本包统一格式，Core 不认识任何工具原生格式。

用法：
  python provider_gate.py <源码根> [--only=c,javascript] [--list]
  python provider_gate.py --selftest          用合成数据验证映射与判定（不需要真装工具）

退出码：0 全通过 · 1 有[问题] · 2 仅[待核] · 3 脚本 / 用法错误
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, problem, tbd  # noqa: E402

PKG = Path(__file__).resolve().parent.parent
REG = Path(os.environ.get("CP_PROVIDER_REGISTRY", str(PKG / "config" / "providers.json")))


def load_registry():
    return json.loads(REG.read_text(encoding="utf-8"))["providers"]


def tool_available(probe):
    return shutil.which(probe[0]) is not None


def ingest(lines):
    """统一格式：每行一个 JSON —— file / line / rule / severity / message。

    severity 映射：error -> 阻断 · warning -> 观察 · info/note -> 提示。
    """
    blocked, warned, noted, bad = 0, 0, 0, []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except Exception:
            bad.append(raw[:80])
            continue
        if not isinstance(rec, dict):
            bad.append(raw[:80])
            continue
        sev = str(rec.get("severity", "warning")).lower()
        loc = "%s:%s" % (rec.get("file", "?"), rec.get("line", "?"))
        msg = "%s [%s] %s" % (loc, rec.get("rule", "-"), rec.get("message", ""))
        if sev == "error":
            blocked += 1
            problem("[Provider·阻断] " + msg)
        elif sev == "warning":
            warned += 1
            note("[Provider·观察] " + msg)
        else:
            noted += 1
            note("[Provider·信息] " + msg)
    return blocked, warned, noted, bad


SYNTHETIC = [
    json.dumps({"file": "src/a.c", "line": 12, "rule": "CERT ARR30-C", "severity": "error", "message": "数组越界"}),
    json.dumps({"file": "src/b.js", "line": 3, "rule": "security/detect-eval", "severity": "error", "message": "eval 使用"}),
    json.dumps({"file": "src/c.yaml", "line": 7, "rule": "yamllint.truthy", "severity": "warning", "message": "truthy 值"}),
    json.dumps({"file": "src/d.R", "line": 21, "rule": "lintr.object_usage", "severity": "warning", "message": "未使用对象"}),
    json.dumps({"file": "src/e.go", "line": 9, "rule": "govet.lostcancel", "severity": "error", "message": "context 取消函数丢失"}),
    json.dumps({"file": "src/f.rs", "line": 4, "rule": "clippy::unwrap_used", "severity": "warning", "message": "unwrap 使用"}),
    json.dumps({"file": "src/g.ts", "line": 8, "rule": "no-floating-promises", "severity": "error", "message": "未等待的 Promise"}),
    json.dumps({"file": "src/h.java", "line": 15, "rule": "OBL_UNSATISFIED_OBLIGATION", "severity": "warning", "message": "资源未关闭"}),
]


def main(argv):
    ap = argparse.ArgumentParser(description="通用 Provider 门禁（调用成熟工具，不自己实现分析器）")
    ap.add_argument("root", nargs="?")
    ap.add_argument("--only", default="", help="只看指定 provider（逗号分隔 key）")
    ap.add_argument("--list", action="store_true", help="只列出档案与就绪状态")
    ap.add_argument("--selftest", action="store_true", help="用合成数据验证映射与判定")
    a = ap.parse_args(argv[1:])
    provs = load_registry()
    if a.only:
        want = set(x.strip() for x in a.only.split(",") if x.strip())
        provs = [p for p in provs if p["key"] in want]
    if a.list:
        for p in provs:
            ok = tool_available(p["probe"]) if p.get("probe") else False
            print("%-14s %-9s %-22s %s" % (p["key"], p["kind"], p.get("tool", "?"),
                                           "工具就绪" if ok else "工具未安装 -> 待核"))
        return 0
    if a.selftest:
        print("== Provider 门禁自检：用合成数据验证映射与判定（不需要真装工具）==")
        blocked, warned, noted, bad = ingest(SYNTHETIC)
        print("---")
        print("合成记录 %d 条 -> 阻断 %d · 观察 %d · 提示 %d · 解析失败 %d" %
              (len(SYNTHETIC), blocked, warned, noted, len(bad)))
        # 合成数据：error 4 条 · warning 4 条（早先写成 3/3 是本人误数，自检把它抓出来了）
        ok = (blocked == 4 and warned == 4 and not bad)
        print("[%s] 自检：error->阻断 / warning->观察 的映射%s" %
              ("通过" if ok else "失败", "正确" if ok else "不正确"))
        # 三条异常路径的端到端负向测试（2026-10-02 补）
        # 必须走【子进程 + 真注册表】：本轮 P0（计数器遮蔽 tbd 函数）正是只测映射才溜过去的。
        import tempfile as _tf
        _cases = [
            ("未声明探针", {"providers": [{"key": "x1", "kind": "language", "title": "noprobe", "tool": "x1", "probe": None, "run": []}]}, 2),
            ("工具未安装", {"providers": [{"key": "x2", "kind": "language", "title": "notool", "tool": "x2", "probe": ["definitely-not-a-real-tool-zzz"], "run": []}]}, 2),
            ("工具启动失败", {"providers": [{"key": "x3", "kind": "language", "title": "badpath", "tool": "x3", "probe": ["python"], "run": ["definitely-not-a-real-program-zzz"]}]}, 2),
            ("异常退出但有部分输出（未声明）", {"providers": [{"key": "x4", "kind": "language", "title": "partial", "tool": "x4", "probe": ["python"], "run": ["python", "-c", "import json,sys;print(json.dumps(dict(file=chr(97),line=1,rule=chr(114),severity=chr(101)+chr(114)+chr(114)+chr(111)+chr(114),message=chr(109))));sys.exit(1)"]}]}, 2),
            ("已声明 exit_findings 的非零退出（进入判定并阻断）", {"providers": [{"key": "x5", "kind": "language", "title": "declared", "tool": "x5", "probe": ["python"], "exit_findings": [1], "run": ["python", "-c", "import json,sys;print(json.dumps(dict(file=chr(97),line=1,rule=chr(114),severity=chr(101)+chr(114)+chr(114)+chr(111)+chr(114),message=chr(109))));sys.exit(1)"]}]}, 1),
            ("正常退出但输出损坏", {"providers": [{"key": "x6", "kind": "language", "title": "broken", "tool": "x6", "probe": ["python"], "run": ["python", "-c", "print(chr(122))"]}]}, 2),
        ]
        _neg_ok = True
        for _case in _cases:
            _title, _reg = _case[0], _case[1]
            _want = _case[2] if len(_case) > 2 else 2
            _d = _tf.mkdtemp(prefix="pgneg_")
            _rp = Path(_d) / "reg.json"
            _rp.write_text(json.dumps(_reg, ensure_ascii=False), encoding="utf-8")
            _env = dict(os.environ)
            _env["CP_PROVIDER_REGISTRY"] = str(_rp)
            _env["PYTHONIOENCODING"] = "utf-8"
            _r = subprocess.run([sys.executable, str(Path(__file__).resolve()), _d],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=_env)
            _txt = (_r.stdout or "") + (_r.stderr or "")
            _good = (_r.returncode == _want) and ("Traceback" not in _txt)
            if not _good:
                _neg_ok = False
            print("      [%s] 负向·%s exit=%d" % ("通过" if _good else "失败", _title, _r.returncode))
        print("[%s] 自检：六条异常语义路径均不崩且分类正确" % ("通过" if _neg_ok else "失败"))
        return 0 if (ok and _neg_ok) else 1
    if not a.root:
        print("[用法] python provider_gate.py <源码根> [--only=...] [--list] [--selftest]")
        return 3
    root = Path(a.root).resolve()
    if not root.is_dir():
        print("[用法] 路径不是目录：%s" % root)
        return 3
    blocked = warned = tbd_count = 0
    for p in provs:
        if not p.get("probe"):
            tbd_count += 1
            tbd(" %s：未声明探针（档案不完整）" % p["key"])
            continue
        if not tool_available(p["probe"]):
            tbd_count += 1
            tbd(" %s：工具未安装（%s）—— 不猜、不静默通过" % (p["key"], p["probe"][0]))
            continue
        cmd = [x.replace("{root}", str(root)) for x in p["run"]]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600)
        except Exception as e:
            tbd_count += 1
            tbd(" %s：工具执行失败（%s）" % (p["key"], e))
            continue
        _rc = r.returncode
        _ok = set(p.get("exit_ok", [0]))
        _find = set(p.get("exit_findings", []))
        #  A+ 退出码语义（2026-10-02）：工具退出码 != 门禁退出码。
        #  只有声明过的码才算【扫描完整】，才可进入 finding 解释；未声明的非零一律待核。
        if _rc not in _ok and _rc not in _find:
            tbd_count += 1
            tbd("%s：工具退出码 %d 未在 Provider 声明中（exit_ok=%s exit_findings=%s）—— 无法证明扫描完整，不得判定通过" % (p["key"], _rc, sorted(_ok), sorted(_find)))
            continue
        print("== %s（%s）==" % (p["title"], p.get("tool", "?")))
        b, w, _n, bad = ingest((r.stdout or "").splitlines())
        blocked += b
        warned += w
        if bad:
            tbd_count += 1
            tbd(" %s：有 %d 行不是统一 JSON —— 需要项目侧薄适配器（见 references/provider-gates.md）" % (p["key"], len(bad)))
    print("-" * 46)
    print("阻断 %d · 观察 %d · 待核 %d" % (blocked, warned, tbd_count))
    if blocked:
        return 1
    return 2 if tbd_count or warned else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
