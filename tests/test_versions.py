"""版本判定测试。"""

import pytest

from gh_core.versions import is_stable_release, parse_version


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("v1.2.3", True),
        ("1.2.3", True),
        ("app-v1.2.3", True),
        ("v1.2.3-rc.1", False),
        ("v1.2.3-beta", False),
        ("v1.2.3-alpha.10", False),
        ("nightly", False),
        ("", False),
    ],
)
def test_is_stable_release(tag, expected):
    assert is_stable_release(tag) is expected


def test_prerelease_flag_wins():
    assert is_stable_release("v1.2.3", prerelease_flag=True) is False


def test_parse_version_fields():
    version = parse_version("app-v0.1.5-rc.1")
    assert version is not None
    assert (version.major, version.minor, version.patch) == (0, 1, 5)
    assert version.prerelease == "rc.1"
    assert version.core == "0.1.5"


def test_parse_version_rejects_non_version():
    assert parse_version("release-notes") is None
