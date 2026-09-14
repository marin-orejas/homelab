from __future__ import annotations

import sqlite3
import time

import pytest

from app import storage
from app.collectors.system import whole_disks
from app.config import settings


def _sample(ts: int, **overrides):
    system = {
        "timestamp": ts,
        "cpu": {"percent": 10.0, "load_average": {"1m": 0.5}},
        "memory": {"ram": {"percent": 20.0, "used": 100}, "swap": {"percent": 0.0}},
        "sensors": {"temperatures": [{"current": 40.0}], "fans": [{"rpm": 1000}]},
        "network": [{"bytes_recv": ts * 1000, "bytes_sent": ts * 10}],
        "disk_io": [{"device": "sda", "read_bytes": ts * 100, "write_bytes": ts * 5}],
        "disks": [
            {"label": "root", "percent": 40.0, "used": 400, "total": 1000},
        ],
        "processes": {"total": 200},
    }
    system.update(overrides)
    return {"system": system, "sessions": {"active_count": 0, "transcoding_count": 0}}


def test_history_respects_the_bucket_count(db_path):
    """A window must come back downsampled, not one point per sample."""
    storage.initialise()

    now = int(time.time())
    for index in range(2000):
        storage.record(_sample(now - 2000 * 30 + index * 30))

    window = storage.HistoryWindow(seconds=30 * 2000, buckets=180)
    result = storage.history(window)

    assert result["point_count"] <= window.max_points <= 181
    assert len(result["points"]) == result["point_count"]
    assert result["bucket_seconds"] > settings.history_interval_seconds
    for disk in result["disks"]:
        assert len(disk["points"]) <= window.max_points


def test_history_buckets_are_aligned_and_ordered(db_path):
    storage.initialise()
    now = int(time.time())
    for index in range(400):
        storage.record(_sample(now - 400 * 30 + index * 30))

    result = storage.history(storage.HistoryWindow(seconds=12000, buckets=20))
    stamps = [p["ts"] for p in result["points"]]

    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)
    assert all(ts % result["bucket_seconds"] == 0 for ts in stamps)


def test_counters_come_back_as_rates_and_the_first_point_is_null(db_path):
    storage.initialise()
    now = int(time.time())
    for index in range(10):
        storage.record(_sample(now - 300 + index * 30))

    points = storage.history(storage.HistoryWindow(seconds=600, buckets=180))["points"]

    assert points[0]["net_rx_bps"] is None
    assert all("net_rx_bytes" not in p for p in points), "counters must not leak"
    assert points[-1]["net_rx_bps"] == pytest.approx(1000 / 1, rel=0.2)


def _build_v1(path):
    """A database exactly as version 1 left it, with a row in it."""
    connection = sqlite3.connect(path)
    connection.executescript(storage._BASELINE)
    for statement in storage._MIGRATIONS[1]:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', '1')"
    )
    connection.execute("INSERT INTO samples (ts, cpu_percent) VALUES (1, 5.0)")
    connection.commit()
    connection.close()


def test_migration_reaches_an_existing_database(db_path):
    _build_v1(db_path)

    storage.initialise()

    connection = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    version = connection.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    kept = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    connection.close()

    assert "smart_daily" in tables
    assert int(version) == storage.SCHEMA_VERSION
    assert kept == 1, "existing samples must survive the migration"


def test_a_fresh_database_runs_the_same_ladder(db_path):
    """A new file must not take a separate code path, or the ladder rots."""
    storage.initialise()

    connection = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    version = connection.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    connection.close()

    assert {"meta", "samples", "disk_samples", "disk_daily", "smart_daily"} <= tables
    assert int(version) == storage.SCHEMA_VERSION


def test_initialise_is_repeatable(db_path):
    storage.initialise()
    storage.initialise()
    storage.record(_sample(int(time.time())))
    assert storage.statistics()["samples"] == 1


def test_recording_survives_a_new_column(db_path):
    """The named-column INSERT must not depend on column order."""
    storage.initialise()
    connection = sqlite3.connect(db_path)
    connection.execute("ALTER TABLE samples ADD COLUMN future_metric REAL")
    connection.commit()
    connection.close()

    storage.record(_sample(int(time.time())))
    assert storage.statistics()["samples"] == 1


def test_forget_labels_removes_only_what_is_named(db_path):
    storage.initialise()
    now = int(time.time())
    storage.record(
        _sample(
            now,
            disks=[
                {"label": "root", "percent": 40.0, "used": 400, "total": 1000},
                {"label": "pool", "percent": 50.0, "used": 500, "total": 1000},
            ],
        )
    )

    removed = storage.forget_labels(["pool"])

    labels = {d["label"] for d in storage.disk_trend(30)["disks"]}
    assert removed == 2, "one disk_samples row and one disk_daily row"
    assert labels == {"root"}


def test_partitions_do_not_double_count():
    assert whole_disks(["nvme0n1", "nvme0n1p1", "nvme0n1p2", "sda"]) == [
        "nvme0n1",
        "sda",
    ]
    assert whole_disks(["sda", "sdb"]) == ["sda", "sdb"]


def test_projection_reports_a_fill_rate_and_a_deadline():
    points = [
        {"day": f"2026-09-0{n}", "used": 100 + n * 10, "total": 200, "percent": 0.0}
        for n in range(1, 6)
    ]
    projection = storage._projection(points)

    assert projection["bytes_per_day"] == 10
    assert projection["free_bytes"] == 50
    assert projection["days_until_full"] == pytest.approx(5.0)


def test_projection_stays_quiet_when_it_has_nothing_to_say():
    flat = [
        {"day": f"2026-09-0{n}", "used": 100, "total": 200, "percent": 0.0}
        for n in range(1, 6)
    ]
    shrinking = [
        {"day": f"2026-09-0{n}", "used": 200 - n * 10, "total": 400, "percent": 0.0}
        for n in range(1, 6)
    ]
    too_few = [{"day": "2026-09-01", "used": 1, "total": 2, "percent": 0.0}]

    assert storage._projection(flat)["days_until_full"] is None
    assert storage._projection(shrinking)["days_until_full"] is None
    assert storage._projection(too_few) is None


def _smart(day, start_stop, load_cycle):
    return {
        "generated_at": f"{day}T03:00:10+02:00",
        "disks": [
            {
                "label": "wd1tb",
                "health": "PASSED",
                "start_stop": start_stop,
                "load_cycle": load_cycle,
                "realloc": 0,
                "temp_c": 31,
            }
        ],
    }


def test_smart_deltas_compare_the_last_two_days(db_path):
    storage.initialise()
    now = int(time.time())
    for index, (day, ss, lc) in enumerate(
        [("2026-09-05", 6560, 24400), ("2026-09-06", 6572, 24430), ("2026-09-07", 6589, 24457)]
    ):
        payload = _sample(now + index)
        payload["smart"] = _smart(day, ss, lc)
        storage.record(payload)

    delta = storage.smart_deltas()["wd1tb"]

    assert delta["start_stop_delta"] == 17
    assert delta["load_cycle_delta"] == 27
    assert delta["delta_since_day"] == "2026-09-06"
    assert delta["delta_until_day"] == "2026-09-07"


def test_smart_delta_needs_two_days(db_path):
    storage.initialise()
    payload = _sample(int(time.time()))
    payload["smart"] = _smart("2026-09-07", 6589, 24457)
    storage.record(payload)

    assert storage.smart_deltas() == {}


def test_the_first_smart_reading_of_a_day_wins(db_path):
    storage.initialise()
    now = int(time.time())
    for index, value in enumerate([6589, 9999]):
        payload = _sample(now + index)
        payload["smart"] = _smart("2026-09-07", value, 24457)
        storage.record(payload)

    connection = sqlite3.connect(db_path)
    stored = connection.execute("SELECT start_stop FROM smart_daily").fetchall()
    connection.close()

    assert stored == [(6589,)]


def test_projection_starts_over_after_the_disk_is_emptied():
    """A wipe is a new beginning, not a downward trend."""
    before = [
        {"day": f"2026-08-2{n}", "used": 500, "total": 1000, "percent": 50.0}
        for n in range(4, 10)
    ]
    after = [
        {"day": f"2026-09-0{n}", "used": (n - 1) * 40, "total": 1000, "percent": 0.0}
        for n in range(1, 8)
    ]
    projection = storage._projection(before + after)

    assert projection["bytes_per_day"] == 40
    assert projection["sample_days"] == len(after)
    assert projection["days_until_full"] == pytest.approx(19.0, abs=0.1)


def test_projection_ignores_a_deletion_too_small_to_be_a_reset():
    """Deleting one series is not starting again."""
    points = [
        {"day": f"2026-09-0{n}", "used": used, "total": 1000, "percent": 0.0}
        for n, used in enumerate([100, 200, 300, 280, 380, 480], start=1)
    ]
    projection = storage._projection(points)

    assert projection["sample_days"] == 6
    assert projection["bytes_per_day"] > 0
