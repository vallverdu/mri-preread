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
artifact hashes validate. The two reviewed Unsplash website photos have their own pinned source/license
records and hashes. Labels alone cannot authorize a scan or photograph. This guard is
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
permissions are limited to the deployment job; no owner-image or owner-volume options are used.

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

The homepage first shows a white-background capture of the actual viewer. Selecting **Explore in 3D**
downloads a reference display volume and the actual viewer's ray marcher. Drag the reconstruction or
use arrow keys to rotate it. Three independent sliders cut the sagittal, coronal and axial axes;
cut faces show MRI intensities. Plus/minus zoom, **Reset view** restores the whole volume, and
**Show image** releases the rendering resources and returns to the capture. No automatic rotation or
background model inference runs. Drawing happens on demand and pauses when the header is offscreen.
Unsupported browsers or failed downloads retain the image.

The source version uses only the reviewed CC0 research study. Its reference volume is fetched only
after activation; the header does not load other sequences, annotations, reports or a model endpoint.
To substitute one owner-approved JPEG for
an independently hosted website, keep the input under ignored `data/` and opt in when packaging:

```bash
python3 scripts/package_site.py --output dist/website-owner-header \
  --header-image data/website-assets/header.jpg
```

This copies only that JPEG into the website package and updates the header credit and licensing notice.
It disables header interaction so the owner image never switches to an unrelated public volume.
It does not copy the study, notes, reports or model weights. The manifest marks private image inclusion
and records its hash. Owner permission applies to this website image separately from MIT and CC0.
The public source audit remains unchanged: this image is not committed or included in the source ZIP.
Without `--header-image`, the website package contains only the reviewed public assets.

To make the owner capture interactive, explicitly export the reference from the **same** prepared
viewer. Keep both inputs outside public source. Exporting is not anonymization: the display volume
remains private medical imagery and can retain identifying anatomy. Its publication needs the same
permission and delivery controls as the image itself.

```bash
.venv/bin/python scripts/build_hero_volume.py \
  --viewer data/owner-study/brain_viewer.html \
  --output data/website-assets/owner-reference.json --appearance volume
python3 scripts/package_site.py --output dist/website-owner-interactive \
  --header-image data/website-assets/header.jpg \
  --hero-volume data/website-assets/owner-reference.json
```

The export keeps only the reference's normalized uint8 voxels, spacing, dimensions and display window.
It uses anti-aliased linear interpolation to limit the longest axis to 128 voxels, preserving physical
proportions, and reduces intensities to 64 levels before compression. This is a lightweight visual
preview; the full viewer retains its existing image detail. Use `--max-axis 192 --intensity-bits 8`
when exporting if a larger, more detailed header is preferred. Rotation and three-axis cuts use the
same real MRI data at the selected preview resolution.
It excludes original DICOM/NIfTI files, identifying metadata, other sequences, annotations and model
reports. Packaging validates fields, geometry, voxel length and checksum. The browser checks the
same structure and length, and verifies SHA-256 when WebCrypto is available (HTTPS or localhost).
The manifest explicitly marks private display-volume inclusion. The volume and owner image
are website-only additions, excluded from Git and the clean source ZIP. This header is a visual overview;
use the full viewer for slice review, annotations and measurements.

After changing the full viewer shader, regenerate its shared header copy with
`python3 scripts/build_hero_volume.py --sync-renderer`; the consistency test detects drift.

On an existing S3/CloudFront site, use a new project prefix and an explicit `index.html` entry point;
set HTML/CSS/JS/SVG/PNG/JPEG/JSON content types and refresh only the changed cache paths. This release does not
change or overwrite the separately published private-scan viewer. For institutional patient viewers,
follow the controlled delivery requirements in [hospital-integration.md](hospital-integration.md).
