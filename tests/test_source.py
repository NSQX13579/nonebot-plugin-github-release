"""数据源解析测试（不发网络请求）。"""

import pytest

from gh_core.models import Release
from gh_core.source import ReleaseFetchError, parse_atom

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-US">
  <title>Release notes from repo</title>
  <entry>
    <id>tag:github.com,2008:Repository/1/v1.1.0</id>
    <updated>2026-09-12T02:00:00Z</updated>
    <link rel="alternate" type="text/html"
          href="https://github.com/owner/repo/releases/tag/v1.1.0"/>
    <title>v1.1.0</title>
    <content type="html">&lt;p&gt;正式版公告&lt;/p&gt;</content>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/1/v1.2.0-rc.1</id>
    <updated>2026-09-10T03:42:23Z</updated>
    <link rel="alternate" type="text/html"
          href="https://github.com/owner/repo/releases/tag/v1.2.0-rc.1"/>
    <title>v1.2.0-rc.1</title>
    <content type="html">&lt;h3&gt;新增功能&lt;/h3&gt;</content>
  </entry>
</feed>
"""


def test_parse_atom_extracts_releases():
    releases = parse_atom(ATOM_FEED)
    assert [r.tag for r in releases] == ["v1.1.0", "v1.2.0-rc.1"]

    stable, prerelease = releases
    assert stable.url.endswith("/releases/tag/v1.1.0")
    assert stable.prerelease is False
    assert stable.body == "<p>正式版公告</p>"
    assert stable.published_at.hour == 2
    assert prerelease.prerelease is True


def test_parse_atom_rejects_broken_xml():
    with pytest.raises(ReleaseFetchError):
        parse_atom("<feed><entry>")


def test_parse_atom_rejects_empty_feed():
    with pytest.raises(ReleaseFetchError):
        parse_atom('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"/>')


def test_release_from_github_keeps_draft_and_prerelease_separate():
    release = Release.from_github(
        {
            "tag_name": "v1.0.0",
            "name": "v1.0.0",
            "html_url": "https://example.com",
            "body": "正文",
            "created_at": "2026-09-01T00:00:00Z",
            "draft": True,
            "prerelease": False,
            "author": {"login": "someone", "avatar_url": "https://example.com/a.png"},
            "reactions": {"+1": 3, "total_count": 3},
        }
    )
    assert release is not None
    assert release.draft is True
    assert release.prerelease is False
    assert release.author_login == "someone"
    assert release.reactions == {"+1": 3, "total_count": 3}


def test_release_from_github_requires_tag():
    assert Release.from_github({"name": "no tag"}) is None
