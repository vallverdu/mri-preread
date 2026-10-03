"""Check an explicit source-file list for accidental patient data or credentials.

This is a release guard, not a proof of anonymization. Never scans ignored study directories.
"""
import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath
from public_demo import ARTIFACTS, validate
from site_photos import PHOTOS, validate as validate_photos

ROOT = Path(__file__).resolve().parents[1]
BAD_EXT = ('.dcm', '.nii', '.nii.gz', '.npz', '.npy', '.nrrd', '.mha', '.mhd', '.ima', '.img', '.hdr',
           '.safetensors', '.gguf', '.pt', '.pth', '.ckpt', '.onnx', '.h5', '.hdf5', '.sqlite', '.sqlite3',
           '.sqlite3-wal', '.sqlite3-shm', '.db', '.pem', '.key', '.p12', '.pfx', '.zip')
BAD_NAMES = {'.mcp.json', '.env', 'DICOMDIR', 'annotations.json', 'findings.json', 'brain_viewer.html', 'CLAUDE.md', 'CLAUDE.local.md'}
SECRET_PATTERNS = [
    re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    re.compile(rb'\bhf_[A-Za-z0-9]{30,}\b'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]
PERSONAL_PATH = re.compile(rb'/Users/[A-Za-z0-9_.-]+/')
DATED_STUDY = re.compile(rb'data/\d{4}-\d{2}-\d{2}_brain')


def source_paths(root=ROOT, include_untracked=False):
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=True)
    paths = {p.decode() for p in result.stdout.split(b'\0') if p}
    if include_untracked:
        result = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=root, capture_output=True, check=True)
        paths.update(p.decode() for p in result.stdout.split(b'\0') if p)
    return sorted(paths)


def audit(root, paths):
    issues = []
    public_paths = {'site/' + name for name in ARTIFACTS}
    public_valid = not validate(root / 'site') if public_paths.intersection(paths) else False
    if public_paths.intersection(paths) and not public_valid:
        issues.append(('site/demo/artifacts.json', 'public MRI provenance/integrity check failed'))
    stock_paths = {'site/' + name for name in PHOTOS}
    stock_valid = not validate_photos(root / 'site') if stock_paths.intersection(paths) else False
    if stock_paths.intersection(paths) and not stock_valid:
        issues.append(('site/assets/photo-credits.json', 'website photo provenance/integrity check failed'))
    for name in paths:
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            issues.append((name, 'unsafe path')); continue
        path = root / name
        if path.is_symlink():
            issues.append((name, 'symlink cannot be included in a release')); continue
        local_env = relative.name.startswith('.env') and relative.name != '.env.example'
        if any(part in {'data', 'studies', 'models', '.aws', '.venv', '.git', 'dist'} for part in relative.parts) or relative.name in BAD_NAMES or relative.name.upper() == 'DICOMDIR' or local_env or name.lower().endswith(BAD_EXT):
            issues.append((name, 'data, model, local configuration or credential file')); continue
        if not path.is_file():
            issues.append((name, 'missing source file')); continue
        blob = path.read_bytes()
        if len(blob) > 20_000_000:
            issues.append((name, 'unexpected file over 20 MB'))
        if any(pattern.search(blob) for pattern in SECRET_PATTERNS):
            issues.append((name, 'possible credential (value withheld)'))
        if PERSONAL_PATH.search(blob) or DATED_STUDY.search(blob):
            issues.append((name, 'personal filesystem or study reference'))
        # A label alone cannot authorize an embedded scan. Require the reviewed derivative manifest.
        if name.endswith('.html') and re.search(rb'type=[\'\"]application/octet-stream[\'\"]', blob):
            if name != 'site/demo/index.html' or not public_valid:
                issues.append((name, 'unapproved embedded imaging volume'))
        if re.search(rb'"data_gzip_base64"\s*:', blob):
            if name != 'site/assets/hero-volume.json' or not public_valid:
                issues.append((name, 'unapproved header imaging volume'))
        approved_raster = (name in public_paths and public_valid) or (name in stock_paths and stock_valid)
        if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and not approved_raster:
            issues.append((name, 'unapproved raster image; use reviewed public derivatives or licensed website photos'))
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true', help='also summarize historical paths and identifying prose')
    parser.add_argument('--include-untracked', action='store_true', help='also check new non-ignored source files before staging')
    args = parser.parse_args()
    paths = source_paths(include_untracked=args.include_untracked)
    issues = audit(ROOT, paths)
    for path, reason in issues:
        print(f'FAIL {path}: {reason}')
    print(f'Checked {len(paths)} source files; {len(issues)} issue(s).')
    if args.history:
        historical = subprocess.check_output(['git', 'log', '--all', '--format=', '--name-only'], cwd=ROOT).decode().splitlines()
        bad = sorted({p for p in historical if p and (PurePosixPath(p).name in BAD_NAMES or p.lower().endswith(BAD_EXT) or p.startswith(('data/', 'studies/', 'models/')))})
        print(f'Historical patient/configuration paths: {len(bad)}')
        # Report file paths and counts only, never the private text.
        revisions = subprocess.check_output(['git', 'rev-list', '--all', '--', 'docs/KNOWLEDGE.md'], cwd=ROOT).decode().splitlines()
        found = 0
        for revision in revisions:
            r = subprocess.run(['git', 'show', f'{revision}:docs/KNOWLEDGE.md'], cwd=ROOT, capture_output=True)
            if re.search(rb'Private GE|private T1|private study|Private-scan', r.stdout, re.I):
                found += 1
        print(f'Knowledge-document revisions with private-study descriptions: {found}')
        if bad or found:
            print('Publish the clean source snapshot produced by export_public_release.py; do not push this local history.')
    raise SystemExit(bool(issues))


if __name__ == '__main__':
    main()
