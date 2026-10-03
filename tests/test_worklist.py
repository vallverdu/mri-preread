import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from mri_preread.worklist import Store, discover, handler, inspect_export, process_job, worker_lock


def dicom(path, study_uid=None, sop_uid=None):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MRImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid or generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = MRImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study_uid or generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "MR"
    ds.Rows = ds.Columns = 2
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, 0]
    ds.PixelSpacing = [1, 1]
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = b"\0" * 8
    ds.save_as(path, enforce_file_format=True)
    return ds


class WorklistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.source = self.inbox / "example"
        self.source.mkdir()
        dicom(self.source / "one.dcm")
        self.store = Store(self.root / "worklist")

    def ready(self):
        (self.source / ".ready").touch()
        fingerprint, _ = inspect_export(self.source)
        return self.store.add(self.source, fingerprint)

    def test_waits_for_completion_and_deduplicates_copied_exports(self):
        discover(self.inbox, self.store, {})
        self.assertEqual(self.store.rows(), [])
        self.ready()
        shutil.copytree(self.source, self.inbox / "same-export-again")
        discover(self.inbox, self.store, {})
        self.assertEqual(len(self.store.rows()), 1)

    def test_mixed_studies_are_visible_failures(self):
        dicom(self.source / "different-study.dcm")
        (self.source / ".ready").touch()
        discover(self.inbox, self.store, {})
        row = self.store.rows()[0]
        self.assertEqual(row["state"], "failed")
        self.assertIn("exactly one", row["error"])
        with self.assertRaises(ValueError):
            self.store.human_action(row["id"], "retry")

    def test_duplicate_instance_is_rejected(self):
        shutil.copy2(self.source / "one.dcm", self.source / "duplicate.dcm")
        (self.source / ".ready").touch()
        with self.assertRaisesRegex(ValueError, "Repeated SOP"):
            inspect_export(self.source)

    def test_changed_export_is_not_processed_as_old_job(self):
        row = self.ready()
        (self.source / "roles.json").write_text('{"series": {"t1": "changed"}}')
        calls = []
        process_job(self.store, row, "unused", command=lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(self.store.get(row["id"])["state"], "failed")

    def test_successful_pipeline_preserves_human_priority_and_source(self):
        row = self.ready()
        original = (self.source / "one.dcm").read_bytes()
        self.store.human_action(row["id"], "priority", "expedite")
        commands = []

        def fake_command(args, log):
            commands.append(args[3])
            study = self.store.root / "jobs" / row["id"] / "study"
            (study / "analysis").mkdir(parents=True, exist_ok=True)
            if args[3] == "extract":
                (study / "series.json").write_text('[{"name":"001_DWI","nifti":"001_DWI.nii.gz"}]')
                (study / "roles.json").write_text('{"series":{"dwi":"001_DWI"}}')
            elif args[3] == "analyze":
                (study / "analysis/meta.json").write_text(json.dumps({"available": ["dwi", "adc"], "sequences": {}}))
            elif args[3] == "medgemma":
                report = Path(args[args.index("--output") + 1])
                report.write_text('{"status":"complete","reviews":[]}')
                report.with_suffix(".html").write_text("<html>trace</html>")
            elif args[3] == "build":
                (study / "brain_viewer.html").write_text("<html>viewer</html>")

        process_job(self.store, row, "unused", fake_command)
        result = self.store.get(row["id"])
        self.assertEqual(commands, ["extract", "analyze", "build", "medgemma"])
        self.assertEqual(result["state"], "draft_ready")
        self.assertEqual(result["priority"], "expedite")
        self.assertEqual((self.source / "one.dcm").read_bytes(), original)
        self.store.human_action(row["id"], "reviewed")
        self.assertEqual(self.store.get(row["id"])["reviewed"], 1)

    def test_unsupported_multiframe_export_is_rejected(self):
        import pydicom
        path = self.source / "one.dcm"
        ds = pydicom.dcmread(path)
        ds.NumberOfFrames = 2
        ds.save_as(path, enforce_file_format=True)
        (self.source / ".ready").touch()
        with self.assertRaisesRegex(ValueError, "single-frame"):
            inspect_export(self.source)

    def test_external_sequence_path_cannot_reach_analysis(self):
        (self.source / "roles.json").write_text('{"series":{"dwi":"../../outside"}}')
        row = self.ready()
        calls = []

        def extract_only(args, log):
            calls.append(args[3])
            study = self.store.root / "jobs" / row["id"] / "study"
            study.mkdir()
            (study / "series.json").write_text('[{"name":"001_DWI","nifti":"001_DWI.nii.gz"}]')

        process_job(self.store, row, "unused", extract_only)
        self.assertEqual(calls, ["extract"])
        self.assertEqual(self.store.get(row["id"])["state"], "failed")
        self.assertIn("extracted series", self.store.get(row["id"])["error"])

    def test_restart_exposes_interruption_and_preserves_priority(self):
        row = self.ready()
        self.store.update(row["id"], "test", state="processing", priority="expedite")
        restarted = Store(self.store.root)
        restarted.recover()
        self.assertEqual(restarted.get(row["id"])["state"], "failed")
        self.assertEqual(restarted.get(row["id"])["priority"], "expedite")
        restarted.human_action(row["id"], "retry")
        self.assertEqual(restarted.get(row["id"])["state"], "queued")

    def test_only_one_worker_can_own_workspace(self):
        with worker_lock(self.store.root):
            with self.assertRaises(SystemExit):
                with worker_lock(self.store.root):
                    pass

    def request(self, path, origin=None, body=None):
        obj = object.__new__(handler(self.store, self.inbox, 8800))
        obj.path = path
        obj.headers = {"Host": "127.0.0.1:8800"}
        if origin:
            obj.headers["Origin"] = origin
        result = []
        obj.send = lambda body, content_type="application/json", status=200: result.append((status, body))
        if body is None:
            obj.do_GET()
        else:
            data = json.dumps(body).encode()
            obj.headers["Content-Length"] = str(len(data))
            obj.rfile = io.BytesIO(data)
            obj.do_POST()
        return result[0]

    def test_cross_origin_priority_change_is_rejected(self):
        row = self.ready()
        status, _ = self.request("/api/action", "https://untrusted.example", {"id": row["id"], "action": "priority", "value": "expedite"})
        self.assertEqual(status, 403)
        self.assertEqual(self.store.get(row["id"])["priority"], "unassigned")

    def test_workspace_files_are_not_exposed_by_traversal(self):
        row = self.ready()
        status, _ = self.request(f"/study/{row['id']}/../../../worklist.sqlite3")
        self.assertEqual(status, 404)
        status, body = self.request("/api/jobs")
        payload = json.loads(body)
        self.assertNotIn("source", payload["jobs"][0])
        self.assertEqual(payload["jobs"][0]["ai_priority"], "unavailable")


if __name__ == "__main__":
    unittest.main()
