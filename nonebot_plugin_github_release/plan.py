"""纯逻辑：筛选要推的 release、算待推送列表。不依赖 NoneBot，方便单测。"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .models import Release
from .store import RepoState


def select_releases(
    releases: Sequence[Release],
    *,
    include_prerelease: bool = True,
    require_body: bool = True,
) -> List[Release]:
    """挑出需要推送的 release，按发布时间升序。

    - 草稿（draft）永远不推
    - `require_body=True`（默认）时，没有正文的不算公告
    - `include_prerelease=False` 时，alpha / beta / rc 一律不推
    """
    selected: List[Release] = []
    for release in releases:
        if not release.tag or release.draft:
            continue
        if require_body and not release.body.strip():
            continue
        if not include_prerelease and release.prerelease:
            continue
        selected.append(release)
    return sorted(selected, key=lambda release: release.published_at)


def plan(state: RepoState, releases: Sequence[Release]) -> Tuple[RepoState, List[Release]]:
    """算待推送列表并返回更新后的状态。

    首次运行只把当前 release 记为基线（不补推历史）；之后返回所有「还没推过的」。
    """
    new_state = state.copy()
    tags = {release.tag for release in releases}
    if not state.initialized:
        new_state.initialized = True
        new_state.pushed = sorted(set(state.pushed) | tags)
        return new_state, []
    pushed = set(state.pushed)
    return new_state, [release for release in releases if release.tag not in pushed]
