# Security and data handling

This is an early research project, not an authenticated hospital portal or a certified clinical product.
The local HTTP services bind to `127.0.0.1` and have no login or tenant isolation. Keep them local.

The generated viewer contains scan voxels, annotations and attached reports. A recipient can download
its content, including a head/face surface if the source covers it. Stripping a few DICOM identifiers
is not anonymization. Public demonstrations need synthetic data or an explicitly reviewed public-data
license/provenance exception. This website uses approved CC0 OpenNeuro derivatives; see
[open-demo.md](docs/open-demo.md). Private patient viewers need institution-controlled access,
sharing and retention policies. See [hospital integration](docs/hospital-integration.md).

MCP clients choose the model/provider. When a cloud model receives tool images, they leave the local
machine. The optional MLX MedGemma runner uses local weights with offline inference. Browser clinician
notes save in IndexedDB per browser origin and scan; clearing browser data removes them. Exported JSON
contains notes and segmentation and must be handled like the scan.

Report a vulnerability privately through the maintainer's [profile](https://github.com/vallverdu)
or contact route on [jordivallverdu.com](https://jordivallverdu.com). A dedicated security reporting
channel is not yet configured. Do not post patient images, credentials, real institution URLs or
reproduction exports in a public issue. Describe the affected version, behavior and a synthetic reproducer.
No security certification, response SLA, or regulatory conformity is claimed.
