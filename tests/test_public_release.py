"""Release guards must catch leakage and require the approved public MRI provenance."""
import hashlib
import base64
import gzip
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from release_audit import audit
from public_demo import ARTIFACTS, COMMIT, DATASET, INPUT_SHA256, MARKER, SUBJECT, validate
from site_photos import FILES as PHOTO_FILES, validate as validate_photos


class PublicReleaseTests(unittest.TestCase):
    def photo_fixture(self, root):
        source = Path(__file__).resolve().parents[1] / 'site'
        for name in PHOTO_FILES:
            path = root / 'site' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, path)
        return root / 'site'

    def test_reviewed_stock_photos_are_allowed_but_replacement_images_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = self.photo_fixture(root)
            paths = ['site/' + name for name in PHOTO_FILES]
            self.assertEqual(audit(root, paths), [])
            (site / 'assets/clinical-review.jpg').write_bytes(b'unapproved replacement')
            self.assertTrue(audit(root, paths))
            # Editing the credit manifest cannot approve different bytes at the same filename.
            credits = site / 'assets/photo-credits.json'
            record = json.loads(credits.read_text())
            record['photos']['assets/clinical-review.jpg']['sha256'] = hashlib.sha256(b'unapproved replacement').hexdigest()
            credits.write_text(json.dumps(record))
            self.assertTrue(validate_photos(site))

    def test_stock_photo_credits_cannot_be_missing_or_relicensed(self):
        with tempfile.TemporaryDirectory() as directory:
            site = self.photo_fixture(Path(directory))
            credits = site / 'assets/photo-credits.json'
            original = credits.read_text()
            credits.unlink()
            self.assertTrue(validate_photos(site))
            record = json.loads(original)
            record['license'] = 'MIT'
            credits.write_text(json.dumps(record))
            self.assertTrue(validate_photos(site))

    def test_credentials_are_reported_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = 'AK' + 'IA' + 'A' * 16
            (root / 'config.txt').write_text(token)
            issues = audit(root, ['config.txt'])
            self.assertEqual(len(issues), 1)
            self.assertIn('credential', issues[0][1])
            self.assertNotIn(token, str(issues))

    def public_fixture(self, root):
        record = {'dataset': DATASET, 'subject': SUBJECT, 'publisher_commit': COMMIT,
                  'input_sha256': INPUT_SHA256, 'license': 'CC0-1.0',
                  'private_scan_included': False, 'model_predictions_included': False}
        site = root / 'site'
        for name in ARTIFACTS:
            path = site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        stream, sequence = 'octet-stream', 'flair'
        (site / 'demo/index.html').write_bytes(
            f'<script type="application/{stream}" id="d-{sequence}">AAAA</script>'.encode() + MARKER)
        (site / 'demo/source-record.json').write_text(json.dumps(record))
        raw = bytes(range(8))
        payload = {'format': 'mri-hero-volume-v1', 'dims': [2, 2, 2], 'spacing_mm': [1, 1, 1],
                   'sequence': 't1', 'window': [.35, .7], 'appearance': 'surface',
                   'data_gzip_base64': base64.b64encode(gzip.compress(raw)).decode(),
                   'voxel_sha256': hashlib.sha256(raw).hexdigest()}
        (site / 'assets/hero-volume.json').write_text(json.dumps(payload))
        manifest = {'source': record, 'files': {name: hashlib.sha256((site / name).read_bytes()).hexdigest() for name in ARTIFACTS}}
        (site / 'demo/artifacts.json').write_text(json.dumps(manifest))
        return site, manifest

    def test_header_volume_cannot_be_renamed_or_include_extra_patient_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, manifest = self.public_fixture(root)
            blob = (site / 'assets/hero-volume.json').read_bytes()
            (root / 'preview.json').write_bytes(blob)
            self.assertTrue(audit(root, ['preview.json']))
            payload = json.loads(blob)
            payload['patient'] = 'unexpected metadata'
            (site / 'assets/hero-volume.json').write_text(json.dumps(payload))
            manifest['files']['assets/hero-volume.json'] = hashlib.sha256((site / 'assets/hero-volume.json').read_bytes()).hexdigest()
            (site / 'demo/artifacts.json').write_text(json.dumps(manifest))
            self.assertTrue(validate(site))

    def test_only_the_manifest_verified_public_viewer_can_embed_a_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, _ = self.public_fixture(root)
            self.assertEqual(audit(root, ['site/' + name for name in ARTIFACTS]), [])
            blob = (site / 'demo/index.html').read_bytes()
            (root / 'viewer.html').write_bytes(blob)
            self.assertIn('unapproved', audit(root, ['viewer.html'])[0][1])
            (site / 'demo/index.html').write_bytes(blob + b'changed')
            self.assertTrue(any('unapproved' in reason for _, reason in audit(root, ['site/demo/index.html'])))

    def test_a_dataset_label_without_provenance_cannot_authorize_an_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, _ = self.public_fixture(root)
            (site / 'demo/artifacts.json').unlink()
            self.assertTrue(audit(root, ['site/assets/axial.png']))
            (root / 'scan.jpg').write_bytes(b'image')
            self.assertIn('unapproved', audit(root, ['scan.jpg'])[0][1])

    def test_wrong_license_source_and_additional_paths_are_rejected(self):
        for field, value in [('license', 'other'), ('subject', 'other'), ('private_scan_included', True)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                site, manifest = self.public_fixture(Path(directory))
                manifest['source'][field] = value
                (site / 'demo/source-record.json').write_text(json.dumps(manifest['source']))
                (site / 'demo/artifacts.json').write_text(json.dumps(manifest))
                self.assertTrue(validate(site))
        with tempfile.TemporaryDirectory() as directory:
            site, manifest = self.public_fixture(Path(directory))
            manifest['files']['../unapproved.jpg'] = '0' * 64
            (site / 'demo/artifacts.json').write_text(json.dumps(manifest))
            self.assertTrue(validate(site))

    def test_modified_screenshot_is_rejected_even_when_viewer_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, _ = self.public_fixture(root)
            (site / 'assets/feature-masks.jpg').write_bytes(b'other image')
            self.assertTrue(audit(root, ['site/demo/index.html', 'site/assets/feature-masks.jpg']))

    def test_paths_cannot_include_data_local_config_or_symlink_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.txt').write_text('public example')
            (root / 'linked.txt').symlink_to(root / 'source.txt')
            paths = ['data/study.txt', '.mcp.json', 'volume.nii.gz', '.env.production', 'database.sqlite3-wal',
                     'weights.gguf', 'private.p12', '../outside.txt', 'linked.txt']
            self.assertEqual(len(audit(root, paths)), len(paths))
            self.assertEqual(audit(root, ['source.txt']), [])


if __name__ == '__main__':
    unittest.main()
