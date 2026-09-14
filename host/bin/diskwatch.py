#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

INTERVAL = 60
LOG = Path("/var/log/diskwatch/diskwatch.log")
CGROUP_ROOT = Path("/sys/fs/cgroup")

WATCHED = {
    "/mnt/disks/wd1tb": "wd1tb",
    "/mnt/disks/toshiba2tb": "toshiba2tb",
}

MIN_BYTES = 4096

SECTOR = 512
IO_LINE = re.compile(r"^(\d+:\d+)\s+(.*)$")
DOCKER_SCOPE = re.compile(r"docker-([0-9a-f]{64})\.scope")


def parent_disk(part: str) -> str:
    """sdb1 -> sdb. Block-layer accounting is per whole disk, not partition."""
    link = Path("/sys/class/block") / part
    if not link.exists():
        return part
    parent = link.resolve().parent
    return parent.name if (parent / "dev").exists() else part


def resolve_disks() -> dict[str, str]:
    """label -> "major:minor" of the whole disk, read fresh every cycle."""
    found: dict[str, str] = {}
    for line in Path("/proc/mounts").read_text().splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] not in WATCHED or not parts[0].startswith("/dev/"):
            continue
        devfile = Path("/sys/block") / parent_disk(os.path.basename(parts[0])) / "dev"
        if devfile.exists():
            found[WATCHED[parts[1]]] = devfile.read_text().strip()
    return found


def disk_totals(devnums: dict[str, str]) -> dict[str, tuple[int, int]]:
    """Kernel-side totals per disk, from /sys/block/<disk>/stat."""
    by_devnum = {devnum: label for label, devnum in devnums.items()}
    out: dict[str, tuple[int, int]] = {}
    for blk in Path("/sys/block").iterdir():
        devfile = blk / "dev"
        if not devfile.exists():
            continue
        label = by_devnum.get(devfile.read_text().strip())
        if label is None:
            continue
        f = (blk / "stat").read_text().split()
        out[label] = (int(f[2]) * SECTOR, int(f[6]) * SECTOR)
    return out


def container_names() -> dict[str, str]:
    """Full container id -> name, so cgroup scopes read as something useful."""
    try:
        ps = subprocess.run(
            ["docker", "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}}"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if ps.returncode != 0:
        return {}
    out = {}
    for row in ps.stdout.splitlines():
        cid, _, name = row.partition(" ")
        if cid and name:
            out[cid] = name
    return out


def pretty(path: Path, names: dict[str, str]) -> str:
    rel = str(path.relative_to(CGROUP_ROOT))
    if rel == ".":
        return "root"
    match = DOCKER_SCOPE.search(rel)
    if match:
        return names.get(match.group(1), f"docker:{match.group(1)[:12]}")
    return rel


def cgroup_io(devnums: dict[str, str], names: dict[str, str]) -> dict[tuple[str, str], tuple[int, int]]:
    """(source, disk label) -> cumulative (read, write) for that cgroup alone."""
    wanted = {devnum: label for label, devnum in devnums.items()}
    raw: dict[Path, dict[str, tuple[int, int]]] = {}

    for stat in CGROUP_ROOT.rglob("io.stat"):
        try:
            text = stat.read_text()
        except OSError:
            continue
        per_disk: dict[str, tuple[int, int]] = {}
        for line in text.splitlines():
            m = IO_LINE.match(line.strip())
            if not m or m.group(1) not in wanted:
                continue
            fields = dict(kv.split("=", 1) for kv in m.group(2).split() if "=" in kv)
            per_disk[wanted[m.group(1)]] = (
                int(fields.get("rbytes", 0)),
                int(fields.get("wbytes", 0)),
            )
        if per_disk:
            raw[stat.parent] = per_disk

    out: dict[tuple[str, str], tuple[int, int]] = {}
    for cg, per_disk in raw.items():
        for label, (read, write) in per_disk.items():
            own_r, own_w = read, write
            for other, other_disks in raw.items():
                if other.parent == cg and label in other_disks:
                    own_r -= other_disks[label][0]
                    own_w -= other_disks[label][1]
            if own_r > 0 or own_w > 0:
                out[(pretty(cg, names), label)] = (max(own_r, 0), max(own_w, 0))
    return out


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOG.exists():
        LOG.write_text("# ts\tdisk\tsource\tread_bytes\twrite_bytes\n")

    prev_disk: dict[str, tuple[int, int]] = {}
    prev_src: dict[tuple[str, str], tuple[int, int]] = {}

    while True:
        devnums = resolve_disks()
        totals = disk_totals(devnums)
        sources = cgroup_io(devnums, container_names())
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")

        rows: list[str] = []
        for label, (read, write) in totals.items():
            pr, pw = prev_disk.get(label, (read, write))
            d_read = read - pr if read >= pr else 0
            d_write = write - pw if write >= pw else 0

            claimed_r = claimed_w = 0
            for (name, disk), (cr, cw) in sources.items():
                if disk != label:
                    continue
                pcr, pcw = prev_src.get((name, disk), (cr, cw))
                dr = cr - pcr if cr >= pcr else 0
                dw = cw - pcw if cw >= pcw else 0
                claimed_r += dr
                claimed_w += dw
                if dr + dw >= MIN_BYTES:
                    rows.append(f"{stamp}\t{label}\t{name}\t{dr}\t{dw}")

            rest_r = max(d_read - claimed_r, 0)
            rest_w = max(d_write - claimed_w, 0)
            if rest_r + rest_w >= MIN_BYTES:
                rows.append(f"{stamp}\t{label}\tunaccounted\t{rest_r}\t{rest_w}")

        if rows:
            with LOG.open("a") as fh:
                fh.write("\n".join(rows) + "\n")

        prev_disk = totals
        prev_src = sources
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
