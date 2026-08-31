# Publishing plug-in releases

For the full one-time setup of a new plug-in repository and website page, see [Adding a plug-in to Schlue Audio](README.md).

The reusable `.github/workflows/publish-plugin.yml` workflow publishes successful plug-in `main` builds as immutable GitHub Releases in `rotnroll/schlue-audio`. Feature branches and pull requests must not call the publisher.

## Release contract

- Tags use `<plugin-id>-v<version>`, for example `relatilt-v1.1`.
- Releases are stable only; draft and prerelease entries are not shown on the website.
- Binary assets are Windows `.exe`/`.zip` and macOS `.pkg`/`.zip` packages.
- Each release includes `SHA256SUMS.txt`.
- Published asset names and contents are immutable. Changed binaries require a new version.

Plugin metadata and tag prefixes are configured in `plugins.json`.

## Calling the publisher

The caller supplies the configured plug-in directory, version, and exact Windows and macOS Actions artifact names. It must map `release_token` to a secret containing a fine-grained token with Contents write permission for only `rotnroll/schlue-audio`:

```yaml
uses: rotnroll/schlue-audio/.github/workflows/publish-plugin.yml@main
with:
  plugin-directory: Relatilt
  version: "1.1"
  windows-artifact: RelaTilt-1.1-windows-x64
  macos-artifact: RelaTilt-1.1-macos-universal
secrets:
  release_token: ${{ secrets.SCHLUE_AUDIO_RELEASE_TOKEN }}
```

The workflow creates a draft, uploads packages and checksums, and publishes only after all uploads succeed. A rerun accepts an existing release only when the complete asset-name set and checksum manifest match.

## Download counts

The Pages build reads GitHub's public Release metadata and generates its catalog during deployment. A plug-in total is the sum of `download_count` for its user-facing binary assets across all stable published versions. Checksums, metadata, and GitHub-generated source archives are excluded. The catalog refreshes hourly without creating Git commits.
