# CI package delivery

CI packages can be transferred without GitHub Actions artifact storage. Each
platform uploads its installer and ZIP into a separate unpublished draft Release
in `rotnroll/schlue-audio`. These drafts are also marked as prereleases. They do
not appear on the website and are not published by the transport script.

`scripts/ci-delivery.py stage` records the source repository, commit, ref, event,
run ID, attempt, version, platform, file sizes and SHA-256 hashes. It emits a
`release-id` step output only after both files have uploaded. Use the existing
`SCHLUE_AUDIO_RELEASE_TOKEN` in that step; no additional token scope is needed.
Pull requests must skip staging and never receive that secret.

The publisher accepts `windows-release-id` and `macos-release-id` instead of the
older `windows-artifact` and `macos-artifact` inputs. It checks the complete
package set, provenance and every downloaded file before preparing the public
Release. Both the publisher job and its package fetch require a direct push to
`refs/heads/main`. Every required build, test and memory-safety job must be in
the caller's `needs` list. Branch CI packages remain unpublished.

A rerun of a failed publisher may reuse successful packages from an earlier
attempt of the same CI run. Packages from another run, commit or ref are rejected.

The existing immutable, namespaced public Release and Pages deployment remain
the website delivery mechanism. Existing download URLs and counts are retained.
Older callers can continue using Actions artifacts until migrated.

Run `python -m unittest discover -s tests -v` to verify transfer, integrity,
provenance, publication restrictions and exclusion of drafts from the catalog.
