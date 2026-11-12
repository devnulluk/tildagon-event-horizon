# Publishing Event Horizon

The official store discovers a **public** GitHub or Codeberg repository carrying
the `tildagon-app` topic and a published release. There is no developer portal,
upstream pull request or separate upload approval. The official guide allows
about 15 minutes for indexing.
See [Publish your app](https://tildagon.badge.emfcamp.org/tildagon-apps/publish/).

This app uses one root `tildagon.toml`, with the `Media` category and MIT license.
`app.py` defines `EventHorizon` and `__app_export__ = EventHorizon`. Both frontboards
are declared optional; a bare badge can run the show. Keep the manifest version
and release tag aligned, initially `0.1.0` / `v0.1.0`.

The current [manifest schema](https://github.com/emfcamp/badge-2024-app-store/blob/main/packages/tildagon-app/src/TildagonAppManifest.ts)
requires name/category and author/license/source URL/description/version. It has
no screenshot, icon, pricing or `app.files` field. Current code accepts TOML or
JSON but rejects a repository containing both `tildagon.toml` and `tildagon.json`.
Some older documentation still says JSON is unsupported; the
[current GitHub registry](https://github.com/emfcamp/badge-2024-app-store/blob/main/packages/tildagon-app-directory-core/src/sources/github.ts)
is the source of truth for that behavior.

## Keep the badge download small

Release **0.1.0** was verified in the live store on 12 November 2026. The store
record points to commit `706805e8141d389e01bd4011d3b03a2347a9c3b2`; its cached
download is 27,062 bytes and contains 13 runtime files (88,170 bytes unpacked).
The validator checked every file against the release source. The
[publication record](store-publication.json) preserves that result.

The registry selects the newest release by creation time and downloads its
**commit source tarball**. Uploaded custom runtime archives are not selected.
The repository can contain videos, screenshots and soundtrack downloads, while
the committed `.gitattributes` excludes all but flat runtime Python files,
`tildagon.toml` and `LICENSE` from that source archive. Put development scripts
under `tools/` and tests under `tests/`, never beside the runtime modules.

This follows the official publishing guide's `export-ignore` advice and Git's
[archive attributes](https://git-scm.com/docs/gitattributes#_creating_an_archive).
An uploaded small release asset cannot repair an oversized source archive.
Check the actual archive before publishing; the badge needs memory to download
and decompress it. Our validator limits the runtime payload to 100,000 bytes.

With Python 3.11+ (or Python 3.10 plus `tomli`) and Git:

```powershell
python tools/validate_manifest.py
python tools/validate_manifest.py --git-ref HEAD --write-archive event-horizon-runtime.tar.gz
```

The first command validates working files. The second validates the committed
archive, rejects documentation/media or missing modules, and writes only a
validated archive. Commit `.gitattributes` before creating the release tag.
Do not commit the generated runtime archive; a release attachment is optional.

## Publish and verify

After simulator, hardware and content checks pass:

1. Push the complete public repository to
   `https://github.com/devnulluk/tildagon-event-horizon`.
2. Apply the `tildagon-app` repository topic.
3. Create a normal published GitHub release for the tested commit, such as
   `v0.1.0`. A tag alone is insufficient. Keep unready releases as drafts.
4. Download the release's **Source code (tar.gz)** and validate that archive,
   then wait for indexing and verify the store's own cached download.

```powershell
python tools/validate_manifest.py --archive path/to/source-code.tar.gz
python tools/validate_manifest.py --check-store --expected-commit FULL_TESTED_COMMIT_SHA
```

For that exact owner/repository, the current store algorithm produces code
**21344014**. Verify it online after publication; identity collisions are checked
by the validator. The expected page is
[Event Horizon](https://apps.badge.emfcamp.org/apps/21344014/), and the listing API
is [the app record](https://apps.badge.emfcamp.org/v1/apps/21344014).
The badge installs through App Store → CodeInstall using the eight digits.
The store page displays those digits and button instructions; a QR code is not
required. Screenshots and videos belong in the repository README.

If indexing takes longer than 15 minutes, inspect the
[official errors page](https://apps.badge.emfcamp.org/errors) and confirm the
repository is public, unarchived, topic-tagged and has a valid published release.
Releases are pinned to a commit, so fixes need a new version and release rather
than editing a previously published tag.
