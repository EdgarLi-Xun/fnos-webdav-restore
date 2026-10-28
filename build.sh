#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 generate_icons.py

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE"
cp -a app/ui app/bin "$STAGE/"

rm -f app.tgz webdavfix.fpk manifest.checksum
tar -C "$STAGE" -czf app.tgz ui bin
if command -v md5sum >/dev/null 2>&1; then
  md5sum app.tgz | awk '{print $1}' > manifest.checksum
elif command -v md5 >/dev/null 2>&1; then
  md5 -q app.tgz > manifest.checksum
fi

STAGE_FPK="$(mktemp -d)"
trap 'rm -rf "$STAGE" "$STAGE_FPK"' EXIT
cp -a manifest cmd config wizard ICON.PNG ICON_256.PNG README.md LICENSE app.tgz "$STAGE_FPK/"
[ -f manifest.checksum ] && cp manifest.checksum "$STAGE_FPK/"
tar -C "$STAGE_FPK" -czf webdavfix.fpk .
ls -lh webdavfix.fpk app.tgz
