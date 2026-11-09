#!/usr/bin/env bash
# Starts a built Tailarr image and checks it works like it will on Unraid.
# Usage: docker/smoke-test.sh IMAGE
# Set SMOKE_SKIP_TOOLS=1 to skip the tool check (only for images built without them).
set -euo pipefail

image="${1:?usage: smoke-test.sh IMAGE}"
port="${SMOKE_PORT:-18484}"
work="$(mktemp -d)"
name="tailarr-smoke-$$"
mkdir -p "$work/config" "$work/data/media/movies" "$work/data/media/tv" "$work/data/torrents"
chmod -R 777 "$work/data"

cleanup() {
    docker logs "$name" > "$work/container.log" 2>&1 || true
    docker rm -f "$name" > /dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
    echo "FAILED: $*"
    docker logs "$name" 2>&1 | tail -30 || true
    exit 1
}

docker run -d --name "$name" -p "127.0.0.1:$port:8484" \
    -v "$work/config:/config" -v "$work/data:/data" \
    "$image" > /dev/null

echo "Waiting for Tailarr to start..."
for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$port/api/health" > "$work/health.json" 2> /dev/null; then
        break
    fi
    sleep 1
done
[ -s "$work/health.json" ] || fail "Tailarr didn't start"

python3 - "$work/health.json" "${SMOKE_SKIP_TOOLS:-0}" << 'PY' || fail "health check"
import json, sys
health = json.load(open(sys.argv[1]))
skip_tools = sys.argv[2] == "1"
print(json.dumps(health, indent=2))
if not skip_tools:
    missing = [t["name"] for t in health["tools"] if not t["ok"]]
    assert not missing, f"tools missing: {missing}"
folders = {f["key"]: f for f in health["folders"]}
for key in ("movies", "tv", "config"):
    assert folders[key]["ok"], f"folder not usable: {folders[key]}"
assert folders["movies"]["path"] == "/data/media/movies"
assert folders["tv"]["path"] == "/data/media/tv"
assert health["running_as"] == {"uid": 99, "gid": 100, "umask": "002"}, health["running_as"]
PY

# Files Tailarr creates belong to 99:100 with rw-rw-r-- permissions.
owner="$(stat -c '%u:%g %a' "$work/config/tailarr.db")"
[ "$owner" = "99:100 664" ] || fail "database file has owner/permissions '$owner', expected '99:100 664'"

curl -fsS "http://127.0.0.1:$port/films" | grep -q "<title>Tailarr</title>" || fail "web page not served"

if [ "${SMOKE_SKIP_TOOLS:-0}" != "1" ]; then
    docker exec "$name" sh -c 'mkvmerge --version && mkvextract --version && mkvpropedit --version && mediainfo --version && dovi_tool --version' \
        || fail "a tool doesn't run inside the image"
fi

echo "Smoke test passed."
