"""Integrity and provenance for the the reviewed tablet photograph and AI consultation illustration."""
import hashlib
import json
from pathlib import Path

CREDITS = 'assets/photo-credits.json'
# Pin the generation record independently of the packaged JSON: editing the JSON
# must never approve replacement images or altered source/license claims.
RECORD = json.loads(r'''{
  "license": "Per-image: MIT / Unsplash License",
  "usage": "One licensed tablet photograph and one AI-generated consultation illustration; neither documents customers, deployments or clinical evidence.",
  "private_scan_used": false,
  "photos": {
    "assets/clinical-review.jpg": {
      "origin": "AI-generated",
      "sha256": "a406ed20a527f77dfa526bbfd4b6c7b2fc280834213c789a26a6f3a2b6c70c30",
      "width": 1536,
      "height": 1024,
      "composition_reference": {
        "photo_id": "5VkNa1LrS8A",
        "photographer": "Accuray",
        "photo_url": "https://unsplash.com/photos/medical-professionals-reviewing-brain-scan-5VkNa1LrS8A",
        "photographer_url": "https://unsplash.com/@accuray",
        "sha256": "5a7d22695e06abc90a4c5a2c7fe188b88ef9373612ba7fb170cf67ae3e307ea2"
      },
      "prompt": "Use case: photorealistic-natural.\nAsset type: landscape website illustration, approximately 3:2 composition.\nInput images: Image 1 is a reference for two clinicians reviewing two desktop screens ONLY, not an edit target; do not reproduce the people or fashionable room. Image 2 is an actual mri-preread application screenshot for one monitor.\nPrimary request: Create a new realistic documentary photograph of two doctors discussing a brain MRI at a workstation in a modest everyday hospital consultation or radiology office. One seated clinician at keyboard and mouse, one standing colleague leaning slightly toward the screens, both wearing plain practical white coats and focused on the scan, not the camera.\nSurroundings: believable working clinic, simple off-white walls, ordinary desk and office chairs, standard fluorescent and window lighting, cable runs, a few papers and a pen, functional shelves; restrained everyday detail, not glamorous, no glass penthouse or designer furniture.\nComposition: side three-quarter view with both doctors and TWO ordinary desktop monitors visible, screens large enough to recognize the application; do not block them with the doctors' bodies or hands.\nScreens: faithfully insert Image 2 on one monitor with correct perspective and subtle physical reflections, keeping its dark viewer, real brain reconstruction and linked axial/coronal/sagittal images. The other monitor shows a plain neutral study list with no readable patient information. Do not create futuristic medical UI or imaginary scan anatomy.\nLighting/style: photorealistic candid hospital photography, realistic skin texture, modest lived-in materials, neutral colors and natural tonal range, no stock-fashion poses.\nConstraints: two new fictional adults, no recognizable people from the reference, no logos, no watermarks, no patient names, no floating UI, no promotional text. Natural hands, coherent monitor geometry and practical consultation-room scale. Photograph only, not a collage or website layout.",
      "license": "MIT",
      "created_on": "2026-10-03",
      "generator": "OpenAI built-in image_gen",
      "viewer_reference": "assets/feature-views.jpg",
      "viewer_dataset": "OpenNeuro ds007401 / sub-4082 / CC0-1.0"
    },
    "assets/tablet-review.jpg": {
      "origin": "Unsplash photograph",
      "license": "Unsplash License",
      "license_url": "https://unsplash.com/license",
      "license_verified_on": "2026-10-02",
      "photo_id": "8Ls2cnZwAaM",
      "photographer": "Vitaly Gariev",
      "photo_url": "https://unsplash.com/photos/doctor-shows-brain-scan-on-tablet-in-office-8Ls2cnZwAaM",
      "photographer_url": "https://unsplash.com/@silverkblack",
      "sha256": "9cd2c3d96b118bb276c30676e330a74ec8a915cfd75416f56dbd7809df0e101d",
      "download_url": "https://images.unsplash.com/photo-1758691462774-f01ed567f2c4?auto=format&fit=max&fm=jpg&q=82&w=1600",
      "width": 1600,
      "height": 900,
      "modifications": "CDN resize to 1600 pixels wide and JPEG compression; CSS crop for responsive layout.",
      "usage": "Illustrative stock photography; does not depict this application, its users or an endorsement."
    }
  }
}''')
PHOTOS = RECORD['photos']
FILES = (*PHOTOS, CREDITS)


def validate(site):
    site = Path(site)
    try:
        credits = site / CREDITS
        if credits.is_symlink() or json.loads(credits.read_text()) != RECORD:
            return ['website illustration generation/source record is not approved']
        issues = []
        for name, record in PHOTOS.items():
            path = site / name
            if (path.is_symlink() or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']):
                issues.append(f'website illustration missing, unsafe or changed: {name}')
        return issues
    except (OSError, ValueError, TypeError):
        return ['website illustration record missing or malformed']
