"""规则层脚本的画像来源切换：占位画像不变、校准画像走 CLHLS 分布、结果文件名区分。

用法（examples/v2/elder_support 目录）：
  ../../../.venv/bin/python -m pytest tests/test_profile_source.py -q
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

EXP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP_DIR / "init"))

import gen_profiles as gp  # noqa: E402

FAKE_DIST = {
    "_meta": {"n_living_alone_65plus": 3},
    "age_band": {"95+": 1.0},
    "sex": {"1": 1.0},
    "self_rated_health_b12": {"5": 1.0},
    "loneliness_b38": {"1": 1.0},
    "alive_children_count": {"2": 1.0},
    "child_frequent_visits_f103x5": {"1": 1.0},
}


@pytest.fixture
def fake_dist(tmp_path, monkeypatch):
    path = tmp_path / "clhls2021_dist.json"
    path.write_text(json.dumps(FAKE_DIST), encoding="utf-8")
    monkeypatch.setattr(gp, "DIST_PATH", path)
    gp.load_dist.cache_clear()
    yield path
    gp.load_dist.cache_clear()


def test_placeholder_matches_gen_elder(monkeypatch):
    monkeypatch.delenv(gp.PROFILE_ENV, raising=False)
    a = gp.make_elders(random.Random(5), 10)
    rng = random.Random(5)
    b = [gp.gen_elder(rng, i + 1, focal=False) for i in range(10)]
    assert a == b


def test_calibrated_uses_distribution(fake_dist, monkeypatch):
    monkeypatch.setenv(gp.PROFILE_ENV, "calibrated")
    elders = gp.make_elders(random.Random(5), 8, n_focal=2)
    assert all(e["age"] >= 95 and e["gender"] == "男" for e in elders)
    assert all(len(e["children"]) == 2 for e in elders)
    assert [e["focal"] for e in elders] == [True, True] + [False] * 6


def test_calibrated_without_distribution_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "DIST_PATH", tmp_path / "missing.json")
    gp.load_dist.cache_clear()
    with pytest.raises(SystemExit):
        gp.make_elders(random.Random(1), 3, source="calibrated")
    gp.load_dist.cache_clear()


def test_result_path_suffix(monkeypatch):
    base = Path("tests/scan_timing_result.json")
    assert gp.result_path(base, "placeholder") == base
    assert gp.result_path(base, "calibrated").name == "scan_timing_result_calibrated.json"
    monkeypatch.setenv(gp.PROFILE_ENV, "calibrated")
    assert gp.result_path(Path("a/report.md")).name == "report_calibrated.md"


def test_invalid_source_rejected(monkeypatch):
    monkeypatch.setenv(gp.PROFILE_ENV, "random")
    with pytest.raises(SystemExit):
        gp.profile_source()
