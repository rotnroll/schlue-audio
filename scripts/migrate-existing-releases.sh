#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT

publish_existing() {
  local directory="$1"
  local plugin_name="$2"
  local tag_prefix="$3"
  local version="$4"
  local tag="${tag_prefix}${version}"
  local title="${plugin_name} ${version}"
  local assets="$temporary_root/$tag"
  local existing="$temporary_root/${tag}-existing"
  local expected actual

  bash "$repository_root/scripts/stage-release.sh" "$repository_root/$directory/$version" "$assets"
  expected="$(find "$assets" -maxdepth 1 -type f -printf '%f\n' | sort)"

  if gh release view "$tag" >/dev/null 2>&1; then
    actual="$(gh release view "$tag" --json assets --jq '.assets[].name' | sort)"
    if [[ "$actual" != "$expected" ]]; then
      echo "Existing immutable release $tag has a different asset set." >&2
      exit 1
    fi
    mkdir "$existing"
    gh release download "$tag" --pattern SHA256SUMS.txt --dir "$existing"
    cmp "$assets/SHA256SUMS.txt" "$existing/SHA256SUMS.txt"
    echo "Release $tag already matches the migration payload."
    return
  fi

  gh release create "$tag" \
    --target main \
    --title "$title" \
    --notes "Binary distributions and SHA-256 checksums for $title." \
    --draft
  gh release upload "$tag" "$assets"/*
  gh release edit "$tag" --draft=false
}

publish_existing "Relatilt" "RelaTilt" "relatilt-v" "1.0"
publish_existing "Stager" "Stager" "stager-v" "1.0"
