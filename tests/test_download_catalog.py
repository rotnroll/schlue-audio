import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "download_catalog", ROOT / "scripts" / "generate-download-index.py"
)
CATALOG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CATALOG)


def asset(tag, name, size, downloads, digest=None):
    value = {
        "name": name,
        "size": size,
        "download_count": downloads,
        "browser_download_url": f"https://github.com/rotnroll/schlue-audio/releases/download/{tag}/{name}",
    }
    if digest:
        value["digest"] = digest
    return value


class DownloadCatalogTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "plugins.json").read_text(encoding="utf-8"))

    def release(self, tag, counts=(2, 3, 5, 7), **overrides):
        version = tag.rsplit("-v", 1)[1]
        plugin = next(
            item for item in self.config["plugins"] if tag.startswith(item["releaseTagPrefix"])
        )
        product = plugin["name"]
        assets = [
            asset(tag, f"{product}-{version}-windows-x64-setup.exe", 100, counts[0]),
            asset(tag, f"{product}-{version}-windows-x64.zip", 100, counts[1]),
            asset(tag, f"{product}-{version}-macos-universal.pkg", 100, counts[2]),
            asset(tag, f"{product}-{version}-macos-universal.zip", 100, counts[3], "sha256:" + "a" * 64),
            asset(tag, "SHA256SUMS.txt", 100, 999),
        ]
        release = {"tag_name": tag, "draft": False, "prerelease": False, "assets": assets}
        release.update(overrides)
        return release

    def test_counts_only_user_facing_assets_and_orders_versions(self):
        releases = [
            self.release("relatilt-v1.0"),
            self.release("relatilt-v1.1", counts=(1, 1, 1, 1)),
            self.release("stager-v1.0", counts=(4, 0, 0, 0)),
            self.release("rerider-v1.0", counts=(2, 2, 2, 2)),
            self.release("relatilt-v9.0", prerelease=True),
        ]
        catalog = CATALOG.build_catalog(self.config, releases, "rotnroll/schlue-audio", "2026-08-31T12:00:00Z")

        relatilt = catalog["plugins"]["relatilt"]
        self.assertEqual([item["version"] for item in relatilt["versions"]], ["1.1", "1.0"])
        self.assertEqual(relatilt["downloads"], 21)
        self.assertEqual(relatilt["versions"][1]["downloads"], 17)
        self.assertEqual(catalog["plugins"]["stager"]["downloads"], 4)
        self.assertEqual(catalog["plugins"]["rerider"]["downloads"], 8)
        self.assertEqual(catalog["schema"], 2)

    def test_rejects_unmapped_binary(self):
        release = self.release("relatilt-v1.0")
        release["assets"].append(asset("relatilt-v1.0", "RelaTilt-1.0.zip", 100, 1))
        with self.assertRaisesRegex(ValueError, "Cannot map"):
            CATALOG.build_catalog(self.config, [release], "rotnroll/schlue-audio", "now")

    def test_rejects_missing_checksums(self):
        release = self.release("stager-v1.0")
        release["assets"] = [item for item in release["assets"] if item["name"] != "SHA256SUMS.txt"]
        with self.assertRaisesRegex(ValueError, "no SHA256SUMS"):
            CATALOG.build_catalog(self.config, [release], "rotnroll/schlue-audio", "now")


if __name__ == "__main__":
    unittest.main()
