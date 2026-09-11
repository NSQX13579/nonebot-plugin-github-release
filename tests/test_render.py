"""文本渲染测试。"""

from datetime import datetime, timezone

from gh_core.models import Release
from gh_core.render import clean_body, render_release, truncate_text

ATOM_BODY = """<p>本次更新内容如下。</p>
<h3>新增功能</h3>
<ul>
<li>新增 <code>DeepSeek-V41-Flash</code> 支持。 @CreatixChu</li>
<li>Web 支持上传文件。@turtle1999</li>
</ul>
<h3 id="en">English</h3>
<p>English notes.</p>"""


def make_release(body=ATOM_BODY, tag="v1.2.3"):
    return Release(
        tag=tag,
        name=tag,
        url=f"https://github.com/a/b/releases/tag/{tag}",
        body=body,
        published_at=datetime(2026, 9, 10, 3, 9, tzinfo=timezone.utc),
        prerelease="-" in tag,
    )


def test_clean_body_handles_markup():
    cleaned = clean_body(ATOM_BODY)
    assert "▍新增功能" in cleaned
    assert "· 新增 DeepSeek-V41-Flash 支持。" in cleaned
    assert "<" not in cleaned and ">" not in cleaned


def test_clean_body_strips_mentions_including_after_punctuation():
    cleaned = clean_body("优化了提交体验。@yixiangihsiang", strip_mentions=True)
    assert cleaned == "优化了提交体验。"
    kept = clean_body("优化了提交体验。@yixiangihsiang", strip_mentions=False)
    assert "@yixiangihsiang" in kept


def test_truncate_text_marks_cut():
    truncated = truncate_text("一二三四五\n六七八九十", 6)
    assert truncated.startswith("一二三四五")
    assert "完整内容见下方链接" in truncated
    assert truncate_text("短文本", 100) == "短文本"


def test_render_release_shape():
    text = render_release(make_release(), repo="owner/repo", max_chars=10000)
    lines = text.splitlines()
    assert lines[0] == "【owner/repo 正式版】v1.2.3"
    assert lines[1] == "发布时间：2026-09-10 11:09"
    assert text.endswith("完整公告：https://github.com/a/b/releases/tag/v1.2.3")


def test_render_release_marks_prerelease():
    text = render_release(make_release(tag="v1.2.3-rc.1"), repo="owner/repo")
    assert text.startswith("【owner/repo 预发布】v1.2.3-rc.1")


def test_cut_foreign_keeps_only_first_language():
    cleaned = clean_body(ATOM_BODY, cut_foreign=True)
    assert "新增功能" in cleaned
    assert "English notes." not in cleaned
    # 默认不裁剪，两段都在
    assert "English notes." in clean_body(ATOM_BODY)


def test_cut_foreign_drops_language_switcher_line():
    body = "<p>中文 | English</p><p>中文正文。</p><h3 id=\"en-x\">English</h3><p>english body</p>"
    cleaned = clean_body(body, cut_foreign=True)
    assert "中文 | English" not in cleaned
    assert "中文正文。" in cleaned
    assert "english body" not in cleaned
