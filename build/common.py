"""Shared loaders and helpers for ark_social build pipeline."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths (override with ARK_STORY / ARK_GAMEDATA env vars if layout differs)
# ---------------------------------------------------------------------------
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARK_STORY = Path(os.environ.get("ARK_STORY", "/home/ubuntu/git/ark_story"))
ARK_GAMEDATA = Path(os.environ.get("ARK_GAMEDATA", "/home/ubuntu/git/ArknightsGameData"))

OVERVIEW = ARK_STORY / "output" / "剧情一览"
EXCEL = ARK_GAMEDATA / "zh_CN" / "gamedata" / "excel"

BUILD_DATA = PROJECT_ROOT / "build" / "data"
WEB_DATA = PROJECT_ROOT / "web" / "public" / "data"

BUILD_DATA.mkdir(parents=True, exist_ok=True)
WEB_DATA.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Story-unit (chapter) ordering for the timeline
# ---------------------------------------------------------------------------
CATEGORY_ORDER = {
    "主线": 0,
    "支线": 1,
    "故事集": 2,
    "干员密录": 3,
    "特殊": 4,
    "干员档案": 5,
}

SPEAKER_RE = re.compile(r'^"([^"]*)"\s*:\s*(.*)$')

# Categories whose files are flat (no chapter subdirectory)
FLAT_CATEGORIES = {"干员密录", "干员档案"}


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def chapter_sort_key(name: str):
    """Numeric-aware sort for chapter folder names like '00.黑暗时代·上'."""
    m = re.match(r"^(\d+)", name)
    return (int(m.group(1)) if m else 9999, name)


def iter_story_files():
    """Yield (path, rel_posix, category, chapter_name) for every story txt.

    Mirrors investigation/talulah/scan.py: 合集版 excluded (derived duplicate).
    """
    for p in sorted(OVERVIEW.rglob("*.txt")):
        rel = p.relative_to(OVERVIEW)
        parts = rel.parts
        category = parts[0] if parts else ""
        if category in FLAT_CATEGORIES:
            chapter = ""
        else:
            chapter = parts[1] if len(parts) > 2 else ""
        yield p, rel.as_posix(), category, chapter


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return []
