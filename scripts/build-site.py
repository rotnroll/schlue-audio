#!/usr/bin/env python3

import argparse
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Assemble the GitHub Pages artifact.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("output", nargs="?", default="_site")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = (root / args.output).resolve()
    if output.parent != root:
        raise SystemExit("Output must be a direct child of the repository root.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir()

    for name in ("index.html", "404.html", ".nojekyll"):
        shutil.copy2(root / name, output / name)
    shutil.copytree(root / "assets", output / "assets")
    shutil.copytree(root / "contact", output / "contact")

    config = json.loads((root / "plugins.json").read_text(encoding="utf-8"))
    for plugin in config["plugins"]:
        destination = output / plugin["directory"]
        destination.mkdir()
        shutil.copy2(root / plugin["directory"] / "index.html", destination / "index.html")


if __name__ == "__main__":
    main()
