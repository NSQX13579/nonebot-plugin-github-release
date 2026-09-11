"""离线预览：拉取真实 release，按插件逻辑渲染成纯文本推送内容。

用法（在仓库根目录执行）::

    python tools/preview.py                       # 默认仓库的最新一条
    python tools/preview.py --repo owner/repo
    python tools/preview.py --repo owner/repo --tag v1.2.3
    python tools/preview.py --repo owner/repo --list 5
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "nonebot_plugin_github_release"


def _load_without_nonebot() -> None:
    """用影子包导入内部模块，避免触发插件的 NoneBot 注册流程。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if "gh_core" not in sys.modules:
        shadow = types.ModuleType("gh_core")
        shadow.__path__ = [str(PACKAGE_DIR)]  # type: ignore[attr-defined]
        sys.modules["gh_core"] = shadow


async def main() -> int:
    parser = argparse.ArgumentParser(description="预览 release 的文本渲染效果")
    parser.add_argument("--repo", default="deepseek-ai/deepseek-harness")
    parser.add_argument("--tag", default="")
    parser.add_argument("--list", type=int, default=0, metavar="N", help="列最近 N 条")
    parser.add_argument("--max-chars", type=int, default=600)
    parser.add_argument("--timezone", default="Asia/Shanghai")
    args = parser.parse_args()

    _load_without_nonebot()

    from gh_core.config import Config
    from gh_core.plan import select_releases
    from gh_core.render import render_release
    from gh_core.source import fetch_releases

    cfg = Config(gh_watch_repos=[args.repo])
    fetched = await fetch_releases(cfg, args.repo)
    releases = select_releases(fetched.releases)
    print(f"仓库 {args.repo}：{len(releases)} 条（数据源：{fetched.source}）")
    if not releases:
        print("没有符合条件的 release")
        return 1

    if args.list:
        from gh_core.latest import render_list

        print("-" * 60)
        print(
            render_list(
                list(reversed(releases[-args.list :])),
                repo=args.repo,
                tz_name=args.timezone,
            )
        )
        print("-" * 60)
        return 0

    if args.tag:
        picked = [r for r in releases if r.tag == args.tag]
        if not picked:
            print(f"没有找到 {args.tag}")
            return 1
        release = picked[0]
    else:
        release = releases[-1]

    print("-" * 60)
    print(
        render_release(
            release,
            repo=args.repo,
            tz_name=args.timezone,
            max_chars=args.max_chars,
            strip_mentions=True,
        )
    )
    print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
