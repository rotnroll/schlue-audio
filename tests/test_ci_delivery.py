import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ci_delivery', ROOT / 'scripts' / 'ci-delivery.py')
DELIVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DELIVERY)
CATALOG_SPEC = importlib.util.spec_from_file_location('catalog', ROOT / 'scripts' / 'generate-download-index.py')
CATALOG = importlib.util.module_from_spec(CATALOG_SPEC)
CATALOG_SPEC.loader.exec_module(CATALOG)


class FakeReleases:
    """The external API boundary; exercise real staging, provenance and file checks."""
    def __init__(self):
        self.releases = {}
        self.data = {}
        self.mutations = []

    def api(self, method, path, *, payload=None, file=None, binary=False):
        if method == 'POST' and payload is not None:
            self.mutations.append(copy.deepcopy(payload))
            release_id = len(self.releases) + 1
            value = dict(payload, id=release_id, published_at=None, assets=[], html_url='https://example.test/draft')
            self.releases[release_id] = copy.deepcopy(value)
            return value
        if method == 'POST' and file is not None:
            release_id = int(path.split('/releases/')[1].split('/')[0])
            asset_id = len(self.data) + 1
            data = file.read_bytes()
            self.data[asset_id] = data
            value = dict(id=asset_id, name=file.name, size=len(data),
                         digest='sha256:' + DELIVERY.hashlib.sha256(data).hexdigest())
            self.releases[release_id]['assets'].append(value)
            return value
        if binary:
            return self.data[int(path.rsplit('/', 1)[1])]
        return copy.deepcopy(self.releases[int(path.rsplit('/', 1)[1])])


class CiDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environ = dict(GITHUB_REPOSITORY='rotnroll/rerider', GITHUB_SHA='a' * 40,
                            GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME='push',
                            GITHUB_RUN_ID='100', GITHUB_RUN_ATTEMPT='1')
        self.plugin, self.source = DELIVERY.context('ReRider', '1.2', self.environ)
        self.service = FakeReleases()
        self.mock = patch.object(DELIVERY, 'api', side_effect=self.service.api)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def stage(self, platform='windows', source=None):
        directory = self.root / platform
        directory.mkdir(exist_ok=True)
        for name in DELIVERY.package_names(self.plugin, '1.2', platform):
            (directory / name).write_bytes(('CI-built ' + name).encode())
        return DELIVERY.stage(self.plugin, source or self.source, platform, directory)

    def fetch(self, release, source=None, require_main=False):
        return DELIVERY.fetch(self.plugin, source or self.source, 'windows', release['id'],
                              self.root / 'received', require_main)

    def test_both_platforms_round_trip_exact_bytes(self):
        for platform in ('windows', 'macos'):
            release = self.stage(platform)
            destination = self.root / ('received-' + platform)
            DELIVERY.fetch(self.plugin, self.source, platform, release['id'], destination, True)
            for name in DELIVERY.package_names(self.plugin, '1.2', platform):
                self.assertEqual((destination / name).read_bytes(), (self.root / platform / name).read_bytes())
        self.assertTrue(all(r['draft'] and r['prerelease'] for r in self.service.mutations))

    def test_branch_packages_are_available_without_publishing(self):
        source = dict(self.source, ref='refs/heads/Rel-1.2')
        release = self.stage(source=source)
        self.fetch(release, source)
        with self.assertRaisesRegex(ValueError, 'Only a push to main'):
            self.fetch(release, source, require_main=True)
        self.assertTrue(self.service.releases[release['id']]['draft'])

    def test_only_main_push_can_supply_website(self):
        release = self.stage()
        for event, ref in [('push', 'refs/heads/other'), ('push', 'refs/tags/v1.2'),
                           ('workflow_dispatch', 'refs/heads/main'), ('pull_request', 'refs/heads/main')]:
            with self.subTest(event=event, ref=ref), self.assertRaisesRegex(ValueError, 'Only a push to main'):
                self.fetch(release, dict(self.source, event=event, ref=ref), True)

    def test_pull_requests_cannot_stage(self):
        with self.assertRaisesRegex(ValueError, 'trusted push'):
            DELIVERY.context('ReRider', '1.2', dict(self.environ, GITHUB_EVENT_NAME='pull_request'))

    def test_different_commit_run_ref_version_and_platform_are_rejected(self):
        release = self.stage()
        for key, value in [('sha', 'b' * 40), ('run_id', '101'),
                           ('repository', 'someone/other'), ('version', '1.3'), ('ref', 'refs/heads/other')]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'provenance'):
                self.fetch(release, dict(self.source, **{key: value}))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            DELIVERY.fetch(self.plugin, self.source, 'macos', release['id'], self.root / 'wrong')

    def test_rerunning_publisher_reuses_successful_packages_from_same_run(self):
        release = self.stage()
        self.fetch(release, dict(self.source, run_attempt='2'), require_main=True)
        self.assertTrue((self.root / 'received' / 'ReRider-1.2-windows-x64.zip').is_file())

    def test_packages_cannot_claim_a_future_build_attempt(self):
        release = self.stage(source=dict(self.source, run_attempt='2'))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.fetch(release, self.source)

    def test_incomplete_extra_duplicate_or_published_assets_are_rejected(self):
        release = self.stage()
        original = copy.deepcopy(self.service.releases[release['id']])
        changes = [dict(assets=original['assets'][:1]),
                   dict(assets=original['assets'] + [dict(original['assets'][0], name='extra.zip')]),
                   dict(assets=original['assets'] + [original['assets'][0]]),
                   dict(draft=False, published_at='now'), dict(prerelease=False)]
        for change in changes:
            self.service.releases[release['id']] = dict(original, **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.fetch(release)

    def test_corrupt_content_manifest_size_and_server_digest_are_rejected(self):
        release = self.stage()
        stored = self.service.releases[release['id']]
        asset = stored['assets'][0]
        original = self.service.data[asset['id']]
        self.service.data[asset['id']] = b'bad'
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.fetch(release)
        self.service.data[asset['id']] = original
        for field, value in [('size', 999), ('digest', 'sha256:' + '0' * 64)]:
            saved = asset[field]
            asset[field] = value
            with self.assertRaisesRegex(ValueError, 'integrity'):
                self.fetch(release)
            asset[field] = saved
        record = json.loads(stored['body'])
        record['files'][asset['name']]['sha256'] = '0' * 64
        stored['body'] = json.dumps(record)
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.fetch(release)

    def test_missing_package_fails_before_creating_release(self):
        with self.assertRaisesRegex(ValueError, 'Missing or invalid package'):
            DELIVERY.stage(self.plugin, self.source, 'windows', self.root)
        self.assertEqual(self.service.mutations, [])

    def test_upload_failure_is_not_reported_as_success(self):
        real = self.service.api
        def failing(method, path, **kwargs):
            if kwargs.get('file'):
                raise RuntimeError('Upload rejected')
            return real(method, path, **kwargs)
        with patch.object(DELIVERY, 'api', side_effect=failing), self.assertRaisesRegex(RuntimeError, 'Upload rejected'):
            self.stage()
        self.assertTrue(all(r['draft'] for r in self.service.releases.values()))

    def test_staging_drafts_never_enter_website_catalog(self):
        self.stage('windows')
        self.stage('macos')
        config = json.loads((ROOT / 'plugins.json').read_text())
        catalog = CATALOG.build_catalog(config, list(self.service.releases.values()), DELIVERY.REPOSITORY, 'now')
        self.assertEqual(catalog['plugins']['rerider']['versions'], [])

    def test_backend_error_stops_fetch(self):
        release = self.stage()
        with patch.object(DELIVERY, 'api', side_effect=RuntimeError('Service unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'Service unavailable'):
                self.fetch(release, require_main=True)


if __name__ == '__main__':
    unittest.main()
