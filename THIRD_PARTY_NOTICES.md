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

## Website photography

Two illustrative photographs are included under the [Unsplash License](https://unsplash.com/license),
verified on their individual photo pages on 2 October 2026:

- `site/assets/clinical-review.jpg`: [Accuray](https://unsplash.com/@accuray),
  [medical professionals reviewing a brain scan](https://unsplash.com/photos/medical-professionals-reviewing-brain-scan-5VkNa1LrS8A).
- `site/assets/tablet-review.jpg`: [Vitaly Gariev](https://unsplash.com/@silverkblack),
  [doctor showing a brain scan on a tablet](https://unsplash.com/photos/doctor-shows-brain-scan-on-tablet-in-office-8Ls2cnZwAaM).

These photos are not MIT or CC0. The Unsplash license permits free commercial/non-commercial use and
distribution, with restrictions on unmodified image sales and competing image services. Photographer
credits are included voluntarily. The website license link supplies the full terms.

The CDN supplied 1600 px JPEG versions; CSS may crop their presentation. They illustrate medical
review settings and do not depict this application, existing customers, partners or endorsements.
They are not model/evaluation inputs. See [source and checksum records](site/assets/photo-credits.json).
