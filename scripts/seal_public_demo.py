"""Record reviewed public derivatives after building the pinned dataset and capturing the viewer.

Hashing records integrity, not anonymization. Review every new derivative before sealing.
"""
import argparse
import json
from pathlib import Path
from public_demo import ARTIFACTS, COMMIT, DATASET, SUBJECT, INPUT_SHA256, check_record, sha, validate

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--workspace', type=Path, default=ROOT / 'data/public-demo-openneuro')
args = p.parse_args()
workspace = args.workspace.resolve()
if not workspace.is_relative_to(ROOT / 'data'):
    raise SystemExit('Expected the ignored public-demo workspace')
expected = {'dataset': DATASET, 'subject': SUBJECT, 'publisher_commit': COMMIT, 'input_sha256': INPUT_SHA256}
if json.loads((workspace / 'public-source-record.json').read_text()) != expected:
    raise SystemExit('Workspace is not the verified public example')
site = ROOT / 'site'
record = json.loads((site / 'demo/source-record.json').read_text())
if not check_record(record):
    raise SystemExit('Unexpected source or license')
hashes = {}
for name in ARTIFACTS:
    path = site / name
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f'Missing or unsafe derivative: {name}')
    hashes[name] = sha(path)
(site / 'demo/artifacts.json').write_text(json.dumps({'source': record, 'files': hashes}, indent=2) + '\n')
issues = validate(site)
if issues:
    raise SystemExit('\n'.join(issues))
print(f'Sealed {len(hashes)} reviewed public MRI derivatives.')
