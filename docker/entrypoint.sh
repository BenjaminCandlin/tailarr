#!/bin/sh
# Starts Tailarr as the Unraid user (PUID/PGID, default 99/100) with the
# Unraid file permission mask (UMASK, default 002), so every file Tailarr
# creates can be read and changed by your other containers and shares.
set -eu

PUID="${PUID:-99}"
PGID="${PGID:-100}"
UMASK="${UMASK:-002}"

umask "$UMASK"

if [ "$(id -u)" = "0" ]; then
    mkdir -p /config
    # Only Tailarr's own config folder is adjusted. Media files are never chowned.
    find /config \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown "$PUID:$PGID" {} +
    echo "Tailarr: running as user $PUID, group $PGID, umask $UMASK"
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups -- "$@"
fi

echo "Tailarr: running as user $(id -u), group $(id -g), umask $UMASK"
exec "$@"
