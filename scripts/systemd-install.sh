#!/usr/bin/env bash
# Copy timer units to ~/.config/systemd/user and enable them.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
dest="${HOME}/.config/systemd/user"
mkdir -p "$dest"
for f in "$repo"/scripts/systemd/*.{service,timer}; do
  sed "s|@REPO@|${repo}|g" "$f" > "${dest}/$(basename "$f")"
done
chmod +x "$repo/scripts/regenerate-loop.sh"
systemctl --user daemon-reload
systemctl --user enable --now fr-mirror-pipeline.timer fr-mirror-regenerate.timer
systemctl --user list-timers 'fr-mirror-*'
