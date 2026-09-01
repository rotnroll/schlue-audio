#!/usr/bin/env bash

set -euo pipefail

incoming_root="${1:?incoming artifact root is required}"
output_root="${2:?release output directory is required}"

windows_source="$incoming_root/win64"
macos_source="$incoming_root/macos"

test -d "$windows_source"
test -d "$macos_source"
mkdir -p "$output_root"

find "$windows_source" -maxdepth 1 -type f \( -name '*.zip' -o -name '*.exe' \) -exec cp -- '{}' "$output_root/" \;
find "$macos_source" -maxdepth 1 -type f \( -name '*.zip' -o -name '*.pkg' \) -exec cp -- '{}' "$output_root/" \;

test "$(find "$output_root" -maxdepth 1 -type f \( -name '*.zip' -o -name '*.exe' -o -name '*.pkg' \) | wc -l)" -ge 4

(
  cd "$output_root"
  find . -maxdepth 1 -type f \( -name '*.zip' -o -name '*.exe' -o -name '*.pkg' \) -printf '%f\0' \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS.txt
)
