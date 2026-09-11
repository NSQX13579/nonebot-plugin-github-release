"""卡片 HTML 生成测试（不跑浏览器）。"""

from datetime import datetime, timedelta, timezone

from gh_core.card import body_to_html, build_card_html, humanize_time
from gh_core.models import Release

BODY = """<p>本次更新内容如下。</p>
<h3>新增功能</h3>
<ul>
<li>新增 <code>flash</code> 支持。</li>
</ul>
"""


def make_release(**kwargs) -> Release:
    base = dict(
        tag="v1.2.3",
        name="v1.2.3",
        url="https://github.com/a/b/releases/tag/v1.2.3",
        body=BODY,
        published_at=datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc),
        prerelease=False,
    )
    base.update(kwargs)
    return Release(**base)


def test_body_to_html_structure():
    rendered = body_to_html("▍新增功能\n· 第一条\n· 第二条\n---\n结尾一句")
    assert "<h4>新增功能</h4>" in rendered
    assert rendered.count("<li>") == 2
    assert "<hr>" in rendered
    assert "<p>结尾一句</p>" in rendered


def test_body_to_html_inline_code_and_mention():
    rendered = body_to_html("· 新增 `flash` 支持 @CreatixChu")
    assert "<code>flash</code>" in rendered
    assert '<span class="mention">@CreatixChu</span>' in rendered


def test_body_to_html_escapes_html():
    rendered = body_to_html("· <script>alert(1)</script>")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_card_contains_real_fields():
    card = build_card_html(make_release(), repo="owner/repo")
    assert "owner/repo 发布" in card
    assert "v1.2.3" in card
    assert "正式版" in card
    assert "完整公告：" in card


def test_card_avatar_fallback_and_image():
    assert 'class="avatar-fallback"' in build_card_html(make_release(), repo="owner/repo")
    assert ">O<" in build_card_html(make_release(), repo="owner/repo")

    with_avatar = build_card_html(
        make_release(), repo="owner/repo", avatar_uri="data:image/png;base64,iVBORw0KGgo="
    )
    assert '<img class="avatar"' in with_avatar


def test_card_marks_prerelease_and_reactions():
    card = build_card_html(make_release(prerelease=True), repo="a/b")
    assert 'class="tag pre"' in card
    assert "预发布" in card

    with_reactions = build_card_html(make_release(reactions={"+1": 85, "rocket": 0}), repo="a/b")
    assert 'class="reaction"' in with_reactions
    assert "85" in with_reactions
    assert "🚀" not in with_reactions
    assert 'class="reaction"' not in build_card_html(make_release(), repo="a/b")


def test_card_truncates_long_body():
    long_body = "\n".join(f"· 第 {i} 条内容" for i in range(200))
    card = build_card_html(make_release(body=long_body), repo="a/b", max_chars=80)
    assert "正文较长" in card


def test_humanize_time_buckets():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    assert humanize_time(now - timedelta(seconds=30), now=now) == "刚刚"
    assert humanize_time(now - timedelta(minutes=5), now=now) == "5 分钟前"
    assert humanize_time(now - timedelta(hours=16), now=now) == "16 小时前"
    assert humanize_time(now - timedelta(days=1), now=now) == "昨天"
    assert humanize_time(now - timedelta(days=3), now=now) == "3 天前"
