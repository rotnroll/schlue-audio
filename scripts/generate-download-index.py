#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)*(?:[-+][A-Za-z0-9.-]+)?$")
COUNTABLE_SUFFIXES = {".exe", ".pkg", ".zip"}
CHECKSUM_NAME = "SHA256SUMS.txt"
REPOSITORY = "rotnroll/schlue-audio"


def version_key(value: str):
    parts = re.split(r"[-+]", value, maxsplit=1)
    main = parts[0]
    suffix = parts[1] if len(parts) > 1 else ""
    return tuple(int(part) for part in main.split(".")), not bool(suffix), suffix


def github_releases(repository: str, token: str | None):
    releases = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "schlue-audio-pages-build",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                batch = json.load(response)
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError(f"GitHub Releases API request failed: {error}") from error
        if not isinstance(batch, list):
            raise RuntimeError("GitHub Releases API returned an unexpected response")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def platform_for(asset_name: str):
    lower = asset_name.lower()
    suffix = Path(lower).suffix
    if suffix == ".exe":
        return "win64"
    if suffix == ".pkg":
        return "macos"
    if suffix == ".zip":
        if "windows" in lower or "win64" in lower:
            return "win64"
        if "macos" in lower or "mac-" in lower or "universal" in lower:
            return "macos"
    return None


def build_catalog(config: dict, releases: list[dict], repository: str, generated_at: str):
    catalog = {"schema": 2, "generatedAt": generated_at, "plugins": {}}

    for plugin in config["plugins"]:
        prefix = plugin["releaseTagPrefix"]
        plugin_versions = []

        for release in releases:
            tag = release.get("tag_name", "")
            if release.get("draft") or release.get("prerelease") or not tag.startswith(prefix):
                continue

            version = tag[len(prefix):]
            if not VERSION_PATTERN.fullmatch(version):
                raise ValueError(f"Invalid version suffix in release tag: {tag}")

            platforms = {"win64": [], "macos": []}
            checksum = None
            version_downloads = 0
            seen_names = set()

            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if not name or name in seen_names:
                    raise ValueError(f"Duplicate or empty asset name in {tag}: {name!r}")
                seen_names.add(name)
                url = asset.get("browser_download_url", "")
                size = asset.get("size")
                downloads = asset.get("download_count")
                expected_prefix = f"https://github.com/{repository}/releases/download/{tag}/"
                if not url.startswith(expected_prefix):
                    raise ValueError(f"Unexpected asset URL in {tag}: {url}")

                if name == CHECKSUM_NAME:
                    checksum = {"name": name, "url": url}
                    continue

                suffix = Path(name).suffix.lower()
                if suffix not in COUNTABLE_SUFFIXES:
                    continue
                if not name.startswith(plugin["assetPrefix"]):
                    raise ValueError(f"Unexpected binary asset prefix in {tag}: {name}")
                platform = platform_for(name)
                if platform is None:
                    raise ValueError(f"Cannot map binary asset to a platform in {tag}: {name}")
                if not isinstance(size, int) or size <= 0:
                    raise ValueError(f"Invalid asset size in {tag}: {name}")
                if not isinstance(downloads, int) or downloads < 0:
                    raise ValueError(f"Invalid download count in {tag}: {name}")

                item = {"name": name, "url": url, "size": size, "downloads": downloads}
                digest = asset.get("digest")
                if digest:
                    item["digest"] = digest
                platforms[platform].append(item)
                version_downloads += downloads

            if not checksum:
                raise ValueError(f"Release {tag} has no {CHECKSUM_NAME}")
            if not any(platforms.values()):
                raise ValueError(f"Release {tag} has no countable binary assets")
            for assets in platforms.values():
                assets.sort(key=lambda item: item["name"].lower())

            plugin_versions.append({
                "version": version,
                "tag": tag,
                "downloads": version_downloads,
                "platforms": platforms,
                "checksums": checksum,
            })

        plugin_versions.sort(key=lambda item: version_key(item["version"]), reverse=True)
        catalog["plugins"][plugin["id"]] = {
            "name": plugin["name"],
            "downloads": sum(item["downloads"] for item in plugin_versions),
            "versions": plugin_versions,
        }

    return catalog


def generated_timestamp(value: str | None):
    if value:
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main():
    parser = argparse.ArgumentParser(description="Generate a GitHub Release-backed download catalog.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--output", default="downloads.json")
    parser.add_argument("--repository", default=REPOSITORY)
    parser.add_argument("--releases-file", help="Read a captured Releases API response instead of the network.")
    parser.add_argument("--generated-at", help="Use a fixed generation timestamp (for tests).")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    config = json.loads((root / "plugins.json").read_text(encoding="utf-8"))
    try:
        if args.releases_file:
            releases = json.loads(Path(args.releases_file).read_text(encoding="utf-8"))
        else:
            releases = github_releases(args.repository, os.environ.get("GITHUB_TOKEN"))
        catalog = build_catalog(config, releases, args.repository, generated_timestamp(args.generated_at))
    except (KeyError, RuntimeError, TypeError, ValueError) as error:
        print(f"Catalog generation failed: {error}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
