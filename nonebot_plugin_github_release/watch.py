"""定时检查 + 推送。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import nonebot
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.log import logger

from .card import render_card
from .config import Config, load_config
from .models import Release
from .plan import plan, select_releases
from .render import render_release
from .source import ReleaseFetchError, fetch_releases
from .store import (
    RepoState,
    load_states,
    load_subscriptions,
    now_iso,
    resolve_data_dir,
    save_states,
    state_path,
    subscriptions_path,
)


@dataclass
class CheckResult:
    """一次检查的结果。"""

    status: str
    detail: str
    repo_count: int = 0
    pushed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def effective_subscriptions(
    cfg: Config, stored: Dict[str, Set[int]]
) -> Dict[str, Set[int]]:
    """配置里的默认订阅 + 群内动态订阅。

    `GH_WATCH_REPOS × GH_WATCH_GROUPS` 的组合等价于「这些群都订阅这些仓库」。
    """
    result: Dict[str, Set[int]] = {repo: set(groups) for repo, groups in stored.items()}
    default_groups = set(cfg.gh_watch_groups)
    for repo in cfg.gh_watch_repos:
        result.setdefault(repo, set()).update(default_groups)
    return {repo: groups for repo, groups in result.items() if groups}


async def build_announce_message(release: Release, repo: str, cfg: Config) -> "str | Message":
    """构造要发送的消息：优先卡片图，失败回退纯文本。"""
    if cfg.gh_watch_send_image:
        png = await render_card(
            release,
            repo=repo,
            max_chars=cfg.gh_watch_card_max_chars,
            show_reactions=cfg.gh_watch_card_show_reactions,
            cut_foreign=cfg.gh_watch_body_language != "all",
            width=cfg.gh_watch_card_width,
            body_max_height=cfg.gh_watch_card_max_height,
        )
        if png is not None:
            stage = "预发布" if release.prerelease else "正式版"
            # 图片里的链接点不了，附一行文字方便复制
            caption = f"【{repo} {stage}】{release.title}\n完整公告：{release.url}"
            return Message(MessageSegment.image(png)) + f"\n{caption}"

    return render_release(
        release,
        repo=repo,
        tz_name=cfg.gh_watch_timezone,
        max_chars=cfg.gh_watch_max_chars,
        strip_mentions=cfg.gh_watch_strip_mentions,
        cut_foreign=cfg.gh_watch_body_language != "all",
    )


async def push_to_groups(
    message: "str | Message", groups: Iterable[int]
) -> Tuple[List[int], List[str]]:
    """推送消息，返回 (成功的群, 错误信息)。"""
    try:
        bots = [
            bot for bot in nonebot.get_bots().values() if isinstance(bot, OneBotV11Bot)
        ]
    except Exception as exc:  # pragma: no cover - 依赖运行时状态
        return [], [f"获取机器人实例失败：{exc.__class__.__name__}: {exc}"]

    if not bots:
        return [], ["当前没有已连接的 OneBot V11 机器人"]

    succeeded: List[int] = []
    errors: List[str] = []
    for group_id in groups:
        for bot in bots:
            try:
                await bot.send_group_msg(group_id=int(group_id), message=message)
            except Exception as exc:  # noqa: BLE001 - 发送失败原因很多，统一记录
                errors.append(
                    f"群 {group_id} 推送失败（bot {bot.self_id}）："
                    f"{exc.__class__.__name__}: {exc}"
                )
                continue
            succeeded.append(int(group_id))
            break
    return succeeded, errors


async def check_once(cfg: Optional[Config] = None) -> CheckResult:
    """遍历所有订阅的仓库，把新 release 推到对应的群。"""
    cfg = cfg or load_config()
    data_dir = resolve_data_dir(cfg)
    states_file = state_path(data_dir)
    states = load_states(states_file)
    subscriptions = effective_subscriptions(cfg, load_subscriptions(subscriptions_path(data_dir)))

    if not subscriptions:
        return CheckResult(
            status="no-repo",
            detail="没有任何订阅：在群里发 /gh订阅 owner/repo，或配置 GH_WATCH_REPOS",
        )

    pushed: List[str] = []
    failed: List[str] = []
    errors: List[str] = []
    limit = max(1, cfg.gh_watch_max_per_round)

    for repo, groups in sorted(subscriptions.items()):
        state = states.get(repo) or RepoState()
        try:
            fetched = await fetch_releases(cfg, repo)
        except ReleaseFetchError as exc:
            state.last_check = now_iso()
            state.last_error = str(exc)
            states[repo] = state
            save_states(states_file, states)
            errors.append(f"{repo}：{exc}")
            logger.warning(f"[gh-release] {repo} 拉取失败：{exc}")
            continue

        announcements = select_releases(
            fetched.releases,
            include_prerelease=cfg.gh_watch_include_prerelease,
            require_body=cfg.gh_watch_require_body,
        )
        state, pending = plan(state, announcements)
        state.last_check = now_iso()
        state.last_ok = now_iso()
        state.last_error = None
        state.last_source = fetched.source
        if announcements:
            state.latest = announcements[-1].tag
        states[repo] = state
        save_states(states_file, states)

        for release in pending[:limit]:
            message = await build_announce_message(release, repo, cfg)
            succeeded, send_errors = await push_to_groups(message, groups)
            errors.extend(send_errors)
            for error in send_errors:
                logger.warning(f"[gh-release] {error}")
            if succeeded:
                state.pushed = sorted(set(state.pushed) | {release.tag})
                states[repo] = state
                save_states(states_file, states)
                pushed.append(f"{repo} {release.tag}")
                logger.success(f"[gh-release] 已推送 {repo} {release.tag} 到 {len(succeeded)} 个群")
            else:
                failed.append(f"{repo} {release.tag}")

    if pushed:
        detail = "已推送 " + "、".join(pushed)
        if failed or errors:
            detail += f"（{len(failed)} 条失败、{len(errors)} 条错误）"
        status = "pushed"
    elif errors:
        status = "error"
        detail = "；".join(errors[:3])
    else:
        status = "no-update"
        detail = f"没有新 release（监控 {len(subscriptions)} 个仓库）"

    return CheckResult(
        status=status,
        detail=detail,
        repo_count=len(subscriptions),
        pushed=pushed,
        failed=failed,
        errors=errors,
    )
