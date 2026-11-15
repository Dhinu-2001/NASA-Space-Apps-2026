"""Size caps on the on-disk result caches (Stage 11 security review: unbounded caches are a disk-fill risk on a public host)."""

import os
import time
from pathlib import Path

from lunarnav import scenarios
from lunarnav.cachecap import touch, trim_oldest


def _make(d: Path, names: list[str], start: float = 1_000_000.0) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        p = d / n
        p.write_text("x", encoding="utf-8")
        os.utime(p, (start + i, start + i))          # increasing age order: first name is the oldest


def test_trim_removes_the_least_recently_used_and_keeps_the_newest(tmp_path):
    _make(tmp_path, [f"{i}.json" for i in range(6)])
    assert trim_oldest(tmp_path, "*.json", 4) == 2
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["2.json", "3.json", "4.json", "5.json"]
    assert trim_oldest(tmp_path, "*.json", 4) == 0                       # idempotent below the cap


def test_touch_makes_an_old_entry_survive(tmp_path):
    _make(tmp_path, ["old.json", "a.json", "b.json", "c.json"])
    touch(tmp_path / "old.json")                                          # a cache hit refreshes it
    trim_oldest(tmp_path, "*.json", 3)
    assert (tmp_path / "old.json").exists() and not (tmp_path / "a.json").exists()


def test_in_progress_temp_files_and_other_patterns_are_never_touched(tmp_path):
    _make(tmp_path, ["1.json", "2.json", "3.tmp", "keep.txt"])
    trim_oldest(tmp_path, "*.json", 1)
    assert (tmp_path / "3.tmp").exists() and (tmp_path / "keep.txt").exists()
    assert [p.name for p in tmp_path.glob("*.json")] == ["2.json"]


def test_a_missing_directory_is_not_an_error(tmp_path):
    assert trim_oldest(tmp_path / "nope", "*.json", 1) == 0


def test_the_scenario_store_enforces_its_cap_and_refreshes_entries_it_serves(tmp_path, monkeypatch):
    monkeypatch.setattr(scenarios, "MAX_CACHED_SCENARIOS", 3)
    store = scenarios.ScenarioStore(tmp_path)
    ids = [f"{i:064x}" for i in range(5)]
    for n, sid in enumerate(ids):
        store.save(sid, {"id": sid, "model_version": scenarios.MODEL_VERSION})
        os.utime(store.dir / f"{sid}.json", (1_000_000 + n, 1_000_000 + n))
    assert len(list(store.dir.glob("*.json"))) <= 4
    # serve the oldest survivor, add a new one: the served (recently used) entry must outlive an untouched one
    survivors = sorted(store.dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    oldest = survivors[0].stem
    assert store.load(oldest) is not None
    time.sleep(0.01)
    newest = f"{9:064x}"
    store.save(newest, {"id": newest, "model_version": scenarios.MODEL_VERSION})
    left = {p.stem for p in store.dir.glob("*.json")}
    assert oldest in left and newest in left and len(left) <= 3
