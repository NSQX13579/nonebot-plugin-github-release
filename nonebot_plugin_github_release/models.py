"""数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def parse_time(value: Any) -> datetime:
    """解析 GitHub 返回的时间，失败时退化为当前时间（UTC）。"""
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Release:
    """一条 GitHub Release。"""

    tag: str
    name: str
    url: str
    body: str
    published_at: datetime
    prerelease: bool
    draft: bool = False
    # 以下字段只有走 GitHub API 时才有；atom 源拿不到，用于渲染卡片
    author_login: str = ""
    author_avatar_url: str = ""
    reactions: Optional[Dict[str, int]] = None

    @property
    def title(self) -> str:
        return self.name or self.tag

    @classmethod
    def from_github(cls, data: dict) -> Optional["Release"]:
        tag = str(data.get("tag_name") or "").strip()
        if not tag:
            return None
        author = data.get("author") or {}
        raw_reactions = data.get("reactions") or {}
        reactions = {
            str(key): int(value)
            for key, value in raw_reactions.items()
            if isinstance(value, int)
        } or None
        return cls(
            tag=tag,
            name=str(data.get("name") or tag).strip(),
            url=str(data.get("html_url") or "").strip(),
            body=str(data.get("body") or ""),
            # 草稿没有 published_at，退回 created_at
            published_at=parse_time(data.get("published_at") or data.get("created_at")),
            prerelease=bool(data.get("prerelease")),
            draft=bool(data.get("draft")),
            author_login=str(author.get("login") or ""),
            author_avatar_url=str(author.get("avatar_url") or ""),
            reactions=reactions,
        )
