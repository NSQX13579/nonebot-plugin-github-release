"""让测试直接导入插件内部模块。

插件的 ``__init__.py`` 在导入时会向 NoneBot 注册定时任务和命令，
测试环境没有 NoneBot 运行时，所以这里用指向同一目录的「影子包」导入内部模块。
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "nonebot_plugin_github_release"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "gh_core" not in sys.modules:
    shadow = types.ModuleType("gh_core")
    shadow.__path__ = [str(PACKAGE_DIR)]  # type: ignore[attr-defined]
    sys.modules["gh_core"] = shadow
