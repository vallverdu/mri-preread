# Hospital and imaging-clinic integration

This guide describes an initial brain MRI research pilot. The browser viewer can complement image
delivery; local AI review remains experimental. Keep the clinical PACS/RIS and reading queue authoritative.
The repository is MIT licensed; infrastructure, integration effort and model terms remain separate.

## What runs where

| Layer | Implemented behavior | Requirements |
|---|---|---|
| Patient/clinician browser | One HTML containing volume data, 2D/3D views, measurements, notes and manual voxel masks | Current browser with WebGL2 and `DecompressionStream`; IndexedDB for local drafts; test your managed desktops |
| Preparation workstation | DICOM extraction or NIfTI import, brain-oriented processing, viewer build | Python 3.10+, scientific dependencies, storage for original exports and prepared data; verified here on macOS |
| MCP client | Spawns a per-study tool server through stdio; chosen model reads images and may write MCP annotations | Vision-capable, tool-capable MCP client; provider configuration approved by your institution |
| Local MedGemma | Fixed read-only sampled-image workflow using MCP tools | Apple Silicon Mac, macOS/Metal access and optional MLX runtime; weights downloaded once |
| Folder watcher | Serial completed-export processing with SQLite worklist and human review controls | Apple Silicon for integrated inference; local filesystem and `fcntl` lock; `.ready` export contract |
| Institutional portal | Authentication, patient/clinician access and controlled sharing | Supplied by your existing portal/integration; not included |

Opening a prepared viewer requires no viewer installation on Mac or Windows. Installing Python,
preparing a study and running the AI are workstation tasks. This release has no CUDA/Windows/CPU model
backend. A Linux preprocessing deployment requires local testing of its dependencies and protocols.
Browser operating-system compatibility does not imply inference-platform compatibility.

## Model-host independence

The viewer and stdio MCP tools do not require a particular accelerator. A compatible MCP client/agent
can bridge these tools to a chosen vision model endpoint on NVIDIA, llama.cpp or other supported
infrastructure. The client must handle image results and tool routing; an inference server by itself
is not an MCP client. Cloud endpoints receive supplied tool images.

The included `medgemma review` command and integrated worklist use one specific backend; their
prerequisites below do not define the whole application's hardware support. Replacing automatic-worker
inference needs an adapter and independent evaluation. See [model runtimes and hardware](hardware-and-model.md).

## 1. Obtain and install the source

After the maintainer publishes the audited source, clone its public URL. Until that URL is assigned,
the [source release procedure](public-release.md) produces a local ZIP with the same source.

```bash
# Replace REPOSITORY_URL with the actual published repository URL.
git clone REPOSITORY_URL mri-preread
cd mri-preread
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dicom-compressed]"
python3 -m http.server 8080 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8080/demo/` to test the full viewer using approved CC0 OpenNeuro MRI.
See [provenance and reproduction](open-demo.md); example drawings are not clinical labels. The demo is
a research illustration, not an AI accuracy evaluation or clinical interpretation. For Windows PowerShell, use `py -m venv .venv` and
`.venv\Scripts\python.exe -m pip install -e ".[dicom-compressed]"`; executable paths are then
`.venv\Scripts\mri-preread.exe`. Local Windows inference and the integrated watcher are not supported.

Pin the source commit and installed dependencies for each pilot. See
[hardware-and-model.md](hardware-and-model.md) for inference and [README.md](../README.md) for detailed CLI options.

## 2. Pilot one checked brain study

```bash
.venv/bin/mri-preread extract "/path/to/completed-dicom-export" data/pilot-study
# Inspect series.json and correct roles.json against the acquisition protocol before continuing.
.venv/bin/mri-preread analyze data/pilot-study
.venv/bin/mri-preread build data/pilot-study
```

Input must contain one patient/study. Classic single-frame MRI is the tested route; enhanced multi-frame
MRI is rejected by the watcher. Verify vendor-specific compressed transfer syntaxes and sequence-role
mapping with an institutional sample. Do not infer compatibility from file extension alone.

NIfTI import is an alternative:

```bash
.venv/bin/mri-preread import data/pilot-study \
  --flair "/path/to/flair.nii.gz" --dwi "/path/to/dwi.nii.gz" --adc "/path/to/adc.nii.gz"
.venv/bin/mri-preread analyze data/pilot-study
.venv/bin/mri-preread build data/pilot-study
```

Review geometry, orientation, reference spacing, alignment warnings, missing coverage and measurement
behavior against a trusted viewer. The viewer uses prepared/downsampled arrays; retain original DICOM
for authoritative interpretation. Import, registration and windows need local verification.

## 3. Add a viewer to image delivery

The generated `data/pilot-study/brain_viewer.html` is one self-contained file. Serve it from your
existing authenticated portal as `text/html; charset=utf-8`. If transferring a gzip copy, set
`Content-Encoding: gzip`. Verify your portal CSP permits the embedded scripts and data images; this
viewer currently embeds inline scripts, so a strict portal may need a separate controlled viewer route
or adapted hashing/nonce policy. Do not weaken your whole portal policy to accommodate it.

Use authorization checks on every request, including underlying object storage. A static URL by itself
is not an access-control mechanism. The file includes voxels, possibly identifiable facial anatomy,
annotations and reports. Clinical cases belong in controlled delivery, not a public product demo.
Sharing grants access to a downloadable copy and cannot revoke copies already saved by a recipient.

Clinician notes/masks save in each browser and can be exported/imported as JSON. They do not synchronize
to the PACS, portal or other doctors. Implement centralized storage, identity, review sign-off and audit
integration if those records must become part of the clinical record. The mask JSON is not DICOM SEG,
DICOM SR or NIfTI; any conversion must map the provided reference affine back to source geometry and be checked.

## 4. Connect an MCP-capable model client

Copy `.mcp.json.example` into the config location required by your chosen client. Replace both paths
with absolute paths to the installed executable and analyzed study. A generic stdio example is:

```json
{
  "mcpServers": {
    "mri-preread": {
      "command": "/absolute/path/mri-preread/.venv/bin/mri-preread",
      "args": ["serve", "/absolute/path/to/analyzed-study"]
    }
  }
}
```

A successful connection exposes the 16 tools listed in the README. Start with `get_study_overview`,
then `view_overview`, `view_region` and `region_stats`. The client needs to understand image tool results
and coordinate conventions. Tools for adding annotations mutate only that study's MCP annotation store.
They are distinct from browser-local clinician notes. `rebuild_standalone_viewer` embeds MCP annotations
for delivery. The live viewer is at `http://127.0.0.1:8765/` while the stdio server is running.

Each instance serves one study. A second study requires an independently configured process and HTTP
port (`BRAIN_VIEWER_PORT`), not concurrent mutation of one process's globals. There is no shared remote
MCP service, authentication layer or network multi-tenant API. Do not expose the loopback HTTP helper
as a hospital API. See the [official MCP documentation](https://modelcontextprotocol.io/docs/getting-started/intro).

MCP is a tool interface, not a guarantee that any LLM can read MRI images. Select a compatible vision
and tool-calling model/client. A cloud provider receives the image outputs given to its model; configure
data processing and access accordingly. The local MedGemma runner below operates without a cloud client.

## 5. Enable local MedGemma research drafts

On an Apple Silicon workstation, review the model's separate terms, then:

```bash
.venv/bin/python -m pip install -e ".[medgemma]"
.venv/bin/mri-preread medgemma download
.venv/bin/mri-preread medgemma smoke-test
.venv/bin/mri-preread medgemma review data/pilot-study \
  --sequences flair dwi adc --step-mm 10 --max-tokens 128
```

Only specify sequences present and verified in that study. The default uses available sequences.
`download` requires network access; subsequent inference loads local weights with offline mode enabled.
The smoke test checks runtime operation on a synthetic image. It does not measure clinical accuracy.
Use a regular local Terminal with Metal access. The runner does not execute generated model text as tools.

Successful review writes a new timestamped JSON, HTML trace and exact-input PNG directory, then rebuilds
the study viewer with its report. Inspect each sampled plane, original input, prompt and response. Changing
roles or preprocessing requires a new review. Ten-millimetre axial sampling can miss intervening lesions.
The current pilot flagged all 91 planes in six cases; it is unsuitable for automatic clinical priority.

## 6. Connect your completed-export pipeline

Your scanner/PACS export integration supplies immediate study folders to a local inbox. No DICOM C-STORE
receiver or DICOMweb connector is included. The existing system must write a completion signal:

```text
incoming-dicom/
  study-opaque-id/
    series-a/...
    series-b/...
    roles.json          optional verified mapping using the extractor's actual series names
    .ready              create last, after all files have been closed
```

Run the integrated watcher only after local model setup:

```bash
.venv/bin/mri-preread worklist \
  --inbox /srv/mri/incoming-dicom \
  --workspace /srv/mri/worklist \
  --model-dir /srv/mri/models/medgemma-1.5-4b-it-4bit
```

These are example paths; choose writable directories on your Mac workstation, and use the same model
path for `medgemma download --model-dir`. Inbox and workspace must be non-nested. `.ready` means the
export integration guarantees completeness; a folder that stops growing is not enough. The watcher
snapshots input, retains original DICOM metadata, rejects mixed studies, and records failures and warnings.
Human review and urgency are explicit. Do not replace the clinical reading queue with this research worklist.
For viewer-only processing, use the CLI commands in step 2; the integrated watcher always invokes MedGemma.

## 7. Measure institutional throughput and release scope

Count studies, image dimensions, sequences and sampled planes, not just weekly image files. The watcher
processes one study at a time and reloads a model per review process. An M5/16 GB inference demonstration
is not a benchmark for thousands of weekly studies. Measure complete-export-to-viewer and complete-export-
to-draft latency, memory/disk peaks, failures, and recovery on representative protocols.

For greater volume, design an external durable queue and isolated workspaces/workers, reserve accelerator
capacity, separate viewer delivery from optional AI jobs, and add monitoring/backpressure. Those adapters
and worker orchestration are not implemented here. A CUDA backend for the bundled automatic worker
requires an adapter; external model servers can already connect through a compatible MCP client.

Stage adoption: viewer usability checks → retrospective approved cases → viewer delivery pilot → AI shadow
review against expert labels → intended-use and operational review by your institution. Include readers,
IT, security and clinical governance. Measure missed findings and false flags as well as convenience;
keep validated human workflows available through every phase.

## Current integration gaps

- Brain-focused preparation and analysis; other anatomy needs new masks, alignment and candidate rules.
- No enhanced multi-frame ingestion, DICOM networking, PACS/RIS API, FHIR/HL7 write-back or DICOM SEG/SR export.
- No institution authentication, patient identity reconciliation, centralized annotation store or tenant isolation.
- No validated clinical diagnosis, AI urgency, clinical certification or high-volume performance guarantee.
- External GPU-server or llama.cpp vision models can use the tools through a compatible MCP client.
  The bundled review/worklist inference backend remains MLX; other automatic workers require an adapter.

These boundaries let an engineering team scope a realistic pilot rather than assume a turnkey hospital system.
