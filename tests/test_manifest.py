import re

from constants import MANIFEST


def test_manifest_version_is_strict_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", MANIFEST["version"])
