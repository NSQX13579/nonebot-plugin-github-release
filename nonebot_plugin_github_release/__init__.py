"""nonebot-plugin-github-release

监控任意 GitHub 仓库的 release，把新版本推送到 QQ 群。

- 数据源：Releases API 为主，被限流时自动切到不限流的 `releases.atom`
- 推送形式：默认发一张类 GitHub 卡片的图片，渲染失败自动回退纯文本
- 按群订阅：`/gh订阅 owner/repo`，每个群只收自己关心的仓库
"""

from datetime import datetime, timedelta

from nonebot import require

require("nonebot_plugin_apscheduler")

from nonebot.log import logger  # noqa: E402
from nonebot.plugin import PluginMetadata  # noqa: E402
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

from . import commands as _commands  # noqa: E402,F401
from .config import Config, load_config  # noqa: E402
from .watch import check_once  # noqa: E402

__all__ = ["Config", "check_once"]

__plugin_meta__ = PluginMetadata(
    name="GitHub 发布推送",
    description="监控 GitHub 仓库的 release，把新版本推送到 QQ 群",
    usage=(
        "/gh订阅 owner/repo 让本群订阅（群管）\n"
        "/gh公告 owner/repo 看最新 release\n"
        "/gh状态 看推送状态"
    ),
    type="application",
    homepage="https://github.com/NSQX13579/nonebot-plugin-github-release",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

_JOB_ID = "github_release_watch"

plugin_config: Config = load_config()


async def _scheduled_check() -> None:
    result = await check_once(plugin_config)
    logger.debug(f"[gh-release] 定时检查：{result.status} | {result.detail}")


scheduler.add_job(
    _scheduled_check,
    "interval",
    minutes=max(1, plugin_config.gh_watch_interval_minutes),
    # 启动 30 秒后先跑一轮，不用干等一个完整间隔
    next_run_time=datetime.now() + timedelta(seconds=30),
    id=_JOB_ID,
    replace_existing=True,
    coalesce=True,
    max_instances=1,
    misfire_grace_time=300,
)

if plugin_config.gh_watch_repos or plugin_config.gh_watch_groups:
    logger.info(
        f"[gh-release] 已启动：每 {plugin_config.gh_watch_interval_minutes} 分钟检查 "
        f"{len(plugin_config.gh_watch_repos)} 个仓库"
    )
else:
    logger.info("[gh-release] 尚未配置仓库，可在群里用 /gh订阅 owner/repo 添加")
