"""本地自检：在最小 NoneBot 环境里加载插件，确认整体接线没问题。

用法（在仓库根目录执行）::

    pip install -e ".[test]" nonebot-adapter-onebot fastapi uvicorn
    python tools/loadcheck.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JOB_ID = "github_release_watch"


def main() -> int:
    try:
        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter
    except ImportError as exc:
        print(f"[!] 缺少依赖：{exc}")
        print('    请先执行：pip install -e ".[test]" nonebot-adapter-onebot fastapi uvicorn')
        return 2

    nonebot.init(driver="~fastapi")
    nonebot.get_driver().register_adapter(Adapter)
    nonebot.load_plugin("nonebot_plugin_apscheduler")
    plugin = nonebot.load_plugin("nonebot_plugin_github_release")
    if plugin is None:
        print("[✗] 插件加载失败，请看上面的异常信息")
        return 1

    metadata = plugin.metadata
    print(f"[✓] 插件已加载：{metadata.name if metadata else plugin.name}")
    print(f"    元数据：type={metadata.type}，适配器={sorted(metadata.supported_adapters or [])}")

    from nonebot_plugin_apscheduler import scheduler

    jobs = {job.id: job for job in scheduler.get_jobs()}
    if JOB_ID not in jobs:
        print(f"[✗] 定时任务 {JOB_ID} 未注册")
        return 1
    print(f"[✓] 定时任务已注册：{JOB_ID}，触发间隔 {jobs[JOB_ID].trigger}")

    from nonebot_plugin_github_release.config import load_config

    cfg = load_config()
    print(
        f"[✓] 配置读取正常：默认仓库 {len(cfg.gh_watch_repos)} 个，"
        f"含预发布={cfg.gh_watch_include_prerelease}，间隔={cfg.gh_watch_interval_minutes} 分钟"
    )

    commands = sorted(getattr(plugin, "matcher", set()), key=lambda m: str(m))
    print(f"[✓] 已注册 {len(commands)} 个指令匹配器")

    # 命令走最长前缀匹配，前缀撞车时短命令会把长命令吃掉，所以把实际命中的前缀打出来
    from nonebot.rule import TrieRule

    print("[✓] 命令前缀匹配：")
    for probe in [
        "/gh帮助",
        "gh",
        "/gh列表",
        "/gh订阅 owner/repo",
        "/gh退订 owner/repo",
        "/gh公告 owner/repo",
        "/gh状态",
        "/gh检查",
    ]:
        matched = TrieRule.prefix.longest_prefix(probe)
        print(f"    {probe:<22} -> {matched.key if matched else None}")

    from nonebot_plugin_github_release.store import resolve_data_dir

    data_dir = resolve_data_dir(cfg)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".loadcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        print(f"[✗] 数据目录不可写：{data_dir}（{exc}）")
        return 1
    print(f"[✓] 数据目录可写：{data_dir}")

    print("\n全部检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
