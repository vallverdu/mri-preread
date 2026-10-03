"""Exercise the real stdio MCP/image path without weights or medical data."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from mcp.types import CallToolResult, TextContent
from PIL import Image

from mri_preread.medgemma import main, review, unpack_result
from mri_preread.study import Study


class FakeModel:
    path = "synthetic-test-model"
    provenance = {"test": True}

    def infer(self, prompt, image, max_tokens):
        assert isinstance(image, Image.Image) and image.mode == "RGB"
        assert image.width > 100 and image.height > 100
        return {"text": "Synthetic integration test only", "seconds": 0}


class MedGemmaTests(unittest.TestCase):
    def test_real_mcp_images_and_preserved_annotations(self):
        with tempfile.TemporaryDirectory() as root:
            study = Study(root)
            analysis = Path(study.analysis)
            analysis.mkdir()
            full = np.full((32, 32, 32), 100, dtype=np.uint8)
            half = np.zeros((16, 16, 16), dtype=np.uint8)
            mask = half.copy()
            mask[2:14, 2:14, 2:14] = 255
            np.savez(analysis / "viewer_data.npz", ref="flair", flair=full,
                     flair_hi=200., sp1=np.ones(3), mask=mask, outlier=half, asym=half)
            (analysis / "findings.json").write_text(json.dumps([
                {"kind": "outlier", "cls": "review", "pos": [16, 16, 16]},
            ]))
            original = '{"summary": null, "items": []}'
            Path(study.annotations).write_text(original)
            output = analysis / "medgemma-review-test.json"
            args = argparse.Namespace(sequences=None, max_candidates=1, max_tokens=32)
            with patch("mri_preread.medgemma.version", return_value="test"):
                asyncio.run(review(FakeModel(), study, args, output))
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "complete")
            self.assertEqual([r["tool"] for r in report["reviews"]], ["view_overview", "view_region"])
            self.assertEqual(Path(study.annotations).read_text(), original)
            self.assertFalse(Path(study.viewer_html).exists())

    def test_mcp_errors_are_not_sent_as_images(self):
        result = CallToolResult(isError=True, content=[TextContent(type="text", text="bad coordinates")])
        with self.assertRaisesRegex(RuntimeError, "bad coordinates"):
            unpack_result(result)

    def test_existing_report_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            analysis = Path(root, "analysis")
            analysis.mkdir()
            (analysis / "viewer_data.npz").touch()
            output = analysis / "existing.json"
            output.write_text("existing review")
            args = argparse.Namespace(action="review", study=root, max_candidates=0, output=str(output))
            with self.assertRaisesRegex(SystemExit, "already exists"):
                main(args)
            self.assertEqual(output.read_text(), "existing review")


if __name__ == "__main__":
    unittest.main()
