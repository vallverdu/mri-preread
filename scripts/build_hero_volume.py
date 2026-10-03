"""Export one display-resolution MRI reference volume for the optional website header.

This is a display export, not anonymization. Patient exports must stay in ignored data/.
No reports, patient fields, other sequences, overlays or annotations are copied.
"""
import argparse
import base64
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'mri-hero-volume-v1'
FIELDS = {'format', 'dims', 'spacing_mm', 'sequence', 'window', 'appearance',
          'data_gzip_base64', 'voxel_sha256'}
ROLES = {'t1', 't2', 'flair', 'swi', 'dwi', 'adc'}
MAX_VOXELS = 16_000_000
DEFAULT_MAX_AXIS = 128
DEFAULT_INTENSITY_BITS = 6


class ViewerData(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.scripts = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        key = a.get('id', '')
        if tag == 'script' and (key == 'meta' or key.startswith('d-')):
            if key in self.scripts:
                raise ValueError('Duplicate viewer data block')
            self.current = key
            self.scripts[key] = ''

    def handle_data(self, text):
        if self.current:
            self.scripts[self.current] += text

    def handle_endtag(self, tag):
        if tag == 'script':
            self.current = None


def geometry(dims, spacing):
    if (not isinstance(dims, list) or len(dims) != 3 or
            any(type(n) is not int or not 2 <= n <= 1024 for n in dims) or
            math.prod(dims) > MAX_VOXELS):
        raise ValueError('Invalid or excessive reference dimensions')
    if (not isinstance(spacing, list) or len(spacing) != 3 or
            any(type(n) not in (int, float) or not math.isfinite(n) or not 0 < n <= 20 for n in spacing)):
        raise ValueError('Invalid voxel spacing')


def decode_voxels(encoded, size):
    if not isinstance(encoded, str) or len(encoded) > 24_000_000:
        raise ValueError('Invalid or excessive volume payload')
    try:
        compressed = base64.b64decode(encoded, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(size + 1)
        if len(raw) != size:
            raise ValueError('Voxel count disagrees with dimensions')
        return raw
    except (OSError, EOFError, ValueError) as error:
        raise ValueError('Invalid compressed voxel array') from error


def validate_payload(payload):
    if not isinstance(payload, dict) or set(payload) != FIELDS or payload['format'] != FORMAT:
        raise ValueError('Unexpected hero volume fields or format')
    geometry(payload['dims'], payload['spacing_mm'])
    if max(payload['dims']) > 256 or payload['sequence'] not in ROLES or payload['appearance'] not in ('surface', 'volume'):
        raise ValueError('Unexpected hero volume settings')
    window = payload['window']
    if (not isinstance(window, list) or len(window) != 2 or
            any(type(n) not in (int, float) or not math.isfinite(n) for n in window) or
            not 0 <= window[0] <= 1 or not 0 < window[1] <= 2):
        raise ValueError('Invalid display window')
    raw = decode_voxels(payload['data_gzip_base64'], math.prod(payload['dims']))
    if hashlib.sha256(raw).hexdigest() != payload['voxel_sha256']:
        raise ValueError('Hero voxel checksum mismatch')
    return raw


def export(viewer, max_axis=DEFAULT_MAX_AXIS, appearance='surface', intensity_bits=DEFAULT_INTENSITY_BITS):
    if not 32 <= max_axis <= 256 or appearance not in ('surface', 'volume') or intensity_bits not in (6, 8):
        raise ValueError('Choose a display axis limit of 32–256, surface or volume, and 6 or 8 intensity bits')
    source = Path(viewer)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 120_000_000:
        raise ValueError('Expected a regular prepared viewer below 120 MB')
    blocks = ViewerData(source.read_text()).scripts
    meta = json.loads(blocks['meta'])
    dims, spacing, role = meta['dims1'], meta['sp1'], meta['ref']
    geometry(dims, spacing)
    if role not in ROLES:
        raise ValueError('Unknown reference sequence')
    volume = next(v for v in meta['vols'] if v['key'] == role)
    if volume['dims'] != dims or volume['f'] != 1:
        raise ValueError('Reference volume must use the reference grid')
    raw = decode_voxels(blocks['d-' + role].strip(), math.prod(dims))
    # Anti-aliased linear resampling at voxel centres, retaining the physical extent.
    # Array ordering is the same as the viewer: x fastest, then y, then z.
    scale = min(1, max_axis / max(dims))
    small = [max(2, round(n * scale)) for n in dims]
    if small != dims:
        import numpy as np
        from scipy.ndimage import gaussian_filter, zoom
        array = np.frombuffer(raw, dtype=np.uint8).reshape(tuple(reversed(dims)))
        sigma = tuple(max(0, (n / m - 1) / 2) for n, m in reversed(list(zip(dims, small))))
        smoothed = gaussian_filter(array.astype(np.float32), sigma=sigma, mode='nearest')
        resized = zoom(smoothed, tuple(m / n for n, m in reversed(list(zip(dims, small)))),
                       order=1, grid_mode=True, mode='nearest', prefilter=False)
        if resized.shape != tuple(reversed(small)):
            raise ValueError('Unexpected display resampling dimensions')
        if intensity_bits == 8:
            raw = np.rint(resized).astype(np.uint8).tobytes()
        else:
            levels = (1 << intensity_bits) - 1
            raw = np.rint(np.rint(resized * levels / 255) * 255 / levels).astype(np.uint8).tobytes()
    elif intensity_bits == 6:
        # Preserve the uint8 texture format while using 64 levels that compress better.
        levels = (1 << intensity_bits) - 1
        table = bytes(round(round(n * levels / 255) * 255 / levels) for n in range(256))
        raw = raw.translate(table)
    payload = {'format': FORMAT, 'dims': small,
               'spacing_mm': [s * n / m for s, n, m in zip(spacing, dims, small)],
               'sequence': role, 'window': [volume['lev'], volume['wid']], 'appearance': appearance,
               'data_gzip_base64': base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode(),
               'voxel_sha256': hashlib.sha256(raw).hexdigest()}
    validate_payload(payload)
    return payload


def renderer_source():
    """Use the full viewer's camera math and ray marcher, with a white background."""
    template = (ROOT / 'mri_preread/viewer_template.html').read_text()
    math_js = template.split('// ---------- math ----------\n', 1)[1].split('const toWorld =', 1)[0]
    shaders = re.search(r'const VS = `[\s\S]+?\n}`;', template).group()
    # Keep the ray marcher identical; only the background presentation changes.
    shaders, count = re.subn(r'vec3 bg = mix\([^;]+;', 'vec3 bg = vec3(1.0);', shaders)
    if count != 1:
        raise ValueError('Viewer shader changed: review the header renderer export')
    return ("// Generated by scripts/build_hero_volume.py --sync-renderer; do not edit.\n"
            "// Camera math and MRI ray marcher from mri_preread/viewer_template.html.\n"
            "(function (root) {\n'use strict';\n" + math_js + shaders +
            "\nconst core = { M, VS, FS };\n"
            "if (typeof module === 'object' && module.exports) module.exports = core;\n"
            "else root.MriHeroRenderer = core;\n})(typeof window === 'object' ? window : globalThis);\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--viewer', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-axis', type=int, default=DEFAULT_MAX_AXIS,
        help='Longest preview dimension in voxels (default: 128); does not change the full viewer')
    parser.add_argument('--intensity-bits', type=int, choices=[6, 8], default=DEFAULT_INTENSITY_BITS,
        help='6 uses 64 preview intensity levels for smaller downloads; 8 retains all uint8 levels')
    parser.add_argument('--appearance', choices=['surface', 'volume'], default='surface')
    parser.add_argument('--sync-renderer', action='store_true')
    args = parser.parse_args()
    if args.sync_renderer:
        (ROOT / 'site/hero-renderer.js').write_text(renderer_source())
    if args.viewer or args.output:
        if not args.viewer or not args.output or args.output.exists():
            parser.error('Provide --viewer and a new --output file; existing exports are preserved')
        payload = export(args.viewer, args.max_axis, args.appearance, args.intensity_bits)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, separators=(',', ':')) + '\n')
        print(f'Exported reference display volume: {payload["dims"]}; {args.output.stat().st_size / 1e6:.2f} MB')
    elif not args.sync_renderer:
        parser.error('Provide --viewer/--output or --sync-renderer')


if __name__ == '__main__':
    main()
