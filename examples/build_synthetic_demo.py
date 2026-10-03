"""Build the public viewer using only a deterministic mathematical phantom.

No patient file is read. Apparent tissues and coloured regions are synthetic illustrations,
not clinical images, model output or performance evidence.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mri_preread.build_viewer import run
from mri_preread.study import Study

ROOT = Path(__file__).resolve().parents[1]


def phantom():
    dims = (112, 128, 112)
    x, y, z = np.meshgrid(*[np.linspace(-1, 1, n, dtype=np.float32) for n in dims], indexing='ij')
    r = np.sqrt((x / .78) ** 2 + (y / .85) ** 2 + ((z - .05) / .9) ** 2)
    angle = np.arctan2(y, x)
    folded = r + .035 * np.sin(22 * angle + 11 * z) * np.sin(9 * z + 4 * x)
    brain = r < .86
    wm = folded < .71
    sulci = (folded > .71) & (np.sin(23 * angle + 16 * z + 6 * x) > .35)
    vent = ((np.abs(x) - .13) / .095) ** 2 + ((y + .08) / .33) ** 2 + ((z - .09) / .18) ** 2 < 1
    midline = (np.abs(x) < .018) & (r < .84)
    csf = brain & (vent | midline | sulci)
    texture = 5 * np.sin(29 * x + 17 * y) * np.cos(24 * z - 9 * x) + 3 * np.sin(41 * y + 11 * z)
    head = r < 1
    skull = (r > .91) & (r < .96)
    t1 = np.where(head, 125 + texture, 0)
    t1[skull] = 28
    t1[brain] = np.where(wm[brain], 175, 115) + texture[brain]
    t1[csf] = 35 + texture[csf] * .3
    flair = np.where(brain, np.where(wm, 100, 145) + texture, 0)
    flair[csf] = 20
    dwi = np.where(brain, 100 + texture, 0); dwi[csf] = 35
    adc = np.where(brain, 780 + texture * 8, 0); adc[csf] = 2400
    spot = ((x + .4) / .09) ** 2 + ((y - .1) / .13) ** 2 + ((z - .18) / .095) ** 2 < 1
    flair[spot] = 230; dwi[spot] = 220; adc[spot] = 450
    outlier = ndi.gaussian_filter(spot.astype(np.float32), .7) * 180
    asym = outlier + outlier[::-1]
    return {'t1': t1, 'flair': flair, 'dwi': dwi, 'adc': adc}, brain, outlier, asym


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=ROOT / 'data/synthetic-demo/index.html')
    args = ap.parse_args()
    volumes, brain, outlier, asym = phantom()
    spacing = [1.5, 1.5, 1.5]
    affine = np.diag(spacing + [1.])
    dims = volumes['t1'].shape
    affine[:3, 3] = -np.array(dims) * 1.5 / 2
    with tempfile.TemporaryDirectory() as temp:
        study = Study(temp); a = Path(study.analysis); a.mkdir()
        nib.save(nib.Nifti1Image(volumes['t1'].astype(np.float32), affine), a / 'ref_grid.nii.gz')
        def half(arr):
            i, j, k = dims
            return arr.reshape(i//2, 2, j//2, 2, k//2, 2).mean((1, 3, 5))
        arrays = {'ref': 't1', 'sp1': spacing, 't1': np.clip(volumes['t1'], 0, 255).astype(np.uint8), 't1_hi': 255,
                  'mask': (half(brain) * 255).astype(np.uint8), 'outlier': half(outlier).astype(np.uint8), 'asym': half(asym).astype(np.uint8)}
        for seq in ['flair', 'dwi', 'adc']:
            high = 3200 if seq == 'adc' else 255
            arrays[seq] = np.clip(half(volumes[seq]) / high * 255, 0, 255).astype(np.uint8)
            arrays[seq + '_hi'] = high
        np.savez(a / 'viewer_data.npz', **arrays)
        (a / 'meta.json').write_text(json.dumps({'sequences': {seq: {'description': 'Synthetic phantom'} for seq in volumes}}))
        (a / 'findings.json').write_text(json.dumps([{'kind': 'outlier', 'pos': [33, 70, 66], 'vol': 2400, 'peak': 8, 'cls': 'review',
                                                    'where': 'Phantom region', 'text': 'Synthetic signal pattern — manually generated, not an analysis result', 'drivers': ['Synthetic FLAIR', 'Synthetic DWI']}]))
        (a / 'annotations.json').write_text(json.dumps({'summary': {'text': 'Synthetic phantom. No patient data, model review, or clinical findings. Try the ruler, 3D cuts, clinician notes and mask brushes.'},
            'items': [{'id': 1, 'title': 'Demonstration region', 'rationale': 'Generated from an ellipsoid. This is a UI example, not a model observation.', 'priority': 'info', 'pos': [33, 70, 66], 'sequences': ['flair', 'dwi', 'adc']}]}))
        run(study)
        html = Path(study.viewer_html).read_text()
        html = html.replace('<title>Brain MRI 3D Viewer</title>', '<title>Synthetic phantom · mri-preread demo</title>')
        html = html.replace('<h1>Brain MRI · 3D</h1>', '<h1>Synthetic phantom · 3D</h1><p class="warn">Mathematical demonstration. No patient data or AI diagnosis. Coloured maps are generated illustrations.</p>')
        # Retain all viewer features, including notes and segmentation. No live local MCP required.
        html = html.replace("['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)", 'false')
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(html)
    assets = args.output.parent / 'assets'; assets.mkdir(parents=True, exist_ok=True)
    for label, axis in [('axial', 2), ('coronal', 1), ('sagittal', 0)]:
        data = np.take(volumes['t1'], int(dims[axis] * .55), axis=axis)
        data = np.rot90(data)
        image = Image.fromarray(np.clip(data, 0, 255).astype(np.uint8)).convert('RGB')
        image.resize((480, 480), Image.Resampling.BILINEAR).save(assets / (label + '.png'))
    print(f'Patient-free demo: {args.output}')


if __name__ == '__main__':
    main()
