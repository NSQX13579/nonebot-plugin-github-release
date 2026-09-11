"""把 release 正文渲染成群消息文本。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional
from zoneinfo import ZoneInfo

from .models import Release

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_HEADING_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)
_HTML_LI_RE = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_HTML_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_BLOCK_RE = re.compile(
    r"</?(?:p|div|ul|ol|section|article|blockquote|table|tr|td)\b[^>]*>",
    re.IGNORECASE,
)
# atom 源整篇可能挤在一行，先在块级标签后补换行（保留标签本身给后面的清洗用）
_HTML_BLOCK_BREAK_RE = re.compile(
    r"</(?:p|div|h[1-6]|li|ul|ol|blockquote|section|article|tr|td)\s*>",
    re.IGNORECASE,
)
_MD_HEADING_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MENTION_RE = re.compile(r"(^|[\s。，、：；）】」!?！？])(@[A-Za-z0-9][A-Za-z0-9._-]*)")
_BULLET_PREFIXES = ("- ", "* ", "+ ")

# 英文段落的起始标记（中英双语公告的分界）
_EN_ANCHOR_RE = re.compile(
    r"""^\s*(?:
        <h[1-6][^>]*id=["'](?:user-content-)?en(?:-[^"']*)?["'][^>]*>
        | <h[1-6][^>]*>\s*(?:<a[^>]*>\s*)?english\b
        | \#{1,6}\s*english\b
        | \[english\]\(
    )""",
    re.IGNORECASE | re.VERBOSE,
)
# 顶部的语言切换行：[中文](#cn) | [English](#en)，或剥掉标签后的「中文 | English」
_LANG_SWITCH_RE = re.compile(
    r"^\s*\[?中文\]?(?:\([^)]*\))?\s*\|\s*\[?(?:English|EN)\]?(?:\([^)]*\))?\s*$",
    re.IGNORECASE,
)


def clean_body(
    text: str, *, strip_mentions: bool = True, cut_foreign: bool = False
) -> str:
    """把 Markdown / HTML 清洗成适合展示的纯文本。

    `cut_foreign=True` 时，遇到中英双语正文只保留前半部分（中文段），
    并丢掉顶部的「中文 | English」切换行。
    """
    if cut_foreign:
        text = cut_foreign_section(text)
    text = _HTML_BLOCK_BREAK_RE.sub(lambda match: match.group(0) + "\n", text or "")
    text = _HTML_LI_RE.sub("\n· ", text)
    text = _HTML_BR_RE.sub("\n", text)
    text = _HTML_BLOCK_RE.sub("\n", text)
    text = _HTML_HEADING_RE.sub(
        lambda match: f"\n▍{_HTML_TAG_RE.sub('', match.group(1)).strip()}\n", text
    )
    text = _HTML_TAG_RE.sub("", text)
    text = _MD_LINK_RE.sub(r"\1", text)

    output: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            output.append("")
            continue
        heading = _MD_HEADING_RE.match(line)
        if heading is not None:
            line = f"▍{heading.group(1)}"
        elif line.startswith(_BULLET_PREFIXES):
            line = "· " + line[2:].strip()
        line = line.replace("`", "").replace("**", "")
        if strip_mentions:
            line = _MENTION_RE.sub(r"\1", line)
        output.append(line.rstrip())

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()
    # 中英双语公告用 --- 分隔，落在末尾就是噪音
    return re.sub(r"(?:\n\s*(?:-{3,}|\*{3,}|_{3,})\s*)+\s*$", "", result).strip()


def cut_foreign_section(body: str) -> str:
    """只保留中英双语正文的前半部分（中文段）。

    必须在其它清洗之前调用——清洗会把 `<h3 id="en-x">English</h3>` 变成
    `▍English`，那时就认不出分界了。
    """
    body = _HTML_BLOCK_BREAK_RE.sub(lambda match: match.group(0) + "\n", body or "")
    lines: List[str] = []
    for raw in body.splitlines():
        if _EN_ANCHOR_RE.match(raw.strip()):
            break
        plain = _HTML_TAG_RE.sub("", raw).strip()
        if _LANG_SWITCH_RE.match(plain):
            continue
        lines.append(raw)
    return "\n".join(lines)


def truncate_text(text: str, max_chars: int) -> str:
    """按行截断，尽量不破坏行结构。"""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    kept: List[str] = []
    total = 0
    for line in text.splitlines():
        if total + len(line) + 1 > max_chars:
            break
        kept.append(line)
        total += len(line) + 1
    if not kept:
        return text[:max_chars].rstrip() + "…"
    return "\n".join(kept).rstrip() + "\n…（正文较长，完整内容见下方链接）"


@lru_cache(maxsize=8)
def resolve_timezone(name: str) -> timezone:
    """解析时区名，失败退回 UTC（Windows 上需要 tzdata）。"""
    try:
        return ZoneInfo(name)  # type: ignore[return-value]
    except Exception:
        return timezone.utc


def format_local_time(moment: Optional[datetime], tz_name: str) -> str:
    if moment is None:
        return "-"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(resolve_timezone(tz_name)).strftime("%Y-%m-%d %H:%M")


def format_iso_local(value: Optional[str], tz_name: str) -> str:
    if not value:
        return "-"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return format_local_time(moment, tz_name)


def render_release(
    release: Release,
    *,
    repo: str,
    tz_name: str = "Asia/Shanghai",
    max_chars: int = 600,
    strip_mentions: bool = True,
    cut_foreign: bool = True,
) -> str:
    """渲染纯文本推送内容。"""
    body = truncate_text(
        clean_body(release.body, strip_mentions=strip_mentions, cut_foreign=cut_foreign),
        max_chars,
    )
    stage = "预发布" if release.prerelease else "正式版"

    parts = [f"【{repo} {stage}】{release.title}"]
    published = format_local_time(release.published_at, tz_name)
    if published != "-":
        parts.append(f"发布时间：{published}")
    if body:
        parts.append(body)
    if release.url:
        parts.append(f"完整公告：{release.url}")
    return "\n".join(parts)
