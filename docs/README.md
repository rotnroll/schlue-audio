# Adding a plug-in to Schlue Audio

This guide covers the one-time setup required to add a new plug-in repository to the Schlue Audio website, binary distribution, and download counter. New plug-ins are deliberately not added to the website automatically.

## 1. Prepare the plug-in build

The source repository needs a GitHub Actions workflow that builds and tests all supported packages before publishing:

- Windows x64 installer (`.exe`) and portable package (`.zip`)
- macOS universal installer (`.pkg`) and portable package (`.zip`)
- any required plug-in formats inside those packages, such as VST3, AU, or AAX

Upload the Windows and macOS package sets as separate GitHub Actions artifacts. Publishing must run only for a direct push to the source repository's `main` branch and only after every required build, test, and memory-safety job succeeds.

## 2. Add the central publisher call

Add a job like this to the source repository's build workflow:

```yaml
publish-binaries:
  name: Publish binaries to schlue-audio
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  needs:
    - required-windows-job
    - required-macos-job
    - required-test-job
  uses: rotnroll/schlue-audio/.github/workflows/publish-plugin.yml@main
  with:
    plugin-directory: ExamplePlugin
    version: "1.0"
    windows-artifact: ExamplePlugin-1.0-windows-x64
    macos-artifact: ExamplePlugin-1.0-macos-universal
  secrets:
    release_token: ${{ secrets.SCHLUE_AUDIO_RELEASE_TOKEN }}
```

Replace the job names, directory, version, and artifact names with the exact values used by the new repository.

Store the central release token in the source repository as an Actions secret named `SCHLUE_AUDIO_RELEASE_TOKEN`. The token itself needs Contents write access only to `rotnroll/schlue-audio`; it does not need access to the source repository after the secret has been stored.

## 3. Register the plug-in

Add one entry to `plugins.json` in this repository:

```json
{
  "id": "exampleplugin",
  "name": "ExamplePlugin",
  "directory": "ExamplePlugin",
  "releaseTagPrefix": "exampleplugin-v",
  "assetPrefix": "ExamplePlugin-"
}
```

Requirements:

- `id` is lowercase and unique.
- `directory` matches the `plugin-directory` publisher input.
- `releaseTagPrefix` is unique across the entire distribution repository.
- `assetPrefix` matches every user-facing binary filename.

The resulting Release tag is `<releaseTagPrefix><version>`, for example `exampleplugin-v1.0`.

## 4. Add the website files

Create:

```text
ExamplePlugin/index.html
assets/exampleplugin-logo.png
assets/exampleplugin-ui.png
```

Use an existing product page as the structural template, but write only current user-facing information: what the plug-in does, supported platforms/formats, its screenshot, and its Downloads section. Set these body attributes so the shared JavaScript can find the correct catalog entry:

```html
<body class="product-page" data-plugin="exampleplugin" data-root="..">
```

Add one card to the main `index.html`. Its count slot must use the same plug-in ID:

```html
<span class="plugin-download-count" data-download-count="exampleplugin"></span>
```

The shared Pages builder automatically includes product pages registered in `plugins.json`. It does not invent the page, description, screenshot, or overview card.

## 5. Package and Release naming

Use deterministic names for every version:

```text
ExamplePlugin-1.0-windows-x64-setup.exe
ExamplePlugin-1.0-windows-x64.zip
ExamplePlugin-1.0-macos-universal.pkg
ExamplePlugin-1.0-macos-universal.zip
SHA256SUMS.txt
```

Published versions are immutable. If the same tag already exists, the publisher accepts it only when its complete asset-name set and checksum manifest match. Changed binaries require a new version and tag.

## 6. Publish and verify

1. Merge the website registration and product page into `schlue-audio/main`.
2. Confirm the Pages workflow succeeds.
3. Push the finished plug-in version to the source repository's `main` branch.
4. Confirm all required source build/test jobs succeed.
5. Confirm the publisher creates the namespaced Release in `rotnroll/schlue-audio`.
6. Confirm the subsequent Pages deployment succeeds.
7. Open the product page and test every platform package and checksum link.
8. Confirm the version appears newest-first and the overview card shows a numeric count.

## Download-count behavior

GitHub maintains `download_count` separately for each Release asset. The Pages build sums all user-facing `.exe`, `.pkg`, and distributable `.zip` assets across every stable published version of the plug-in. Checksums, metadata, drafts, prereleases, and GitHub-generated source archives are excluded.

The number is not a unique-user count. One person downloading an installer and a ZIP contributes two downloads. Counts begin when a package becomes a GitHub Release asset; earlier repository-file downloads cannot be transferred.

Pages regenerates the public catalog when `main` changes, when a Release is published, on manual dispatch, and hourly so counts remain current without adding Git commits.

## Local checks before committing

From the `schlue-audio` repository root:

```text
python -m unittest discover -s tests -v
python scripts/build-site.py . _site
python scripts/generate-download-index.py . --output _site/downloads.json
python scripts/validate-site.py . --site-root _site --catalog _site/downloads.json
```

`GITHUB_TOKEN` may be set for authenticated API access, but it must never be committed or exposed in the generated website.
