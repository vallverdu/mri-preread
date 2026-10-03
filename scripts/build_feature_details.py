"""Frame unchanged, approved app captures as distinct feature close-ups."""
import base64
import hashlib
import json
from pathlib import Path
from public_demo import check_record

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
# Each pane is (destination x/y/width/height, source x/y/width/height).
# Source coordinates refer to the original 1470 x 756 app screenshots.
DETAILS = {
    'views': ('Linked 3D, axial, coronal and sagittal MRI views', [
        ((0, 0, 1024, 640), (307, 35, 1163, 721)),
    ]),
    'measures': ('Axial ruler and circular ROI beside their measured statistics', [
        ((0, 20, 630, 600), (1025, 80, 320, 280)),
        ((654, 130, 350, 380), (14, 553, 269, 186)),
    ]),
    'notes': ('Written clinical note beside its location marker on an axial MRI', [
        ((22, 90, 430, 460), (13, 451, 272, 181)),
        ((472, 20, 532, 600), (1030, 70, 310, 300)),
    ]),
    'masks': ('Manual orange voxel mask enlarged in 3D and checked on an axial slice', [
        ((0, 20, 670, 600), (485, 110, 280, 210)),
        ((690, 105, 314, 430), (1035, 80, 285, 280)),
    ]),
}


def build():
    manifest_path = SITE / 'demo/artifacts.json'
    manifest = json.loads(manifest_path.read_text())
    if not check_record(manifest['source']):
        raise ValueError('Feature details require the approved public MRI study')
    for name, (title, panes) in DETAILS.items():
        source = f'assets/feature-{name}.jpg'
        image = (SITE / source).read_bytes()
        if hashlib.sha256(image).hexdigest() != manifest['files'][source]:
            raise ValueError(f'Unreviewed source screenshot: {source}')
        href = 'data:image/jpeg;base64,' + base64.b64encode(image).decode()
        elements = ['<rect width="1024" height="640" fill="#111318"/>',
                    f'<defs><image id="capture" href="{href}" width="1470" height="756"/></defs>']
        for index, (destination, crop) in enumerate(panes):
            x, y, width, height = destination
            viewbox = ' '.join(map(str, crop))
            elements.append(f'<svg x="{x}" y="{y}" width="{width}" height="{height}" '
                            f'viewBox="{viewbox}" preserveAspectRatio="xMidYMid meet" overflow="hidden">'
                            f'<clipPath id="crop{index}"><rect x="{crop[0]}" y="{crop[1]}" '
                            f'width="{crop[2]}" height="{crop[3]}"/></clipPath>'
                            f'<use href="#capture" clip-path="url(#crop{index})"/></svg>')
        if name in ('measures', 'notes', 'masks'):
            separator = {'measures': 642, 'notes': 462, 'masks': 680}[name]
            elements.append(f'<path d="M {separator} 32 V 608" stroke="#30343d"/>')
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="640" '
               'viewBox="0 0 1024 640" role="img" aria-labelledby="title">'
               f'<title id="title">{title}</title>' + ''.join(elements) + '</svg>\n')
        asset = f'assets/feature-{name}-detail.svg'
        (SITE / asset).write_text(svg)
        manifest['files'][asset] = hashlib.sha256(svg.encode()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built four feature details from unchanged, checksum-verified public app captures.')


if __name__ == '__main__':
    build()
