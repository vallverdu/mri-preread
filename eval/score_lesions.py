"""Score a pre-read against a ground-truth lesion mask.

  python eval/score_lesions.py <study> <mask.nii.gz> [--space dwi] [--annotations frozen.json] [--findings frozen.json] [--tol 10]

The mask is mapped onto the viewer (reference) grid with the pipeline's own saved transform for the sequence it was
drawn on (default: dwi), using nearest-neighbour resampling. Then:
  - lesion components (26-connected, >= 10 mm3) count as found when a point lies within --tol mm of them;
  - each annotation / algorithm candidate counts as a hit when it lies within --tol mm of any lesion voxel.
One case is an anecdote: aggregate over many cases before drawing conclusions.
"""
import argparse
import json
import os

import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi


def score(study, mask, space="dwi", tol=10.0, annotations=None, findings=None):
    A = os.path.join(study, "analysis")
    ref = sitk.ReadImage(os.path.join(A, "ref_grid.nii.gz"))
    tfm = os.path.join(A, f"transform_{space}.tfm")
    T = sitk.ReadTransform(tfm) if os.path.exists(tfm) else sitk.Transform()
    gt = sitk.GetArrayFromImage(sitk.Resample(sitk.ReadImage(mask), ref, T, sitk.sitkNearestNeighbor, 0)).transpose(2, 1, 0) > 0
    sp = np.array(ref.GetSpacing())
    lab, n = ndi.label(gt, structure=np.ones((3, 3, 3)))
    comps = [(i, float((lab == i).sum() * sp.prod())) for i in range(1, n + 1)]
    comps = [(i, v) for i, v in comps if v >= 10]
    dist_any = ndi.distance_transform_edt(~gt, sampling=sp) if gt.any() else None
    ann = json.load(open(annotations or os.path.join(A, "annotations.json")))["items"]
    fnd = json.load(open(findings or os.path.join(A, "findings.json")))

    def at(d, p):
        i = tuple(int(np.clip(round(p[k]), 0, gt.shape[k] - 1)) for k in range(3)); return float(d[i])

    comp_dist = {i: ndi.distance_transform_edt(lab != i, sampling=sp) for i, _ in comps}
    res = {"lesion_volume_ml": round(float(gt.sum() * sp.prod() / 1000), 2), "components": [], "annotations": [], "findings": []}
    for i, v in comps:
        d_ann = [(x["priority"], at(comp_dist[i], x["pos"])) for x in ann]
        d_fnd = [(f["cls"], at(comp_dist[i], f["pos"])) for f in fnd]
        res["components"].append({"volume_ml": round(v / 1000, 3),
            "found_by_llm_high_medium": any(pr in ("high", "medium") and d <= tol for pr, d in d_ann),
            "found_by_llm_any": any(d <= tol for _, d in d_ann),
            "found_by_algorithm_any": any(d <= tol for _, d in d_fnd),
            "found_by_algorithm_review_only": any(c == "review" and d <= tol for c, d in d_fnd)})
    for x in ann:
        d = at(dist_any, x["pos"]) if dist_any is not None else 1e9
        res["annotations"].append({"id": x["id"], "priority": x["priority"], "dist_mm": round(d, 1), "hit": d <= tol, "title": x["title"][:70]})
    for j, f in enumerate(fnd):
        d = at(dist_any, f["pos"]) if dist_any is not None else 1e9
        res["findings"].append({"id": j, "cls": f["cls"], "dist_mm": round(d, 1), "hit": d <= tol})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("study"); ap.add_argument("mask")
    ap.add_argument("--space", default="dwi"); ap.add_argument("--tol", type=float, default=10.0)
    ap.add_argument("--annotations"); ap.add_argument("--findings"); ap.add_argument("--json")
    a = ap.parse_args()
    res = score(a.study, a.mask, a.space, a.tol, a.annotations, a.findings)
    if a.json: json.dump(res, open(a.json, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
