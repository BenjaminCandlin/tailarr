#!/usr/bin/env bash
# Starts Tailarr for the browser tests, using generated sample files.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"
tmp="$here/.tmp"
rm -rf "$tmp/config"
mkdir -p "$tmp/config"
python3 "$repo/tests/samples/make_samples.py" "$tmp/samples" > /dev/null
export TAILARR_CONFIG_DIR="$tmp/config"
export TAILARR_MOVIES_DIR="$tmp/samples/data/media/movies"
export TAILARR_TV_DIR="$tmp/samples/data/media/tv"
export TAILARR_WORK_DIR="$tmp/no-work-folder"
export TAILARR_STATIC_DIR="$repo/frontend/dist"
cd "$repo/backend"
exec uv run --frozen uvicorn tailarr.main:create_app --factory --host 127.0.0.1 --port "${PORT:-8485}"
