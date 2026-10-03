"""The header is a bounded reference-only display derivative, not a study dump."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_hero_volume import export, validate_payload, renderer_source


class HeroVolumeTests(unittest.TestCase):
    def viewer(self, root, dims=(4, 3, 2)):
        raw = bytes(i % 256 for i in range(dims[0] * dims[1] * dims[2]))
        meta = {'dims1': list(dims), 'sp1': [1, 2, 3], 'ref': 't1',
                'vols': [{'key': 't1', 'dims': list(dims), 'f': 1, 'lev': .35, 'wid': .7}],
                'patient': 'excluded identity', 'findings': [{'text': 'excluded observation'}]}
        path = root / 'viewer.html'
        path.write_text('<script id="meta">' + json.dumps(meta) + '</script>' +
                        '<script id="d-t1">' + base64.b64encode(gzip.compress(raw)).decode() + '</script>' +
                        '<script id="annotations">excluded notes</script><script id="d-flair">excluded other sequence</script>')
        return path, raw

    def test_reference_voxels_and_physical_extent_are_preserved_without_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            viewer, raw = self.viewer(Path(directory))
            payload = export(viewer, intensity_bits=8)
            self.assertEqual(validate_payload(payload), raw)
            self.assertEqual(payload['spacing_mm'], [1, 2, 3])
            self.assertNotIn('excluded', json.dumps(payload))
            self.assertNotIn('patient', payload)
            self.assertNotIn('findings', payload)
            self.assertNotIn('annotations', payload)
            # A large axis is reduced while retaining each axis's full physical extent.
            viewer, _ = self.viewer(Path(directory), (64, 4, 2))
            reduced = export(viewer, max_axis=32)
            self.assertEqual(reduced['dims'], [32, 2, 2])
            self.assertEqual(reduced['spacing_mm'], [2, 4, 3])
            self.assertEqual(len(validate_payload(reduced)), 128)

    def test_corruption_extra_fields_and_excessive_geometry_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            viewer, _ = self.viewer(Path(directory))
            payload = export(viewer)
            cases = [{**payload, 'patient': 'unexpected'}, {**payload, 'dims': [256, 256, 256]},
                     {**payload, 'spacing_mm': [1, float('nan'), 1]}, {**payload, 'voxel_sha256': '0' * 64},
                     {**payload, 'data_gzip_base64': base64.b64encode(gzip.compress(b'x' * 100)).decode()}]
            for bad in cases:
                with self.subTest(bad=list(bad)), self.assertRaises(ValueError):
                    validate_payload(bad)

    def test_preview_quantization_is_bounded_and_preserves_the_intensity_range(self):
        with tempfile.TemporaryDirectory() as directory:
            viewer, raw = self.viewer(Path(directory), (8, 8, 4))
            payload = export(viewer)
            decoded = validate_payload(payload)
            self.assertEqual(payload['dims'], [8, 8, 4])
            self.assertEqual(payload['spacing_mm'], [1, 2, 3])
            self.assertEqual(len(set(decoded)), 64)
            self.assertEqual((min(decoded), max(decoded)), (0, 255))
            self.assertLessEqual(max(abs(a - b) for a, b in zip(raw, decoded)), 2)
            with self.assertRaises(ValueError):
                export(viewer, intensity_bits=4)

    def test_header_shader_stays_in_sync_with_the_actual_viewer(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / 'site/hero-renderer.js').read_text(), renderer_source())
        self.assertIn('vec3 bg = vec3(1.0);', renderer_source())

    def test_public_header_is_the_reviewed_simplified_reference_from_the_public_viewer(self):
        site = Path(__file__).resolve().parents[1] / 'site'
        self.assertEqual(json.loads((site / 'assets/hero-volume.json').read_text()), export(site / 'demo/index.html'))


if __name__ == '__main__':
    unittest.main()
