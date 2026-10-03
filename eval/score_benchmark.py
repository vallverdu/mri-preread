"""Freeze and score a blinded benchmark built by prepare_benchmark.py.

  python eval/score_benchmark.py data/benchmark            (writes data/benchmark/_key/results.json + freeze manifest)

Stroke cases are scored against their lesion masks (score_lesions.score, 10 mm tolerance). On healthy controls
every high/medium item counts as a false alarm (controls have no labels, so an incidental real finding would also
count as one). 95% intervals are Wilson score intervals.
"""
import glob
import hashlib
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_lesions import score  # noqa: E402

HM = ("high", "medium")
BINS = [(0.01, 0.1), (0.1, 1), (1, 10), (10, 1e9)]


def wilson(k, n, z=1.96):
    if n == 0: return (None, None)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def frac(k, n): return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci95": wilson(k, n)}


def main(root):
    keyd = os.path.join(root, "_key"); key = json.load(open(os.path.join(keyd, "key.json")))["cases"]
    frz = os.path.join(keyd, "frozen"); os.makedirs(frz, exist_ok=True); manifest = []
    per_case = {}
    for cid, info in sorted(key.items()):
        A = os.path.join(root, cid, "analysis")
        for name in ("annotations.json", "findings.json"):
            src = os.path.join(A, name); dst = os.path.join(frz, f"{cid}_{name}")
            if not os.path.exists(src): json.dump({"summary": None, "items": []}, open(src, "w"))
            shutil.copyfile(src, dst); manifest.append(f"{hashlib.sha256(open(dst, 'rb').read()).hexdigest()}  {cid}_{name}")
        ann = json.load(open(os.path.join(frz, f"{cid}_annotations.json")))
        fnd = json.load(open(os.path.join(frz, f"{cid}_findings.json")))
        row = {"source": info["source"], "n_items": len(ann["items"]), "summary": bool(ann.get("summary")),
               "n_high_medium": sum(i["priority"] in HM for i in ann["items"]),
               "n_review_candidates": sum(f["cls"] == "review" for f in fnd)}
        if info["mask"]:
            r = score(os.path.join(root, cid), info["mask"], "dwi", 10.0,
                      os.path.join(frz, f"{cid}_annotations.json"), os.path.join(frz, f"{cid}_findings.json"))
            row.update(lesion_ml=r["lesion_volume_ml"], components=r["components"],
                       hm_hits=sum(a["hit"] for a in r["annotations"] if a["priority"] in HM),
                       case_found_llm=any(c["found_by_llm_high_medium"] for c in r["components"]),
                       case_found_algo=any(c["found_by_algorithm_review_only"] for c in r["components"]),
                       review_hits=sum(f["hit"] for f in r["findings"] if f["cls"] == "review"))
        per_case[cid] = row
    open(os.path.join(keyd, "FROZEN_SHA256.txt"), "w").write("\n".join(manifest) + "\n")

    S = [r for r in per_case.values() if r.get("components")]                  # stroke cases with a labelled lesion
    E = [r for r in per_case.values() if "lesion_ml" in r and not r.get("components")]   # dataset case, empty mask
    C = [r for r in per_case.values() if "lesion_ml" not in r]                   # healthy controls
    comps = [c for r in S for c in r["components"]]
    out = {"n_stroke": len(S), "n_control": len(C), "n_empty_mask": len(E),
           "empty_mask_cases": {k: {"n_high_medium": r["n_high_medium"]} for k, r in per_case.items() if r in E},
           "llm": {"stroke_cases_with_lesion_found": frac(sum(r["case_found_llm"] for r in S), len(S)),
                   "lesion_components_found": frac(sum(c["found_by_llm_high_medium"] for c in comps), len(comps)),
                   "components_by_size_ml": {f"{lo}-{hi if hi < 1e9 else 'inf'}": frac(
                       sum(c["found_by_llm_high_medium"] for c in comps if lo <= c["volume_ml"] < hi),
                       sum(lo <= c["volume_ml"] < hi for c in comps)) for lo, hi in BINS},
                   "high_medium_items_on_lesion_in_stroke_cases": frac(sum(r["hm_hits"] for r in S), sum(r["n_high_medium"] for r in S)),
                   "controls_with_any_high_medium": frac(sum(r["n_high_medium"] > 0 for r in C), len(C)),
                   "high_medium_items_per_control": round(sum(r["n_high_medium"] for r in C) / len(C), 2) if C else None,
                   "cases_without_summary": [k for k, r in per_case.items() if not r["summary"]]},
           "algorithm_review_candidates": {
                   "stroke_cases_with_lesion_hit": frac(sum(r["case_found_algo"] for r in S), len(S)),
                   "lesion_components_hit": frac(sum(c["found_by_algorithm_review_only"] for c in comps), len(comps)),
                   "candidates_on_lesion_in_stroke_cases": frac(sum(r["review_hits"] for r in S), sum(r["n_review_candidates"] for r in S)),
                   "controls_with_any_candidate": frac(sum(r["n_review_candidates"] > 0 for r in C), len(C)),
                   "candidates_per_control": round(sum(r["n_review_candidates"] for r in C) / len(C), 2) if C else None},
           "per_case": per_case}
    json.dump(out, open(os.path.join(keyd, "results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_case"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
