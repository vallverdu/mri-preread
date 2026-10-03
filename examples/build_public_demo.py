"""Build the explicitly approved CC0 OpenNeuro example; never accepts a private study.

Inputs must match the publisher's git-annex SHA-256 keys at the pinned commit.
Original NIfTIs stay ignored. Only brain-masked viewer data and derived illustrations are public.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mri_preread.build_viewer import run
from mri_preread.study import Study
from scripts.public_demo import COMMIT, DATASET, SUBJECT, INPUT_SHA256
INPUTS = {
    't1': ('T1w', INPUT_SHA256['t1']),
    'flair': ('FLAIR', INPUT_SHA256['flair']),
}
MARKER = 'OpenNeuro ds007401 / sub-4082 / CC0'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preview(study):
    """Scientific slice rendering with physical aspect, radiological orientation and a true scale."""
    with np.load(Path(study.analysis) / 'viewer_data.npz') as data:
        volume = data['t1']; spacing = data['sp1']
    cross = [int(volume.shape[0] / 2), int(volume.shape[1] / 2), int(volume.shape[2] * .55)]
    for name, axis, u, v, labels in [('axial', 2, 0, 1, ('R','L','A','P')),
                                     ('coronal', 1, 0, 2, ('R','L','S','I')),
                                     ('sagittal', 0, 1, 2, ('A','P','S','I'))]:
        frame = np.take(volume, cross[axis], axis=axis)[::-1, ::-1].T
        physical = (volume.shape[u] * spacing[u], volume.shape[v] * spacing[v])
        scale = 550 / max(physical)
        size = tuple(round(float(n * scale)) for n in physical)
        image = Image.fromarray(frame).convert('RGB').resize(size, Image.Resampling.BILINEAR)
        canvas = Image.new('RGB', (640, 640), '#080c0f')
        origin = ((640-size[0])//2, (640-size[1])//2)
        canvas.paste(image, origin)
        draw = ImageDraw.Draw(canvas)
        for text, xy in zip(labels, [(15,315),(616,315),(315,12),(315,614)]):
            draw.text(xy,text,fill='#b9c9c4')
        length = round(30 * scale)
        draw.line((600-length,585,600,585),fill='#cad6cd',width=2)
        draw.text((600-length,595),'30 mm',fill='#cad6cd')
        canvas.save(ROOT / 'site/assets' / (name + '.png'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, default=ROOT/'data/bench/_downloads'/SUBJECT)
    p.add_argument('--workspace', type=Path, default=ROOT/'data/public-demo-openneuro')
    p.add_argument('--download', action='store_true', help='download just the two pinned public inputs when missing')
    p.add_argument('--reuse', action='store_true', help='reuse this demo workspace after verifying its source record')
    args = p.parse_args()
    source = args.source_dir.resolve(); workspace = args.workspace.resolve()
    if not workspace.is_relative_to(ROOT/'data') or source.is_relative_to(workspace):
        raise SystemExit('Use a separate ignored data/ workspace')
    for role, (name, expected) in INPUTS.items():
        path = source / (name+'.nii.gz')
        if not path.exists() and args.download:
            path.parent.mkdir(parents=True, exist_ok=True)
            url = f'https://s3.amazonaws.com/openneuro.org/{DATASET}/{SUBJECT}/ses-1/anat/{SUBJECT}_ses-1_{name}.nii.gz'
            urllib.request.urlretrieve(url, path)
        if not path.is_file() or sha(path) != expected:
            raise SystemExit(f'{role}: missing or different input; refusing an unverified scan')
    record = {'dataset': DATASET, 'subject': SUBJECT, 'publisher_commit': COMMIT,
              'input_sha256': {role: digest for role, (_, digest) in INPUTS.items()}}
    if workspace.exists():
        old = workspace/'public-source-record.json'
        if not args.reuse or not old.is_file() or json.loads(old.read_text()) != record:
            raise SystemExit('Choose a new workspace, or --reuse only this verified public example')
    else:
        cmd = [sys.executable, '-m', 'mri_preread']
        subprocess.run(cmd + ['import', str(workspace), '--t1', str(source/'T1w.nii.gz'), '--flair', str(source/'FLAIR.nii.gz')], cwd=ROOT, check=True)
        subprocess.run(cmd + ['analyze', str(workspace)], cwd=ROOT, check=True)
        (workspace/'public-source-record.json').write_text(json.dumps(record, indent=2)+'\n')
    study = Study(workspace); analysis = Path(study.analysis)
    mask_image = nib.load(analysis/'brain_mask.nii.gz')
    mask = np.asanyarray(mask_image.dataobj) > 0
    with np.load(analysis/'viewer_data.npz') as loaded:
        arrays = {key: loaded[key] for key in loaded.files}
    arrays['t1'] = arrays['t1'] * mask
    arrays['flair'] = arrays['flair'] * (arrays['mask'] >= 128)
    np.savez(analysis/'viewer_data.npz', **arrays)
    # Remove outside-brain anatomy from the published data and MCP image input alike.
    for name, keep in [('ref_grid.nii.gz', mask), ('flair_in_ref_space.nii.gz', arrays['mask'] >= 128)]:
        image = nib.load(analysis/name)
        data = image.get_fdata(dtype=np.float32) * keep
        nib.save(nib.Nifti1Image(data, image.affine), analysis/name)
    # The public demo has no patient metadata, prior model report or invented AI findings.
    (analysis/'annotations.json').write_text(json.dumps({'summary': {'text': 'Public OpenNeuro research MRI. Notes and painted masks are demonstration drawings, not clinical findings. No AI review is embedded.'}, 'items': []}))
    meta_path = analysis/'meta.json'; meta = json.loads(meta_path.read_text())
    for role in ('t1','flair'):
        meta['sequences'][role]['description'] = 'OpenNeuro research MRI'
    meta_path.write_text(json.dumps(meta, indent=2)+'\n')
    run(study)
    html = Path(study.viewer_html).read_text()
    html = html.replace('<title>Brain MRI 3D Viewer</title>', '<title>OpenNeuro MRI · mri-preread demo</title>')
    banner = '<h1>Open research MRI · 3D</h1><p class="warn">'+MARKER+'. Brain-masked T1 + FLAIR. Example drawings are not clinical labels.</p><p class="note"><a href="../integrate.html#dataset" style="color:#a7d5ba">Dataset credit &amp; modifications ↗</a></p>'
    html = html.replace('<h1>Brain MRI · 3D</h1>', banner)
    html = html.replace('<head>', '<head><meta name="mri-preread-public-dataset" content="'+MARKER+'">')
    html = html.replace("['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)", 'false')
    target = ROOT/'site/demo'; target.mkdir(exist_ok=True)
    (target/'index.html').write_text(html)
    preview(study)
    (target/'source-record.json').write_text(json.dumps({**record, 'license': 'CC0-1.0',
        'dataset_url': 'https://openneuro.org/datasets/ds007401/versions/1.0.0',
        'publisher_metadata': f'https://github.com/OpenNeuroDatasets/ds007401/blob/{COMMIT}/dataset_description.json',
        'modifications': ['T1/FLAIR selection', 'canonical orientation and reference resampling', 'rigid sequence alignment',
                          'brain masking; outside-brain voxels removed', 'display windowing and uint8 packing',
                          'demonstration notes, measurements and manual masks in feature screenshots',
                          'actual MCP view_region montage, 100 mm field of view at reference voxel (86,94,84)'],
        'private_scan_included': False, 'model_predictions_included': False}, indent=2)+'\n')
    print(f'Verified public MRI viewer: {target / "index.html"}', flush=True)


if __name__ == '__main__':
    main()
