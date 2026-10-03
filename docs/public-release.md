# Prepare and publish public source

The repository contains application source, institutional integration documentation and reviewed CC0
OpenNeuro MRI derivatives. Private scans, raw NIfTIs, local MCP config, reports, exported notes and model
weights remain ignored. See [public demo provenance](open-demo.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).
The private viewer already hosted on a personal website is not part of this public source/demo.

## Audit and preserve the local history

An older revision of `docs/KNOWLEDGE.md` described a private study. Removing the text from the latest
file does not remove that historical disclosure. Do not push the local development history publicly.
Prepare a new public repository from the clean source export below; the local repo and history stay intact.

```bash
.venv/bin/python -m unittest discover -s tests
node --test tests/test_*.cjs
.venv/bin/python examples/build_synthetic_demo.py
python3 scripts/check_site.py
python3 scripts/release_audit.py --history
# Commit the reviewed public source, then export:
python3 scripts/export_public_release.py --output dist/public-release
```

`release_audit.py` examines tracked paths and content for known data/config/model/credential patterns,
with values withheld from findings. It permits only the narrowly allowlisted CC0 demo derivatives when their pinned source record and
artifact hashes validate. The two reviewed AI-generated clinical illustrations have their own pinned
generation, composition-reference and license records and hashes. Labels alone cannot authorize a scan or photograph. This guard is
not a guarantee of anonymization or comprehensive secret detection; inspect newly added files.
`export_public_release.py` requires a clean committed tree, exports only tracked audited files, and
writes a SHA-256 manifest and `mri-preread-source.zip`. No `.git`, ignored file or private history is copied.
Existing output directories are refused; use a new release directory for later snapshots.

## Start the public Git history

Once the maintainer selects the actual public repository URL:

```bash
cd dist/public-release/mri-preread
git init -b main
git add .
git commit -m "Initial public source release"
git remote add origin PUBLIC_REPOSITORY_URL
git push -u origin main
```

Create the destination repository first without importing this local history. Do not use `git push
--mirror`, upload the working directory as an unrestricted archive, or make the local repo public as-is.
The archive includes CI, contribution guidance, a synthetic-data issue template and dependency/model
licensing notes. Check the hosted source tree and repository settings after the first push.

## Publish the website

The public repository is [vallverdu/mri-preread](https://github.com/vallverdu/mri-preread), and the
website is [vallverdu.github.io/mri-preread](https://vallverdu.github.io/mri-preread/).
The Pages workflow in `.github/workflows/pages.yml` audits the public source, checks local links and
JavaScript, packages the explicitly approved public assets, and deploys that package. It runs for
changes to the site, packaging scripts or workflow on `main`, and can also be started manually.
Choose **GitHub Actions** as the Pages publishing source in the repository settings. Deployment
permissions are limited to the deployment job. When the repository variable `MRI_OWNER_HEADER_RELEASE` is set to an approved asset release,
the build downloads its two header files, checks `site/owner-header.sha256`, and passes them
explicitly to the packager. An unset variable uses the public CC0 fallback. Original studies, notes and reports are excluded.

The site is plain HTML, CSS and JavaScript: no framework, build service, analytics, remote fonts or
model endpoint. The embedded demonstration uses brain-masked public OpenNeuro MRI and the actual viewer code.
Feature screenshots show actual app operations; demonstration notes and masks are not lesion ground truth.
Separately credited [Unsplash photos](website-photos.md) illustrate medical review settings; their license
is separate from MIT code and CC0 MRI data.

```bash
# After the public repository exists, wire its clone URL and source buttons.
python3 scripts/configure_site.py --repo-url https://github.com/OWNER/REPOSITORY
python3 scripts/check_site.py
python3 scripts/package_site.py --output dist/website-release
```

Upload only the produced `dist/website-release/` directory to a dedicated static project prefix or
static hosting service. It includes the product page, integration page, local assets and demo. It does
not include private patient data, original NIfTIs, Python tools, local configuration or model weights.
The package manifest explicitly records public research data inclusion and each file's SHA-256. Do not sync the repository's `data/` directory to hosting.

### Interactive header and website-only owner imagery

The homepage paints a white-background MRI poster immediately, then downloads the reference
preview and renderer automatically in the background. The image remains visible until the first
volume frame succeeds, with no layout shift or load button. The header always uses the volume
transfer function, including during a cut; it never switches to surface rendering.

A slow, repeating coronal cut traverses front to back and returns. Scroll over the head to change
that same depth; wheel input, dragging, the depth slider or keyboard interaction pauses the sweep.
Drag to rotate, use left/right keys to rotate, up/down to change depth, plus/minus to zoom, Space
to play/pause and Home to reset. The visible Play/Pause and Reset controls also work on touch screens.
Reduced-motion preferences disable automatic animation. Background tabs and an offscreen header
pause rendering and animation. Failed loading or unsupported browsers retain the poster.
This is a visualization; no model or report endpoint is invoked.

Image authors, sources and license notices are consolidated in `site/license.txt`, linked in the
footer. The package appends owner-image notices there rather than placing credits over the imagery.

The source preview retains the reviewed CC0 research study. For the live website, the owner has
approved publication of one poster and the matching simplified MRI volume. When publication is approved for GitHub, they are hosted as
separate GitHub release assets, outside the source tree/history and the clean source ZIP. Set `MRI_OWNER_HEADER_RELEASE` to that release tag only after the upload is approved and
completed, then dispatch the Pages workflow. The build verifies both pinned hashes before packaging them. This does not authorize uploading
any other private study files. The release-asset permission is separate from MIT and CC0.

To prepare an equivalent owner-approved deployment, keep inputs in ignored `data/` and opt in:

```bash
.venv/bin/python scripts/build_hero_volume.py \
  --viewer data/owner-study/brain_viewer.html \
  --output data/website-assets/owner-reference.json --max-axis 160 --intensity-bits 8 --appearance volume
python3 scripts/package_site.py --output dist/website-owner-interactive \
  --header-image data/website-assets/header.jpg \
  --hero-volume data/website-assets/owner-reference.json
```

An image-only package disables volume loading so it cannot switch to another subject's volume.
Without the owner options, packaging includes only the reviewed public imagery. Exporting a volume
is not anonymization; the owner preview can retain identifying facial anatomy, and is published
here with the owner's explicit permission. Your own patient deployments need their own authority.

The export keeps only the reference's normalized uint8 voxels, spacing, dimensions and display window.
It uses anti-aliased linear interpolation to limit the longest axis to 128 voxels, preserving physical
proportions, and reduces intensities to 64 levels before compression. This is a lightweight visual
preview; the full viewer retains its existing image detail. Use `--max-axis 192 --intensity-bits 8`
when exporting if a larger, more detailed header is preferred. Rotation and front-to-back cuts use the
same real MRI data at the selected preview resolution. The live owner preview uses a 160-voxel
axis limit and 8-bit intensities (about 2.35 MB) to balance load time and volume detail.
It excludes original DICOM/NIfTI files, identifying metadata, other sequences, annotations and model
reports. Packaging validates fields, geometry, voxel length and checksum. The browser checks the
same structure and length, and verifies SHA-256 when WebCrypto is available (HTTPS or localhost).
The manifest explicitly marks private display-volume inclusion. The volume and owner image
are website-only additions, excluded from Git source history and the clean source ZIP. This header is a visual overview;
use the full viewer for slice review, annotations and measurements.

After changing the full viewer shader, regenerate its shared header copy with
`python3 scripts/build_hero_volume.py --sync-renderer`; the consistency test detects drift.

On an existing S3/CloudFront site, use a new project prefix and an explicit `index.html` entry point;
set HTML/CSS/JS/SVG/PNG/JPEG/JSON content types and refresh only the changed cache paths. This release does not
change or overwrite the separately published private-scan viewer. For institutional patient viewers,
follow the controlled delivery requirements in [hospital-integration.md](hospital-integration.md).
