"""版本号解析与「正式版」判定。"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

# 兼容 `v0.1.5`、`dsh-v0.1.5`、`dsh-v0.1.5-rc.1` 这几种 tag 写法
_TAG_RE = re.compile(
    r"^(?:[^0-9]*?)v?(\d+)\.(\d+)\.(\d+)"
    r"(?:-([0-9A-Za-z.\-]+))?"
    r"(?:\+[0-9A-Za-z.\-]+)?$"
)


class Version(NamedTuple):
    """语义化版本。"""

    major: int
    minor: int
    patch: int
    prerelease: Optional[str]

    @property
    def is_stable(self) -> bool:
        """没有预发布后缀才算正式版。"""
        return self.prerelease is None

    @property
    def core(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_version(tag: str) -> Optional[Version]:
    """解析 tag 中的版本号，解析不出来返回 None。"""
    match = _TAG_RE.match((tag or "").strip())
    if match is None:
        return None
    major, minor, patch, prerelease = match.groups()
    return Version(int(major), int(minor), int(patch), prerelease)


def is_stable_release(tag: str, *, prerelease_flag: bool = False) -> bool:
    """判断是否为正式版。

    两个条件同时满足才算正式版：GitHub 没有标记为 prerelease，且 tag 中没有
    预发布后缀。解析不出版本号的 tag（例如 `nightly`）一律不算，避免误报。
    """
    if prerelease_flag:
        return False
    version = parse_version(tag)
    return bool(version and version.is_stable)
