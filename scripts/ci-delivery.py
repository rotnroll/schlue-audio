"""Transfer CI packages through unpublished Releases, independently of Actions storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


REPOSITORY = "rotnroll/schlue-audio"
ROOT = Path(__file__).resolve().parents[1]


def api(method, path, *, payload=None, file=None, binary=False):
    command = ["gh", "api", path, "--method", method]
    data = None
    if payload is not None:
        command += ["--input", "-"]
        data = json.dumps(payload).encode("utf-8")
    if file is not None:
        command += ["-H", "Content-Type: application/octet-stream", "--input", str(file)]
    if binary:
        command += ["-H", "Accept: application/octet-stream"]
    result = subprocess.run(command, input=data, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout if binary else json.loads(result.stdout)


def context(directory, version, environ):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid version")
    plugin = next(p for p in json.loads((ROOT / "plugins.json").read_text())['plugins']
                  if p['directory'] == directory)
    source = {key: environ['GITHUB_' + variable] for key, variable in (
        ('repository', 'REPOSITORY'), ('sha', 'SHA'), ('ref', 'REF'),
        ('event', 'EVENT_NAME'), ('run_id', 'RUN_ID'), ('run_attempt', 'RUN_ATTEMPT'))}
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source['repository'])
            or not re.fullmatch(r"[0-9a-f]{40}", source['sha'])
            or not re.fullmatch(r"[1-9][0-9]*", source['run_id'])
            or not re.fullmatch(r"[1-9][0-9]*", source['run_attempt'])
            or source['event'] not in ('push', 'workflow_dispatch')
            or not source['ref'].startswith(('refs/heads/', 'refs/tags/'))):
        raise ValueError("Packages require a trusted push or manual CI run")
    return plugin, dict(schema=1, kind='ci-packages', plugin_directory=directory,
                        version=version, **source)


def package_names(plugin, version, platform):
    base = plugin['assetPrefix'] + version
    if platform == 'windows':
        return [base + '-windows-x64.zip', base + '-windows-x64-setup.exe']
    return [base + '-macos-universal.zip', base + '-macos-universal.pkg']


def tag_name(plugin, source, platform):
    return f"ci-{plugin['id']}-{source['run_id']}-{source['run_attempt']}-{platform}"


def stage(plugin, source, platform, directory):
    files = {}
    for name in package_names(plugin, source['version'], platform):
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 2 ** 31:
            raise ValueError(f"Missing or invalid package: {name}")
        files[name] = dict(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    record = dict(source=source, platform=platform, files=files)
    release = api('POST', f'repos/{REPOSITORY}/releases', payload={
        'tag_name': tag_name(plugin, source, platform), 'target_commitish': 'main',
        'name': f"CI {plugin['name']} {source['version']} / {source['run_id']} / {platform}",
        'body': json.dumps(record, sort_keys=True), 'draft': True, 'prerelease': True})
    if not release['draft'] or release['published_at'] is not None:
        raise ValueError("CI delivery must remain unpublished")
    for name in files:
        api('POST', f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release['id']}/assets?name={quote(name, safe='')}",
            file=directory / name)
    return release


def fetch(plugin, source, platform, release_id, output, require_main=False):
    if require_main and (source['event'] != 'push' or source['ref'] != 'refs/heads/main'):
        raise ValueError("Only a push to main may supply website packages")
    if not re.fullmatch(r"[1-9][0-9]*", str(release_id)):
        raise ValueError("Invalid source release ID")
    release = api('GET', f'repos/{REPOSITORY}/releases/{release_id}')
    record = json.loads(release['body'])
    built_source = record['source']
    # A rerun of only the publisher reuses successful build jobs from an earlier
    # attempt. They must still belong to this exact run, commit and source ref.
    attempt = built_source.get('run_attempt', '')
    if not re.fullmatch(r"[1-9][0-9]*", attempt) or int(attempt) > int(source['run_attempt']):
        raise ValueError("CI package provenance does not match this run")
    if (not release['draft'] or release['published_at'] is not None
            or not release['prerelease']
            or release['tag_name'] != tag_name(plugin, built_source, platform)
            or built_source != dict(source, run_attempt=attempt) or record['platform'] != platform):
        raise ValueError("CI package provenance does not match this run")
    names = set(package_names(plugin, source['version'], platform))
    assets = {a['name']: a for a in release['assets']}
    if (set(record['files']) != names or set(assets) != names
            or len(release['assets']) != len(names)):
        raise ValueError("CI package set is incomplete or contains unexpected files")
    output.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        asset = assets[name]
        expected = record['files'][name]
        data = api('GET', f"repos/{REPOSITORY}/releases/assets/{asset['id']}", binary=True)
        digest = hashlib.sha256(data).hexdigest()
        if (len(data) != expected['size'] or len(data) != asset['size']
                or digest != expected['sha256']
                or (asset.get('digest') and asset['digest'] != 'sha256:' + digest)):
            raise ValueError(f"CI package integrity check failed: {name}")
        (output / name).write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['stage', 'fetch'])
    parser.add_argument('--plugin-directory', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--platform', required=True, choices=['windows', 'macos'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--release-id')
    parser.add_argument('--require-main', action='store_true')
    args = parser.parse_args()
    plugin, source = context(args.plugin_directory, args.version, os.environ)
    if args.command == 'stage':
        release = stage(plugin, source, args.platform, args.directory)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
                output.write(f"release-id={release['id']}\n")
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
                summary.write(f"CI packages ({args.platform}): {release['html_url']}\n\n"
                              f"Source: `{source['repository']}@{source['sha']}`. Unpublished.\n")
        print(f"CI package release ID: {release['id']} (unpublished)")
    else:
        fetch(plugin, source, args.platform, args.release_id, args.directory, args.require_main)
        print(f"Verified {args.platform} packages from CI run {source['run_id']}")


if __name__ == '__main__':
    main()
