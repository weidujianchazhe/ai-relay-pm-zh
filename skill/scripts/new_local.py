# -*- coding: utf-8 -*-
"""new_local.py —— 项目自定义脚本脚手架

用法：
    python new_local.py <管理区> <脚本名> --purpose "<一句话用途>"
    python new_local.py <管理区> <脚本名> --purpose "..." --force

何时跑：需要一条本项目专属的检查、而技能包里没有对应脚本时。
依据：scripts/local/README.md（自定义脚本契约）
回本口径：省掉"每个项目重写一遍三态输出 / 退出码 / 参数解析 / 统计汇总"的样板；
         通用检查已随包提供，本脚手架只服务**项目专属**判据。写一次，之后每张卡都受益。

为什么不是"给规格让 AI 临时造"：
    给**规格**的结果是每个项目手写一遍样板、且写出的脚本弱于规格。
    本脚手架的口径：通用检查随包给**实现**；项目专属检查给**骨架**——样板由机器生成，人只写判据。

不做的事（诚实边界）：不生成判据本身；不猜测项目结构；不写盘到 scripts/ 之外。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, run, usage_exit  # noqa: E402

TEMPLATE = (Path(__file__).resolve().parent / "templates" / "new_local_module_template.txt").read_text(encoding="utf-8")

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成项目自定义脚本骨架（放到 scripts/local/）")
    usage_exit(ap)
    ap.add_argument("root", help="管理区（脚本将写入 <root>/scripts/local/）")
    ap.add_argument("name", help="脚本名（小写字母/数字/下划线，不含 .py）")
    ap.add_argument("--purpose", default="<一句话用途>", help="一句话用途，写入 docstring")
    ap.add_argument("--when", default="<何时跑>", help="何时跑，写入 docstring")
    ap.add_argument("--force", action="store_true", help="目标已存在时覆盖")
    args = ap.parse_args()

    if not NAME_RE.match(args.name):
        print("[问题] 脚本名不合法（只允许小写字母/数字/下划线，起首为字母）：%s" % args.name)
        return 3
    root = Path(args.root)
    local = root / "scripts" / "local"
    if not (root / "scripts").is_dir():
        print("[问题] %s 下没有 scripts/ —— 请先按 references/onboarding.md §3 建工作区" % root)
        return 3
    if not local.is_dir():
        local.mkdir(parents=True)
        print("[建议] 已创建 %s（自定义脚本目录本应由初始化创建）" % local)
    dest = local / (args.name + ".py")
    if dest.exists() and not args.force:
        print("[问题] 已存在：%s —— 需覆盖请加 --force" % dest)
        return 1

    dest.write_text(
        TEMPLATE.format(name=args.name, purpose=args.purpose, when=args.when),
        encoding="utf-8")
    # 原子性：单文件小写入，直接落盘即可；解析校验放在写后
    ok("已生成 %s" % dest)
    note("三件事写完再收尾：① 补判据 ② 补回本口径 ③ 补踩坑记录")
    note("在 MAP 路径注册表登记该脚本，接手者才找得到它")
    return 0


if __name__ == "__main__":
    sys.exit(run(main))
