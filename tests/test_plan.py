"""筛选与待推送计算测试。"""

from datetime import datetime, timedelta, timezone

from gh_core.models import Release
from gh_core.plan import plan, select_releases
from gh_core.store import RepoState

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def make_release(tag, *, hours=0, body="正文", prerelease=None, draft=False):
    if prerelease is None:
        prerelease = "-" in tag.split("v", 1)[-1]
    return Release(
        tag=tag,
        name=tag,
        url=f"https://example.com/{tag}",
        body=body,
        published_at=BASE + timedelta(hours=hours),
        prerelease=prerelease,
        draft=draft,
    )


def test_includes_prerelease_by_default():
    releases = [
        make_release("v1.0.0-alpha.1", hours=1),
        make_release("v1.0.0", hours=2),
    ]
    assert [r.tag for r in select_releases(releases)] == ["v1.0.0-alpha.1", "v1.0.0"]


def test_can_exclude_prerelease():
    releases = [
        make_release("v1.0.0-alpha.1", hours=1),
        make_release("v1.0.0", hours=2),
    ]
    assert [r.tag for r in select_releases(releases, include_prerelease=False)] == ["v1.0.0"]


def test_skips_drafts():
    releases = [make_release("v1.0.0", draft=True), make_release("v0.9.0", hours=1)]
    assert [r.tag for r in select_releases(releases)] == ["v0.9.0"]


def test_requires_body():
    releases = [make_release("v1.0.0", body="  \n "), make_release("v0.9.0", hours=1)]
    assert [r.tag for r in select_releases(releases)] == ["v0.9.0"]
    assert len(select_releases(releases, require_body=False)) == 2


def test_first_run_only_builds_baseline():
    state = RepoState()
    new_state, pending = plan(state, [make_release("v1.0.0"), make_release("v1.1.0", hours=1)])
    assert pending == []
    assert new_state.initialized is True
    assert new_state.pushed == ["v1.0.0", "v1.1.0"]
    assert state.initialized is False


def test_new_release_is_pending():
    state = RepoState(initialized=True, pushed=["v1.0.0"])
    _, pending = plan(state, [make_release("v1.0.0"), make_release("v1.1.0", hours=1)])
    assert [r.tag for r in pending] == ["v1.1.0"]


def test_failed_push_stays_pending():
    state = RepoState(initialized=True, pushed=[])
    _, pending = plan(state, [make_release("v1.0.0")])
    assert [r.tag for r in pending] == ["v1.0.0"]
