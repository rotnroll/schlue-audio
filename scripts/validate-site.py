#!/usr/bin/env python3

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
REPOSITORY = "rotnroll/schlue-audio"
PROJECT_NAME = REPOSITORY.rsplit("/", 1)[1]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for attribute in ("href", "src"):
            if attribute in values:
                self.links.append(values[attribute])


def local_target(root: Path, page: Path, value: str):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("#"):
        return None
    path = unquote(parsed.path)
    project_prefix = f"/{PROJECT_NAME}/"
    if path == f"/{PROJECT_NAME}":
        target = root
    elif path.startswith(project_prefix):
        target = root / path[len(project_prefix):]
    else:
        target = (page.parent / path).resolve()
    if path.endswith("/"):
        target /= "index.html"
    return target


def validate_catalog(catalog: dict, config: dict, errors: list[str]):
    if catalog.get("schema") != 2:
        errors.append("downloads.json must use schema 2")
        return

    configured = {plugin["id"]: plugin for plugin in config["plugins"]}
    if set(catalog.get("plugins", {})) != set(configured):
        errors.append("Catalog plug-ins do not match plugins.json")

    for plugin_id, plugin in catalog.get("plugins", {}).items():
        metadata = configured.get(plugin_id)
        if metadata is None:
            continue
        plugin_total = 0
        versions = plugin.get("versions", [])
        for release in versions:
            tag = release.get("tag", "")
            if not tag.startswith(metadata["releaseTagPrefix"]):
                errors.append(f"Unexpected tag for {plugin_id}: {tag}")
            version_total = 0
            names = set()
            for platform, assets in release.get("platforms", {}).items():
                if platform not in {"win64", "macos"}:
                    errors.append(f"Unknown platform in {tag}: {platform}")
                for asset in assets:
                    name = asset.get("name")
                    if name in names:
                        errors.append(f"Duplicate asset name in {tag}: {name}")
                    names.add(name)
                    if not isinstance(name, str) or not name.startswith(metadata["assetPrefix"]):
                        errors.append(f"Unexpected asset prefix in {tag}: {name}")
                    url = asset.get("url", "")
                    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
                    if not url.startswith(expected):
                        errors.append(f"Invalid Release URL in {tag}: {url}")
                    if not isinstance(asset.get("size"), int) or asset["size"] <= 0:
                        errors.append(f"Invalid size in {tag}: {name}")
                    count = asset.get("downloads")
                    if not isinstance(count, int) or count < 0:
                        errors.append(f"Invalid count in {tag}: {name}")
                    else:
                        version_total += count
                    digest = asset.get("digest")
                    if digest is not None and not DIGEST_PATTERN.fullmatch(digest):
                        errors.append(f"Invalid digest in {tag}: {name}")
            checksum = release.get("checksums") or {}
            if checksum.get("name") != "SHA256SUMS.txt" or not checksum.get("url", "").startswith(
                f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
            ):
                errors.append(f"Invalid or missing checksums in {tag}")
            if release.get("downloads") != version_total:
                errors.append(f"Version download total is incorrect in {tag}")
            plugin_total += version_total
        if plugin.get("downloads") != plugin_total:
            errors.append(f"Plugin download total is incorrect for {plugin_id}")


def main():
    parser = argparse.ArgumentParser(description="Validate the Schlue Audio static site and catalog.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--site-root", default="_site")
    parser.add_argument("--catalog", default="_site/downloads.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    site_root = (root / args.site_root).resolve()
    catalog_path = (root / args.catalog).resolve()
    errors = []
    config = json.loads((root / "plugins.json").read_text(encoding="utf-8"))
    pages = [site_root / "index.html", site_root / "404.html", site_root / "contact" / "index.html"]
    pages.extend(site_root / item["directory"] / "index.html" for item in config["plugins"])

    forbidden = tuple(f"github.com/rotnroll/{plugin['id']}" for plugin in config["plugins"])
    readme = (root / "README.md").read_text(encoding="utf-8").lower()
    if any(value in readme for value in forbidden):
        errors.append("Source-code link found in README.md")

    for page in pages:
        if not page.is_file():
            errors.append(f"Missing built page: {page.relative_to(site_root)}")
            continue
        text = page.read_text(encoding="utf-8")
        if any(value in text.lower() for value in forbidden):
            errors.append(f"Source-code link found in {page.relative_to(site_root)}")
        parser = LinkParser()
        parser.feed(text)
        for value in parser.links:
            target = local_target(site_root, page, value)
            if target is not None and not target.exists():
                errors.append(f"Broken local link in {page.relative_to(site_root)}: {value}")

    if not catalog_path.is_file():
        errors.append(f"Missing catalog: {catalog_path}")
    else:
        validate_catalog(json.loads(catalog_path.read_text(encoding="utf-8")), config, errors)

    forbidden_packages = (
        list(site_root.rglob("*.exe"))
        + list(site_root.rglob("*.pkg"))
        + list(site_root.rglob("*.zip"))
    )
    if forbidden_packages:
        errors.append("Binary installers were copied into the Pages artifact")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Validated {len(pages)} built pages and the Release-backed catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
