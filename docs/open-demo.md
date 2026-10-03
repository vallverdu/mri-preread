# Public MRI demo and illustrations

The website uses real T1w and FLAIR MRI from **OpenNeuro ds007401 / IDEAS II**, subject `sub-4082`,
session `ses-1`. The publisher's [dataset metadata](https://github.com/OpenNeuroDatasets/ds007401/blob/2e7f2573a5f8a9921cb19fca5e601bc141633f49/dataset_description.json)
specifies **CC0**. See [the dataset](https://openneuro.org/datasets/ds007401/versions/1.0.0) and
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

Requested T1/FLAIR citation: Taylor, Peter N., et al. “The imaging database for epilepsy and surgery
(IDEAS).” *Epilepsia* 66.2 (2025): 471–481. [DOI](https://doi.org/10.1111/epi.18192).
The website also includes separately credited [Unsplash stock photos](website-photos.md); those photos
are illustrative settings, not this dataset or app screenshots.

Dataset authors are credited in the pinned metadata. Their release does not imply endorsement of this
application. Code and the new MRI logo are MIT; dataset derivatives retain the CC0 dedication.

## What was changed

We selected two original anatomical sequences, canonicalized orientation, resampled to the reference
grid, rigidly aligned FLAIR, removed outside-brain voxels and packed windowed display arrays. The site
includes only the brain-masked viewer and derivatives. Original NIfTIs stay in ignored `data/`.
Brain masking is not a general anonymization guarantee for arbitrary institutional scans.

The axial/coronal/sagittal previews preserve physical aspect and use a 30 mm scale. The four feature
screenshots capture actual app operations: linked views, a ruler and ROI, a written note, and a manual
3D brush mask checked across slices. These demonstration drawings are **not lesion labels, an expert
reference or model predictions**. The MCP illustration is an actual `view_region` result. No AI report
is embedded in the public viewer; statistical candidates come from the preparation algorithm.

The header asset (`site/assets/hero-volume.jpg`) is a capture of the same public MRI reconstruction
on white, with interface overlays hidden. Its appearance comes directly from the viewer renderer; no
generative image model changed the anatomy. The shader background for this capture is `vec3(1.0)`
instead of the dark gradient. Camera framing and the white matte are presentation changes only.

The optional interactive header uses `site/assets/hero-volume.json`, derived from the reference
T1 array embedded in the public viewer. Its preview is anti-aliased and resampled to a maximum axis of
128 voxels, with 64 intensity levels in the same uint8 texture format. The download is about 390 KB
(formerly 1.63 MB); the full viewer's images remain unchanged. It contains only display voxels, physical spacing, dimensions
and rendering settings. It loads after **Explore in 3D**, keeps a static-image fallback, and supports
rotation, zoom and independent cuts on three axes. The camera math and ray-marching shader in
`site/hero-renderer.js` are generated from `viewer_template.html`, with only the background set to white.
Cut faces use the viewer's grayscale MRI window. This is an overview, not a replacement for full slice
review. Its checksum is recorded alongside the other reviewed public derivatives.

The public demo establishes usability, not diagnostic accuracy. It is separate from the ignored
labelled evaluation datasets. The ISLES archive is not redistributed: its bundled terms include a
written-permission condition despite its CC BY metadata.

## Rebuild from the pinned public inputs

Install the project following the README, then:

```bash
.venv/bin/python examples/build_public_demo.py --download
python3 -m http.server 8080 --bind 127.0.0.1 --directory site
```

The approximately 8 MB download contains only the two selected anatomical inputs. Before import, the
builder verifies their SHA-256 against the publisher's git-annex keys at commit
`2e7f2573a5f8a9921cb19fca5e601bc141633f49`. It refuses different inputs. The dataset DOI and original
checksums are in [source-record.json](../site/demo/source-record.json). This is a curated exception,
not a command to publish any scan.

The default workspace is `data/public-demo-openneuro`. Existing workspaces are preserved; choose a
new `--workspace data/public-demo-rebuild` for a fresh preparation. `--reuse` is only for the verified
public workspace during local development. It is not a substitute for checking modified derivatives.

The builder writes `site/demo/index.html` and three previews. Feature screenshots require actual UI
capture after a viewer change: open the public demo, perform the captioned actions, and save the four
captures as `site/assets/feature-{views,measures,notes,masks}.jpg`. Use demonstration text only and
review all visible information. No private study may be used for these paths. To regenerate the MCP
illustration from the default prepared public workspace:

```bash
.venv/bin/python eval/mcpcall.py data/public-demo-openneuro view_region \
  '{"x":86,"y":94,"z":84,"sequences":["t1","flair"],"fov_mm":100}' \
  data/public-demo-openneuro/mcp-feature
cp data/public-demo-openneuro/mcp-feature_1.png site/assets/feature-mcp.png
```

After reviewing the derivatives, record their integrity and check the release:

```bash
python3 scripts/seal_public_demo.py --workspace data/public-demo-openneuro
python3 scripts/check_site.py
python3 scripts/release_audit.py --include-untracked
```

`site/demo/artifacts.json` records the exact allowlisted derivative hashes and pinned source record.
The release guard rejects changed assets, absent provenance, another subject/license and unapproved
embedded viewers or raster files. Hashes detect changes; they cannot prove anonymization or replace
review. Do not reseal a changed asset merely to suppress an audit failure.

## Synthetic regression fixture

`examples/build_synthetic_demo.py` remains available for geometry and viewer regression checks. Its
default output is now `data/synthetic-demo/index.html`, so it cannot silently replace the real website
demo. CI builds this ignored fixture and validates the separately bundled public dataset derivatives.
