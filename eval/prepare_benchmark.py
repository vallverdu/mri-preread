"""Build a blinded benchmark: N random ISLES 2022 stroke cases + M healthy controls (OpenNeuro ds007401, CC0).

Every case gets the same three sequences (FLAIR, DWI b1000, ADC), skull-stripped (ISLES ships them stripped; for
controls the brain mask comes from their T1 through this pipeline), a neutral id (case_01 ...) and its own study
folder. The key (which case is which, and where its lesion mask is) is written to <out>/_key/key.json, which the
readers must not open.

  python eval/prepare_benchmark.py --isles-zip data/_downloads/ISLES-2022.zip --out data/bench --n-isles 30 --n-controls 10
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi

S3 = "https://s3.amazonaws.com/openneuro.org"
EXCLUDE = {"sub-strokecase0232", "sub-strokecase0062", "sub-strokecase0125"}   # used while developing
CLI = [sys.executable, "-m", "mri_preread"]


def fetch(url, dest):
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        urllib.request.urlretrieve(url, dest + ".part"); os.replace(dest + ".part", dest)
    return dest


def list_controls():
    xml = urllib.request.urlopen(f"{S3}?list-type=2&prefix=ds007401/sub-4&delimiter=/&max-keys=1000").read().decode()
    return sorted(set(re.findall(r"<Prefix>ds007401/(sub-4\d{3})/</Prefix>", xml)))


def diffusion_maps(dwi_path, bval_path, out_dwi, out_adc):
    """Clinical-style maps from multi-shell data: ADC by log-linear fit over b <= 1000 (trace = geometric mean over
    directions per shell), and a synthetic b=1000 trace image S0 * exp(-1000 * ADC). ADC in x1e-6 mm2/s."""
    img = nib.load(dwi_path); d = img.get_fdata(dtype=np.float32); b = np.loadtxt(bval_path)
    shells = sorted({int(round(x / 100) * 100) for x in b if x <= 1000})
    logS = np.stack([np.log(np.maximum(d[..., np.abs(b - s) < 50], 1)).mean(-1) for s in shells], -1)
    B = np.array(shells, float); Bc = B - B.mean()
    slope = (logS * Bc).sum(-1) / (Bc ** 2).sum()                      # d log S / d b
    adc = np.clip(-slope, 0, 5e-3); s0 = np.exp(logS.mean(-1) - slope * B.mean())
    fg = s0 > np.percentile(s0, 60) * 0.3
    nib.save(nib.Nifti1Image((adc * 1e6 * fg).astype(np.float32), img.affine), out_adc)
    nib.save(nib.Nifti1Image((s0 * np.exp(-1000 * adc) * fg).astype(np.float32), img.affine), out_dwi)


def strip_with_t1(work, t1, flair, dwi, adc, out):
    """Brain mask from the T1 through mri-preread, mapped into each native sequence; zero outside (dilated 2 mm)."""
    st = os.path.join(work, "t1study")
    subprocess.run(CLI + ["import", st, "--t1", t1, "--flair", flair, "--dwi", dwi, "--adc", adc], check=True, capture_output=True)
    r = json.load(open(os.path.join(st, "roles.json"))); r["skull_strip"] = "t1"      # IDEAS images are only loosely masked
    json.dump(r, open(os.path.join(st, "roles.json"), "w"), indent=1)
    subprocess.run(CLI + ["analyze", st], check=True, capture_output=True)
    A = os.path.join(st, "analysis")
    mask = sitk.ReadImage(os.path.join(A, "brain_mask.nii.gz"), sitk.sitkUInt8)
    mask = sitk.BinaryDilate(mask, [2, 2, 2])
    for role, src in [("flair", flair), ("dwi", dwi), ("adc", adc)]:
        T = sitk.ReadTransform(os.path.join(A, f"transform_{role}.tfm"))
        try: Ti = T.GetInverse()
        except Exception: Ti = sitk.Transform()
        img = sitk.ReadImage(src, sitk.sitkFloat32)
        m = sitk.Resample(mask, img, Ti, sitk.sitkNearestNeighbor, 0)
        arr = sitk.GetArrayFromImage(img) * (sitk.GetArrayFromImage(m) > 0)
        o = sitk.GetImageFromArray(arr.astype(np.float32)); o.CopyInformation(img)
        sitk.WriteImage(o, os.path.join(out, f"{role}.nii.gz"))


def prepare_control(sub, downloads, staged):
    dl = os.path.join(downloads, sub); p = f"{S3}/ds007401/{sub}/ses-1"
    t1 = fetch(f"{p}/anat/{sub}_ses-1_T1w.nii.gz", f"{dl}/T1w.nii.gz")
    fl = fetch(f"{p}/anat/{sub}_ses-1_FLAIR.nii.gz", f"{dl}/FLAIR.nii.gz")
    dw = fetch(f"{p}/dwi/{sub}_ses-1_dwi.nii.gz", f"{dl}/dwi.nii.gz")
    bv = fetch(f"{p}/dwi/{sub}_ses-1_dwi.bval", f"{dl}/dwi.bval")
    work = os.path.join(dl, "work_bench"); os.makedirs(work, exist_ok=True)
    diffusion_maps(dw, bv, f"{work}/dwi1000.nii.gz", f"{work}/adc.nii.gz")
    strip_with_t1(work, t1, fl, f"{work}/dwi1000.nii.gz", f"{work}/adc.nii.gz", staged)
    A = os.path.join(work, "t1study", "analysis")                 # quality gates: plausible brain mask, FLAIR aligned
    m = nib.load(os.path.join(A, "brain_mask.nii.gz")); v = m.get_fdata().sum() * np.prod(np.sqrt((m.affine[:3, :3] ** 2).sum(0))) / 1000
    meta = json.load(open(os.path.join(A, "meta.json")))
    if not 900 <= v <= 1750: raise RuntimeError(f"T1 brain mask {v:.0f} cm3 outside 900-1750")
    if "rejected" in (meta["sequences"]["flair"].get("alignment") or ""): raise RuntimeError("FLAIR registration to T1 failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--isles-zip", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--n-isles", type=int, default=30); ap.add_argument("--n-controls", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260928); ap.add_argument("--downloads")
    a = ap.parse_args()
    raw = os.path.join(a.out, "_raw"); keyd = os.path.join(a.out, "_key"); os.makedirs(keyd, exist_ok=True)
    rng = random.Random(a.seed)

    z = zipfile.ZipFile(a.isles_zip)
    subs = sorted({m.group(1) for n in z.namelist() if (m := re.match(r"ISLES-2022/(sub-strokecase\d+)/", n))} - EXCLUDE)
    isles = rng.sample(subs, a.n_isles)
    pool = list_controls(); rng.shuffle(pool)                 # controls are drawn in this order; failures are replaced
    entries = [("isles", s) for s in isles] + [("control", None)] * a.n_controls
    rng.shuffle(entries)
    key, excluded = {}, []
    for i, (src, sub) in enumerate(entries, 1):
        cid = f"case_{i:02d}"; staged = os.path.join(raw, cid); os.makedirs(staged, exist_ok=True)
        print(cid, "...", flush=True)
        if src == "isles":
            base = f"ISLES-2022/{sub}/ses-0001"
            for role, member in [("flair", f"{base}/anat/{sub}_ses-0001_FLAIR.nii.gz"), ("dwi", f"{base}/dwi/{sub}_ses-0001_dwi.nii.gz"),
                                 ("adc", f"{base}/dwi/{sub}_ses-0001_adc.nii.gz")]:
                with z.open(member) as fi, open(os.path.join(staged, f"{role}.nii.gz"), "wb") as fo: shutil.copyfileobj(fi, fo)
            mask = os.path.join(keyd, f"{cid}_mask.nii.gz")
            with z.open(f"ISLES-2022/derivatives/{sub}/ses-0001/{sub}_ses-0001_msk.nii.gz") as fi, open(mask, "wb") as fo: shutil.copyfileobj(fi, fo)
            key[cid] = {"source": "ISLES-2022", "subject": sub, "mask": mask, "mask_space": "dwi"}
        else:
            while True:
                sub = pool.pop(0)
                try:
                    prepare_control(sub, a.downloads or os.path.join(a.out, "_downloads"), staged); break
                except Exception as e:
                    excluded.append({"subject": sub, "reason": str(e)[:200]}); print(f"  control {sub} excluded: {e}", flush=True)
            key[cid] = {"source": "OpenNeuro ds007401 (healthy control)", "subject": sub, "mask": None}
        study = os.path.join(a.out, cid)
        subprocess.run(CLI + ["import", study, "--flair", f"{staged}/flair.nii.gz", "--dwi", f"{staged}/dwi.nii.gz",
                              "--adc", f"{staged}/adc.nii.gz"], check=True, capture_output=True)
        json.dump({"cases": key, "excluded_controls": excluded, "seed": a.seed}, open(os.path.join(keyd, "key.json"), "w"), indent=1)
    print(f"{len(entries)} cases -> {a.out}; key in {keyd}/key.json (do not show to readers)")


if __name__ == "__main__":
    main()
