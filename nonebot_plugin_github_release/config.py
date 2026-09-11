"""插件配置，全部可用 `.env` 里的 `GH_WATCH_*` 覆盖。"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class Config(BaseModel):
    """配置项。"""

    model_config = ConfigDict(extra="ignore")

    # 默认监控并推送的仓库（owner/repo）。群里也能用 /gh订阅 动态加
    gh_watch_repos: List[str] = Field(default_factory=list)

    # 默认接收推送的群。与上面的仓库做组合：每个群都订阅每个仓库
    gh_watch_groups: List[int] = Field(default_factory=list)

    # 轮询间隔（分钟）
    gh_watch_interval_minutes: int = 10

    # 展示时间使用的时区
    gh_watch_timezone: str = "Asia/Shanghai"

    # 是否连 alpha / beta / rc 一起推
    gh_watch_include_prerelease: bool = True

    # 没有正文的 release 不算公告，不推
    gh_watch_require_body: bool = True

    # GitHub Token（可选，提高 API 限额）
    gh_watch_github_token: str = ""

    # 代理（可选，留空则沿用环境变量）
    gh_watch_proxy: str = ""

    # 文本推送的正文上限
    gh_watch_max_chars: int = 600

    # /gh公告 查询时的正文上限
    gh_watch_query_max_chars: int = 1200

    # 每个仓库每轮最多推几条
    gh_watch_max_per_round: int = 3

    # 正文里的 @贡献者 是否去掉（只影响文本推送，卡片里保留）
    gh_watch_strip_mentions: bool = True

    # 中英双语公告只保留中文段（值改成 all 则两段都保留）
    gh_watch_body_language: str = "zh"

    # 是否发送渲染好的卡片图片（需要 nonebot-plugin-htmlrender + chromium）
    gh_watch_send_image: bool = True

    gh_watch_card_width: int = 900
    gh_watch_card_max_height: int = 1500
    gh_watch_card_max_chars: int = 2400
    gh_watch_card_show_reactions: bool = True

    # 数据目录，默认交给 nonebot-plugin-localstore 管
    gh_watch_data_dir: str = ""


def load_config() -> Config:
    """从 NoneBot 全局配置读取插件配置。"""
    import nonebot

    return nonebot.get_plugin_config(Config)
