#!/bin/sh
# Runs one lab command in the container. Source videos are read from media/ (not committed), read-only.
#   ./lab/run.sh probe /in/IMG_7821.MOV
cd "$(dirname "$0")/.." || exit 1
exec docker run --rm --env-file .env -v "${MEDIA_DIR:-$PWD/media}":/in:ro -v "$PWD":/work reel-lab "$@"
