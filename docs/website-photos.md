# Website imagery

The four feature previews are close-ups of actual application captures from the approved CC0
OpenNeuro study. They frame different evidence: linked planes, a ruler with ROI statistics, a
written note with a location marker, and a manual mask in 3D with a slice check. The MRI pixels,
measurement values, notes and painted voxels are unchanged. Each preview links to the full capture.

Run `python3 scripts/build_feature_details.py` to reproduce the SVG previews. The script verifies
the original screenshot hashes before framing them, embeds those exact JPEG bytes, and records
the derivative hashes in `site/demo/artifacts.json`. These self-contained SVGs work without
JavaScript and keep details visible in the two-column and mobile layouts.

The tablet image is the original reviewed Unsplash photograph by Vitaly Gariev, restored
unchanged on 3 October 2026. It illustrates a clinician holding an MRI tablet; it does not
depict this application or imply endorsement.

The consultation-room image is an **AI-generated illustration**, created on 3 October 2026
with the built-in OpenAI image_gen tool. Its people and setting are fictional. The actual
public viewer capture supplied the screen reference. It does not document clinical use,
represent a customer endorsement, or provide medical evidence. No private MRI was supplied.

Final assets:
- `site/assets/tablet-review.jpg` — 1600 × 900.
- `site/assets/clinical-review.jpg` — 1536 × 1024.
- `site/assets/feature-{views,measures,notes,masks}-detail.svg` — 1024 × 640.

Optimized JPEGs are served locally, with explicit dimensions and lazy loading. The generated
consultation PNG master is preserved outside the source release. The tablet uses its original
Unsplash license; the AI-generated consultation image uses MIT. The real MRI derivatives retain
their CC0 source dedication. The [website license](../site/license.txt) and
[source/generation/checksum record](../site/assets/photo-credits.json) provide provenance without
credits over the images.

The consultation composition reference was the previously reviewed free-license photograph by
[Accuray](https://unsplash.com/photos/medical-professionals-reviewing-brain-scan-5VkNa1LrS8A).
The current tablet photograph is by
[Vitaly Gariev](https://unsplash.com/photos/doctor-shows-brain-scan-on-tablet-in-office-8Ls2cnZwAaM).
Their source hashes, URLs and separate Unsplash license are retained in the record.

The release audit pins image bytes and generation records independently. Replacing an image
requires inspection, updated hashes and provenance in `scripts/site_photos.py`, and site/release checks.
Do not widen the MRI approval rules to include photographs or alter the original scan screenshots.

## Consultation generation prompt

### Clinical consultation

```text
Use case: photorealistic-natural.
Asset type: landscape website illustration, approximately 3:2 composition.
Input images: Image 1 is a reference for two clinicians reviewing two desktop screens ONLY, not an edit target; do not reproduce the people or fashionable room. Image 2 is an actual mri-preread application screenshot for one monitor.
Primary request: Create a new realistic documentary photograph of two doctors discussing a brain MRI at a workstation in a modest everyday hospital consultation or radiology office. One seated clinician at keyboard and mouse, one standing colleague leaning slightly toward the screens, both wearing plain practical white coats and focused on the scan, not the camera.
Surroundings: believable working clinic, simple off-white walls, ordinary desk and office chairs, standard fluorescent and window lighting, cable runs, a few papers and a pen, functional shelves; restrained everyday detail, not glamorous, no glass penthouse or designer furniture.
Composition: side three-quarter view with both doctors and TWO ordinary desktop monitors visible, screens large enough to recognize the application; do not block them with the doctors' bodies or hands.
Screens: faithfully insert Image 2 on one monitor with correct perspective and subtle physical reflections, keeping its dark viewer, real brain reconstruction and linked axial/coronal/sagittal images. The other monitor shows a plain neutral study list with no readable patient information. Do not create futuristic medical UI or imaginary scan anatomy.
Lighting/style: photorealistic candid hospital photography, realistic skin texture, modest lived-in materials, neutral colors and natural tonal range, no stock-fashion poses.
Constraints: two new fictional adults, no recognizable people from the reference, no logos, no watermarks, no patient names, no floating UI, no promotional text. Natural hands, coherent monitor geometry and practical consultation-room scale. Photograph only, not a collage or website layout.
```
