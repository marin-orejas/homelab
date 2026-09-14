# Host

Everything that runs outside Docker: the machine, the disks, and a few small
scripts and units that watch them.

## Hardware and OS

| Part | Detail |
|---|---|
| Machine | ASUS NUC13ANH-B |
| CPU | Intel Core i3-1315U, 6 cores, 8 threads |
| GPU | Intel iGPU with Quick Sync, used by Jellyfin |
| Memory | 15 GiB |
| System disk | 238.5 GB NVMe: EFI, 225 GB ext4 root, 12 GB swap |
| Film disk | Toshiba DT01ACA200, 1.8 TB, ext4 |
| Series disk | WD10EZEX, 931.5 GB, ext4 |
| Disk enclosure | USB dual bay dock with a JMicron JMS561U bridge |
| OS | Debian 13 (trixie), kernel 6.12 |
| Containers | Docker 29.7.2, Compose 5.5.0 |

The NVMe holds the OS, every container's config and the download scratch
space. It is 5 percent full. The two hard drives hold only media.

## The disks

The two drives are mounted separately and never joined:

```
UUID=<uuid> /mnt/disks/wd1tb      ext4 defaults,noatime,nofail,x-systemd.device-timeout=30 0 2
UUID=<uuid> /mnt/disks/toshiba2tb ext4 defaults,noatime,nofail,x-systemd.device-timeout=30 0 2
```

| Option | Why |
|---|---|
| `UUID=` | Device letters are not stable here. Three reboots gave three different orders of `sda` and `sdb`. |
| `noatime` | Reading a file does not write to the disk |
| `nofail` | A missing dock does not stop the machine from booting |
| `device-timeout=30` | Two 7200 rpm drives need time to spin up over USB |

An earlier version joined both drives into one folder with mergerfs. It was
removed for two reasons. One dead disk would damage the whole library, and all
disk I/O was billed by the kernel to the mergerfs process, which made it
impossible to see which container was using a disk. Now a failed disk takes
only its own half of the library. There is no RAID and no LVM for the same
reason.

## The USB dock shapes everything below

The JMicron JMS561U bridge in the dock does not pass drive power state commands
through correctly, and its firmware parks the drives after about 10 minutes of
idle time, whatever the OS asks for.

That has three consequences.

**No tool can tell whether a drive is asleep.** `hdparm -C` reports standby even
right after a full SMART read. `smartctl -n standby` always reports the drive as
awake. The only reliable measurement is the drive's own `Start_Stop_Count`,
compared between two days.

**Parking is safe.** Over a 46 hour test each drive stopped and started 92
times, with zero USB disconnects, zero resets and zero I/O errors. The drives
also ran 4 to 5 °C cooler.

**Anything that polls a drive wakes it.** That is why SMART is read once a day,
why the dashboard reads a file instead of the drives, and why Jellyfin's
scheduled work runs at 03:00.

## Files in this folder

| File | Installed at | Purpose |
|---|---|---|
| [`bin/smartcheck.sh`](bin/smartcheck.sh) | `/usr/local/bin/` | Daily SMART read of both drives |
| [`systemd/smartcheck.service`](systemd/smartcheck.service) | `/etc/systemd/system/` | Runs the script once |
| [`systemd/smartcheck.timer`](systemd/smartcheck.timer) | `/etc/systemd/system/` | At 03:00 every day |
| [`bin/diskwatch.py`](bin/diskwatch.py) | `/usr/local/bin/` | Logs which process or container used a media drive |
| [`systemd/diskwatch.service`](systemd/diskwatch.service) | `/etc/systemd/system/` | Keeps it running |
| [`bin/wait-for-dns.sh`](bin/wait-for-dns.sh) | `/usr/local/bin/` | Holds Docker until DNS works |
| [`systemd/docker-wait-for-storage.conf`](systemd/docker-wait-for-storage.conf) | `/etc/systemd/system/docker.service.d/` | Docker starts only with both drives mounted |
| [`udev/60-scheduler.rules`](udev/60-scheduler.rules) | `/etc/udev/rules.d/` | I/O scheduler for the media drives |
| [`sysctl/99-quic-buffers.conf`](sysctl/99-quic-buffers.conf) | `/etc/sysctl.d/` | UDP buffer limit for the tunnel |

Disk serial numbers and UUIDs are replaced with placeholders.

## smartcheck

Reads SMART from both drives at 03:00, writes one line per drive to the
journal, and saves the result to `/var/lib/smartcheck/latest.json` for the
dashboard.

```
toshiba2tb health=PASSED start_stop=3922 load_cycle=3927 realloc=0 temp_c=28
wd1tb health=PASSED start_stop=6619 load_cycle=24530 realloc=0 temp_c=28
```

**Why not smartd.** smartd polls every 30 minutes. Its "skip if asleep" check
never works through this bridge, so every poll woke a parked drive. That was 92
spin-ups per drive in 46 hours with no disk activity at all, or 48 a day. The
script costs 1. `/etc/smartd.conf` now watches only the NVMe:

```
/dev/nvme0 -d nvme -a -m root -M exec /usr/share/smartmontools/smartd-runner
```

**Why 03:00.** Jellyfin runs its daily work at the same time, so the drives
wake once for both.

**Why `Persistent=false`.** A run missed while the machine was off does not fire
at boot and wake a parked drive for nothing.

**Why a JSON file.** The host has no mail agent, so an alert in the journal
reached nobody. The dashboard reads the file and shows the reading, and it flags
the reading if the file is more than 26 hours old, because a stopped timer means
nobody is watching the drives.

**How severity is decided.** Health other than PASSED is critical. Any
reallocated sector is critical, because the drive has already failed once and
hidden it. A missing reallocated sector count is a warning. The file is written
to a temporary name and renamed, so the dashboard never reads half a file.

The drives are addressed by `/dev/disk/by-id/ata-*`. Device letters change
between boots, and the `usb-*` ids follow the dock bay rather than the drive.

## diskwatch

Samples every 60 seconds and writes one line for each source that read or wrote
at least 4 KB on a media drive:

```
timestamp                  disk        source      read_bytes  write_bytes
2026-09-14T16:22:15+02:00  toshiba2tb  user.slice  4096        0
```

It reads cgroup v2 `io.stat`. Cgroup counters include their children, so each
cgroup is reported as its own counters minus those of its direct children.
Docker scopes are turned into container names, so a line says `jellyfin` rather
than a 64 character id. Anything the cgroups do not account for, such as
readahead and journal flushes, is logged as `unaccounted`.

This made it possible to plan the 03:00 window from facts. For example, it
showed one Bazarr subtitle extraction reading 316 GB in a day, and ordinary
playback reading 40 to 58 MB a minute.

Two things to know when reading the log. An empty log is the normal state,
because an idle system moves nothing. Recreating a container produces one line
faster than the hardware can go, because the old cgroup's totals drop out of the
subtraction. That line should be ignored.

The unit runs at the lowest CPU and I/O priority, with no access to home
directories and no new privileges. Its log rotates daily and is kept for 14
days.

## Docker startup guard

`docker-wait-for-storage.conf` adds two things to `docker.service`.

`RequiresMountsFor` refuses to start Docker unless both drives are mounted.
This came from a real failure. With the dock unplugged, the mount point was an
empty folder on the NVMe, and the stack ran for four days writing to the wrong
disk without a single error.

`wait-for-dns.sh` runs before Docker and waits up to 30 seconds for DNS to
answer. Docker copies the host resolver when it starts, and on this machine the
network can report ready before DHCP has written that resolver. The script
always exits 0, so a DNS problem delays the stack rather than stopping it.

## I/O scheduler

`60-scheduler.rules` sets the `bfq` scheduler and 4 MB read-ahead on both media
drives. It matches each drive by serial number, not by device letter.

## UDP buffers for the tunnel

`99-quic-buffers.conf` raises the largest UDP buffer a socket may request from
208 KiB to about 7.2 MiB. cloudflared uses QUIC, which asks for 7 MiB. Without
this it got 416 KiB and remote playback through the tunnel was throttled. This
only raises the ceiling. Nothing is allocated up front.

## SSH and access

SSH is reachable from the LAN only. No port is forwarded on the router and SSH
does not go through the tunnel. Every key in `authorized_keys` is also limited
to the LAN subnet.

`/etc/ssh/sshd_config.d/99-hardening.conf`:

```
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
PermitRootLogin no
AllowUsers <user>
LogLevel VERBOSE
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
```

It is a drop-in because sshd keeps the first value it reads, and Debian's
include line sits at the top of the main file. The drop-in wins and survives
package updates. `VERBOSE` logs the fingerprint of the key used, so separate
keys can be told apart in the journal.

fail2ban watches sshd through the journal and bans for one hour after 3 failures
in 10 minutes, using nftables.

Secrets reach containers as environment variables, never as command line
arguments. A process's arguments are readable by every user in
`/proc/<pid>/cmdline`, while its environment is not. This is also why
cloudflared gets its token from `TUNNEL_TOKEN` and not from `--token`.

## Retired

`spinkeep.sh` wrote 4 KB to each drive every few minutes to stop the dock
parking them. It was removed after the 46 hour test showed parking is harmless.
It worked directly against letting the drives rest.
