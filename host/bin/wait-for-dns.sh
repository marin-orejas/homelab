#!/bin/bash

for i in $(seq 1 30); do
    if getent hosts google.com >/dev/null 2>&1; then
        exit 0
    fi
    sleep 1
done
echo "wait-for-dns: timed out after 30s, starting anyway" >&2
exit 0
