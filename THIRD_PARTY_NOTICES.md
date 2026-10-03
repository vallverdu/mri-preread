# Third-party notices

Application source and the MRI bore/brain logo are MIT licensed; see [LICENSE](LICENSE).
Dependencies retain their respective licenses. No model weights are distributed.

## Public MRI illustrations

`site/demo/index.html`, the three slice previews, four feature screenshots and the MCP image montage
derive from OpenNeuro **ds007401 / IDEAS II**, `sub-4082`, `ses-1`, original T1w and FLAIR sequences.
The [publisher metadata](https://github.com/OpenNeuroDatasets/ds007401/blob/2e7f2573a5f8a9921cb19fca5e601bc141633f49/dataset_description.json)
specifies [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
Dataset DOI: [10.18112/openneuro.ds007401.v1.0.0](https://doi.org/10.18112/openneuro.ds007401.v1.0.0).

Requested anatomical-image citation: Taylor, Peter N., et al. “The imaging database for epilepsy and
surgery (IDEAS).” *Epilepsia* 66.2 (2025): 471–481. [10.1111/epi.18192](https://doi.org/10.1111/epi.18192).
The publisher metadata lists the dataset contributors. Credit does not imply endorsement.

We added alignment, resampling, brain masking, windowing and demonstration notes/measurements/masks.
These drawings are not clinical annotations or model findings. See [demo provenance](docs/open-demo.md),
[input checksums](site/demo/source-record.json) and [derivative hashes](site/demo/artifacts.json).
Private studies and original NIfTIs are excluded from the public packages.

## MedGemma

Google MedGemma weights have separate [Health AI Developer Foundations terms](https://developers.google.com/health-ai-developer-foundations/terms).
The application MIT license does not relicense those weights, including community conversions.
Review the chosen model and runtime's terms before deployment.

## Website clinical illustrations

The tablet and consultation-room images are generated illustrations of fictional clinicians,
created with OpenAI's built-in image_gen tool on 3 October 2026 and distributed under MIT.
They use the approved public viewer capture as a screen reference; no private MRI was supplied.
They do not document a real deployment, represent clinical evidence, or imply endorsement.

Composition references were previously reviewed photographs under the
[Unsplash License](https://unsplash.com/license), verified on 2 October 2026:
[Accuray's workstation scene](https://unsplash.com/photos/medical-professionals-reviewing-brain-scan-5VkNa1LrS8A)
and [Vitaly Gariev's tablet scene](https://unsplash.com/photos/doctor-shows-brain-scan-on-tablet-in-office-8Ls2cnZwAaM).
The original photos are not shipped in the current website; their source records and original
hashes are retained in [photo-credits.json](site/assets/photo-credits.json). Their historical
versions retain the original Unsplash license.

See [generation prompts and reproduction](docs/website-photos.md) and the
[website license file](site/license.txt). Actual feature screenshots and their close-up SVG
derivatives retain the CC0 MRI provenance above; their anatomy was not generated.
