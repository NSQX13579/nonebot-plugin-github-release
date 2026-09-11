"""把 release 渲染成一张「类 GitHub 卡片」的图片。

版式照 GitHub 的 release 卡片做，但只画真实存在的东西——仓库头像、发布时间、
版本号、正文、表情计数都是 API 给的真实数据；不伪造浏览器外框和可点控件。
任何一步失败都返回 None，由调用方回退纯文本。
"""

from __future__ import annotations

import html
import re
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from nonebot.log import logger

from .models import Release
from .render import clean_body, resolve_timezone

_CARD_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #ffffff; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei",
    "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
    "WenQuanYi Micro Hei", sans-serif;
  color: #1f2328;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.card { width: __WIDTH__px; padding: 20px 24px 22px; }
.head { display: flex; align-items: center; gap: 10px; }
.avatar {
  width: 40px; height: 40px; border-radius: 50%; object-fit: cover;
  display: block; background: #d0d7de;
}
.avatar-fallback {
  width: 40px; height: 40px; border-radius: 50%; background: #0969da;
  color: #ffffff; font-size: 18px; font-weight: 600; line-height: 40px;
  text-align: center;
}
.head-text { display: flex; flex-direction: column; gap: 2px; }
.repo { font-size: 14px; font-weight: 600; color: #1f2328; }
.when { font-size: 12px; color: #656d76; }
.title { font-size: 24px; font-weight: 600; margin: 14px 0 12px; line-height: 1.25; }
.tag {
  display: inline-block; font-size: 12px; font-weight: 500; color: #1a7f37;
  background: #dafbe1; border: 1px solid #aceebb; border-radius: 100px;
  padding: 1px 8px; margin-left: 8px; vertical-align: 3px;
}
.tag.pre { color: #9a6700; background: #fff8c5; border-color: #f5e6a2; }
.body {
  background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 6px;
  padding: 16px; max-height: __BODY_MAX_HEIGHT__px; overflow: hidden;
}
.body h4 { font-size: 16px; font-weight: 600; margin: 14px 0 8px; padding: 0; }
.body h4:first-child { margin-top: 0; }
.body p { font-size: 14px; line-height: 1.6; margin: 0 0 10px; }
.body ul { margin: 0 0 10px; padding-left: 22px; }
.body li { font-size: 14px; line-height: 1.6; margin: 4px 0; }
.body hr { border: 0; border-top: 1px solid #d8dee4; margin: 14px 0; }
.body code {
  font-family: ui-monospace, SFMono-Regular, "Cascadia Mono", Consolas,
    "Liberation Mono", monospace;
  font-size: 12.5px; background: rgba(175, 184, 193, 0.2);
  padding: 1px 5px; border-radius: 6px;
}
.body .mention { color: #0969da; font-weight: 500; }
.foot { margin-top: 12px; font-size: 12.5px; color: #656d76; }
.foot a { color: #0969da; text-decoration: none; }
.reactions { display: flex; gap: 6px; margin-top: 14px; flex-wrap: wrap; }
.reaction {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12px;
  color: #1f2328; background: #f6f8fa; border: 1px solid #d0d7de;
  border-radius: 100px; padding: 3px 10px;
}
.reaction .count { font-weight: 600; }
.truncated { color: #656d76; font-size: 12.5px; margin-top: 8px; }
"""

_BULLET_RE = re.compile(r"^(·|\*|-)\s+(.*)$")
_HEADING_RE = re.compile(r"^▍\s*(.+)$")
_CODE_RE = re.compile(r"`([^`]+)`")
_MENTION_RE = re.compile(r"@([A-Za-z0-9][A-Za-z0-9._-]*)")

_REACTION_EMOJI: Dict[str, str] = {
    "+1": "👍",
    "-1": "👎",
    "laugh": "😄",
    "hooray": "🎉",
    "confused": "😕",
    "heart": "❤️",
    "rocket": "🚀",
    "eyes": "👀",
}

# 头像取到一次就记住，避免网络抖动时卡片退化成字母头像
_AVATAR_MEMORY: Dict[str, str] = {}


def humanize_time(moment: datetime, *, now: Optional[datetime] = None) -> str:
    """把时间说成「16 小时前」。"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    seconds = (now - moment).total_seconds()
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    days = int(seconds // 86400)
    if days == 1:
        return "昨天"
    if days < 30:
        return f"{days} 天前"
    return moment.astimezone(resolve_timezone("Asia/Shanghai")).strftime("%Y-%m-%d")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = _CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = _MENTION_RE.sub(
        lambda m: f'<span class="mention">@{m.group(1)}</span>', escaped
    )
    return escaped


def body_to_html(text: str) -> str:
    """把清洗过的正文转成 HTML 片段。"""
    blocks: List[str] = []
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            blocks.append("</ul>")
            list_open = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if set(line) == {"-"} and len(line) >= 3:
            close_list()
            blocks.append("<hr>")
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            close_list()
            blocks.append(f"<h4>{_inline(heading.group(1))}</h4>")
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            blocks.append(f"<li>{_inline(bullet.group(2))}</li>")
            continue
        close_list()
        blocks.append(f"<p>{_inline(line)}</p>")

    close_list()
    return "\n".join(blocks)


def _reaction_html(reactions: Optional[Dict[str, int]]) -> str:
    if not reactions:
        return ""
    items: List[str] = []
    for key, emoji in _REACTION_EMOJI.items():
        count = int(reactions.get(key, 0) or 0)
        if count <= 0:
            continue
        items.append(f'<span class="reaction">{emoji}<span class="count">{count}</span></span>')
    if not items:
        return ""
    return f'<div class="reactions">{"".join(items)}</div>'


def build_card_html(
    release: Release,
    *,
    repo: str,
    avatar_uri: Optional[str] = None,
    max_chars: int = 2400,
    show_reactions: bool = True,
    cut_foreign: bool = True,
    width: int = 900,
    body_max_height: int = 1500,
) -> str:
    """生成卡片 HTML。正文保留 @提及（渲染成蓝字），它不影响任何人。"""
    cleaned = clean_body(release.body, strip_mentions=False, cut_foreign=cut_foreign)
    truncated = False
    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
        truncated = True

    if avatar_uri:
        avatar = (
            f'<img class="avatar" src="{html.escape(avatar_uri, quote=True)}" '
            f'alt="{html.escape(repo)}">'
        )
    else:
        initial = html.escape((repo.split("/")[0] or "g")[:1].upper())
        avatar = f'<div class="avatar-fallback">{initial}</div>'

    stage = "预发布" if release.prerelease else "正式版"
    body_html = body_to_html(cleaned) or "<p>（这条 release 没有正文）</p>"
    if truncated:
        body_html += '<div class="truncated">……正文较长，完整内容见下方链接</div>'

    reactions = _reaction_html(release.reactions) if show_reactions else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{_CARD_CSS.replace("__WIDTH__", str(width)).replace("__BODY_MAX_HEIGHT__", str(body_max_height))}</style>
</head>
<body>
  <div class="card">
    <div class="head">
      {avatar}
      <div class="head-text">
        <div class="repo">{html.escape(repo)} 发布</div>
        <div class="when">{html.escape(humanize_time(release.published_at))}</div>
      </div>
    </div>
    <div class="title">{html.escape(release.title)}<span class="tag{" pre" if release.prerelease else ""}">{stage}</span></div>
    <div class="body">
{body_html}
    </div>
    <div class="foot">完整公告：<a href="{html.escape(release.url, quote=True)}">{html.escape(release.url)}</a></div>
    {reactions}
  </div>
</body>
</html>"""


async def render_card(
    release: Release,
    *,
    repo: str,
    max_chars: int = 2400,
    show_reactions: bool = True,
    cut_foreign: bool = True,
    width: int = 900,
    body_max_height: int = 1500,
    scale: float = 2.0,
) -> Optional[bytes]:
    """渲染卡片图片；失败返回 None，由调用方回退纯文本。"""
    try:
        import nonebot_plugin_htmlrender as htmlrender
    except ImportError:
        logger.warning(
            "[gh-release] 未安装 nonebot-plugin-htmlrender，卡片功能不可用，将发送文本"
        )
        return None

    card_html = build_card_html(
        release,
        repo=repo,
        avatar_uri=await load_avatar_uri(repo, release.author_avatar_url),
        max_chars=max_chars,
        show_reactions=show_reactions,
        cut_foreign=cut_foreign,
        width=width,
        body_max_height=body_max_height,
    )
    try:
        return await htmlrender.html_to_pic(
            card_html,
            # 视口高度给小值，full_page 才会贴着内容走，底部不留空白
            viewport={"width": width, "height": 100},
            device_scale_factor=scale,
        )
    except Exception as exc:  # noqa: BLE001 - 渲染失败姿势很多，统一降级
        logger.warning(f"[gh-release] 卡片渲染失败，回退文本：{exc.__class__.__name__}: {exc}")
        return None


async def load_avatar_uri(repo: str, fallback_url: str = "") -> Optional[str]:
    """把仓库头像下载下来内联成 data URI，并缓存到内存与磁盘。

    优先用仓库主的头像（GitHub 的 `/{owner}.png`），跟真实卡片一致。
    """
    if repo in _AVATAR_MEMORY:
        return _AVATAR_MEMORY[repo]

    cache_file = _avatar_cache_file(repo)
    if cache_file is not None and cache_file.exists():
        try:
            cached = cache_file.read_bytes()
        except OSError:
            cached = b""
        if cached:
            uri = f"data:image/png;base64,{b64encode(cached).decode()}"
            _AVATAR_MEMORY[repo] = uri
            return uri

    candidates = []
    owner = repo.split("/")[0].strip()
    if owner:
        candidates.append(f"https://github.com/{owner}.png?size=96")
    if fallback_url:
        candidates.append(fallback_url)

    import httpx

    for url in candidates:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                response = await client.get(
                    url, headers={"User-Agent": "nonebot-plugin-github-release"}
                )
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - 头像拿不到不算错误
            logger.debug(f"[gh-release] 头像获取失败（{url}）：{exc}")
            continue
        content = response.content
        if not content or len(content) > 512 * 1024:
            continue
        mime = response.headers.get("content-type", "image/png").split(";")[0]
        if not mime.startswith("image/"):
            continue
        if cache_file is not None:
            try:
                cache_file.write_bytes(content)
            except OSError as exc:
                logger.debug(f"[gh-release] 头像缓存写入失败：{exc}")
        uri = f"data:{mime};base64,{b64encode(content).decode()}"
        _AVATAR_MEMORY[repo] = uri
        return uri
    return None


def _avatar_cache_file(repo: str) -> Optional[Path]:
    """头像磁盘缓存路径，拿不到就返回 None。"""
    try:
        from .config import load_config
        from .store import resolve_data_dir

        directory = resolve_data_dir(load_config()) / "avatar"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{repo.replace('/', '_')}.png"
    except Exception as exc:  # noqa: BLE001 - 缓存不可用不影响主流程
        logger.debug(f"[gh-release] 头像缓存目录不可用：{exc}")
        return None
