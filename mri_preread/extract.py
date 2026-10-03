"""DICOM export -> NIfTI volumes (+ optional PNGs), series.json, study.json and a first guess of roles.json.

Walks a DICOM folder (CD/USB export, PACS download...) recursively, groups images by SeriesInstanceUID and writes
one NIfTI per series with the patient geometry (RAS). Nothing identifying is written: study.json only keeps the
fields that matter for reading the scan.
"""
import glob
import os
import re

import nibabel as nib
import numpy as np
import pydicom

from .study import ROLES

SKIP_EXT = {".jar", ".gz", ".exe", ".dll", ".jpg", ".png", ".txt", ".xml", ".html", ".js", ".css", ".bat", ".sh",
            ".ini", ".properties", ".zip", ".so", ".dylib", ".class", ".pdf", ".ds_store", ".json", ".plist", ".icns"}
STUDY_FIELDS = ["StudyDescription", "StudyDate", "Modality", "Manufacturer", "ManufacturerModelName",
                "MagneticFieldStrength", "PatientAge", "PatientSex"]      # deliberately no name / ID / birth date
PLANE = {0: "sagittal", 1: "coronal", 2: "axial"}


def slug(s): return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "series"


def is_dicom(f):
    if os.path.splitext(f)[1].lower() in SKIP_EXT or os.path.basename(f).upper() == "DICOMDIR": return False
    try:
        with open(f, "rb") as fh: return fh.read(132)[128:] == b"DICM"
    except OSError: return False


def scan(src):
    """{SeriesInstanceUID: [datasets with pixel data]}"""
    series = {}
    files = [f for f in glob.glob(os.path.join(src, "**", "*"), recursive=True) if os.path.isfile(f)]
    for f in files:
        if not is_dicom(f): continue
        try: d = pydicom.dcmread(f)
        except Exception: continue
        if "PixelData" not in d or "ImageOrientationPatient" not in d or "ImagePositionPatient" not in d: continue
        series.setdefault(str(d.get("SeriesInstanceUID", "")), []).append(d)
    return series


def pixels(d):
    a = d.pixel_array.astype(np.float32)
    return a * float(d.get("RescaleSlope", 1) or 1) + float(d.get("RescaleIntercept", 0) or 0)


def to_nifti(g, out):
    """Single-orientation series -> NIfTI (multi-volume series such as multi-b DWI become 4D)."""
    ori = np.array(g[0].ImageOrientationPatient, float); n = np.cross(ori[:3], ori[3:])
    if len({(int(d.Rows), int(d.Columns)) for d in g}) != 1: return None
    pos = np.array([np.dot(d.ImagePositionPatient, n) for d in g])
    upos = np.unique(np.round(pos, 2))
    nvol = len(g) // len(upos)
    if nvol * len(upos) != len(g): return None
    vols = []
    for v in range(nvol):
        sel = [g[j] for j in range(len(g)) if j % nvol == v] if nvol > 1 else g
        vols.append(np.stack([pixels(d) for d in sel], axis=-1).transpose(1, 0, 2))   # (col, row, slice)
    data = np.stack(vols, -1) if nvol > 1 else vols[0]
    dr, dc = map(float, g[0].PixelSpacing)
    dz = float(np.median(np.diff(upos))) if len(upos) > 1 else float(g[0].get("SliceThickness", 1) or 1)
    A = np.eye(4)
    A[:3, 0] = ori[:3] * dc; A[:3, 1] = ori[3:] * dr; A[:3, 2] = n * dz
    A[:3, 3] = g[0].ImagePositionPatient
    A = np.diag([-1, -1, 1, 1]) @ A                    # DICOM LPS -> NIfTI RAS
    integer = np.allclose(data, np.round(data))
    dtype = np.int16 if integer and data.min() >= -32768 and data.max() <= 32767 else np.float32
    img = nib.Nifti1Image(data.astype(dtype), A); img.header.set_xyzt_units("mm")
    nib.save(img, out)
    return dict(shape=list(data.shape), voxel_mm=[round(dc, 4), round(dr, 4), round(dz, 4)],
                plane=PLANE[int(np.argmax(np.abs(n)))], volumes=nvol)


def run(src, study, png=False, log=print):
    os.makedirs(study.nifti, exist_ok=True)
    raw = scan(src)
    if not raw: raise SystemExit(f"no DICOM images found under {src}")
    log(f"{sum(map(len, raw.values()))} images in {len(raw)} series")
    order = sorted(raw.values(), key=lambda ds: (int(ds[0].get("SeriesNumber", 0) or 0), str(ds[0].get("SeriesDescription", ""))))
    first = order[0][0]
    study.write_json("study.json", {k: str(first.get(k, "")) for k in STUDY_FIELDS})
    series, used = [], set()
    for ds in order:
        num = int(ds[0].get("SeriesNumber", 0) or 0); desc = str(ds[0].get("SeriesDescription", "") or "series").strip()
        name = f"{num:03d}_{slug(desc)}"
        while name in used: name += "_b"
        used.add(name)
        groups = {}                                    # localizers mix 3 planes: group by orientation
        for d in ds: groups.setdefault(tuple(np.round(np.array(d.ImageOrientationPatient, float), 3)), []).append(d)
        allimgs = []
        for ori, g in groups.items():
            n = np.cross(ori[:3], ori[3:])
            g.sort(key=lambda d: float(d.get("InstanceNumber", 0) or 0))
            g.sort(key=lambda d: float(np.dot(d.ImagePositionPatient, n)))
            allimgs += g
        s = dict(name=name, number=num, description=desc, images=len(allimgs), orientations=len(groups),
                 image_type=[str(x) for x in (ds[0].get("ImageType") or [])],
                 acquisition=str(ds[0].get("MRAcquisitionType", "")), thickness=float(ds[0].get("SliceThickness", 0) or 0),
                 nifti=None)
        if len(groups) == 1:
            info = to_nifti(allimgs, os.path.join(study.nifti, name + ".nii.gz"))
            if info: s.update(nifti=name + ".nii.gz", **info)
        if png: write_png(allimgs, os.path.join(study.png, name))
        series.append(s)
        log(f"  {name}: {len(allimgs)} images" + (f" -> {s['shape']} @ {s['voxel_mm']} mm ({s['plane']})" if s["nifti"] else ""))
    study.write_json("series.json", series)
    if study.read_json("roles.json"):
        log("roles.json exists, left unchanged")
    else:
        roles = guess_roles(series); study.write_json("roles.json", roles)
        for k in ROLES: log(f"  role {k:5s} = {roles['series'].get(k) or '-- NOT FOUND --'}")
        log(f"check {study.path('roles.json')} and fix any wrong or missing role before `mri-preread analyze`")
    return series


def write_png(imgs, folder):
    from PIL import Image
    os.makedirs(folder, exist_ok=True)
    arrs = [pixels(d) for d in imgs]
    lo, hi = np.percentile(np.stack(arrs) if len({a.shape for a in arrs}) == 1 else np.concatenate([a.ravel() for a in arrs]), [0.5, 99.7])
    for i, a in enumerate(arrs):
        Image.fromarray(np.clip((a - lo) / (hi - lo + 1e-6) * 255, 0, 255).astype(np.uint8)).save(os.path.join(folder, f"{i + 1:03d}.png"))


def from_nifti(files, study, log=print):
    """Study from NIfTI files, e.g. {"flair": "a.nii.gz", "dwi": "b.nii.gz"} (no DICOM: study.json stays minimal)."""
    import shutil
    os.makedirs(study.nifti, exist_ok=True)
    series, roles = [], {}
    for role, path in files.items():
        name = f"{role}_{slug(os.path.basename(path).split('.')[0])}"
        shutil.copyfile(path, os.path.join(study.nifti, name + ".nii.gz") if path.endswith(".gz") else os.path.join(study.nifti, name + ".nii"))
        if not path.endswith(".gz"):
            nib.save(nib.load(os.path.join(study.nifti, name + ".nii")), os.path.join(study.nifti, name + ".nii.gz"))
            os.remove(os.path.join(study.nifti, name + ".nii"))
        img = nib.load(os.path.join(study.nifti, name + ".nii.gz"))
        vs = np.sqrt((img.affine[:3, :3] ** 2).sum(0))
        series.append(dict(name=name, description="", source_file=os.path.basename(path), nifti=name + ".nii.gz", shape=list(img.shape),
                           voxel_mm=[round(float(x), 4) for x in vs], thickness=round(float(vs[2]), 3),
                           plane=PLANE[int(np.argmax(np.abs(img.affine[:3, 2])))], volumes=img.shape[3] if img.ndim == 4 else 1))
        roles[role] = name
        log(f"  {role:5s} <- {path}  {list(img.shape)} @ {np.round(vs, 2).tolist()} mm")
    study.write_json("series.json", series)
    if not study.read_json("study.json"): study.write_json("study.json", {"note": "imported from NIfTI (no DICOM header)"})
    study.write_json("roles.json", {"series": {k: roles.get(k) for k in ROLES}, "register": {}})


# ---------------------------------------------------------------- role guessing
KEYS = {
    "flair": ["FLAIR"],
    "swi": ["SWAN", "SWI", "SUSC", "T2*", "T2STAR", "HEMO", "MERGE", "GRE"],
    "dwi": ["DWI", "DIFF", "TRACE", "B1000"],
    "adc": ["ADC", "APPARENT"],
    "t2": ["T2"],
    "t1": ["T1", "MPRAGE", "SPGR", "BRAVO", "TFE"],
}
NOT = {"flair": [], "swi": ["T1", "FLAIR"], "dwi": ["ADC", "APPARENT", "EXPONENTIAL", "EADC", "FA", "COLOR"],
       "adc": ["EXPONENTIAL", "EADC"], "t2": ["FLAIR", "T2*", "SWAN", "SWI", "GRE", "DWI"], "t1": ["FLAIR", "POST", "+C", "GAD", "CONTRAST"]}


def guess_roles(series):
    """Keyword guess on SeriesDescription. Prefers original over reformatted images, axial for 2D sequences,
    and the finest 3D series for T1 (it becomes the viewer grid)."""
    vol = [s for s in series if s.get("nifti")]
    up = lambda s: s["description"].upper().replace(" ", "")
    out = {}
    for role in ["flair", "swi", "adc", "dwi", "t1", "t2"]:
        c = [s for s in vol if s["name"] not in out.values()
             and any(k.replace(" ", "") in up(s) for k in KEYS[role]) and not any(k in up(s) for k in NOT[role])]
        derived = lambda s: any(t in s.get("image_type", []) for t in ("REFORMATTED", "SECONDARY"))
        if role == "t1":
            c.sort(key=lambda s: (derived(s), -int(np.prod(s["shape"][:3]))))
        else:
            c.sort(key=lambda s: (derived(s), s.get("plane") != "axial", -int(np.prod(s["shape"][:3]))))
        if c: out[role] = c[0]["name"]
    return {"series": {k: out.get(k) for k in ROLES},
            "register": {},
            "note": "series names from series.json. 'register': {role: true|false} forces or skips rigid registration to T1 "
                    "(default: register, and fall back to scanner coordinates if the result moves the brain surface > 15 mm)."}
