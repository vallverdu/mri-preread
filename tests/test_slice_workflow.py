import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from mri_preread.slice_input import SliceInputs
from mri_preread.medgemma_trace import parse_decision, review_slices
from mri_preread.study import Study
from eval.medgemma_pilot import aligned_mask, freeze, score, summarize


def synthetic_study(root):
    study = Study(root)
    a = Path(study.analysis)
    a.mkdir()
    d = np.full((32, 32, 32), 20, dtype=np.float32)
    d[22:28, 20:26, 10:16] = 200
    affine = np.diag([1., 2., 3., 1.])
    mask = np.zeros(d.shape, dtype=np.uint8)
    mask[3:29, 3:29, 3:29] = 1
    nib.save(nib.Nifti1Image(d, affine), a / "ref_grid.nii.gz")
    nib.save(nib.Nifti1Image(mask, affine), a / "brain_mask.nii.gz")
    half = d.reshape(16, 2, 16, 2, 16, 2).mean((1, 3, 5))
    coarse = affine @ np.diag([2, 2, 2, 1])
    coarse[:3, 3] = affine[:3, :3] @ [.5, .5, .5]
    nib.save(nib.Nifti1Image(half, coarse), a / "flair_in_ref_space.nii.gz")
    (a / "meta.json").write_text(json.dumps({"reference": "t1", "available": ["t1", "flair"],
                                           "sequences": {"t1": {}, "flair": {}}}))
    (a / "findings.json").write_text("[]")
    (a / "annotations.json").write_text('{"items": [], "summary": null}')
    np.savez(a / "viewer_data.npz", ref="t1", sp1=[1, 2, 3], t1=d.astype(np.uint8), t1_hi=255,
             flair=half.astype(np.uint8), flair_hi=255, mask=mask[::2, ::2, ::2] * 255,
             outlier=np.zeros(half.shape), asym=np.zeros(half.shape))
    return study


class FakeModel:
    path = "synthetic"
    provenance = {"test": True}

    def infer_images(self, prompt, images, max_tokens, decision_mode=False):
        assert len(images) == 2 and all(i.size == (896, 896) for i in images)
        assert decision_mode
        assert "stroke" not in prompt.lower() and "ground-truth" not in prompt.lower()
        return {"text": "uncertain\nSynthetic test only.", "seconds": .1, "hit_token_limit": False}


class SliceTests(unittest.TestCase):
    def test_orientation_alignment_aspect_and_no_annotations(self):
        with tempfile.TemporaryDirectory() as root:
            study = synthetic_study(root)
            renderer = SliceInputs(study)
            meta, images = renderer.render(12, ["t1", "flair"])
            json.dumps(meta)  # metadata must also survive MCP JSON serialization
            self.assertEqual(meta["frames"][0]["content_size"], [448, 896])
            for im in images:
                arr = np.asarray(im)
                yy, xx = np.where(arr[:, :, 0] > 200)
                self.assertLess(xx.mean(), 448)  # high x (patient right) appears on image left
                self.assertLess(yy.mean(), 448)  # high y (anterior) appears toward image top
                self.assertEqual(arr[:, :224].sum(), 0)  # letterbox preserves physical aspect
            a, b = [np.asarray(im)[:, :, 0] for im in images]
            self.assertLess(abs(np.where(a > 200)[1].mean() - np.where(b > 200)[1].mean()), 5)
            Path(study.annotations).write_text('{"items": [{"title": "DO NOT LEAK", "pos": [24,22,12]}]}')
            _, again = renderer.render(12, ["t1", "flair"])
            self.assertEqual(images[0].tobytes(), again[0].tobytes())
            with self.assertRaises(ValueError):
                renderer.render(-1, ["t1"])

    def test_real_mcp_trace_and_preservation(self):
        with tempfile.TemporaryDirectory() as root:
            study = synthetic_study(root)
            before = Path(study.annotations).read_bytes()
            output = Path(study.analysis, "medgemma-review.json")
            args = argparse.Namespace(step_mm=10, sequences=None, max_slices=2, max_tokens=32)
            with patch("mri_preread.medgemma_trace.version", return_value="test"):
                asyncio.run(review_slices(FakeModel(), study, args, output))
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "complete")
            self.assertEqual(len(report["reviews"]), 2)
            self.assertTrue(output.with_suffix(".html").exists())
            self.assertEqual(Path(study.annotations).read_bytes(), before)
            self.assertTrue(all((output.parent / im["path"]).exists() for r in report["reviews"] for im in r["images"]))

    def test_parse_abstentions_and_invalid(self):
        self.assertEqual(parse_decision("uncertain\nArtifact prevents assessment")["review"], "uncertain")
        self.assertEqual(parse_decision("FINDINGS: normal")["review"], "invalid")
        self.assertEqual(parse_decision('A\nFinding', True)["review"], "yes")
        self.assertTrue(parse_decision('A\nFinding', True)["observation_truncated"])

    def test_scoring_does_not_turn_abstention_into_negative(self):
        metrics = summarize([{"lesion_present": True, "decision": "uncertain"},
                             {"lesion_present": True, "decision": "yes"},
                             {"lesion_present": False, "decision": "invalid"}])
        self.assertEqual(metrics["flagged_lesion_planes"]["rate"], .5)
        self.assertEqual(metrics["counts"]["negative"]["no"], 0)

    def test_ground_truth_transform_direction(self):
        with tempfile.TemporaryDirectory() as root:
            a = Path(root, "analysis")
            a.mkdir()
            image = sitk.Image([10, 10, 10], sitk.sitkUInt8)
            sitk.WriteImage(image, str(a / "ref_grid.nii.gz"))
            image[6, 4, 2] = 1
            mask = Path(root, "mask.nii.gz")
            sitk.WriteImage(image, str(mask))
            tx = sitk.TranslationTransform(3, [1., 0., 0.])
            sitk.WriteTransform(tx, str(a / "transform_dwi.tfm"))
            gt = aligned_mask(root, mask, "dwi")
            self.assertTrue(gt[5, 4, 2])
            self.assertEqual(gt.sum(), 1)

    def test_modified_input_is_rejected_before_labels_are_opened(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root)
            image = out / "input.png"
            image.write_bytes(b"synthetic input")
            report = {"status": "complete", "planned_slices": 1, "reviews": [{"images": [
                {"path": image.name, "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
            ]}]}
            (out / "case_test.json").write_text(json.dumps(report))
            freeze(out, ["case_test"])
            image.write_bytes(b"modified input")
            with self.assertRaisesRegex(ValueError, "Frozen artifact was modified"):
                score(out / "no-label-directory", out, ["case_test"])


if __name__ == "__main__":
    unittest.main()
