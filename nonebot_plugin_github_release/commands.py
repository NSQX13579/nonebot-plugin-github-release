"""群内指令。

命名约定：`gh` + 一个名词。命令名一律按字面注册（不用 `CommandGroup`，
它会把子命令拼成带分隔符的元组，导致文档里写的命令根本触发不了）。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from nonebot import get_driver, on_command
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg

from .config import load_config
from .latest import fetch_announcements, render_list
from .render import format_iso_local, render_release
from .source import ReleaseFetchError
from .store import (
    load_states,
    load_subscriptions,
    resolve_data_dir,
    save_subscriptions,
    state_path,
    subscriptions_path,
)
from .watch import build_announce_message, check_once, effective_subscriptions

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _is_superuser(event: Event) -> bool:
    return event.get_user_id() in get_driver().config.superusers


async def _is_group_admin(bot: Bot, event: Event) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        info = await bot.get_group_member_info(
            group_id=event.group_id, user_id=event.user_id
        )
    except Exception as exc:  # noqa: BLE001 - 拿不到成员信息时按无权限处理
        logger.debug(f"[gh-release] 查询群成员信息失败：{exc}")
        return False
    return str(info.get("role", "")) in ("owner", "admin")


def _parse_repo(text: str) -> Optional[str]:
    """从参数里取 owner/repo。"""
    candidate = text.strip().strip("/")
    if candidate.startswith("https://github.com/"):
        candidate = candidate[len("https://github.com/") :]
    candidate = candidate.split("/releases")[0].strip("/")
    return candidate if _REPO_RE.match(candidate) else None


def _group_subscriptions(cfg, event: Event) -> Set[str]:
    if not isinstance(event, GroupMessageEvent):
        return set()
    subs = effective_subscriptions(cfg, load_subscriptions(subscriptions_path(resolve_data_dir(cfg))))
    return {repo for repo, groups in subs.items() if event.group_id in groups}


help_cmd = on_command("gh帮助", aliases={"gh指令"}, priority=5, block=True)
list_cmd = on_command("gh列表", priority=5, block=True)
subscribe_cmd = on_command("gh订阅", priority=5, block=True)
unsubscribe_cmd = on_command("gh退订", priority=5, block=True)
announce_cmd = on_command("gh公告", priority=5, block=True)
status_cmd = on_command("gh状态", priority=5, block=True)
check_cmd = on_command("gh检查", priority=5, block=True)


@help_cmd.handle()
async def _handle_help() -> None:
    cfg = load_config()
    await help_cmd.finish(
        "\n".join(
            [
                "【GitHub 发布推送】",
                f"轮询间隔：{cfg.gh_watch_interval_minutes} 分钟",
                f"推送范围：{'含 alpha / rc' if cfg.gh_watch_include_prerelease else '仅正式版'}",
                "",
                "指令：",
                "/gh订阅 owner/repo    本群订阅某个仓库（群管）",
                "/gh退订 owner/repo    取消订阅（群管）",
                "/gh列表               看本群订阅了哪些",
                "/gh公告 owner/repo    看最新一条 release 全文",
                "/gh公告 owner/repo 5  列最近 5 条",
                "/gh状态               推送状态",
                "/gh检查               立刻检查一次（超管）",
            ]
        )
    )


@list_cmd.handle()
async def _handle_list(event: MessageEvent) -> None:
    cfg = load_config()
    if not isinstance(event, GroupMessageEvent):
        await list_cmd.finish("这个命令只能在群里用")
    repos = _group_subscriptions(cfg, event)
    if not repos:
        await list_cmd.finish("本群还没有订阅任何仓库，用 /gh订阅 owner/repo 添加")
    await list_cmd.finish("本群订阅的仓库：\n" + "\n".join(f"· {repo}" for repo in sorted(repos)))


@subscribe_cmd.handle()
async def _handle_subscribe(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    if not isinstance(event, GroupMessageEvent):
        await subscribe_cmd.finish("这个命令只能在群里用")
    if not (_is_superuser(event) or await _is_group_admin(bot, event)):
        await subscribe_cmd.finish("只有群管理员或机器人超管可以改订阅")

    repo = _parse_repo(args.extract_plain_text())
    if repo is None:
        await subscribe_cmd.finish("用法：/gh订阅 owner/repo（例如 /gh订阅 deepseek-ai/deepseek-harness）")

    cfg = load_config()
    path = subscriptions_path(resolve_data_dir(cfg))
    subs: Dict[str, Set[int]] = load_subscriptions(path)
    groups = subs.setdefault(repo, set())
    if event.group_id in groups:
        await subscribe_cmd.finish(f"本群已经订阅 {repo} 了")
    groups.add(event.group_id)
    save_subscriptions(path, subs)
    await subscribe_cmd.finish(f"已订阅 {repo}，下一条 release 会自动推送")


@unsubscribe_cmd.handle()
async def _handle_unsubscribe(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    if not isinstance(event, GroupMessageEvent):
        await unsubscribe_cmd.finish("这个命令只能在群里用")
    if not (_is_superuser(event) or await _is_group_admin(bot, event)):
        await unsubscribe_cmd.finish("只有群管理员或机器人超管可以改订阅")

    cfg = load_config()
    repos = sorted(_group_subscriptions(cfg, event))
    repo = _parse_repo(args.extract_plain_text())
    if repo is None:
        if len(repos) == 1:
            repo = repos[0]
        else:
            await unsubscribe_cmd.finish(
                "用法：/gh退订 owner/repo\n本群当前订阅：" + ("、".join(repos) or "（无）")
            )

    path = subscriptions_path(resolve_data_dir(cfg))
    subs = load_subscriptions(path)
    if event.group_id not in subs.get(repo, set()):
        await unsubscribe_cmd.finish(f"本群没有订阅 {repo}")
    subs[repo].discard(event.group_id)
    save_subscriptions(path, subs)
    await unsubscribe_cmd.finish(f"已退订 {repo}")


@announce_cmd.handle()
async def _handle_announce(event: MessageEvent, args: Message = CommandArg()) -> None:
    """查看某个仓库的 release：默认最新一条，数字列简表，其他按版本号检索。"""
    cfg = load_config()
    parts = args.extract_plain_text().strip().split()

    repo: Optional[str] = None
    keyword = ""
    if parts:
        repo = _parse_repo(parts[0])
        if repo is not None:
            keyword = " ".join(parts[1:]).strip()
    if repo is None:
        candidates = sorted(_group_subscriptions(cfg, event))
        if not parts and len(candidates) == 1:
            repo = candidates[0]
        else:
            await announce_cmd.finish(
                "用法：/gh公告 owner/repo [数量|版本号]\n本群订阅：" + ("、".join(candidates) or "（无）")
            )

    try:
        releases, _source = await fetch_announcements(cfg, repo)
    except ReleaseFetchError as exc:
        await announce_cmd.finish(f"拉取 {repo} 失败：{exc}")

    if not releases:
        await announce_cmd.finish(f"{repo} 暂时没有可展示的 release")

    if keyword.isdigit():
        count = max(1, min(int(keyword), 10))
        await announce_cmd.finish(
            render_list(
                list(reversed(releases[-count:])),
                repo=repo,
                tz_name=cfg.gh_watch_timezone,
            )
        )

    if keyword:
        needle = keyword.lower()
        matched = [
            release
            for release in releases
            if needle in release.tag.lower() or needle in release.name.lower()
        ]
        if not matched:
            await announce_cmd.finish(f"{repo} 没有包含「{keyword}」的 release")
        release = matched[0]
    else:
        release = releases[-1]

    if cfg.gh_watch_send_image:
        await announce_cmd.finish(await build_announce_message(release, repo, cfg))
    await announce_cmd.finish(
        render_release(
            release,
            repo=repo,
            tz_name=cfg.gh_watch_timezone,
            max_chars=cfg.gh_watch_query_max_chars,
            strip_mentions=cfg.gh_watch_strip_mentions,
            cut_foreign=cfg.gh_watch_body_language != "all",
        )
    )


@status_cmd.handle()
async def _handle_status() -> None:
    cfg = load_config()
    data_dir = resolve_data_dir(cfg)
    states = load_states(state_path(data_dir))
    subs = effective_subscriptions(cfg, load_subscriptions(subscriptions_path(data_dir)))

    lines = ["【GitHub 发布推送 状态】", f"订阅仓库：{len(subs)} 个"]
    if not subs:
        lines.append("（还没有订阅，用 /gh订阅 owner/repo 添加）")
    for repo, groups in sorted(subs.items()):
        state = states.get(repo)
        latest = state.latest if state else None
        source = state.last_source if state else None
        error = state.last_error if state else None
        checked = state.last_check if state else None
        lines.append(
            f"· {repo}｜群 {len(groups)} 个｜最新 {latest or '-'}"
            f"｜源 {source or '-'}｜检查 {format_iso_local(checked, cfg.gh_watch_timezone)}"
        )
        if error:
            lines.append(f"  最近错误：{error}")
    lines.append("")
    lines.append(f"轮询间隔：{cfg.gh_watch_interval_minutes} 分钟｜全部指令：/gh帮助")
    await status_cmd.finish("\n".join(lines))


@check_cmd.handle()
async def _handle_check(event: MessageEvent) -> None:
    if not _is_superuser(event):
        await check_cmd.finish("这个命令只有机器人超管能用；看公告用 /gh公告")
    result = await check_once()
    await check_cmd.finish(f"[gh-release] {result.status}：{result.detail}")
