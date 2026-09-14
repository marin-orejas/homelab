from __future__ import annotations

import os
import platform
import threading
import time
from dataclasses import dataclass
from typing import Any

import psutil

from app.config import settings

# psutil has no environment variable for this. The module attribute is the only switch.
if os.path.isdir(settings.procfs_path):
    psutil.PROCFS_PATH = settings.procfs_path
else:  # pragma: no cover
    psutil.PROCFS_PATH = "/proc"

PROCFS_IS_HOST = psutil.PROCFS_PATH != "/proc"

_IGNORED_DEVICE_PREFIXES = ("loop", "ram", "dm-", "sr", "zram")

_IGNORED_NIC_PREFIXES = ("veth", "docker", "br-", "virbr", "tun", "tap", "dummy")

_IMPOSSIBLE_TEMPERATURE_C = 1000.0

_INTERPRETERS = frozenset(
    {
        "python", "python2", "python3", "pypy", "pypy3",
        "sh", "bash", "dash", "zsh", "ash",
        "node", "nodejs", "deno", "bun",
        "dotnet", "mono", "java", "ruby", "perl", "php",
    }
)

_SCRIPT_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".sh", ".rb", ".pl", ".dll")


def _safe(fn, default=None):
    """Run a collector, swallowing anything it throws."""
    try:
        return fn()
    except Exception:
        return default


def _total_time(times: Any) -> float:
    total = sum(times)
    total -= getattr(times, "guest", 0.0)
    total -= getattr(times, "guest_nice", 0.0)
    return total


def _busy_time(times: Any) -> float:
    return _total_time(times) - times.idle - getattr(times, "iowait", 0.0)


def _percent_between(previous: Any, current: Any) -> float | None:
    """Busy percentage over the interval between two cpu_times readings."""
    if previous is None or current is None:
        return None
    elapsed = _total_time(current) - _total_time(previous)
    if elapsed <= 0:
        return None
    busy = _busy_time(current) - _busy_time(previous)
    return round(max(0.0, min(100.0, busy / elapsed * 100)), 1)


def _breakdown_between(previous: Any, current: Any) -> dict[str, float | None] | None:
    """Per-state percentages over the interval between two cpu_times readings."""
    if previous is None or current is None:
        return None
    elapsed = _total_time(current) - _total_time(previous)
    if elapsed <= 0:
        return None

    def share(field: str) -> float | None:
        if not hasattr(current, field):
            return None
        delta = getattr(current, field) - getattr(previous, field, 0.0)
        return round(max(0.0, min(100.0, delta / elapsed * 100)), 1)

    return {
        "user": share("user"),
        "system": share("system"),
        "idle": share("idle"),
        "iowait": share("iowait"),
        "steal": share("steal"),
    }


def collect_cpu(
    previous_times: Any = None,
    previous_percpu: list[Any] | None = None,
    interval_seconds: float | None = None,
) -> dict[str, Any]:
    """CPU usage measured against an explicitly supplied previous reading."""
    times = _safe(psutil.cpu_times)
    percpu = _safe(lambda: psutil.cpu_times(percpu=True), []) or []
    freq = _safe(psutil.cpu_freq)
    load1, load5, load15 = _safe(psutil.getloadavg, (None, None, None))
    logical = psutil.cpu_count(logical=True) or 1

    per_core: list[float | None] = []
    if previous_percpu and len(previous_percpu) == len(percpu):
        per_core = [_percent_between(p, c) for p, c in zip(previous_percpu, percpu)]

    return {
        "percent": _percent_between(previous_times, times),
        "percent_per_core": per_core,
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": logical,
        "interval_seconds": (
            round(interval_seconds, 2) if interval_seconds is not None else None
        ),
        "frequency_mhz": (
            {"current": freq.current, "min": freq.min, "max": freq.max}
            if freq
            else None
        ),
        "load_average": {"1m": load1, "5m": load5, "15m": load15},
        "load_average_percent": (
            round(load1 / logical * 100, 1) if load1 is not None else None
        ),
        "times_percent": _breakdown_between(previous_times, times),
        "_times": times,
        "_times_percpu": percpu,
    }


def collect_host() -> dict[str, Any]:
    boot_time = psutil.boot_time()
    uname = platform.uname()
    hostname = settings.hostname or uname.node

    return {
        "hostname": hostname,
        "kernel": uname.release,
        "architecture": uname.machine,
        "boot_time": boot_time,
        "uptime_seconds": round(time.time() - boot_time),
        "python_version": platform.python_version(),
        "procfs_path": psutil.PROCFS_PATH,
        "reading_host_procfs": PROCFS_IS_HOST,
    }


def collect_memory() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "ram": {
            "total": vm.total,
            "available": vm.available,
            "used": vm.used,
            "free": vm.free,
            "percent": vm.percent,
            "cached": getattr(vm, "cached", None),
            "buffers": getattr(vm, "buffers", None),
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": swap.percent,
        },
    }


def collect_disk_usage() -> list[dict[str, Any]]:
    """Usage per configured mount point."""
    results: list[dict[str, Any]] = []
    for label, path in settings.parsed_disk_mounts().items():
        entry: dict[str, Any] = {"label": label, "path": path}
        try:
            usage = psutil.disk_usage(path)
            entry.update(
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
                error=None,
            )
        except Exception as exc:
            entry.update(
                total=None, used=None, free=None, percent=None, error=str(exc)
            )
        results.append(entry)
    return results


def whole_disks(devices: list[str]) -> list[str]:
    """The subset of `devices` that is not a partition of another entry."""
    return [
        device
        for device in devices
        if not any(
            other != device and device.startswith(other) for other in devices
        )
    ]


def collect_disk_io() -> list[dict[str, Any]]:
    """Cumulative I/O counters per physical block device (since boot)."""
    counters = _safe(lambda: psutil.disk_io_counters(perdisk=True), {}) or {}
    wanted = settings.parsed_io_devices()

    if wanted:
        selected = {d: c for d, c in counters.items() if d in wanted}
    else:
        selected = {
            d: c
            for d, c in counters.items()
            if not d.startswith(_IGNORED_DEVICE_PREFIXES)
        }
        keep = set(whole_disks(list(selected)))
        selected = {d: c for d, c in selected.items() if d in keep}

    results = [
        {
            "device": device,
            "read_bytes": c.read_bytes,
            "write_bytes": c.write_bytes,
            "read_count": c.read_count,
            "write_count": c.write_count,
            "read_time_ms": c.read_time,
            "write_time_ms": c.write_time,
            "busy_time_ms": getattr(c, "busy_time", None),
        }
        for device, c in selected.items()
    ]
    return sorted(results, key=lambda d: d["device"])


def _host_net_dev_path() -> str:
    """Path to a net/dev that reflects the *host* network namespace."""
    return os.path.join(psutil.PROCFS_PATH, "1", "net", "dev")


def _parse_net_dev(text: str) -> dict[str, dict[str, int]]:
    """Parse /proc/net/dev into {interface: counters}."""
    result: dict[str, dict[str, int]] = {}

    for line in text.splitlines()[2:]:
        name, separator, rest = line.partition(":")
        name = name.strip()
        if not separator or not name:
            continue

        fields = rest.split()
        if len(fields) < 16:
            continue

        try:
            values = [int(field) for field in fields[:16]]
        except ValueError:
            continue

        result[name] = {
            "bytes_recv": values[0],
            "packets_recv": values[1],
            "errors_in": values[2],
            "drop_in": values[3],
            "bytes_sent": values[8],
            "packets_sent": values[9],
            "errors_out": values[10],
            "drop_out": values[11],
        }

    return result


def collect_network() -> list[dict[str, Any]]:
    """Cumulative traffic counters per host interface (since boot)."""
    try:
        with open(_host_net_dev_path(), encoding="utf-8") as handle:
            counters = _parse_net_dev(handle.read())
    except OSError:
        return []

    wanted = settings.parsed_net_interfaces()

    results = []
    for nic, counts in counters.items():
        if wanted:
            if nic not in wanted:
                continue
        else:
            if nic == "lo" or nic.startswith(_IGNORED_NIC_PREFIXES):
                continue
            if not counts["bytes_recv"] and not counts["bytes_sent"]:
                continue
        results.append({"interface": nic, **counts})
    return sorted(results, key=lambda d: d["interface"])


def _threshold(value: float | None) -> float | None:
    """Drop hwmon's unset-threshold sentinel."""
    if value is None or value >= _IMPOSSIBLE_TEMPERATURE_C:
        return None
    return value


def collect_sensors() -> dict[str, Any]:
    """Temperatures and fan speeds from hwmon."""
    temps_raw = _safe(psutil.sensors_temperatures, {}) or {}
    fans_raw = _safe(psutil.sensors_fans, {}) or {}

    temperatures = [
        {
            "chip": chip,
            "label": entry.label or chip,
            "current": entry.current,
            "high": _threshold(entry.high),
            "critical": _threshold(entry.critical),
        }
        for chip, entries in temps_raw.items()
        for entry in entries
    ]
    fans = [
        {"chip": chip, "label": entry.label or chip, "rpm": entry.current}
        for chip, entries in fans_raw.items()
        for entry in entries
    ]
    return {"temperatures": temperatures, "fans": fans}


def _read_cmdline(pid: int) -> list[str]:
    """A process's argv, or an empty list."""
    try:
        with open(
            os.path.join(psutil.PROCFS_PATH, str(pid), "cmdline"), "rb"
        ) as handle:
            raw = handle.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def _service_name(pid: int, fallback: str | None) -> str | None:
    """What a process actually is, from its command line."""
    argv = _read_cmdline(pid)
    if not argv:
        return fallback

    name = os.path.basename(argv[0])
    if name in _INTERPRETERS:
        for argument in argv[1:]:
            if argument.startswith("-"):
                continue
            name = os.path.basename(argument)
            break

    for suffix in _SCRIPT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    return name or fallback


def collect_processes(previous_cpu: dict[int, float] | None = None) -> dict[str, Any]:
    """Process count plus the heaviest consumers."""
    attrs = ["pid", "name", "memory_percent", "status", "cpu_times"]
    procs: list[dict[str, Any]] = []
    statuses: dict[str, int] = {}
    cpu_totals: dict[int, float] = {}

    for proc in psutil.process_iter(attrs, ad_value=None):
        info = proc.info
        pid = info.get("pid")
        status = info.get("status") or "unknown"
        statuses[status] = statuses.get(status, 0) + 1

        times = info.get("cpu_times")
        used = (times.user + times.system) if times else None
        if pid is not None and used is not None:
            cpu_totals[pid] = used

        procs.append(
            {
                "pid": pid,
                "name": info.get("name"),
                "cpu_seconds": used,
                "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                "status": status,
            }
        )

    logical = psutil.cpu_count(logical=True) or 1
    for entry in procs:
        entry["cpu_percent"] = None
        pid, used = entry["pid"], entry.pop("cpu_seconds")
        if previous_cpu is None or used is None:
            continue
        before = previous_cpu.get(pid)
        if before is None or used < before:
            continue
        entry["_delta"] = used - before

    elapsed = None
    if previous_cpu is not None:
        elapsed = previous_cpu.get(-1)

    for entry in procs:
        delta = entry.pop("_delta", None)
        if delta is not None and elapsed:
            entry["cpu_percent"] = round(min(100.0 * logical, delta / elapsed * 100), 1)

    limit = settings.top_processes
    top_cpu = sorted(procs, key=lambda p: p["cpu_percent"] or 0.0, reverse=True)[:limit]
    top_memory = sorted(procs, key=lambda p: p["memory_percent"], reverse=True)[:limit]

    for entry in {id(e): e for e in top_cpu + top_memory}.values():
        entry["service"] = _service_name(entry["pid"], entry["name"])

    return {
        "total": len(procs),
        "by_status": statuses,
        "cores_logical": logical,
        "top_cpu": top_cpu,
        "top_memory": top_memory,
        "_cpu_totals": cpu_totals,
    }


@dataclass
class _Snapshot:
    taken_at: float
    payload: dict[str, Any]
    cpu_times: Any
    cpu_times_percpu: list[Any]
    process_cpu: dict[int, float]


_lock = threading.Lock()
_latest: _Snapshot | None = None


def _take(previous: _Snapshot | None, now: float) -> _Snapshot:
    interval = (now - previous.taken_at) if previous else None

    process_cpu = dict(previous.process_cpu) if previous else None
    if process_cpu is not None and interval:
        process_cpu[-1] = interval

    cpu = _safe(
        lambda: collect_cpu(
            previous.cpu_times if previous else None,
            previous.cpu_times_percpu if previous else None,
            interval,
        ),
        {},
    )
    cpu_times = cpu.pop("_times", None)
    cpu_percpu = cpu.pop("_times_percpu", [])

    processes = _safe(lambda: collect_processes(process_cpu), {})
    totals = processes.pop("_cpu_totals", {})

    payload = {
        "timestamp": time.time(),
        "snapshot_age_seconds": 0.0,
        "host": _safe(collect_host, {}),
        "cpu": cpu,
        "memory": _safe(collect_memory, {}),
        "disks": _safe(collect_disk_usage, []),
        "disk_io": _safe(collect_disk_io, []),
        "network": _safe(collect_network, []),
        "sensors": _safe(collect_sensors, {"temperatures": [], "fans": []}),
        "processes": processes,
    }
    return _Snapshot(now, payload, cpu_times, cpu_percpu, totals)


def collect_all(max_age_seconds: float | None = None) -> dict[str, Any]:
    """Full system snapshot, at most `max_age_seconds` old."""
    global _latest

    ttl = (
        settings.snapshot_ttl_seconds if max_age_seconds is None else max_age_seconds
    )
    now = time.monotonic()

    with _lock:
        if _latest is not None and (now - _latest.taken_at) < ttl:
            payload = dict(_latest.payload)
            payload["snapshot_age_seconds"] = round(now - _latest.taken_at, 2)
            return payload

        _latest = _take(_latest, now)
        return _latest.payload


def reset_snapshot() -> None:
    """Forget the cached reading. For tests, and for nothing else."""
    global _latest
    with _lock:
        _latest = None
