import hashlib
import io
import json
import re
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np

from mri_preread.build_viewer import run
from mri_preread.slice_input import SliceInputs
from mri_preread.viewer_review import load_review
from test_slice_workflow import synthetic_study


class ViewerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = synthetic_study(self.temp.name)
        inputs = SliceInputs(self.study)
        _, images = inputs.render(12, ['t1', 'flair'])
        records = []
        for seq, image in zip(['t1', 'flair'], images):
            stream = io.BytesIO()
            image.save(stream, format='PNG')
            records.append({'sequence': seq, 'sha256': hashlib.sha256(stream.getvalue()).hexdigest(),
                            'path': 'https://untrusted.invalid/never-read.png'})
        self.report = {'workflow': 'aligned-slices-v3', 'status': 'complete', 'sampling': inputs.plan(),
                       'planned_slices': 1, 'sequences': ['t1', 'flair'], 'reviews': [
                           {'z': 12, 'decision': {'review': 'yes', 'observation': 'Unlocalized research flag'},
                            'text': '</script><script>untrusted()</script>', 'prompt': 'Question', 'images': records}]}
        self.path = Path(self.study.analysis, 'medgemma-review-test.json')
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report))

    def test_embeds_verified_planes_without_inventing_lesion_coordinates(self):
        result = load_review(self.study)
        self.assertEqual(result['status'], 'complete')
        row = result['reviews'][0]
        self.assertEqual(row['z'], 12)
        self.assertNotIn('pos', row)
        self.assertTrue(all(im['src'].startswith('data:image/png;base64,') for im in row['images']))
        run(self.study, log=lambda _: None)
        html = Path(self.study.viewer_html).read_text()
        self.assertNotIn('</script><script>untrusted()', html)
        self.assertNotIn('__MEDGEMMA__', html)
        self.assertIn('Unlocalized research flag', html)

    def test_same_geometry_but_changed_images_cannot_attach(self):
        path = Path(self.study.analysis, 'ref_grid.nii.gz')
        image = nib.load(path)
        data = image.get_fdata().astype(np.float32)
        data[5:10, 5:10, 12] = 500
        nib.save(nib.Nifti1Image(data, image.affine), path)
        with self.assertRaisesRegex(ValueError, 'inputs differ'):
            load_review(self.study, self.path)
        self.assertEqual(load_review(self.study)['status'], 'unavailable')

    def test_incomplete_or_wrong_geometry_report_is_not_attached(self):
        self.report['status'] = 'in_progress'
        self.save()
        self.assertEqual(load_review(self.study)['status'], 'unavailable')
        self.report['status'] = 'complete'
        self.report['sampling']['shape'][0] += 2
        self.save()
        with self.assertRaisesRegex(ValueError, 'geometry'):
            load_review(self.study, self.path)

    def test_no_report_leaves_viewer_available(self):
        self.path.unlink()
        self.assertEqual(load_review(self.study)['status'], 'absent')
        run(self.study, log=lambda _: None)
        self.assertTrue(Path(self.study.viewer_html).exists())

    def test_clinician_drafts_are_bound_to_image_content_and_affine(self):
        def build_meta():
            run(self.study, log=lambda _: None, medgemma_report=None)
            html = Path(self.study.viewer_html).read_text()
            self.assertNotIn('__ANNOTATION_CORE__', html)
            self.assertNotIn('__CLINICIAN_VIEWER__', html)
            return json.loads(re.search(r'<script id="meta"[^>]*>(.*?)</script>', html, re.S)[1])

        self.path.unlink()
        first = build_meta()
        self.assertEqual(first['study_id'], build_meta()['study_id'])
        image_path = Path(self.study.analysis, 'ref_grid.nii.gz')
        image = nib.load(image_path)
        data = image.get_fdata().astype(np.float32)
        data[0, 0, 0] += 1
        nib.save(nib.Nifti1Image(data, image.affine), image_path)
        second = build_meta()
        self.assertNotEqual(first['study_id'], second['study_id'])
        affine = image.affine.copy()
        affine[0, 3] += 10
        nib.save(nib.Nifti1Image(data, affine), image_path)
        third = build_meta()
        self.assertNotEqual(second['study_id'], third['study_id'])
        self.assertEqual(third['affine'], affine.tolist())


if __name__ == '__main__':
    unittest.main()
