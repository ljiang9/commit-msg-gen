"""commit-msg-gen 命令行入口。

用法示例：
    python3 cli.py                      # 使用内置示例 diff
    python3 cli.py --file my.patch      # 从 diff 文件读取
    git diff | python3 cli.py --stdin   # 从管道读取
    python3 cli.py --example --llm      # 内置示例并启用 LLM 润色
"""

from __future__ import annotations

import argparse
import sys

from commit_msg_gen import EXAMPLE_DIFF, build_commit_message


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="commit-msg-gen",
        description="把 unified diff 解析为 Conventional Commits 风格信息（可选 LLM）",
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--file", help="从 diff 文件读取")
    src.add_argument("--stdin", action="store_true", help="从标准输入读取 diff")
    src.add_argument("--example", action="store_true", help="使用内置示例 diff")
    p.add_argument("--llm", action="store_true", help="启用 LLM 润色（需 OPENAI_API_KEY）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            diff = f.read()
    elif args.stdin:
        diff = sys.stdin.read()
    else:
        diff = EXAMPLE_DIFF  # 默认内置示例

    msg = build_commit_message(diff, use_llm=args.llm)
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
