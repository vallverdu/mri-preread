# Website photos

The two selected Unsplash photographs illustrate clinical review settings. The product gallery and
interactive demo still use actual app captures and the approved CC0 OpenNeuro MRI study.

Credits and source/license links are visible below each photo and in the integration guide. See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and
[photo-credits.json](../site/assets/photo-credits.json). The photograph licenses are separate from MIT
application code and CC0 MRI derivatives. Neither photograph depicts the application or establishes
use or endorsement by the people or organizations shown.

Images are served locally, with explicit dimensions, lazy loading and responsive CSS. There are no
Unsplash requests when someone visits the product website. The two optimized JPEGs total about 350 KB.

`scripts/site_photos.py` pins the reviewed photo URLs, authors, license record and file hashes.
The release audit rejects other raster files, changed photos and missing/altered credit records;
the website packager validates and includes only these approved photos. Do not widen the MRI demo
allowlist to add stock images. Keep the two types of provenance separate.

To replace a photograph, check its individual free-license page, inspect the actual image and caption,
download it from its documented source, then update the pinned record, image dimensions, visible
credits and third-party notices. Search categories alone do not establish modality or license.
Review and run the site/release checks before packaging. Unused downloaded candidates stay ignored.
