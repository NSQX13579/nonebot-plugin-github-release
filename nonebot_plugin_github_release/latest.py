"""按需查询公告（给 /gh公告 用）：只读不写，带短时缓存。"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

from .config import Config
from .models import Release
from .plan import select_releases
from .render import format_local_time
from .source import fetch_releases

_CACHE_TTL_SECONDS = 60.0
_cache: Dict[str, Tuple[float, List[Release], str]] = {}


def _cache_key(cfg: Config, repo: str) -> str:
    return "|".join(
        [repo, str(cfg.gh_watch_include_prerelease), str(cfg.gh_watch_require_body)]
    )


def clear_cache() -> None:
    _cache.clear()


async def fetch_announcements(
    cfg: Config, repo: str, *, use_cache: bool = True
) -> Tuple[List[Release], str]:
    """拉取某个仓库的 release 列表（按发布时间升序），返回 (列表, 数据源)。"""
    key = _cache_key(cfg, repo)
    now = time.monotonic()
    if use_cache:
        cached = _cache.get(key)
        if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1], cached[2]

    fetched = await fetch_releases(cfg, repo)
    releases = select_releases(
        fetched.releases,
        include_prerelease=cfg.gh_watch_include_prerelease,
        require_body=cfg.gh_watch_require_body,
    )
    _cache[key] = (now, releases, fetched.source)
    return releases, fetched.source


def render_list(releases: List[Release], *, repo: str, tz_name: str) -> str:
    """把若干条 release 渲染成简表。"""
    lines = [f"【{repo} 最近 {len(releases)} 条】"]
    for release in releases:
        stage = "预发布" if release.prerelease else "正式版"
        when = format_local_time(release.published_at, tz_name)
        lines.append(f"· {release.title}（{stage}｜{when}）")
        if release.url:
            lines.append(f"  {release.url}")
    lines.append("")
    lines.append(f"发 /gh公告 {repo} 看最新一条全文")
    return "\n".join(lines)
