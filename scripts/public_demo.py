"""The narrowly approved public MRI derivative set; not a general anonymization check."""
import hashlib
import json
from pathlib import Path
from build_hero_volume import validate_payload

DATASET = 'ds007401'
SUBJECT = 'sub-4082'
COMMIT = '2e7f2573a5f8a9921cb19fca5e601bc141633f49'
INPUT_SHA256 = {
    't1': '838411f3596192c9c24f3cf171a6bbc9284d3e7c108abcdb49d3537ee13c2424',
    'flair': 'eef385a0599c2a7d58aac1f0f66df1b40071c2b3050e114004119e42d91ae197',
}
MARKER = b'OpenNeuro ds007401 / sub-4082 / CC0'
ARTIFACTS = (
    'demo/index.html', 'demo/source-record.json',
    'assets/axial.png', 'assets/coronal.png', 'assets/sagittal.png', 'assets/hero-volume.jpg', 'assets/hero-volume.json',
    'assets/feature-views.jpg', 'assets/feature-measures.jpg',
    'assets/feature-notes.jpg', 'assets/feature-masks.jpg', 'assets/feature-mcp.png',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_record(record):
    return (record.get('dataset') == DATASET and record.get('subject') == SUBJECT
            and record.get('publisher_commit') == COMMIT and record.get('input_sha256') == INPUT_SHA256
            and record.get('license') == 'CC0-1.0' and record.get('private_scan_included') is False
            and record.get('model_predictions_included') is False)


def validate(site):
    """Return issues without inspecting private studies or trusting an HTML label alone."""
    site = Path(site)
    try:
        manifest_path = site / 'demo/artifacts.json'
        record_path = site / 'demo/source-record.json'
        if manifest_path.is_symlink() or record_path.is_symlink():
            return ['public demo provenance must be regular files']
        manifest = json.loads(manifest_path.read_text())
        record = json.loads(record_path.read_text())
        if not isinstance(record, dict) or not check_record(record):
            return ['public demo source or license is not approved']
        if not isinstance(manifest, dict) or manifest.get('source') != record:
            return ['public demo manifest disagrees with source record']
        hashes = manifest.get('files', {})
        if not isinstance(hashes, dict) or set(hashes) != set(ARTIFACTS):
            return ['public demo artifact list is not approved']
        issues = []
        for name in ARTIFACTS:
            path = site / name
            if path.is_symlink() or not path.is_file() or sha(path) != hashes[name]:
                issues.append(f'public demo asset missing, unsafe or changed: {name}')
        if not issues and MARKER not in (site / 'demo/index.html').read_bytes():
            issues.append('public demo dataset credit missing')
        if not issues:
            validate_payload(json.loads((site / 'assets/hero-volume.json').read_text()))
        return issues
    except (OSError, ValueError, TypeError, AttributeError):
        return ['public demo provenance missing or malformed']
