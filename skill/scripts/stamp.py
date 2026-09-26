# -*- coding: utf-8 -*-
"""stamp.py —— 机器戳生成（人检标记与审计锚的取值来源）

用法：
    python stamp.py [--root <目录>] [--slot <角色槽>] [--json]   # 产机器戳 + 到期
    python stamp.py --ai-id [--slot <角色槽>]                 # 产 AI 标识（身份锚）
    python stamp.py --verify "<by=... 的值>"                   # 只校验戳的格式与强度档

为什么要有这个脚本（设计依据见 references/audit.md §2.1）：
    「谁负责」这类字段属自报值——可任意填写且无从核实，因此不构成审计锚。
    「哪台机器、几点」是**痕迹**——由工具/版本控制产生，写入者不生产它。
    本脚本只产**痕迹**，不产声明：它不问你叫什么，它报它自己在哪台机器上、现在几点。

戳的强度分档（这是本脚本最重要的输出，不只是格式）：
    强   git:<短hash>@<ISO8601>     由 git 记录；写入者改不了（改历史会留痕）
    中   host:<码>@<ISO8601>        脚本现算 + 文件系统 mtime 可交叉核对
    弱   host:<码>@<ISO8601>        纯脚本现算——能写文件的人也能写假戳

    ⚠ 诚实边界：**本层只出「机器 + 时间段」，不出「人」。**
      由「哪台机器 + 哪段时间」定位到具体是谁，是人工复核的事（查机器清单 /
      查该时段的会话记录 / 查 git author）。协议层不承诺定责，只承诺留下可追溯的痕迹。

依赖：Python 3 标准库。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import run, usage_exit  # noqa: E402  —— 只借「统一入口包装 + 控制台编码降级」两件设施
import lease as _lease  # noqa: E402  —— 共享文件写原语（CAS）；--append 是共享写，不许直接 write_text

STAMP_RE = re.compile(
    r"^(git|host):(?P<code>[0-9a-fA-F]{4,40})@(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z))$"
)
MARKER_RE = re.compile(r"#\u4eba\u68c0\s*\((?P<body>[^)]*)\)")

def platform_token() -> str:
    """平台记号：win / mac / linux（与 MAP 环境段 {PLATFORM} 同一词表）。"""
    s = platform.system().lower()
    return {"windows": "win", "darwin": "mac", "linux": "linux"}.get(s, s[:3] or "unk")

def ai_id(slot: str = "", length: int = 8) -> str:
    """AI 标识：<平台>-<机器码>[@<角色槽>]。

    为什么标识要由脚本产生而不是由 AI 自报（见 references/audit.md §2.1）：
      自报的名字可以任意填写，且填写者就是被审计者——声明与证据同源，不构成审计锚。
      机器码由程序自动识别，填写者不生产该值——声明与证据异源，才可作锚。
    @ 之后是可选的**角色槽**（注册制）：@ 之前是机器产、@ 之后是声明，两者在字形上可分辨。
    """
    base = "%s-%s" % (platform_token(), machine_code(length))
    return "%s@%s" % (base, slot) if slot else base

# ── 运行证据：运行时 / 会话 可自动识别；模型不可得（见 references/audit.md §2.2）──
#  与外层机器的区别：机器码回答「哪台机器」，运行证据回答「在哪个 Agent 运行时里、哪个会话」。
#  两者都是**环境产生**的值（填写者不生产），所以都能作锚；而模型名不是——宿主多半不提供。
RUNTIME_ENV = (
    ("DSH", ("DSH_HOME", "DSH_PROFILE")),
    ("claude-code", ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")),
    ("cursor", ("CURSOR_TRACE_ID",)),
    ("codex", ("CODEX_HOME",)),
    ("qwen-cli", ("QWEN_HOME", "QIANWEN_HOME")),
    ("gemini-cli", ("GEMINI_CLI",)),
    ("cline", ("CLINE_" + "VERSION",)),
    ("aider", ("AIDER_" + "MODEL",)),
    ("copilot", ("COPILOT_AGENT" + "_TASK_ID",)),
)
#: 宿主可能提供的会话标识（有则带上——它同样是环境产生，不是自报）
SESSION_ENV = ("DSH_SESSION_ID", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID", "CURSOR_TRACE_ID")
#: 宿主可能提供的模型名。**没有就留空——绝不去问模型自己**（自报不构成锚）。
MODEL_ENV = ("DSH_MODEL", "CLAUDE_MODEL", "ANTHROPIC_MODEL", "OPENAI_MODEL",
             "QWEN_MODEL", "GEMINI_MODEL", "CODEX_MODEL")


def runtime_identity() -> dict:
    """运行时身份：{runtime, session, model, source}。**全部来自环境，不问模型。**"""
    env = os.environ
    rt, src = "unknown", "未识别"
    for name, keys in RUNTIME_ENV:
        hit = next((k for k in keys if env.get(k)), None)
        if hit:
            rt, src = name, "环境变量 %s" % hit
            break
    if rt == "unknown":
        parent = _parent_process_name()
        if parent:
            rt, src = parent, "父进程名"
    sess = next((env[k] for k in SESSION_ENV if env.get(k)), "")
    model = next((env[k] for k in MODEL_ENV if env.get(k)), "")
    return {"runtime": rt, "source": src, "session": sess, "model": model}


def _parent_process_name() -> str:
    """父进程名（宿主的兜底线索）。Windows 用 wmic/PowerShell，其它平台读 /proc。"""
    try:
        if platform.system().lower() == "windows":
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                 "(Get-CimInstance Win32_Process -Filter \"ProcessId=$PID\").ParentProcessId"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
            ppid = out.stdout.decode("utf-8", "replace").strip()
            if not ppid.isdigit():
                return ""
            out2 = subprocess.run(["powershell", "-NoProfile", "-Command",
                                   "(Get-CimInstance Win32_Process -Filter \"ProcessId=%s\").Name" % ppid],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
            return out2.stdout.decode("utf-8", "replace").strip().replace(".exe", "")
        ppid = open("/proc/self/stat").read().split()[3]
        return open("/proc/%s/comm" % ppid).read().strip()
    except Exception:
        return ""


#: 宿主配置里可能的模型登记处（**按名字找，不按内容猜**）
#  为什么读宿主配置而不是问模型：模型自报是**自报值**——填写者就是被审计者，不构成锚（audit.md §2.2）。
#  宿主配置是**别人写的**，属于 runtime evidence；但它通常记的是「默认/已配置的模型」，
#  与**本会话实际在用的模型**可能不同（用户可在会话里切）——所以它是**弱证据**，必须标注来源。
HOST_MODEL_FILES = ("cordis.patch.yml", "cordis.yml", "settings.yaml.imported", "settings.yaml")


# ── 模型/底座的证据分级（五级降级；见 references/audit.md §2.2）──────────
#  为什么要分级：不同底座给的线索不一样，有的什么都不给。
#  **拿不到也必须记成「拿不到」**——否则将来分不清「当时没记」和「当时确实拿不到」。
MODEL_TAGS = {
    "env": "宿主环境变量", "host-cfg": "宿主配置登记值", "human": "人登记（MAP）",
    "self": "模型自报（**不作锚**）", "absent": "不可得",
}
#: 强度：env 弱偏中（机器值，但仍非本会话实证）；host-cfg / human / self 均为弱；absent 无。
MODEL_STRENGTH = {"env": "弱偏中", "host-cfg": "弱", "human": "弱", "self": "弱（不可作锚）",
                  "absent": "—"}


def declared_model(root) -> str:
    """人在 MAP 里登记的底座/模型（**声明，不是机器值**）。取不到返回空串。"""
    from _common import map_line_value
    return map_line_value(root, ("底座模型", "模型登记", "运行模型", "底座"))


def model_evidence(root, self_report: str = "") -> dict:
    """模型身份的五级降级：env > host-cfg > human > self > absent。

    返回 {value, tag, source, strength, note}；**tag 必须跟着值一起走**——
    值一旦离开标签，就变成了「看起来确凿」的假证据，而那正是本包最防的形态。
    """
    ri = runtime_identity()
    hm = host_model_hint()
    dc = declared_model(root)
    if ri["model"]:
        return {"value": ri["model"], "tag": "env", "source": "宿主环境变量",
                "strength": MODEL_STRENGTH["env"], "note": ""}
    if hm:
        return {"value": hm["model"], "tag": "host-cfg",
                "source": "宿主配置 %s" % hm["source"], "strength": MODEL_STRENGTH["host-cfg"],
                "provider": hm.get("provider", "?"),
                "note": "登记值，非本会话实证"}
    if dc:
        return {"value": dc, "tag": "human", "source": "MAP 登记（人写）",
                "strength": MODEL_STRENGTH["human"],
                "note": "人登记的声明；换模型后必须改这一行，否则是过期声明"}
    if self_report:
        return {"value": self_report, "tag": "self", "source": "模型自报",
                "strength": MODEL_STRENGTH["self"], "note": "自报值不作锚：可伪造、且常记错版本"}
    return {"value": "", "tag": "absent", "source": "宿主未提供",
            "strength": MODEL_STRENGTH["absent"], "note": "留空而不猜（audit.md §2.2）"}


def host_model_hint() -> dict:
    """从宿主配置读「登记的模型」。只读、不写；**只取 model/provider 两行，绝不碰 key/token**。"""
    bases = []
    for var in ("DSH_PROFILE_DIR", "DSH_HOME"):
        v = os.environ.get(var)
        if v:
            bases.append(Path(v))
    for base in bases:
        for name in HOST_MODEL_FILES:
            p = base / name
            try:
                if not p.is_file():
                    continue
                txt = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            # 只截 agent-default-model 段落，避免把别的 provider 的 model 认成当前模型
            m = re.search(r"agent-default-model:(.{0,600}?)(?:\n\s*-\s*id:|\Z)", txt, re.S)
            seg = m.group(1) if m else txt[:1500]
            mod = re.search(r"^\s*model:\s*([\w.\-]+)", seg, re.M)
            if not mod:
                continue
            prov = re.search(r"^\s*provider:\s*([\w.\-]+)", seg, re.M)
            return {"model": mod.group(1), "provider": prov.group(1) if prov else "?",
                    "source": str(p)}
    return {}


def machine_code(length: int = 8) -> str:
    """机器码：主机名 + 机器唯一标识 的哈希前缀。

    刻意**不**取人名、不取用户名——本脚本要回答的是"哪台机器"，不是"谁"。
    """
    parts = [socket.gethostname(), platform.machine(), platform.system()]
    guid = _windows_machine_guid()
    if guid:
        parts.append(guid)
    else:
        # 非 Windows 或注册表读不到：退化为 MAC（uuid.getnode）
        import uuid
        parts.append("%012x" % uuid.getnode())
    raw = "|".join(parts).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:length]

def _windows_machine_guid() -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import winreg  # type: ignore
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Cryptography", 0,
                             winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0))
        val, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(val)
    except Exception:
        return ""

def _run_git(root: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=str(root), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
        if p.returncode != 0:
            return ""
        return p.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return ""

def local_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()

def make_stamp(root: Path) -> dict:
    """产一个戳。有 git 就用 git 戳（强），否则用机器戳（弱）。"""
    head = _run_git(root, "rev-parse", "--short=8", "HEAD")
    if head:
        ts = _run_git(root, "log", "-1", "--format=%cI")
        if not ts:
            ts = local_now_iso()
        return {
            "by": "git:%s@%s" % (head, ts),
            "strength": "strong",
            "why": "git 记录，写入者不生产该值（改历史会留痕）",
        }
    return {
        "by": "host:%s@%s" % (machine_code(), local_now_iso()),
        "strength": "weak",
        "why": "脚本现算；能写文件者亦可伪造同形戳——仅作线索，不作证据。"
               "启用版本控制可升为强锚（见 references/audit.md §3.4）",
    }

def verify(value: str) -> dict:
    m = STAMP_RE.match(value.strip())
    if not m:
        return {"ok": False, "why": "格式不合法，期望 <git|host>:<码>@<ISO8601>"}
    kind = value.split(":", 1)[0]
    return {"ok": True, "kind": kind, "code": m.group("code"),
            "time": m.group("ts"), "strength": "strong" if kind == "git" else "weak"}

def config_machine_len() -> int:
    """机器码位数：读 config/defaults.yml 的 audit.human_check.machine_code_len，缺失回落 8。"""
    try:
        import re as _re
        cfg = Path(__file__).resolve().parent.parent / "config" / "defaults.yml"
        m = _re.search(r"machine_code_len:\s*(\d+)", cfg.read_text(encoding="utf-8"))
        return int(m.group(1)) if m else 8
    except Exception:
        return 8

def expiry(stamp_time: str, period_days: int) -> dict:
    """到期时刻 = 上次戳的时间 + 周期。**不读任何声明字段**，故无从伪造。"""
    t = stamp_time.strip()
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        dt = datetime.fromisoformat(t)
    except Exception:
        return {"ok": False, "why": "时间不可解析：%s" % stamp_time}
    due = dt + timedelta(days=period_days)
    now = datetime.now(due.tzinfo) if due.tzinfo else datetime.now()
    return {"ok": True, "due": due.replace(microsecond=0).isoformat(),
            "overdue": now > due, "age_days": round((now - dt).total_seconds() / 86400, 1)}

def main() -> int:
    ap = argparse.ArgumentParser(description="机器戳生成 / 校验（人检标记取值来源）")
    usage_exit(ap)
    ap.add_argument("--root", default=".", help="工作区或仓库根（用于判定有无 git）")
    ap.add_argument("--slot", default="", help="角色槽位（注册制，非人名）；仅用于拼标记行")
    ap.add_argument("--period-days", type=int, default=90, help="人检周期（算到期用）")
    ap.add_argument("--verify", default="", help="校验一个戳值后退出")
    ap.add_argument("--ai-id", action="store_true", help="只输出 AI 标识（<平台>-<机器码>[@角色槽]）后退出")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--evidence", action="store_true",
                    help="输出运行证据（运行时 / 会话 / 模型登记值 / 机器码）后退出")
    ap.add_argument("--append", action="store_true",
                    help="配合 --evidence：把运行证据追加进元数据通道 REVIEWS.md")
    ap.add_argument("--model-self", default="",
                    help="宿主完全不提供模型信息时，显式记一条**模型自报**（会标 self 标签，不作锚）")
    args = ap.parse_args()

    if args.ai_id:
        print(ai_id(args.slot, config_machine_len()))
        return 0

    if args.evidence:
        ri = runtime_identity()
        st = make_stamp(Path(args.root).resolve())
        hm = host_model_hint()
        print("== 运行证据（由环境与宿主配置产生，**不采信模型自报**） ==")
        print("运行时  : %s（来源：%s）" % (ri["runtime"], ri["source"]))
        print("会话    : %s" % (ri["session"] or "宿主未提供"))
        # 模型身份：**五级降级**，值必须带来源标签一起走（audit.md §2.2）
        me = model_evidence(Path(args.root).resolve(), args.model_self or "")
        prov = hm.get("provider", "?") if hm else "-"
        print("底座    : provider=%s（宿主配置；未提供则 -）" % prov)
        if me["tag"] == "absent":
            print("模型    : **[不可得]** —— 五级来源（env / 宿主配置 / MAP 登记 / 自报）都没有。")
            print("          记「不可得」而不是留空：将来才能分清「当时没记」和「当时确实拿不到」。")
            print("          可选补法：① 让宿主把模型名写进环境变量（最强）；"
                  "② 在 MAP 规则段登记一行「底座模型：<名字>」（人登记，弱）。")
        else:
            print("模型    : %s [%s]" % (me["value"], me["tag"]))
            print("          来源：%s · 强度：%s%s" % (me["source"], me["strength"],
                  (" · " + me["note"]) if me["note"] else ""))
            if me["tag"] in ("host-cfg", "human"):
                print("          提醒：这是**登记值**，与会话实际在用的模型可能不同；换模型后要更新登记。")
        print("机器戳  : %s（强度 %s）" % (st["by"], st["strength"]))
        print("AI 标识 : %s" % ai_id(args.slot, config_machine_len()))
        print("落点建议: 写进元数据通道 REVIEWS.md（追加一行）；**不要写进人检标记**——标记只放机器戳")
        if args.append:
            p = Path(args.root).resolve() / "REVIEWS.md"
            if not p.exists():
                print("[问题] REVIEWS.md 不存在，无法留痕：%s" % p)
                return 1
            line = "- %s · 运行证据 · runtime=%s · provider=%s · model=%s[%s] · session=%s · machine=%s" % (
                local_now_iso(), ri["runtime"], prov, me["value"] or "不可得", me["tag"],
                ri["session"] or "-", st["by"])
            # 共享文件的写必须走原语（CAS）：原来是直接 write_text，连原子写都不是
            _okk, _why = _lease.shared_append(Path(args.root).resolve(), p, line, "运行证据留痕")
            if not _okk:
                print("[问题] 留痕被拒：%s" % _why)
                return 1
            print("[通过] 已追加运行证据到 REVIEWS.md：%s" % line[:110])
        return 0

    if args.verify:
        r = verify(args.verify)
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else
              ("[通过] 戳合法 · 强度=%s" % r["strength"] if r["ok"] else "[问题] " + r["why"]))
        return 0 if r["ok"] else 1

    root = Path(args.root).resolve()
    s = make_stamp(root)
    e = expiry(s["by"].split("@", 1)[1], args.period_days)
    marker = "#\u4eba\u68c0(slot=%s, by=%s)" % (args.slot or "<角色槽>", s["by"])

    if args.json:
        print(json.dumps({"stamp": s, "expiry": e, "marker": marker},
                         ensure_ascii=False, indent=2))
        return 0
    print("戳      : %s" % s["by"])
    print("强度    : %s  （%s）" % (s["strength"], s["why"]))
    if e.get("ok"):
        print("到期    : %s  （已过 %s 天；%s）"
              % (e["due"], e["age_days"], "已超期" if e["overdue"] else "未超期"))
    print("标记行  : %s" % marker)
    if s["strength"] == "weak":
        print("[建议] 本目录无 git：当前为弱锚，只能作线索。"
              "启用版本控制后本项可升至强锚。")
    return 0

if __name__ == "__main__":
    sys.exit(run(main))
