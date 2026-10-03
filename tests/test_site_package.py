"""A website-only header must never change the public source or copy a private study."""
import hashlib
import base64
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import package_site
from release_audit import audit


class SitePackageTests(unittest.TestCase):
    def test_default_and_owner_packages_are_separate_and_truthfully_manifested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'dist').mkdir()
            site = root / 'site'
            site.mkdir()
            index = '<html><figure ' + package_site.PUBLIC_VOLUME + '>' + package_site.PUBLIC_HEADER + ' alt="MRI">' + '</figure></html>'
            guide = '<section id="license"><h2>Licensing</h2></section>'
            (site / 'index.html').write_text(index)
            (site / 'integrate.html').write_text(guide)
            (site / 'license.txt').write_text('Image licenses\n')
            source_image = root / 'data' / 'header.jpg'
            source_image.parent.mkdir()
            # Minimal fixture for the JPEG envelope check; no patient image is used in tests.
            image_bytes = b'\xff\xd8\xff\xe0website-image\xff\xd9'
            source_image.write_bytes(image_bytes)
            (source_image.parent / 'brain_viewer.html').write_text('must never copy this')
            with patch.object(package_site, 'ROOT', root), patch.object(package_site, 'SITE', site), \
                 patch.object(package_site, 'FILES', ['index.html', 'integrate.html', 'license.txt']), \
                 patch.object(package_site, 'validate', return_value=[]), \
                 patch.object(package_site, 'validate_photos', return_value=[]):
                public, _ = package_site.package(root / 'dist/public')
                owner, _ = package_site.package(root / 'dist/owner', source_image)
                with self.assertRaises(ValueError):
                    package_site.package(owner, source_image)
            default_manifest = json.loads((public / 'manifest.json').read_text())
            owner_manifest = json.loads((owner / 'manifest.json').read_text())
            self.assertFalse(default_manifest['private_patient_data_included'])
            self.assertNotIn(package_site.HEADER_ASSET, default_manifest['files'])
            self.assertEqual((public / 'index.html').read_text(), index)
            self.assertTrue(owner_manifest['private_patient_data_included'])
            self.assertFalse(owner_manifest['raw_patient_data_included'])
            self.assertFalse(owner_manifest['owner_header_image']['public_source_included'])
            self.assertEqual(owner_manifest['files'][package_site.HEADER_ASSET], hashlib.sha256(image_bytes).hexdigest())
            self.assertIn(package_site.OWNER_NOTICE, (owner / 'license.txt').read_text())
            self.assertEqual((owner / 'integrate.html').read_text(), guide)
            self.assertIn('data-volume=""', (owner / 'index.html').read_text())
            self.assertFalse(any(p.name == 'brain_viewer.html' for p in owner.rglob('*')))
            self.assertEqual((site / 'index.html').read_text(), index)
            self.assertTrue(audit(root, ['data/header.jpg']))
            self.assertTrue(audit(owner, [package_site.HEADER_ASSET]))

    def test_matching_owner_volume_is_explicit_and_contains_only_the_display_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            site = root / 'site'
            site.mkdir()
            (site / 'index.html').write_text('<figure ' + package_site.PUBLIC_VOLUME + '>' + package_site.PUBLIC_HEADER + '>' + '</figure>')
            (site / 'integrate.html').write_text('<section id="license">')
            (site / 'license.txt').write_text('Image licenses\n')
            image = root / 'data/header.jpg'
            image.parent.mkdir()
            image.write_bytes(b'\xff\xd8\xffwebsite-image\xff\xd9')
            raw = bytes(range(8))
            volume = root / 'data/volume.json'
            payload = {'format': 'mri-hero-volume-v1', 'dims': [2, 2, 2], 'spacing_mm': [1, 1, 1],
                       'sequence': 't1', 'window': [.35, .7], 'appearance': 'volume',
                       'data_gzip_base64': base64.b64encode(gzip.compress(raw)).decode(),
                       'voxel_sha256': hashlib.sha256(raw).hexdigest()}
            volume.write_text(json.dumps(payload))
            with patch.object(package_site, 'ROOT', root), patch.object(package_site, 'SITE', site), \
                 patch.object(package_site, 'FILES', ['index.html', 'integrate.html', 'license.txt']), \
                 patch.object(package_site, 'validate', return_value=[]), \
                 patch.object(package_site, 'validate_photos', return_value=[]):
                with self.assertRaises(ValueError):
                    package_site.package(root / 'dist/rejected', hero_volume=volume)
                self.assertFalse((root / 'dist/rejected').exists())
                out, count = package_site.package(root / 'dist/owner', image, volume)
                payload['patient'] = 'unexpected'
                volume.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    package_site.package(root / 'dist/rejected', image, volume)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(count, 5)
            self.assertTrue(manifest['private_display_volume_included'])
            self.assertFalse(manifest['owner_hero_volume']['patient_metadata_included'])
            self.assertIn(package_site.VOLUME_ASSET, (out / 'index.html').read_text())
            self.assertIn(package_site.OWNER_VOLUME_NOTICE, (out / 'license.txt').read_text())
            self.assertNotIn(package_site.PUBLIC_VOLUME, (out / 'index.html').read_text())

    def test_header_rejects_html_missing_files_and_symlinks_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            site = root / 'site'
            site.mkdir()
            (site / 'index.html').write_text(package_site.PUBLIC_HEADER)
            (site / 'integrate.html').write_text('<section id="license">')
            (site / 'license.txt').write_text('Image licenses\n')
            html = root / 'viewer.jpg'
            html.write_text('<html>private study</html>')
            linked = root / 'linked.jpg'
            linked.symlink_to(html)
            with patch.object(package_site, 'ROOT', root), patch.object(package_site, 'SITE', site), \
                 patch.object(package_site, 'validate', return_value=[]), \
                 patch.object(package_site, 'validate_photos', return_value=[]):
                for candidate in (html, linked, root / 'missing.jpg'):
                    with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                        package_site.package(root / 'dist/rejected', candidate)
                self.assertFalse((root / 'dist/rejected').exists())


if __name__ == '__main__':
    unittest.main()
