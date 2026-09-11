"""状态与订阅持久化测试。"""

from gh_core.config import Config
from gh_core.store import (
    RepoState,
    load_states,
    load_subscriptions,
    resolve_data_dir,
    save_states,
    save_subscriptions,
    state_path,
    subscriptions_path,
)


def test_states_roundtrip(tmp_path):
    path = state_path(tmp_path)
    states = {
        "a/b": RepoState(
            initialized=True,
            pushed=["v1.0.0", "v0.9.0", "v1.0.0"],
            latest="v1.0.0",
            last_check="2026-09-11T03:00:00+00:00",
            last_source="api",
        )
    }
    save_states(path, states)

    loaded = load_states(path)
    assert set(loaded) == {"a/b"}
    assert loaded["a/b"].pushed == ["v0.9.0", "v1.0.0"]
    assert loaded["a/b"].latest == "v1.0.0"
    assert loaded["a/b"].last_source == "api"
    assert list(tmp_path.glob("*.tmp")) == []


def test_load_states_of_missing_and_corrupted_file(tmp_path):
    path = state_path(tmp_path)
    assert load_states(path) == {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert load_states(path) == {}


def test_states_tolerate_old_shape(tmp_path):
    """旧版没有 repos 包裹层，也要能读。"""
    path = state_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"a/b": {"initialized": true, "pushed": ["v1.0.0"]}}', encoding="utf-8")
    loaded = load_states(path)
    assert loaded["a/b"].initialized is True
    assert loaded["a/b"].pushed == ["v1.0.0"]


def test_subscriptions_roundtrip(tmp_path):
    path = subscriptions_path(tmp_path)
    save_subscriptions(path, {"a/b": {123, 456}, "empty/repo": set()})
    assert load_subscriptions(path) == {"a/b": {123, 456}}


def test_subscriptions_of_missing_file(tmp_path):
    assert load_subscriptions(subscriptions_path(tmp_path)) == {}


def test_resolve_data_dir_override():
    assert resolve_data_dir(Config(gh_watch_data_dir="custom")).as_posix() == "custom"
