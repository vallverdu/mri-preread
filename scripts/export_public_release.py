"""Export audited tracked source with a manifest, ZIP, and no local Git history."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from release_audit import ROOT, PROJECT_COVER_FILES, audit, source_paths


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'dist' / 'public-release')
    args = p.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Output already exists. Choose a new release directory; existing releases are preserved.')
    if not output.is_relative_to(ROOT / 'dist'):
        raise SystemExit('Release output must be under the ignored dist/ directory')
    paths = source_paths()
    issues = audit(ROOT, paths)
    if issues:
        for path, reason in issues: print(f'{path}: {reason}')
        raise SystemExit('Release audit failed')
    # The owner-published management thumbnail is not application source or MIT imagery.
    paths = [name for name in paths if name not in PROJECT_COVER_FILES]
    # Export only a clean committed state, including approved CC0 public MRI derivatives.
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise SystemExit('Commit or isolate current changes before exporting a release')
    source = output / 'mri-preread'
    source.mkdir(parents=True)
    manifest = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                'history_included': False, 'private_patient_data_included': False,
                'public_research_data_included': True, 'public_dataset': 'ds007401',
                'stock_photography_included': True, 'stock_photo_license': 'https://unsplash.com/license', 'files': {}}
    for name in paths:
        dest = source / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
        manifest['files'][name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = output / 'mri-preread-source.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(source.rglob('*')):
            if path.is_file(): z.write(path, path.relative_to(output))
    print(f'Source: {source}\nZIP: {archive}\nManifest: {output / "manifest.json"}')


if __name__ == '__main__':
    main()
