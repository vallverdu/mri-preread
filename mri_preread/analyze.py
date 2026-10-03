"""Analysis pipeline: reference grid (T1 if available), skull strip, co-registration, heterogeneity maps, findings.

Reads  <study>/nifti + roles.json      Writes <study>/analysis/ (NIfTI maps, findings.json, meta.json, viewer_data.npz)

Exploratory only. The maps flag voxels that are statistically unusual for THIS scan (or differ from the mirrored
hemisphere). Normal anatomy (veins, sinuses, ventricles) and scanner artifacts get flagged too. Not a diagnosis.
"""
import json
import os

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from sklearn.mixture import GaussianMixture

from .study import ROLE_LABEL as SEQ_NAME

MAX_DRIFT_MM = 15.0     # a registration that moves the brain surface further than this is treated as failed


def half(a):
    I, J, K = (s // 2 for s in a.shape)
    return a[:2 * I, :2 * J, :2 * K].reshape(I, 2, J, 2, K, 2).mean((1, 3, 5))


def to_sitk(a, sp):
    im = sitk.GetImageFromArray(np.ascontiguousarray(a.transpose(2, 1, 0)).astype(np.float32))
    im.SetSpacing([float(s) for s in sp]); return im


def from_sitk(im): return sitk.GetArrayFromImage(im).transpose(2, 1, 0)


def ellip(r_mm, sp):
    r = np.ceil(r_mm / sp).astype(int); z = np.mgrid[-r[0]:r[0] + 1, -r[1]:r[1] + 1, -r[2]:r[2] + 1]
    return ((z[0] * sp[0]) ** 2 + (z[1] * sp[1]) ** 2 + (z[2] * sp[2]) ** 2) <= r_mm ** 2


def adc_scale(values):
    """Factor that brings an ADC map to x1e-6 mm2/s. Sites store mm2/s, x1e-3 mm2/s or x1e-6 mm2/s;
    brain tissue is ~0.7-0.9e-3 mm2/s, so the median of the positive values tells them apart."""
    med = float(np.median(values[values > 0])) if (values > 0).any() else 0.0
    return 1e6 if 0 < med < 0.05 else 1e3 if 0 < med < 50 else 1.0


def load3d(path, role, tmp, log=print):
    """3D NIfTI as SimpleITK image; 4D series: DWI -> its high-b (darkest) volume, anything else -> first volume.
    ADC is converted to x1e-6 mm2/s."""
    img = nib.load(path)
    if img.ndim == 3 and role != "adc": return sitk.ReadImage(path, sitk.sitkFloat32)
    dd = img.get_fdata()
    if dd.ndim == 4:
        i = int(np.argmin([dd[..., j].mean() for j in range(dd.shape[-1])])) if role == "dwi" else 0
        dd = dd[..., i]
    if role == "adc":
        s = adc_scale(dd)
        if s == 1.0: return sitk.ReadImage(path, sitk.sitkFloat32) if img.ndim == 3 else _save(dd, img.affine, tmp)
        log(f"    adc: values look like {'mm2/s' if s == 1e6 else 'x1e-3 mm2/s'}, converted to x1e-6 mm2/s")
        dd = dd * s
    return _save(dd, img.affine, tmp)


def _save(dd, affine, tmp):
    nib.save(nib.Nifti1Image(dd.astype(np.float32), affine), tmp)
    return sitk.ReadImage(tmp, sitk.sitkFloat32)


def otsu(x, bins=256):
    h, e = np.histogram(x, bins); c = (e[:-1] + e[1:]) / 2; w = np.cumsum(h); m = np.cumsum(h * c)
    between = (m[-1] * w - m * w[-1]) ** 2 / (w * (w[-1] - w) + 1e-9)
    return float(c[np.argmax(between[:-1])])


def largest(mask):
    lab, n = ndi.label(mask)
    return lab == (np.argmax(ndi.sum(mask, lab, range(1, n + 1))) + 1) if n else mask


def skull_strip(d, v, sp1, role, mode="auto"):
    """Brain mask on the reference grid. Already skull-stripped data (exact zeros outside the head) is detected;
    T1 uses an intensity band tuned for T1; other contrasts use an Otsu threshold. All morphological, no model."""
    if mode == "auto" and (d == 0).mean() > 0.3:       # zero background: skull-stripped, or only defaced?
        cand = largest(ndi.binary_fill_holes(ndi.binary_opening(d > 0, ellip(1.5, sp1))))
        if cand.sum() * sp1.prod() / 1000 < 2000:      # a brain is ~1000-1700 cm3, a (defaced) head far more
            return cand, "already skull-stripped (zero background)"
    sm = ndi.gaussian_filter(v, 0.8)
    vol = lambda m: m.sum() * sp1.prod() / 1000
    if role == "t1":
        er = ndi.binary_erosion((sm > 0.19) & (sm < 0.45), ellip(3.5, sp1))
        brain = largest(er)
        brain = ndi.binary_dilation(brain, ellip(4.0, sp1)) & (sm > 0.09) & (sm < 0.5)
        how = "T1 intensity band + morphology"
        if not 700 < vol(brain) < 2000:                # band tuned on a scan with scalp fat; retry relative to Otsu
            thr = otsu(sm[sm > 0.03])
            brain = largest(ndi.binary_erosion((sm > 0.6 * thr) & (sm < 0.95), ellip(3.5, sp1)))
            brain = ndi.binary_dilation(brain, ellip(4.0, sp1)) & (sm > 0.3 * thr)
            how = "T1 Otsu threshold + morphology (fixed intensity band gave an implausible volume)"
    else:
        thr = otsu(sm[sm > 0.03])
        brain = largest(ndi.binary_erosion(sm > thr * 0.6, ellip(4.0, sp1)))
        brain = ndi.binary_dilation(brain, ellip(4.0, sp1)) & (sm > thr * 0.3)
        how = f"{role.upper()} Otsu threshold + morphology (rough: may keep scalp)"
    brain = ndi.binary_closing(brain, ellip(3.0, sp1)); brain = ndi.binary_fill_holes(brain)
    for k in range(brain.shape[2]): brain[:, :, k] = ndi.binary_fill_holes(brain[:, :, k])
    return largest(brain), how


def run(study, log=print):
    NI, OUT = study.nifti, study.analysis
    os.makedirs(OUT, exist_ok=True)
    roles = study.roles(); FILES = roles["series"]; force = roles.get("register", {})
    SEQ, REF = roles["available"], roles["reference"]
    others = [k for k in ["flair", "t2", "swi", "adc", "dwi", "t1"] if k in SEQ and k != REF]   # ADC before DWI
    series = {s["name"]: s for s in study.read_json("series.json", [])}
    log(f"sequences: {', '.join(SEQ)} (reference grid: {REF})")

    # ---------- 1. reference grid (RAS, ~1 mm in-plane, even dims) ----------
    log(f"1/5 {REF.upper()} grid")
    img = nib.as_closest_canonical(nib.load(f"{NI}/{FILES[REF]}.nii.gz"))
    if img.ndim == 4:
        dd = img.get_fdata(); i = int(np.argmin([dd[..., j].mean() for j in range(dd.shape[-1])])) if REF == "dwi" else 0
        img = nib.Nifti1Image(dd[..., i], img.affine)
    vs = np.sqrt((img.affine[:3, :3] ** 2).sum(0))
    tilt = float(np.degrees(np.arccos(np.clip(np.abs(img.affine[:3, :3] / vs).max(0).min(), 0, 1))))
    if vs.max() / vs.min() > 2.5 or tilt > 10:          # thick-slice or strongly oblique reference: axis-aligned grid
        from nibabel.processing import resample_to_output
        iso = max(1.0, float(vs.min())) if vs.max() / vs.min() > 2.5 else float(vs.min())
        img = resample_to_output(img, [iso] * 3, order=1)
        log(f"    {vs.round(2).tolist()} mm voxels, {tilt:.0f} deg oblique: resampled to {iso:.2f} mm axis-aligned")
    d = img.get_fdata().astype(np.float32); A = img.affine.copy()
    vox = lambda M: np.sqrt((M[:3, :3] ** 2).sum(0))   # voxel size along each array axis (also for oblique scans)
    f = [max(1, int(np.floor(1.0 / s + 1e-6))) for s in vox(A)]    # e.g. 0.49 mm -> 2x, 0.6 mm -> 1x
    d = d[:d.shape[0] // f[0] * f[0], :d.shape[1] // f[1] * f[1], :d.shape[2] // f[2] * f[2]]
    d = d.reshape(d.shape[0] // f[0], f[0], d.shape[1] // f[1], f[1], d.shape[2] // f[2], f[2]).mean((1, 3, 5))
    A1 = A @ np.diag([*f, 1]); A1[:3, 3] = A[:3, :3] @ [(x - 1) / 2 for x in f] + A[:3, 3]
    ref_hi = np.percentile(d, 99.8); v = np.clip(d / ref_hi, 0, 1)
    m = ndi.gaussian_filter(v, 1) > 25 / 255
    idx = [np.where(m.any(axis=tuple(a for a in range(3) if a != ax)))[0] for ax in range(3)]
    lo = [max(i[0] - 3, 0) for i in idx]; hi = [min(i[-1] + 4, v.shape[a]) for a, i in enumerate(idx)]
    hi = [l + (h - l) // 2 * 2 for l, h in zip(lo, hi)]
    sl = tuple(slice(l, h) for l, h in zip(lo, hi))
    v, d = v[sl], d[sl]; A1[:3, 3] = A1[:3, :3] @ lo + A1[:3, 3]
    sp1 = vox(A1)
    A2 = A1 @ np.diag([2, 2, 2, 1]); A2[:3, 3] = A1[:3, :3] @ [0.5, 0.5, 0.5] + A1[:3, 3]
    sp2 = sp1 * 2
    nib.save(nib.Nifti1Image(d, A1), f"{OUT}/ref_grid.nii.gz")
    nib.save(nib.Nifti1Image(np.zeros([s // 2 for s in d.shape], np.float32), A2), f"{OUT}/_g2_ref.nii.gz")

    # ---------- 2. skull strip ----------
    log("2/5 skull strip")
    brain, strip_how = skull_strip(d, v, sp1, REF, roles.get("skull_strip", "auto"))
    log(f"    {strip_how}: brain volume {brain.sum() * sp1.prod() / 1000:.0f} cm3")
    nib.save(nib.Nifti1Image(brain.astype(np.uint8), A1), f"{OUT}/brain_mask.nii.gz")

    # ---------- 3. co-register the other sequences to the reference (rigid, mutual information) ----------
    log("3/5 registration")
    fixed = sitk.ReadImage(f"{OUT}/ref_grid.nii.gz", sitk.sitkFloat32)
    ref2 = sitk.ReadImage(f"{OUT}/_g2_ref.nii.gz", sitk.sitkFloat32)
    nib.save(nib.Nifti1Image(ndi.binary_dilation(brain, iterations=4).astype(np.uint8), A1), f"{OUT}/_mask_reg.nii.gz")
    fmask = sitk.ReadImage(f"{OUT}/_mask_reg.nii.gz", sitk.sitkUInt8)
    centre = fixed.TransformContinuousIndexToPhysicalPoint([s / 2 for s in fixed.GetSize()])
    surf = np.argwhere(brain & ~ndi.binary_erosion(brain))                   # brain surface voxels
    surf = surf[np.random.default_rng(0).choice(len(surf), min(3000, len(surf)), replace=False)]
    probe = [fixed.TransformContinuousIndexToPhysicalPoint([float(x) for x in q]) for q in surf]

    def register(moving):
        R = sitk.ImageRegistrationMethod()
        R.SetMetricAsMattesMutualInformation(48); R.SetMetricFixedMask(fmask)
        R.SetMetricSamplingStrategy(R.RANDOM); R.SetMetricSamplingPercentage(0.15, seed=1)
        R.SetInterpolator(sitk.sitkLinear)
        R.SetOptimizerAsRegularStepGradientDescent(1.0, 1e-4, 300, relaxationFactor=0.6)
        R.SetOptimizerScalesFromPhysicalShift()
        R.SetShrinkFactorsPerLevel([4, 2, 1]); R.SetSmoothingSigmasPerLevel([2, 1, 0.5])
        R.SetInitialTransform(sitk.Euler3DTransform(centre), inPlace=False)
        return R.Execute(fixed, moving)

    raw, txs, reg_info = {REF: half(d)}, {}, {REF: "reference"}
    for k in others:
        mov = load3d(f"{NI}/{FILES[k]}.nii.gz", k, f"{OUT}/_tmp_{k}.nii.gz", log)
        if k == "dwi" and "adc" in txs:                 # DWI and ADC come from the same acquisition
            txs[k], reg_info[k] = txs["adc"], "same transform as ADC"
        elif force.get(k) is False:
            txs[k], reg_info[k] = sitk.Transform(), "scanner coordinates (registration disabled in roles.json)"
        else:
            T = register(mov)
            drift = max(np.linalg.norm(np.subtract(T.TransformPoint(c), c)) for c in probe)   # largest move of the brain surface
            if drift > MAX_DRIFT_MM and force.get(k) is not True:
                txs[k], reg_info[k] = sitk.Transform(), f"scanner coordinates (registration moved the brain {drift:.0f} mm: rejected)"
            else:
                txs[k], reg_info[k] = T, f"rigid registration ({drift:.1f} mm max shift)"
        raw[k] = from_sitk(sitk.Resample(mov, ref2, txs[k], sitk.sitkLinear, 0.0))
        log(f"    {k}: {reg_info[k]}")
    for k in others:
        nib.save(nib.Nifti1Image(raw[k].astype(np.float32), A2), f"{OUT}/{k}_in_ref_space.nii.gz")
        sitk.WriteTransform(txs[k], f"{OUT}/transform_{k}.tfm")   # maps reference-grid points into that sequence

    # ---------- 4. anomaly maps (2x T1 grid) ----------
    log("4/5 anomaly maps")
    mask_brain = half(brain.astype(np.float32)) > 0.5
    mask = mask_brain.copy()
    for k in others:                                # only where every sequence has data
        mask &= ndi.binary_fill_holes(ndi.binary_erosion(raw[k] > 1e-3, iterations=2, border_value=0))
    msk = sitk.Cast(to_sitk(mask.astype(np.float32), sp2), sitk.sitkUInt8)
    cor = {}
    for k in SEQ:
        cor[k] = raw[k] if k == "adc" else from_sitk(sitk.N4BiasFieldCorrection(to_sitk(np.maximum(raw[k], 0) + 1, sp2), msk))
    Z = {}
    for k in SEQ:
        x = cor[k][mask]; med = np.median(x); iqr = np.subtract(*np.percentile(x, [75, 25]))
        Z[k] = (cor[k] - med) / (iqr / 1.349 + 1e-6)

    # 4a. multi-sequence outlier: how unlikely is this voxel's combination of intensities (all available sequences)?
    X = np.clip(np.stack([ndi.gaussian_filter(Z[k], 0.6)[mask] for k in SEQ], 1), -8, 8)
    core = ndi.binary_erosion(mask, iterations=2)[mask]
    tr = X[core][np.random.default_rng(0).choice(core.sum(), min(60000, int(core.sum())), replace=False)]
    nll = -GaussianMixture(8, covariance_type="full", random_state=0, reg_covar=1e-3).fit(tr).score_samples(X)
    med = np.median(nll); mad = np.median(np.abs(nll - med)) * 1.4826
    outl = np.zeros(mask.shape, np.float32); outl[mask] = (nll - med) / mad
    outl = ndi.gaussian_filter(outl * mask, 0.7) * mask

    # 4b. left-right asymmetry: mirror the brain about its own mid-sagittal plane
    fix = to_sitk(d * brain, sp1); flp = to_sitk((d * brain)[::-1], sp1)
    R = sitk.ImageRegistrationMethod(); R.SetMetricAsCorrelation()
    R.SetMetricSamplingStrategy(R.RANDOM); R.SetMetricSamplingPercentage(0.1, seed=3)
    R.SetOptimizerAsRegularStepGradientDescent(1.0, 1e-4, 300, relaxationFactor=0.6); R.SetOptimizerScalesFromPhysicalShift()
    R.SetShrinkFactorsPerLevel([4, 2, 1]); R.SetSmoothingSigmasPerLevel([2, 1, 0]); R.SetInterpolator(sitk.sitkLinear)
    R.SetInitialTransform(sitk.Euler3DTransform(fix.TransformContinuousIndexToPhysicalPoint([s / 2 for s in fix.GetSize()])), inPlace=False)
    T = R.Execute(fix, flp)
    ref = to_sitk(np.zeros(mask.shape), sp2)
    asym, asym_by = np.zeros(mask.shape, np.float32), {}
    mm = from_sitk(sitk.Resample(to_sitk(mask[::-1].astype(np.float32), sp2), ref, T, sitk.sitkNearestNeighbor, 0)) > 0.5
    both = mask & mm
    for k in SEQ:
        zk = ndi.gaussian_filter(Z[k], 1.0)
        dk = zk - from_sitk(sitk.Resample(to_sitk(zk[::-1], sp2), ref, T, sitk.sitkLinear, 0))
        dk = dk - ndi.gaussian_filter(np.where(both, dk, 0), 6) / (ndi.gaussian_filter(both.astype(float), 6) + 1e-3)
        s = np.median(np.abs(dk[both])) * 1.4826 + 1e-6
        asym_by[k] = np.where(both, dk / s, 0)
        asym = np.maximum(asym, np.abs(asym_by[k]) / 2.5)
    asym = ndi.gaussian_filter(asym, 0.6) * mask
    for name, arr in [("outlier_score", outl), ("asymmetry_score", asym)]:
        nib.save(nib.Nifti1Image(arr.astype(np.float32), A2), f"{OUT}/{name}.nii.gz")

    # ---------- 5. findings ----------
    log("5/5 findings")
    dist = ndi.distance_transform_edt(mask_brain, sampling=sp2)
    mid_i = ndi.center_of_mass(mask_brain)[0]
    bb = [np.where(mask_brain.any(axis=tuple(b for b in range(3) if b != a)))[0] for a in range(3)]

    def where(c):
        x_mm = (c[0] - mid_i) * sp2[0]
        side = "midline" if abs(x_mm) < 6 else ("right" if x_mm > 0 else "left")
        fa = (c[1] - bb[1][0]) / (bb[1][-1] - bb[1][0]); fs = (c[2] - bb[2][0]) / (bb[2][-1] - bb[2][0])
        ap = "posterior" if fa < 0.33 else ("anterior" if fa > 0.66 else "central")
        si = "inferior" if fs < 0.33 else ("superior" if fs > 0.66 else "mid-height")
        return side, f"{side} · {ap} · {si}"

    def signature(p, depth):
        p = {k: p.get(k, 0.0) for k in ["t1", "t2", "flair", "swi", "dwi", "adc"]}
        if p["dwi"] > 4 and depth < 4: return "Bright on DWI at the brain edge: typical diffusion (EPI) distortion near air/bone", "artifact"
        if p["dwi"] > 3 and p["adc"] < -2: return "Bright DWI with low ADC (restricted diffusion pattern)", "review"
        if p["flair"] > 3 and p["t2"] > 1.5: return "Bright on FLAIR and T2 (tissue signal change pattern)", "review"
        if p["adc"] > 3 and p["t2"] > 1.5: return "High ADC and bright T2: fluid-like (CSF / ventricle)", "normal-likely"
        if p["swi"] < -4: return "Dark on SWI: typical of veins/sinuses; small round foci could be mineral or blood products", "normal-likely"
        return "Unusual combination of sequence intensities", "review"

    def clusters(score, thr, minvox, zmaps):
        lab, n = ndi.label(score > thr); res = []
        for i in range(1, n + 1):
            vox = lab == i
            if vox.sum() < minvox: continue
            c = np.array(ndi.center_of_mass(score * vox))
            res.append(dict(vox=vox, c=c, n=int(vox.sum()), peak=float(score[vox].max()), rank=float(score[vox].sum()),
                            depth=float(dist[tuple(np.round(c).astype(int))]),
                            prof={k: float(np.mean(zmaps[k][vox])) for k in SEQ}))
        return sorted(res, key=lambda r: -r["rank"])

    def g1(c): return [round(float(x) * 2 + 0.5, 1) for x in c]

    findings = []
    for r in clusters(outl, 5.0, 6, Z)[:12]:
        side, loc = where(r["c"]); txt, cls = signature(r["prof"], r["depth"])
        drv = sorted(SEQ, key=lambda k: -abs(r["prof"][k]))[:3]
        findings.append(dict(kind="outlier", pos=g1(r["c"]), vol=round(r["n"] * sp2.prod()), peak=round(r["peak"], 1),
                             depth=round(r["depth"], 1), where=loc, text=txt, cls=cls,
                             drivers=[f"{SEQ_NAME[k]} {'↑' if r['prof'][k] > 0 else '↓'}{abs(r['prof'][k]):.1f}σ" for k in drv]))
    ac = clusters(asym, 3.0, 10, asym_by); used = set()
    for a, r in enumerate(ac):
        if a in used or len([f for f in findings if f["kind"] == "asym"]) >= 12: continue
        mir = np.array([2 * mid_i - r["c"][0], r["c"][1], r["c"][2]])
        partner = next((b for b, q in enumerate(ac) if b != a and b not in used and np.linalg.norm((q["c"] - mir) * sp2) < 12), None)
        used.add(a)
        if partner is not None: used.add(partner)
        side, loc = where(r["c"]); k = max(SEQ, key=lambda k: abs(r["prof"][k])); val = r["prof"][k]
        other = {"left": "right", "right": "left"}.get(side, "other side")
        txt = (f"{side.capitalize()} side is {'brighter' if val > 0 else 'darker'} than the mirrored {other} on {SEQ_NAME[k]} ({abs(val):.1f}× the typical L/R difference)"
               if side != "midline" else f"Midline region differs from its mirror on {SEQ_NAME[k]} ({abs(val):.1f}×)")
        cls = "edge" if r["depth"] < 3 else "review"
        if r["depth"] < 3: txt += " · at the brain surface: often an edge/shape effect"
        findings.append(dict(kind="asym", pos=g1(r["c"]), vol=round(r["n"] * sp2.prod()), peak=round(r["peak"], 1),
                             depth=round(r["depth"], 1), where=loc, text=txt, cls=cls, paired=partner is not None,
                             drivers=[f"{SEQ_NAME[q]} {'↑' if r['prof'][q] > 0 else '↓'}{abs(r['prof'][q]):.1f}×" for q in sorted(SEQ, key=lambda q: -abs(r['prof'][q]))[:3]]))
    with open(f"{OUT}/findings.json", "w", encoding="utf-8") as fh: json.dump(findings, fh, indent=1, ensure_ascii=False)

    # ---------- sequence metadata for the viewer and the MCP server ----------
    meta = {"grid1_mm": [round(float(s), 4) for s in sp1], "grid2_mm": [round(float(s), 4) for s in sp2],
            "reference": REF, "available": SEQ, "skull_strip": strip_how, "sequences": {}}
    for k in SEQ:
        s = series.get(FILES[k], {}); vox = s.get("voxel_mm") or [0, 0, 0]
        meta["sequences"][k] = {"series": FILES[k], "description": s.get("description", FILES[k]) if s else FILES[k],
                                "slice_mm": round(float(max(vox[2], s.get("thickness") or 0)), 2) if s else None,
                                "grid": "reference grid" if k == REF else "2x reference grid", "alignment": reg_info.get(k)}
    with open(f"{OUT}/meta.json", "w", encoding="utf-8") as fh: json.dump(meta, fh, indent=1, ensure_ascii=False)

    # ---------- viewer payload ----------
    disp = {}
    for k in others:
        x = raw[k][mask_brain]; top = float(np.percentile(x, 99.7)) if k != "adc" else 3200.0
        disp[k] = (np.clip(raw[k] / top, 0, 1) * 255).astype(np.uint8), top
    np.savez_compressed(f"{OUT}/viewer_data.npz",
                        **{REF: (v * 255).astype(np.uint8), f"{REF}_hi": ref_hi}, ref=np.array(REF), sp1=sp1,
                        mask=(mask_brain * 255).astype(np.uint8),
                        outlier=(np.clip(outl, 0, 12.75) * 20).astype(np.uint8),
                        asym=(np.clip(asym, 0, 12.75) * 20).astype(np.uint8),
                        **{k: disp[k][0] for k in disp}, **{f"{k}_hi": disp[k][1] for k in disp})
    for fn in os.listdir(OUT):
        if fn.startswith("_"): os.remove(f"{OUT}/{fn}")
    log(f"done: {len(findings)} findings -> {OUT}")
    return findings
