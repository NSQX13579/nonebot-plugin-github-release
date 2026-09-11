"""按需查询的渲染测试。"""

from datetime import datetime, timedelta, timezone

from gh_core.latest import render_list
from gh_core.models import Release

BASE = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)


def make_release(tag: str, *, hours: int = 0) -> Release:
    return Release(
        tag=tag,
        name=tag,
        url=f"https://github.com/a/b/releases/tag/{tag}",
        body="正文",
        published_at=BASE + timedelta(hours=hours),
        prerelease="-" in tag,
    )


def test_render_list_shape():
    text = render_list(
        [make_release("v1.0.0", hours=48), make_release("v1.1.0-rc.1", hours=36)],
        repo="owner/repo",
        tz_name="Asia/Shanghai",
    )
    lines = text.splitlines()
    assert lines[0] == "【owner/repo 最近 2 条】"
    assert lines[1] == "· v1.0.0（正式版｜2026-09-10 11:00）"
    assert lines[2].strip().endswith("/releases/tag/v1.0.0")
    assert lines[3] == "· v1.1.0-rc.1（预发布｜2026-09-09 23:00）"
    assert "/gh公告 owner/repo" in text


def test_render_list_without_url():
    release = Release(
        tag="v1.0.0",
        name="v1.0.0",
        url="",
        body="正文",
        published_at=BASE,
        prerelease=False,
    )
    assert "https://" not in render_list([release], repo="a/b", tz_name="Asia/Shanghai")
