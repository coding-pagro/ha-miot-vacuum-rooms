"""Checks that keep the release setup (release-please) consistent."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_DIR = ROOT / "custom_components" / "miot_vacuum_rooms"
MANIFEST = INTEGRATION_DIR / "manifest.json"
MANIFEST_PATH = "custom_components/miot_vacuum_rooms/manifest.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_version_is_semver() -> None:
    version = _load(MANIFEST)["version"]
    assert SEMVER.match(version), version


def test_manifest_matches_release_please_manifest() -> None:
    released = _load(ROOT / ".release-please-manifest.json")
    assert set(released) == {"."}
    assert SEMVER.match(released["."]), released["."]
    assert released["."] == _load(MANIFEST)["version"]


def test_domain_matches_folder_name() -> None:
    assert _load(MANIFEST)["domain"] == INTEGRATION_DIR.name == "miot_vacuum_rooms"


def test_release_please_updates_manifest_version() -> None:
    package = _load(ROOT / "release-please-config.json")["packages"]["."]
    assert package["include-v-in-tag"] is True
    assert {
        "type": "json",
        "path": MANIFEST_PATH,
        "jsonpath": "$.version",
    } in package["extra-files"]
    assert (ROOT / MANIFEST_PATH).is_file()
