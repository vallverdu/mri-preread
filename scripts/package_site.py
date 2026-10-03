"""Package the static website; optional owner imagery stays separate from public source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from public_demo import ARTIFACTS, DATASET, SUBJECT, validate
from site_photos import FILES as PHOTO_FILES, validate as validate_photos
from build_hero_volume import validate_payload

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
FILES = ['index.html', 'integrate.html', 'styles.css', 'site.js', 'site-config.js', 'hero-volume.js', 'hero-renderer.js',
         'assets/icon.svg', 'demo/artifacts.json', *ARTIFACTS, *PHOTO_FILES]
HEADER_ASSET = 'assets/owner-volume-header.jpg'
VOLUME_ASSET = 'assets/owner-hero-volume.json'
PUBLIC_VOLUME = 'data-volume="assets/hero-volume.json?v=preview-128-6"'
PUBLIC_HEADER = '<img id="heroImage" src="assets/hero-volume.jpg"'
PUBLIC_CREDIT = '<span id="heroSource">Viewer capture · Public OpenNeuro MRI · CC0</span>'
OWNER_CREDIT = '<span id="heroSource">Viewer capture · Owner-provided MRI study</span>'
OWNER_NOTICE = ('<p id="headerImageNotice">The homepage header includes an owner-provided MRI '
                'capture, used with permission for this website. That image is separate from the '
                'CC0 research demonstration and is not covered by the application\'s MIT license. '
                'It is excluded from the public source release.</p>')
OWNER_VOLUME_NOTICE = ('<p id="headerVolumeNotice">The interactive header also downloads an '
                       'owner-provided display-resolution MRI reference volume when activated. '
                       'It is private imaging data, included with permission for this website only, '
                       'separate from MIT and CC0 and excluded from public source. '
                       'The volume export contains no reports, patient metadata or annotations.</p>')


def package(output, header_image=None, hero_volume=None):
    """The optional image is a website-only addition; never relax the source-release audit."""
    out = Path(output).resolve()
    if not out.is_relative_to(ROOT / 'dist') or out.exists():
        raise ValueError('Choose a new output directory under dist/; previous packages are preserved')
    issues = validate(SITE) + validate_photos(SITE)
    if issues:
        raise ValueError('\n'.join(issues))
    header_bytes = None
    volume_bytes = None
    index = (SITE / 'index.html').read_text()
    guide = (SITE / 'integrate.html').read_text()
    if hero_volume is not None:
        if header_image is None:
            raise ValueError('An owner volume needs a matching owner header image')
        volume = Path(hero_volume)
        if volume.is_symlink() or not volume.is_file() or volume.stat().st_size > 8_000_000:
            raise ValueError('Hero volume must be a regular display export below 8 MB')
        volume_bytes = volume.read_bytes()
        validate_payload(json.loads(volume_bytes))
        if index.count(PUBLIC_VOLUME) != 1:
            raise ValueError('Hero volume markup changed; review the website-only substitution')
    if header_image is not None:
        image = Path(header_image)
        if image.is_symlink() or not image.is_file() or image.stat().st_size > 4_000_000:
            raise ValueError('Header image must be a regular JPEG file below 4 MB')
        header_bytes = image.read_bytes()
        if not header_bytes.startswith(b'\xff\xd8\xff') or not header_bytes.endswith(b'\xff\xd9'):
            raise ValueError('Header image must be JPEG; HTML and study files are not accepted')
        if index.count(PUBLIC_HEADER) != 1 or index.count(PUBLIC_CREDIT) != 1 or guide.count('<section id="license">') != 1:
            raise ValueError('Header or license markup changed; review the website-only substitution')
        index = index.replace(PUBLIC_HEADER, f'<img id="heroImage" src="{HEADER_ASSET}?v={hashlib.sha256(header_bytes).hexdigest()[:12]}"')
        index = index.replace(PUBLIC_CREDIT, OWNER_CREDIT)
        guide = guide.replace('<section id="license">', '<section id="license">' + OWNER_NOTICE)
        if volume_bytes is not None:
            index = index.replace(PUBLIC_VOLUME, f'data-volume="{VOLUME_ASSET}?v={hashlib.sha256(volume_bytes).hexdigest()[:12]}"')
            guide = guide.replace('<section id="license">', '<section id="license">' + OWNER_VOLUME_NOTICE)
        else:
            # A private poster must never silently switch to a different, public patient's volume.
            index = index.replace(PUBLIC_VOLUME, 'data-volume=""')
            index = index.replace('Interactive MRI overview · Load on demand', 'Owner-provided MRI capture')
    manifest = {'private_patient_data_included': header_bytes is not None,
                'raw_patient_data_included': False, 'model_weights_included': False,
                'private_display_volume_included': volume_bytes is not None,
                'public_research_data_included': True, 'stock_photography_included': True,
                'stock_photo_license': 'https://unsplash.com/license',
                'public_dataset': DATASET, 'public_subject': SUBJECT, 'files': {}}
    for name in FILES:
        source = SITE / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'Missing or unsafe site asset: {name}')
    for name in FILES:
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SITE / name, dest)
    if header_bytes is not None:
        (out / HEADER_ASSET).parent.mkdir(parents=True, exist_ok=True)
        (out / HEADER_ASSET).write_bytes(header_bytes)
        (out / 'index.html').write_text(index)
        (out / 'integrate.html').write_text(guide)
        manifest['owner_header_image'] = {'file': HEADER_ASSET,
            'license': 'Owner permission for this website; separate from MIT and CC0',
            'public_source_included': False}
    if volume_bytes is not None:
        (out / VOLUME_ASSET).write_bytes(volume_bytes)
        manifest['owner_hero_volume'] = {'file': VOLUME_ASSET,
            'license': 'Owner permission for this website; separate from MIT and CC0',
            'public_source_included': False, 'reports_and_annotations_included': False,
            'patient_metadata_included': False}
    for name in [*FILES, *([HEADER_ASSET] if header_bytes is not None else []), *([VOLUME_ASSET] if volume_bytes is not None else [])]:
        manifest['files'][name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return out, len(manifest['files'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/website-release')
    parser.add_argument('--header-image', type=Path,
        help='Opt in to one owner-approved JPEG for this website only; keep its input outside public source')
    parser.add_argument('--hero-volume', type=Path,
        help='Matching owner reference export from build_hero_volume.py; website only, never public source')
    args = parser.parse_args()
    try:
        out, count = package(args.output, args.header_image, args.hero_volume)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
    print(f'Static website package: {out}; {count} allowlisted files')


if __name__ == '__main__':
    main()
