"""Study folder layout.

A study folder holds everything that belongs to one scan. None of it is code, and none of it should ever be
committed or published: it contains medical images of a real person.

    <study>/
      source/          optional: the original DICOM export (CD/USB copy), read by `mri-preread extract`
      study.json       non-identifying study info (description, date, scanner, age, sex)
      series.json      every series found in the DICOM export
      roles.json       which series is used as t1 / flair / t2 / swi / dwi / adc   (auto-guessed, editable)
      nifti/           each series as a NIfTI volume
      png/             optional: every image as 8-bit PNG
      analysis/        co-registered volumes, heterogeneity maps, findings.json, annotations.json, meta.json
      brain_viewer.html  self-contained viewer (contains the images: treat it like the scan itself)
"""
import json
import os

ROLES = ["t1", "t2", "flair", "swi", "dwi", "adc"]          # order used by the analysis and the viewer
ROLE_LABEL = {"t1": "T1", "t2": "T2", "flair": "FLAIR", "swi": "SWI", "dwi": "DWI", "adc": "ADC"}
REF_ORDER = ["t1", "flair", "t2", "swi", "dwi", "adc"]   # the first available one defines the viewer grid
ENV = "MRI_PREREAD_STUDY"


class Study:
    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(root))
        self.source = os.path.join(self.root, "source")
        self.nifti = os.path.join(self.root, "nifti")
        self.png = os.path.join(self.root, "png")
        self.analysis = os.path.join(self.root, "analysis")
        self.viewer_html = os.path.join(self.root, "brain_viewer.html")
        self.annotations = os.path.join(self.analysis, "annotations.json")

    def path(self, *p): return os.path.join(self.root, *p)

    def read_json(self, name, default=None):
        p = self.path(name)
        if not os.path.exists(p): return default
        with open(p, encoding="utf-8") as f: return json.load(f)

    def write_json(self, name, obj):
        p = self.path(name); os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1, ensure_ascii=False)
        os.replace(tmp, p)

    def roles(self):
        """roles.json with the available roles (any subset, in ROLES order) and the reference role."""
        r = self.read_json("roles.json")
        if not r: raise SystemExit(f"{self.path('roles.json')} not found: run `mri-preread extract` first, "
                                   "or write it by hand (see README).")
        series = {k: v for k, v in (r.get("series") or {}).items() if k in ROLES and v}
        if not series: raise SystemExit("roles.json assigns no series to any role (t1, t2, flair, swi, dwi, adc)")
        ref = r.get("reference") or next(k for k in REF_ORDER if k in series)
        if ref not in series: raise SystemExit(f"roles.json: reference '{ref}' has no series")
        return {**r, "series": series, "available": [k for k in ROLES if k in series], "reference": ref}


def resolve(arg=None):
    """Study folder from the command line, or from $MRI_PREREAD_STUDY."""
    root = arg or os.environ.get(ENV)
    if not root: raise SystemExit(f"no study folder given (pass it as an argument or set ${ENV})")
    if not os.path.isdir(root): raise SystemExit(f"study folder not found: {root}")
    return Study(root)
