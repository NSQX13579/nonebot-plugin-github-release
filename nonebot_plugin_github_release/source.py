"""拉取 GitHub 仓库的 release。

两个数据源，自动兜底：

1. GitHub Releases API（首选，字段完整，匿名限额 60 次/小时）
2. `releases.atom`（网页订阅源，不限流，但拿不到表情计数等字段）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from xml.etree import ElementTree

import httpx

from .config import Config
from .models import Release, parse_time
from .versions import parse_version

_USER_AGENT = "nonebot-plugin-github-release/0.1.0"
_API_ROOT = "https://api.github.com"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ReleaseFetchError(RuntimeError):
    """拉取失败。"""


@dataclass
class FetchResult:
    """一次拉取的结果。"""

    repo: str
    releases: List[Release]
    source: str  # "api" 或 "atom"


def _client_kwargs(cfg: Config) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "timeout": httpx.Timeout(20.0, connect=10.0),
        "follow_redirects": True,
    }
    if cfg.gh_watch_proxy:
        kwargs["proxy"] = cfg.gh_watch_proxy
    return kwargs


def _headers(cfg: Config, accept: str = "application/vnd.github+json") -> Dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (cfg.gh_watch_github_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch_releases(
    cfg: Config, repo: str, *, per_page: int = 30
) -> FetchResult:
    """拉取某个仓库最近的 release，API 不行就走 atom。"""
    errors: List[str] = []
    try:
        return FetchResult(repo, await _fetch_from_api(cfg, repo, per_page=per_page), "api")
    except ReleaseFetchError as exc:
        errors.append(f"接口：{exc}")

    try:
        return FetchResult(repo, await _fetch_from_atom(cfg, repo), "atom")
    except ReleaseFetchError as exc:
        errors.append(f"订阅源：{exc}")

    raise ReleaseFetchError("；".join(errors))


async def _fetch_from_api(cfg: Config, repo: str, *, per_page: int = 30) -> List[Release]:
    """走 Releases API。

    注意不能用 `/releases/latest`——仓库只发预发布版时它会返回 404。
    """
    url = f"{_API_ROOT}/repos/{repo}/releases"
    try:
        async with httpx.AsyncClient(**_client_kwargs(cfg)) as client:
            response = await client.get(
                url,
                params={"per_page": max(1, min(per_page, 100))},
                headers=_headers(cfg),
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        hint = ""
        if status == 404:
            hint = "（仓库不存在或没有 release 权限）"
        elif status in (403, 429):
            hint = "（可能触发了 GitHub 限流，可配置 GH_WATCH_GITHUB_TOKEN）"
        raise ReleaseFetchError(f"HTTP {status}{hint}") from exc
    except httpx.HTTPError as exc:
        raise ReleaseFetchError(f"{exc.__class__.__name__}: {exc}") from exc
    except ValueError as exc:
        raise ReleaseFetchError(f"响应无法解析：{exc}") from exc

    if not isinstance(payload, list):
        raise ReleaseFetchError("返回了非预期的数据结构")

    releases: List[Release] = []
    for item in payload:
        if isinstance(item, dict):
            release = Release.from_github(item)
            if release is not None:
                releases.append(release)
    return releases


async def _fetch_from_atom(cfg: Config, repo: str) -> List[Release]:
    """走 releases.atom（不限流）。"""
    url = f"https://github.com/{repo}/releases.atom"
    try:
        async with httpx.AsyncClient(**_client_kwargs(cfg)) as client:
            response = await client.get(
                url, headers=_headers(cfg, "application/atom+xml")
            )
            response.raise_for_status()
            payload = response.text
    except httpx.HTTPStatusError as exc:
        raise ReleaseFetchError(f"HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ReleaseFetchError(f"{exc.__class__.__name__}: {exc}") from exc

    return parse_atom(payload)


def parse_atom(payload: str) -> List[Release]:
    """解析 releases.atom 文本。"""
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ReleaseFetchError(f"订阅源不是合法 XML：{exc}") from exc

    releases: List[Release] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title = (entry.findtext("atom:title", default="", namespaces=_ATOM_NS) or "").strip()
        link = entry.find("atom:link", _ATOM_NS)
        href = (link.get("href") if link is not None else "") or ""
        updated = entry.findtext("atom:updated", default="", namespaces=_ATOM_NS) or ""
        content = entry.findtext("atom:content", default="", namespaces=_ATOM_NS) or ""

        # href 形如 https://github.com/<owner>/<repo>/releases/tag/<tag>
        tag = href.rstrip("/").rsplit("/", 1)[-1] if "/tag/" in href else title
        if not tag:
            continue
        version = parse_version(tag)
        releases.append(
            Release(
                tag=tag,
                name=title or tag,
                url=href,
                body=content,
                published_at=parse_time(updated),
                # atom 不含 prerelease 标记，只能从版本号推断
                prerelease=bool(version and not version.is_stable),
            )
        )
    if not releases:
        raise ReleaseFetchError("订阅源里没有可用条目")
    return releases
