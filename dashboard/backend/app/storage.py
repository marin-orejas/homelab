from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from app.collectors.system import whole_disks
from app.config import settings

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

DEFAULT_BUCKETS = 180

_BASELINE = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS samples (
            ts                INTEGER PRIMARY KEY,
            cpu_percent       REAL,
            load1             REAL,
            mem_percent       REAL,
            mem_used          INTEGER,
            swap_percent      REAL,
            temp_max          REAL,
            fan_rpm           INTEGER,
            net_rx_bytes      INTEGER,
            net_tx_bytes      INTEGER,
            disk_read_bytes   INTEGER,
            disk_write_bytes  INTEGER,
            streams           INTEGER,
            transcodes        INTEGER,
            proc_total        INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS disk_samples (
            ts      INTEGER NOT NULL,
            label   TEXT    NOT NULL,
            percent REAL,
            used    INTEGER,
            total   INTEGER,
            PRIMARY KEY (ts, label)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS disk_daily (
            day     TEXT    NOT NULL,
            label   TEXT    NOT NULL,
            percent REAL,
            used    INTEGER,
            total   INTEGER,
            PRIMARY KEY (day, label)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_disk_samples_label_ts "
        "ON disk_samples (label, ts)",
    ),
    2: (
        """
        CREATE TABLE IF NOT EXISTS smart_daily (
            day        TEXT NOT NULL,
            label      TEXT NOT NULL,
            health     TEXT,
            start_stop INTEGER,
            load_cycle INTEGER,
            realloc    INTEGER,
            temp_c     REAL,
            PRIMARY KEY (day, label)
        )
        """,
    ),
}

_SAMPLE_COLUMNS = (
    "ts",
    "cpu_percent",
    "load1",
    "mem_percent",
    "mem_used",
    "swap_percent",
    "temp_max",
    "fan_rpm",
    "net_rx_bytes",
    "net_tx_bytes",
    "disk_read_bytes",
    "disk_write_bytes",
    "streams",
    "transcodes",
    "proc_total",
)


def database_path() -> Path:
    return Path(settings.history_db_path)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """A short-lived connection."""
    connection = sqlite3.connect(database_path(), timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _stored_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is not None:
        try:
            return int(row[0])
        except (TypeError, ValueError):
            pass

    existing = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='samples'"
    ).fetchone()
    return 1 if existing else 0


def initialise() -> None:
    """Create or migrate the database. Safe to call repeatedly."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.executescript(_BASELINE)

        version = _stored_version(connection)
        for step in range(version + 1, SCHEMA_VERSION + 1):
            for statement in _MIGRATIONS.get(step, ()):
                connection.execute(statement)
            log.info("History database migrated to schema version %d", step)

        connection.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        connection.commit()

    log.info("History database ready at %s (schema v%d)", path, SCHEMA_VERSION)


def _sum_network(system: dict[str, Any]) -> tuple[int, int]:
    """Total bytes across reported interfaces."""
    received = sum(nic.get("bytes_recv") or 0 for nic in system.get("network", []))
    sent = sum(nic.get("bytes_sent") or 0 for nic in system.get("network", []))
    return received, sent


def _sum_disk_io(system: dict[str, Any]) -> tuple[int, int]:
    """Total block-device I/O, partitions excluded."""
    entries = system.get("disk_io", [])
    keep = set(whole_disks([entry.get("device", "") for entry in entries]))
    read = write = 0
    for entry in entries:
        if entry.get("device", "") not in keep:
            continue
        read += entry.get("read_bytes") or 0
        write += entry.get("write_bytes") or 0
    return read, write


def _peak_temperature(system: dict[str, Any]) -> float | None:
    readings = [
        entry.get("current")
        for entry in system.get("sensors", {}).get("temperatures", [])
        if isinstance(entry.get("current"), (int, float))
    ]
    return max(readings) if readings else None


def _record_smart(connection: sqlite3.Connection, smart: dict[str, Any]) -> None:
    """Keep one row per disk per day, from the file the host wrote."""
    day = (smart.get("generated_at") or "")[:10]
    if len(day) != 10 or not smart.get("disks"):
        return

    connection.executemany(
        "INSERT INTO smart_daily "
        "(day, label, health, start_stop, load_cycle, realloc, temp_c) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(day, label) DO NOTHING",
        [
            (
                day,
                disk.get("label"),
                disk.get("health"),
                disk.get("start_stop"),
                disk.get("load_cycle"),
                disk.get("realloc"),
                disk.get("temp_c"),
            )
            for disk in smart["disks"]
            if disk.get("label")
        ],
    )


def record(payload: dict[str, Any]) -> None:
    """Store one sample. Never raises - a failed write must not stop polling."""
    try:
        system = payload["system"]
        sessions = payload.get("sessions") or {}
        if "error" in sessions:
            sessions = {}

        timestamp = int(system.get("timestamp") or time.time())
        received, sent = _sum_network(system)
        read, write = _sum_disk_io(system)
        fans = system.get("sensors", {}).get("fans", [])

        row = {
            "ts": timestamp,
            "cpu_percent": system.get("cpu", {}).get("percent"),
            "load1": system.get("cpu", {}).get("load_average", {}).get("1m"),
            "mem_percent": system.get("memory", {}).get("ram", {}).get("percent"),
            "mem_used": system.get("memory", {}).get("ram", {}).get("used"),
            "swap_percent": system.get("memory", {}).get("swap", {}).get("percent"),
            "temp_max": _peak_temperature(system),
            "fan_rpm": fans[0].get("rpm") if fans else None,
            "net_rx_bytes": received,
            "net_tx_bytes": sent,
            "disk_read_bytes": read,
            "disk_write_bytes": write,
            "streams": sessions.get("active_count"),
            "transcodes": sessions.get("transcoding_count"),
            "proc_total": system.get("processes", {}).get("total"),
        }

        disks = [
            (
                timestamp,
                disk.get("label"),
                disk.get("percent"),
                disk.get("used"),
                disk.get("total"),
            )
            for disk in system.get("disks", [])
            if disk.get("percent") is not None
        ]
        day = time.strftime("%Y-%m-%d", time.localtime(timestamp))

        columns = ", ".join(_SAMPLE_COLUMNS)
        placeholders = ", ".join(f":{name}" for name in _SAMPLE_COLUMNS)

        with _connect() as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO samples ({columns}) VALUES ({placeholders})",
                row,
            )
            connection.executemany(
                "INSERT OR REPLACE INTO disk_samples VALUES (?,?,?,?,?)", disks
            )
            connection.executemany(
                "INSERT INTO disk_daily (day, label, percent, used, total) "
                "VALUES (?,?,?,?,?) "
                "ON CONFLICT(day, label) DO UPDATE SET "
                "percent=excluded.percent, used=excluded.used, total=excluded.total",
                [
                    (day, label, percent, used, total)
                    for _, label, percent, used, total in disks
                ],
            )
            if isinstance(payload.get("smart"), dict):
                _record_smart(connection, payload["smart"])
            connection.commit()

    except Exception:  # pragma: no cover
        log.exception("Failed to record a history sample")


def prune() -> None:
    """Drop samples past the retention window."""
    try:
        cutoff = int(time.time()) - settings.history_retention_days * 86400
        with _connect() as connection:
            connection.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            connection.execute("DELETE FROM disk_samples WHERE ts < ?", (cutoff,))
            connection.commit()
    except Exception:  # pragma: no cover
        log.exception("Failed to prune history")


def forget_labels(labels: list[str]) -> int:
    """Delete every stored reading for the named mounts."""
    if not labels:
        return 0
    marks = ",".join("?" * len(labels))
    with _connect() as connection:
        removed = connection.execute(
            f"DELETE FROM disk_samples WHERE label IN ({marks})", labels
        ).rowcount
        removed += connection.execute(
            f"DELETE FROM disk_daily WHERE label IN ({marks})", labels
        ).rowcount
        connection.commit()
    return removed


_AGGREGATES = """
    AVG(cpu_percent)      AS cpu_percent,
    AVG(load1)            AS load1,
    AVG(mem_percent)      AS mem_percent,
    AVG(swap_percent)     AS swap_percent,
    MAX(temp_max)         AS temp_max,
    AVG(fan_rpm)          AS fan_rpm,
    MAX(net_rx_bytes)     AS net_rx_bytes,
    MAX(net_tx_bytes)     AS net_tx_bytes,
    MAX(disk_read_bytes)  AS disk_read_bytes,
    MAX(disk_write_bytes) AS disk_write_bytes,
    MAX(streams)          AS streams,
    MAX(transcodes)       AS transcodes,
    AVG(proc_total)       AS proc_total
"""

_COUNTERS = (
    ("net_rx_bytes", "net_rx_bps"),
    ("net_tx_bytes", "net_tx_bps"),
    ("disk_read_bytes", "disk_read_bps"),
    ("disk_write_bytes", "disk_write_bps"),
)


@dataclass(frozen=True)
class HistoryWindow:
    seconds: int
    buckets: int

    @property
    def bucket_seconds(self) -> int:
        return max(settings.history_interval_seconds, self.seconds // self.buckets)

    @property
    def max_points(self) -> int:
        """The most points this window can produce."""
        return self.seconds // self.bucket_seconds + 1


def history(window: HistoryWindow) -> dict[str, Any]:
    """Downsampled series over the requested window, with counters as rates."""
    bucket = window.bucket_seconds
    since = int(time.time()) - window.seconds

    with _connect() as connection:
        # The alias must not be called ts. SQLite would group by the table column instead.
        rows = connection.execute(
            f"""
            SELECT (ts / :bucket) * :bucket AS bucket_ts, {_AGGREGATES}
            FROM samples
            WHERE ts >= :since
            GROUP BY bucket_ts
            ORDER BY bucket_ts
            """,
            {"bucket": bucket, "since": since},
        ).fetchall()

        disk_rows = connection.execute(
            """
            SELECT label, (ts / :bucket) * :bucket AS bucket_ts,
                   AVG(percent) AS percent, AVG(used) AS used, MAX(total) AS total
            FROM disk_samples
            WHERE ts >= :since
            GROUP BY label, bucket_ts
            ORDER BY label, bucket_ts
            """,
            {"bucket": bucket, "since": since},
        ).fetchall()

    points = []
    for row in rows:
        point = dict(row)
        point["ts"] = point.pop("bucket_ts")
        points.append(point)
    _counters_to_rates(points)

    disks: dict[str, list[dict[str, Any]]] = {}
    for row in disk_rows:
        disks.setdefault(row["label"], []).append(
            {
                "ts": row["bucket_ts"],
                "percent": row["percent"],
                "used": row["used"],
                "total": row["total"],
            }
        )

    return {
        "from": since,
        "to": int(time.time()),
        "bucket_seconds": bucket,
        "point_count": len(points),
        "points": points,
        "disks": [
            {"label": label, "points": series} for label, series in disks.items()
        ],
    }


def _counters_to_rates(points: list[dict[str, Any]]) -> None:
    """Replace cumulative columns with per-second rates, in place."""
    previous: dict[str, Any] | None = None

    for point in points:
        for source, target in _COUNTERS:
            current = point.get(source)
            if previous is None or current is None or previous.get(source) is None:
                point[target] = None
            else:
                elapsed = point["ts"] - previous["ts"]
                delta = current - previous[source]
                point[target] = delta / elapsed if elapsed > 0 and delta >= 0 else None

        previous = dict(point)
        for source, _ in _COUNTERS:
            point.pop(source, None)


def _last_reset(points: list[dict[str, Any]]) -> int:
    """Where the disk's current contents started accumulating."""
    reset = 0
    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        total = current.get("total") or previous.get("total")
        floor = 0.05 * total if total else 0.05 * previous["used"]
        if previous["used"] - current["used"] > floor:
            reset = index
    return reset


def _projection(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Fill rate and time to full, from a least-squares fit over the days."""
    usable = [p for p in points if p.get("used") is not None]
    usable = usable[_last_reset(usable) :]
    if len(usable) < 3:
        return None

    def day_number(day: str) -> int:
        return int(
            time.mktime(time.strptime(day, "%Y-%m-%d")) // 86400
        )

    try:
        xs = [day_number(p["day"]) for p in usable]
    except (ValueError, TypeError):
        return None

    origin = xs[0]
    xs = [x - origin for x in xs]
    ys = [float(p["used"]) for p in usable]
    n = len(xs)

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    variance = sum((x - mean_x) ** 2 for x in xs)
    if variance == 0:
        return None

    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / variance

    latest = usable[-1]
    total = latest.get("total")
    free = (total - latest["used"]) if total is not None else None

    days_until_full = None
    if slope > 0 and free is not None and free > 0:
        days_until_full = round(free / slope, 1)

    return {
        "observed_days": xs[-1] - xs[0] + 1,
        "sample_days": n,
        "bytes_per_day": round(slope),
        "free_bytes": free,
        "days_until_full": days_until_full,
    }


def disk_trend(days: int) -> dict[str, Any]:
    """Daily fill levels, for answering "when does this run out"."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT day, label, percent, used, total
            FROM disk_daily
            WHERE day >= date('now', ?)
            ORDER BY label, day
            """,
            (f"-{days} days",),
        ).fetchall()

    series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        series.setdefault(row["label"], []).append(
            {
                "day": row["day"],
                "percent": row["percent"],
                "used": row["used"],
                "total": row["total"],
            }
        )

    return {
        "days": days,
        "disks": [
            {"label": label, "points": points, "projection": _projection(points)}
            for label, points in series.items()
        ],
    }


def smart_deltas() -> dict[str, dict[str, Any]]:
    """Change in the SMART counters since the previous stored day, per disk."""
    result: dict[str, dict[str, Any]] = {}
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT day, label, start_stop, load_cycle
                FROM smart_daily
                ORDER BY label, day DESC
                """
            ).fetchall()
    except sqlite3.Error:
        return result

    seen: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        entries = seen.setdefault(row["label"], [])
        if len(entries) < 2:
            entries.append(row)

    for label, entries in seen.items():
        if len(entries) < 2:
            continue
        latest, earlier = entries

        def delta(field: str) -> int | None:
            a, b = latest[field], earlier[field]
            if a is None or b is None or a < b:
                return None
            return a - b

        result[label] = {
            "start_stop_delta": delta("start_stop"),
            "load_cycle_delta": delta("load_cycle"),
            "delta_since_day": earlier["day"],
            "delta_until_day": latest["day"],
        }
    return result


def statistics() -> dict[str, Any]:
    """Row counts and file size, so the page can show what it is holding."""
    try:
        path = database_path()
        with _connect() as connection:
            samples = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
            oldest = connection.execute("SELECT MIN(ts) FROM samples").fetchone()[0]
        size = path.stat().st_size if path.exists() else 0
        return {
            "enabled": True,
            "samples": samples,
            "oldest_sample": oldest,
            "retention_days": settings.history_retention_days,
            "interval_seconds": settings.history_interval_seconds,
            "database_bytes": size,
            "schema_version": SCHEMA_VERSION,
        }
    except Exception:  # pragma: no cover
        log.exception("Failed to read history statistics")
        return {"enabled": True, "error": "unavailable"}
