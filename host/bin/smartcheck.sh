#!/bin/sh

set -u

TAG=smartcheck
STATE_DIR=/var/lib/smartcheck
STATE_FILE="$STATE_DIR/latest.json"

STATUS=0
DISKS_JSON=
WORST=good

attr() {
    echo "$out" | awk -v id="$1" '$1 == id { print $10; exit }'
}

jnum() {
    case "${1:-}" in
        '' | *[!0-9]*) printf 'null' ;;
        *) printf '%s' "$1" ;;
    esac
}

jstr() {
    printf '"%s"' "$(printf '%s' "${1:-}" | tr -d '"\\')"
}

escalate() {
    case "$1" in
        critical) WORST=critical ;;
        warning) [ "$WORST" = critical ] || WORST=warning ;;
    esac
}

add_disk() {
    [ -z "$DISKS_JSON" ] || DISKS_JSON="$DISKS_JSON,"
    DISKS_JSON="$DISKS_JSON$1"
}

check() {
    label=$1
    dev=$2

    if [ ! -e "$dev" ]; then
        logger -t "$TAG" -p daemon.warning "$label absent, skipped ($dev)"
        escalate warning
        add_disk "$(printf '{"label":%s,"present":false,"health":null,"start_stop":null,"load_cycle":null,"realloc":null,"temp_c":null,"severity":"warning"}' "$(jstr "$label")")"
        return 0
    fi

    out=$(smartctl -H -A "$dev" 2>&1) || true

    health=$(echo "$out" | sed -n 's/^SMART overall-health self-assessment test result: *//p')
    [ -n "$health" ] || health=UNKNOWN

    start_stop=$(attr 4)
    realloc=$(attr 5)
    load_cycle=$(attr 193)
    temp=$(attr 194)

    line="$label health=$health start_stop=${start_stop:-?} load_cycle=${load_cycle:-?} realloc=${realloc:-?} temp_c=${temp:-?}"

    sev=good
    if [ "$health" != "PASSED" ]; then
        sev=critical
    elif [ -z "$realloc" ]; then
        sev=warning
    elif [ "$realloc" != "0" ]; then
        sev=critical
    fi

    if [ "$sev" = critical ]; then
        logger -t "$TAG" -p daemon.err "$line"
        STATUS=1
    else
        logger -t "$TAG" -p daemon.info "$line"
    fi
    escalate "$sev"

    add_disk "$(printf '{"label":%s,"present":true,"health":%s,"start_stop":%s,"load_cycle":%s,"realloc":%s,"temp_c":%s,"severity":"%s"}' \
        "$(jstr "$label")" "$(jstr "$health")" "$(jnum "$start_stop")" \
        "$(jnum "$load_cycle")" "$(jnum "$realloc")" "$(jnum "$temp")" "$sev")"
}

write_state() {
    mkdir -p "$STATE_DIR" || return 0
    tmp="$STATE_FILE.tmp.$$"
    printf '{"generated_at":"%s","severity":"%s","disks":[%s]}\n' \
        "$(date -Is)" "$WORST" "$DISKS_JSON" > "$tmp" || return 0
    chmod 0644 "$tmp"
    mv -f "$tmp" "$STATE_FILE"
}

check toshiba2tb "/dev/disk/by-id/ata-TOSHIBA_DT01ACA200_<serial>"
check wd1tb      "/dev/disk/by-id/ata-WDC_WD10EZEX-08WN4A0_<serial>"

write_state

exit "$STATUS"
