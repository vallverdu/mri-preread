"""After scoring: put each case's reference lesion mask into its viewer and write <benchmark>/index.html.

  python eval/results_index.py data/benchmark

Needs <benchmark>/_key/key.json and results.json (from score_benchmark.py). Unblinds the benchmark: only run it after
the readers are done.
"""
import html
import json
import os
import sys

import SimpleITK as sitk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mri_preread import build_viewer  # noqa: E402
from mri_preread.study import Study  # noqa: E402


def mask_to_viewer(study, mask, space="dwi"):
    A = os.path.join(study, "analysis")
    ref = sitk.ReadImage(os.path.join(A, "ref_grid.nii.gz"))
    tfm = os.path.join(A, f"transform_{space}.tfm")
    T = sitk.ReadTransform(tfm) if os.path.exists(tfm) else sitk.Transform()
    m = sitk.Resample(sitk.ReadImage(mask), ref, T, sitk.sitkNearestNeighbor, 0)
    sitk.WriteImage(sitk.Cast(m > 0, sitk.sitkUInt8), os.path.join(A, "reference_lesion.nii.gz"))


def main(root):
    key = json.load(open(os.path.join(root, "_key", "key.json")))["cases"]
    res = json.load(open(os.path.join(root, "_key", "results.json")))
    rows = []
    for cid in sorted(key):
        info, r = key[cid], res["per_case"][cid]
        if info["mask"]: mask_to_viewer(os.path.join(root, cid), info["mask"])
        build_viewer.run(Study(os.path.join(root, cid)), log=lambda *a: None)
        comps = r.get("components")
        if "lesion_ml" not in r: group, lesion, found = "Healthy control", "–", "–"
        elif not comps: group, lesion, found = "Stroke dataset, empty mask", "0", "–"
        else: group, lesion, found = "Stroke", f"{r['lesion_ml']:g}", "found" if r["case_found_llm"] else "missed"
        hm = r["n_high_medium"]
        on = f"{r['hm_hits']} / {hm}" if comps else (f"{hm} (false alarm)" if hm and "lesion_ml" not in r else str(hm))
        algo = ("hit" if r["case_found_algo"] else "no hit") if comps else f"{r['n_review_candidates']} candidates"
        ann = json.load(open(os.path.join(root, cid, "analysis", "annotations.json")))
        summ = (ann.get("summary") or {}).get("text", "")
        rows.append((cid, group, info["subject"], lesion, found, on, algo, summ))

    L = res["llm"]; G = res["algorithm_review_candidates"]
    pct = lambda f: f"{f['k']} / {f['n']} ({round(100 * f['rate'])}%)"
    tr = "\n".join(
        f'<tr class="{ "miss" if f == "missed" else "ok" if f == "found" else "" }"><td><a href="{c}/brain_viewer.html">{c}</a></td>'
        f'<td>{html.escape(g)}<div class="sub">{html.escape(s)}</div></td><td class="n">{l}</td><td><span class="b {f}">{f}</span></td>'
        f'<td class="n">{o}</td><td>{a}</td><td class="sum">{html.escape(sm)}</td>'
        f'<td><a class="open" href="{c}/brain_viewer.html">Open</a> <a class="open" href="{c}/brain_viewer.html#layout=quad&overlay=gt">With lesion mask</a></td></tr>'
        for c, g, s, l, f, o, a, sm in rows)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Benchmark results</title><style>
:root {{ --bg:#0b0d10; --panel:#13161b; --line:#262b34; --text:#e6e8eb; --muted:#8b93a1; --accent:#5aa9ff; --ok:#6ee7a8; --bad:#ff6b6b; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width:1400px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:20px; margin:0 0 4px; }} .lead {{ color:var(--muted); margin:0 0 18px; max-width:900px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:10px; margin-bottom:18px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.card b {{ display:block; font-size:22px; font-variant-numeric:tabular-nums; }} .card span {{ color:var(--muted); font-size:12.5px; }}
.wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; min-width:1000px; }}
th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ background:var(--panel); color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; position:sticky; top:0; }}
td.n {{ font-variant-numeric:tabular-nums; white-space:nowrap; }} .sub {{ color:var(--muted); font-size:12px; }}
td.sum {{ color:var(--muted); font-size:12.5px; max-width:420px; }}
a {{ color:var(--accent); }} a.open {{ white-space:nowrap; margin-right:8px; }}
.b {{ font-size:12px; padding:1px 8px; border-radius:10px; border:1px solid var(--line); color:var(--muted); }}
.b.found {{ color:var(--ok); border-color:#2d5a45; }} .b.missed {{ color:var(--bad); border-color:#6a2d2d; }}
tr.miss td:first-child {{ box-shadow: inset 3px 0 var(--bad); }} tr.ok td:first-child {{ box-shadow: inset 3px 0 var(--ok); }}
.note {{ color:var(--muted); font-size:12.5px; margin-top:14px; max-width:900px; }}
</style></head><body><main>
<h1>Blinded pre-read benchmark</h1>
<p class="lead">{res['n_stroke']} stroke cases (ISLES 2022), {res['n_control']} healthy controls (OpenNeuro ds007401), {res['n_empty_mask']} dataset case with an empty mask.
Each viewer shows the AI pre-read (numbered markers, list in the left panel). Use <b>With lesion mask</b>, or <b>Heterogeneity maps → Lesion mask</b> in a viewer, to see the expert's reference segmentation.</p>
<div class="cards">
<div class="card"><b>{pct(L['stroke_cases_with_lesion_found'])}</b><span>stroke cases whose lesion the pre-read pointed at</span></div>
<div class="card"><b>{pct(L['high_medium_items_on_lesion_in_stroke_cases'])}</b><span>high/medium items that lie on a lesion</span></div>
<div class="card"><b>{pct(L['controls_with_any_high_medium'])}</b><span>healthy controls with any high/medium item</span></div>
<div class="card"><b>{pct(G['stroke_cases_with_lesion_hit'])}</b><span>stroke cases hit by the algorithm alone (it flags every control too)</span></div>
</div>
<div class="wrap"><table><thead><tr><th>Case</th><th>Group · source</th><th>Lesion ml</th><th>Pre-read</th><th>High/medium on lesion</th><th>Algorithm</th><th>AI summary</th><th></th></tr></thead>
<tbody>{tr}</tbody></table></div>
<p class="note">A lesion counts as found when a high or medium item lies within 10 mm of it. Research data only: not a clinical validation, and the
AI pre-read is not a diagnosis. See the README for the method and its limitations.</p>
</main></body></html>"""
    out = os.path.join(root, "index.html"); open(out, "w", encoding="utf-8").write(page); print(out)


if __name__ == "__main__":
    main(sys.argv[1])
