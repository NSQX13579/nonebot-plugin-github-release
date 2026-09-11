"""本地预览：把 release 渲染成卡片图片，输出到 build/ 目录。

用法（需要装好 htmlrender 与 playwright chromium）::

    python tools/cardpreview.py                                   # 拉线上最新一条
    python tools/cardpreview.py --fixture                         # 用样例正文，不联网
    python tools/cardpreview.py --repo owner/repo --tag v1.2.3
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nonebot  # noqa: E402

nonebot.init(driver="~fastapi")

from nonebot_plugin_github_release.card import build_card_html, load_avatar_uri  # noqa: E402
from nonebot_plugin_github_release.config import Config  # noqa: E402
from nonebot_plugin_github_release.models import Release  # noqa: E402
from nonebot_plugin_github_release.plan import select_releases  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample_release_body.md"


def fixture_release(repo: str) -> Release:
    return Release(
        tag="v1.2.3-rc.1",
        name="v1.2.3-rc.1",
        url=f"https://github.com/{repo}/releases/tag/v1.2.3-rc.1",
        body=FIXTURE.read_text(encoding="utf-8"),
        published_at=datetime.now(timezone.utc),
        prerelease=True,
        reactions={"+1": 85, "hooray": 5, "laugh": 18, "heart": 15, "rocket": 14, "eyes": 7},
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 release 卡片预览")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--tag", default="")
    parser.add_argument("--fixture", action="store_true", help="用样例正文，不联网")
    parser.add_argument("--width", type=int, default=900)
    parser.add_argument("--max-chars", type=int, default=2400)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()

    if args.fixture:
        release = fixture_release(args.repo)
    else:
        from nonebot_plugin_github_release.source import fetch_releases

        cfg = Config(gh_watch_repos=[args.repo])
        fetched = await fetch_releases(cfg, args.repo)
        releases = select_releases(fetched.releases)
        if not releases:
            print("没有拉到 release")
            return 1
        if args.tag:
            picked = [r for r in releases if r.tag == args.tag]
            if not picked:
                print(f"没有找到 {args.tag}")
                return 1
            release = picked[0]
        else:
            release = releases[-1]
        print(f"数据源：{fetched.source}｜渲染 {release.tag}")

    card_html = build_card_html(
        release,
        repo=args.repo,
        avatar_uri=await load_avatar_uri(args.repo, release.author_avatar_url),
        max_chars=args.max_chars,
        width=args.width,
    )

    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    html_path = build_dir / "card.html"
    html_path.write_text(card_html, encoding="utf-8")

    import nonebot_plugin_htmlrender as htmlrender

    png = await htmlrender.html_to_pic(
        card_html,
        viewport={"width": args.width, "height": 100},
        device_scale_factor=args.scale,
    )
    png_path = build_dir / "card.png"
    png_path.write_bytes(png)
    print(f"HTML: {html_path}")
    print(f"PNG : {png_path}  ({len(png) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
