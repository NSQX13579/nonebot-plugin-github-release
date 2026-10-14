"""状态与订阅的持久化（JSON，原子写入）。

- `state.json`：每个仓库的推送基线
- `subscriptions.json`：哪个群订阅了哪个仓库
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import Config


def resolve_data_dir(cfg: Config) -> Path:
    """插件数据目录。

    用 nonebot-plugin-localstore 管（依赖已在 ``__init__.py`` 里 require）。
    这里按需导入，是为了让单测和 tools 脚本在没有 NoneBot 运行时的情况下也能跑；
    真正缺 localstore 时退化为 data/github_release，不至于把插件带崩。
    """
    if cfg.gh_watch_data_dir:
        return Path(cfg.gh_watch_data_dir).expanduser()
    try:
        import nonebot_plugin_localstore as store

        return store.get_plugin_data_dir()
    except Exception:  # noqa: BLE001 - 没装 localstore 或未初始化时退化
        return Path("data") / "github_release"


def state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def subscriptions_path(data_dir: Path) -> Path:
    return data_dir / "subscriptions.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RepoState:
    """单个仓库的监控状态。"""

    initialized: bool = False
    pushed: List[str] = field(default_factory=list)
    latest: Optional[str] = None
    last_check: Optional[str] = None
    last_ok: Optional[str] = None
    last_error: Optional[str] = None
    last_source: Optional[str] = None

    def copy(self) -> "RepoState":
        return RepoState(
            initialized=self.initialized,
            pushed=list(self.pushed),
            latest=self.latest,
            last_check=self.last_check,
            last_ok=self.last_ok,
            last_error=self.last_error,
            last_source=self.last_source,
        )

    @classmethod
    def from_dict(cls, raw: Any) -> "RepoState":
        if not isinstance(raw, dict):
            return cls()
        pushed = raw.get("pushed")
        return cls(
            initialized=bool(raw.get("initialized")),
            pushed=[str(tag) for tag in pushed if isinstance(tag, str)]
            if isinstance(pushed, list)
            else [],
            latest=raw.get("latest") or None,
            last_check=raw.get("last_check") or None,
            last_ok=raw.get("last_ok") or None,
            last_error=raw.get("last_error") or None,
            last_source=raw.get("last_source") or None,
        )


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_states(path: Path) -> Dict[str, RepoState]:
    """读取所有仓库状态；文件缺失或损坏时返回空表。"""
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return {}
    repos = raw.get("repos")
    source = repos if isinstance(repos, dict) else raw
    return {
        str(name): RepoState.from_dict(value)
        for name, value in source.items()
        if isinstance(name, str)
    }


def save_states(path: Path, states: Dict[str, RepoState]) -> None:
    payload = {"repos": {name: asdict(state) for name, state in sorted(states.items())}}
    for value in payload["repos"].values():
        value["pushed"] = sorted(set(value["pushed"]))
    _atomic_write_json(path, payload)


def load_subscriptions(path: Path) -> Dict[str, Set[int]]:
    """读取「仓库 → 订阅群」映射。"""
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, Set[int]] = {}
    for repo, groups in raw.items():
        if not isinstance(repo, str) or not isinstance(groups, list):
            continue
        parsed: Set[int] = set()
        for item in groups:
            try:
                parsed.add(int(item))
            except (TypeError, ValueError):
                continue
        if parsed:
            result[repo] = parsed
    return result


def save_subscriptions(path: Path, subscriptions: Dict[str, Set[int]]) -> None:
    payload = {
        repo: sorted(groups)
        for repo, groups in sorted(subscriptions.items())
        if groups
    }
    _atomic_write_json(path, payload)
