"""Local research worklist: completed DICOM exports -> durable jobs -> drafts.

AI outputs never assign clinical priority. Only an explicit human action does.
"""
from contextlib import contextmanager
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import uuid


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "worklist.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, source TEXT, label TEXT,
                created REAL, updated REAL, state TEXT, stage TEXT, error TEXT,
                priority TEXT DEFAULT 'unassigned', reviewed INTEGER DEFAULT 0,
                report TEXT, warnings TEXT DEFAULT '[]')""")
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, job_id TEXT, at REAL, action TEXT, detail TEXT)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, source, fingerprint, error=None):
        now, jid = time.time(), uuid.uuid4().hex[:16]
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO jobs (id,fingerprint,source,label,created,updated,state,stage,error) VALUES (?,?,?,?,?,?,?,?,?)",
                       (jid, fingerprint, str(source), Path(source).name, now, now,
                        "failed" if error else "queued", "export rejected" if error else "intake", error))
            row = db.execute("SELECT * FROM jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
            if row["id"] == jid:
                db.execute("INSERT INTO events(job_id,at,action,detail) VALUES (?,?,?,?)",
                           (jid, now, "received", error or "Completed export accepted"))
        return dict(row)

    def get(self, jid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if row is None:
            raise KeyError("Unknown study")
        return dict(row)

    def rows(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT * FROM jobs ORDER BY
                CASE priority WHEN 'expedite' THEN 0 ELSE 1 END, created, id""")]

    def update(self, jid, action, **fields):
        allowed = {"state", "stage", "error", "priority", "reviewed", "report", "warnings"}
        if not fields or not fields.keys() <= allowed:
            raise ValueError("Invalid job update")
        fields["updated"] = time.time()
        with self.connect() as db:
            count = db.execute("UPDATE jobs SET " + ','.join(f"{key}=?" for key in fields) + " WHERE id=?",
                               [*fields.values(), jid]).rowcount
            if not count:
                raise KeyError("Unknown study")
            db.execute("INSERT INTO events(job_id,at,action,detail) VALUES (?,?,?,?)",
                       (jid, fields["updated"], action, json.dumps(fields)))

    def human_action(self, jid, action, value=None):
        row = self.get(jid)
        if action == "priority" and value in ("unassigned", "routine", "expedite"):
            self.update(jid, "human_priority", priority=value)
        elif action == "reviewed" and row["state"] == "draft_ready":
            self.update(jid, "human_reviewed", reviewed=1)
        elif action == "retry" and row["state"] == "failed" and row["stage"] != "export rejected":
            self.update(jid, "human_retry", state="queued", stage="intake", error=None)
        else:
            raise ValueError("Action not available for this study")

    def recover(self):
        for row in self.rows():
            if row["state"] == "processing":
                self.update(row["id"], "interrupted", state="failed", error="Processing was interrupted. Retry is available.")


def export_signature(source):
    rows = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Export contains a symbolic link")
        if path.is_file() and path.name != ".ready":
            stat = path.stat()
            rows.append((str(path.relative_to(source)), stat.st_size, stat.st_mtime_ns))
    return rows


def inspect_export(source):
    """Read no patient name/ID. Reject mixed studies and inconsistent instance IDs."""
    import pydicom
    from .extract import is_dicom
    if not (source / ".ready").is_file():
        raise ValueError("Export is missing its .ready completion marker")
    signature = export_signature(source)
    study_uids, instances, files = set(), {}, []
    for rel, _, _ in signature:
        path = source / rel
        if not is_dicom(str(path)):
            continue
        ds = pydicom.dcmread(path, stop_before_pixels=True, specific_tags=[
            "StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "Modality", "Rows", "Columns",
            "NumberOfFrames", "ImageOrientationPatient", "ImagePositionPatient", "PixelSpacing"])
        # Ignore DICOMDIR and non-image objects; reject unsupported image modalities.
        if not ds.get("Rows") or not ds.get("Columns"):
            continue
        if str(ds.get("Modality", "")) != "MR":
            raise ValueError("Export includes non-MR images")
        if int(ds.get("NumberOfFrames", 1)) != 1 or any(tag not in ds for tag in (
                "ImageOrientationPatient", "ImagePositionPatient", "PixelSpacing")):
            raise ValueError("Only classic single-frame MR images with patient geometry are supported")
        uid = str(ds.get("StudyInstanceUID", ""))
        sop = str(ds.get("SOPInstanceUID", ""))
        if not uid or not sop or not ds.get("SeriesInstanceUID"):
            raise ValueError("Image is missing required study/series/instance identifiers")
        study_uids.add(uid)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
        if sop in instances:
            raise ValueError("Repeated SOP instance in export; remove duplicates before processing")
        instances[sop] = digest
        files.append(rel)
    if len(study_uids) != 1:
        raise ValueError("Export must contain images from exactly one DICOM study")
    if not files:
        raise ValueError("No supported DICOM images found")
    roles = source / "roles.json"
    roles_digest = hashlib.sha256(roles.read_bytes()).hexdigest() if roles.exists() else None
    fingerprint = hashlib.sha256(json.dumps([sorted(instances.items()), roles_digest]).encode()).hexdigest()
    if signature != export_signature(source):
        raise ValueError("Export changed during intake; wait for completion and retry")
    return fingerprint, files


def discover(inbox, store, cache):
    for source in sorted(inbox.iterdir()):
        if not source.is_dir() or source.is_symlink() or not (source / ".ready").is_file():
            continue
        try:
            signature = export_signature(source)
            if cache.get(str(source)) == signature:
                continue
            fingerprint, _ = inspect_export(source)
            store.add(source, fingerprint)
            cache[str(source)] = signature
        except Exception as exc:
            error_key = hashlib.sha256(f"{source}:{exc}".encode()).hexdigest()
            store.add(source, error_key, error=str(exc))


def run_command(args, log_path):
    with log_path.open("ab") as log:
        proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = proc.wait()
        except BaseException:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise
    if code:
        raise RuntimeError(f"Processing command failed (exit {code}); see processing.log")


def process_job(store, row, model_dir, command=run_command):
    jid = row["id"]
    job = store.root / "jobs" / jid
    job.mkdir(parents=True, exist_ok=True)
    study = job / "study"
    log = job / "processing.log"
    source = Path(row["source"])
    store.update(jid, "processing_started", state="processing", stage="checking", error=None)
    try:
        fingerprint, files = inspect_export(source)
        if fingerprint != row["fingerprint"]:
            raise ValueError("Source export changed since this job was received; intake will create a new job")
        snapshot = job / f"input-{time.time_ns()}"
        snapshot.mkdir()
        for rel in files + (["roles.json"] if (source / "roles.json").exists() else []):
            dest = snapshot / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, dest)
        (snapshot / ".ready").touch()
        if inspect_export(snapshot)[0] != fingerprint:
            raise ValueError("Export changed during snapshot; no analysis was run")
        cli = [sys.executable, "-m", "mri_preread"]
        store.update(jid, "extracting", stage="extracting")
        command(cli + ["extract", str(snapshot), str(study)], log)
        warnings = []
        if (snapshot / "roles.json").exists():
            shutil.copy2(snapshot / "roles.json", study / "roles.json")
        else:
            warnings.append("Sequence assignments were guessed from DICOM metadata and need human verification.")
        from .study import ROLES
        roles = json.loads((study / "roles.json").read_text())
        series = json.loads((study / "series.json").read_text())
        names = {item["name"] for item in series if item.get("nifti")}
        assignments = roles.get("series", {})
        if not isinstance(assignments, dict) or not any(assignments.values()):
            raise ValueError("No sequence roles were assigned; provide roles.json in the export")
        if any(role not in ROLES or (name is not None and name not in names)
               for role, name in assignments.items()):
            raise ValueError("Sequence roles must reference supported roles and extracted series names")
        store.update(jid, "analyzing", stage="preparing images", warnings=json.dumps(warnings))
        command(cli + ["analyze", str(study)], log)
        meta = json.loads((study / "analysis/meta.json").read_text())
        for sequence, info in meta["sequences"].items():
            if "rejected" in (info.get("alignment") or ""):
                warnings.append(f"{sequence.upper()}: registration was rejected; scanner coordinates were used.")
        if "adc" not in meta["available"] or "dwi" not in meta["available"]:
            warnings.append("DWI/ADC pair is incomplete; restricted diffusion cannot be checked across both sequences.")
        store.update(jid, "rendering", stage="building viewer", warnings=json.dumps(warnings))
        command(cli + ["build", str(study)], log)
        report = study / "analysis" / f"medgemma-review-{time.time_ns()}.json"
        store.update(jid, "model_started", stage="local AI review")
        command(cli + ["medgemma", "review", str(study), "--model-dir", str(model_dir),
                       "--step-mm", "10", "--max-tokens", "128", "--output", str(report)], log)
        result = json.loads(report.read_text())
        if result.get("status") != "complete":
            raise ValueError("Model report is incomplete")
        if not report.with_suffix(".html").is_file() or not (study / "brain_viewer.html").is_file():
            raise ValueError("Review material is missing; draft is not ready")
        warnings.append("Current MedGemma setup failed the preliminary benchmark; AI urgency is unavailable.")
        store.update(jid, "draft_ready", state="draft_ready", stage="awaiting human review",
                     report=str(report.relative_to(study).with_suffix(".html")), warnings=json.dumps(warnings))
    except Exception as exc:
        store.update(jid, "processing_failed", state="failed", error=str(exc))


def handler(store, inbox, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, content_type="application/json", status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def permitted(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.permitted():
                return self.send(b'{}', status=403)
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                return self.send(Path(__file__).with_name("worklist_template.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/jobs":
                rows = store.rows()
                for row in rows:
                    row.pop("source")
                    row.pop("fingerprint")
                    row["warnings"] = json.loads(row["warnings"])
                    row["ai_priority"] = "unavailable"
                waiting = [p.name for p in sorted(inbox.iterdir()) if p.is_dir() and not p.is_symlink() and not (p / ".ready").exists()]
                return self.send(json.dumps({"jobs": rows, "waiting": waiting}).encode())
            parts = path.split("/", 3)
            if len(parts) == 4 and parts[1] == "study":
                try:
                    store.get(parts[2])
                    base = (store.root / "jobs" / parts[2] / "study").resolve()
                    file = (base / parts[3]).resolve()
                    if file.is_relative_to(base) and file.is_file() and file.suffix in (".html", ".json", ".png"):
                        return self.send(file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                except KeyError:
                    pass
            self.send(b"Not found", "text/plain", 404)

        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self.permitted() or (origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")):
                return self.send(b'{}', status=403)
            if self.path != "/api/action":
                return self.send(b'{}', status=404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 4096:
                    raise ValueError("Invalid action size")
                action = json.loads(self.rfile.read(length))
                store.human_action(action["id"], action["action"], action.get("value"))
                self.send(b'{}')
            except (ValueError, KeyError, TypeError) as exc:
                self.send(json.dumps({"error": str(exc)}).encode(), status=400)
    return Handler


@contextmanager
def worker_lock(root):
    import fcntl
    with (root / ".worker.lock").open("w") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("A worklist worker is already running for this workspace") from exc
        yield


def configure_parser(sub):
    parser = sub.add_parser("worklist", help="watch completed DICOM exports and serve a local research worklist")
    parser.add_argument("--inbox", required=True)
    parser.add_argument("--workspace", default="data/worklist")
    parser.add_argument("--model-dir", default="models/medgemma-1.5-4b-it-4bit")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--once", action="store_true", help="process currently completed exports, then exit")


def main(args):
    inbox, root = Path(args.inbox).expanduser().resolve(), Path(args.workspace).expanduser().resolve()
    if inbox == root or root.is_relative_to(inbox) or inbox.is_relative_to(root):
        raise SystemExit("Inbox and workspace must be separate, non-nested directories")
    if args.poll_seconds < 1 or not 1 <= args.port <= 65535:
        raise SystemExit("Use a polling interval >= 1 second and a valid port")
    inbox.mkdir(parents=True, exist_ok=True)
    store = Store(root)
    with worker_lock(root):
        store.recover()
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(store, inbox, args.port))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"Research worklist: http://127.0.0.1:{args.port}/", flush=True)
        cache = {}
        try:
            while True:
                discover(inbox, store, cache)
                queued = [row for row in store.rows() if row["state"] == "queued"]
                if queued:
                    # Processing order is receipt order, not clinical priority or model output.
                    row = min(queued, key=lambda item: (item["created"], item["id"]))
                    process_job(store, row, Path(args.model_dir).expanduser().resolve())
                elif args.once:
                    break
                else:
                    time.sleep(args.poll_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
