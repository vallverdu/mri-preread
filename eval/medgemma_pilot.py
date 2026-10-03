"""Run a small local slice-screening pilot; freeze predictions before loading labels.

Scores are plane-level stroke-mask agreement, not point localization or diagnosis.
Existing benchmark annotations, results and frozen files are never modified.
"""
import argparse
import asyncio
import hashlib
import html
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image, ImageOps
import SimpleITK as sitk

from mri_preread.medgemma import DEFAULT_MODEL, LocalModel
from mri_preread.medgemma_trace import review_slices
from mri_preread.study import Study


def aligned_mask(study, mask_path, space):
    analysis = Path(study) / "analysis"
    ref = sitk.ReadImage(str(analysis / "ref_grid.nii.gz"))
    transform = analysis / f"transform_{space}.tfm"
    if not transform.exists():
        meta = json.loads((analysis / "meta.json").read_text())
        if meta["reference"] != space:
            raise ValueError(f"Missing transform for mask space {space}")
    tx = sitk.ReadTransform(str(transform)) if transform.exists() else sitk.Transform()
    mask = sitk.Resample(sitk.ReadImage(str(mask_path)), ref, tx, sitk.sitkNearestNeighbor, 0)
    return sitk.GetArrayFromImage(mask).transpose(2, 1, 0) > 0


def summarize(rows):
    table = {label: {d: 0 for d in ("yes", "no", "uncertain", "invalid")} for label in ("positive", "negative")}
    for row in rows:
        table["positive" if row["lesion_present"] else "negative"][row["decision"]] += 1
    def fraction(n, d):
        return {"numerator": n, "denominator": d, "rate": n / d if d else None}
    p, n = table["positive"], table["negative"]
    return {"counts": table,
            "flagged_lesion_planes": fraction(p["yes"], sum(p.values())),
            "flagged_nonlesion_planes": fraction(n["yes"], sum(n.values())),
            "abstained_or_invalid": fraction(p["uncertain"] + p["invalid"] + n["uncertain"] + n["invalid"], len(rows))}


def freeze(out, cases):
    files = {}
    for case in cases:
        path = out / f"{case}.json"
        data = json.loads(path.read_text())
        if data["status"] != "complete" or len(data["reviews"]) != data["planned_slices"]:
            raise ValueError(f"Incomplete case cannot be scored: {case}")
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for row in data["reviews"]:
            for image in row["images"]:
                digest = hashlib.sha256((out / image["path"]).read_bytes()).hexdigest()
                if digest != image["sha256"]:
                    raise ValueError("Input image changed since inference")
                files[image["path"]] = digest
    manifest = {"frozen_before_label_loading": True, "files": files, "unix_time": time.time()}
    with (out / "FROZEN.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)


def score(root, out, cases):
    manifest = json.loads((out / "FROZEN.json").read_text())
    for name, digest in manifest["files"].items():
        if hashlib.sha256((out / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen artifact was modified: {name}")
    # This is the only place where ground truth is read; no model calls follow.
    key = json.loads((root / "_key/key.json").read_text())["cases"]
    all_rows, per_case = [], {}
    overlays = out / "ground-truth"
    overlays.mkdir(exist_ok=True)
    for case in cases:
        data = json.loads((out / f"{case}.json").read_text())
        info = key[case]
        gt = aligned_mask(root / case, info["mask"], info.get("mask_space", "dwi")) if info["mask"] else None
        rows = []
        for i, row in enumerate(data["reviews"], 1):
            z = int(row["z"])
            pixels = int(gt[:, :, z].sum()) if gt is not None else 0
            entry = {"case": case, "slice": i, "z": z, "decision": row["decision"]["review"],
                     "lesion_present": pixels > 0, "lesion_pixels": pixels,
                     "label_kind": "expert_stroke_mask" if gt is not None else "control_assumed_negative"}
            if gt is not None:
                # Post-inference visual QA only. Never an input to MedGemma.
                im = next((im for im in row["images"] if im["sequence"] == "dwi"), row["images"][0])
                frame = next(f for f in row["image_metadata"]["frames"] if f["sequence"] == im["sequence"])
                mask = Image.fromarray((gt[:, :, z][::-1, ::-1].T * 255).astype(np.uint8))
                size = tuple(frame["content_size"])
                mask = mask.resize(size, Image.Resampling.NEAREST)
                canvas = ImageOps.pad(mask, (896, 896), method=Image.Resampling.NEAREST, color=0)
                base = Image.open(out / im["path"]).convert("RGB")
                overlay = Image.new("RGB", base.size, (255, 110, 40))
                alpha = canvas.point(lambda p: int(p * 0.6))
                base.paste(overlay, (0, 0), alpha)
                name = f"ground-truth/{case}-{i:03d}.png"
                base.save(out / name)
                entry["ground_truth_overlay"] = name
            rows.append(entry)
        coverage = None
        if gt is not None and gt.any():
            # Volume of labelled voxels on the sampled integer planes, not recall.
            occupied = np.flatnonzero(gt.any(axis=(0, 1)))
            covered = sorted(set(occupied.tolist()) & {int(r["z"]) for r in rows})
            coverage = {"lesion_z_planes_total": len(occupied), "lesion_z_planes_sampled": len(covered)}
        per_case[case] = {"label_kind": rows[0]["label_kind"], "metrics": summarize(rows),
                          "sampling_coverage": coverage,
                          "flagged_any_lesion_plane": any(r["lesion_present"] and r["decision"] == "yes" for r in rows),
                          "flagged_any_plane": any(r["decision"] == "yes" for r in rows)}
        all_rows.extend(rows)
    labelled = [r for r in all_rows if r["label_kind"] == "expert_stroke_mask"]
    controls = [r for r in all_rows if r["label_kind"] == "control_assumed_negative"]
    results = {"task": "focal-abnormality flags compared with stroke masks at sampled axial planes",
               "limitations": "Six-case feasibility pilot; slices within each patient are correlated. "
               "No spatial localization is scored: a flag anywhere on a lesion-containing plane counts. "
               "Off-plane lesions are not tested. Other real abnormalities are unlabelled. Controls have no lesion masks. "
               "These metrics are not comparable with the previous point-based reader benchmark.",
               "labelled_cases": summarize(labelled), "controls_assumed_negative": summarize(controls),
               "per_case": per_case, "slices": all_rows}
    (out / "scores.json").write_text(json.dumps(results, indent=2))
    write_index(out, results)
    return results


def write_index(out, results):
    esc = html.escape
    def show_fraction(metric):
        n, d = metric["numerator"], metric["denominator"]
        return f"{n} / {d} ({n / d:.0%})" if d else "No sampled positive planes"

    labelled = results["labelled_cases"]
    controls = results["controls_assumed_negative"]
    cards = ''.join(f'<div class="card"><strong>{show_fraction(metric)}</strong><br>{label}</div>' for label, metric in [
        ("Lesion-containing planes flagged", labelled["flagged_lesion_planes"]),
        ("Planes without labelled stroke flagged", labelled["flagged_nonlesion_planes"]),
        ("Control planes flagged (assumed negative)", controls["flagged_nonlesion_planes"]),
    ])
    warning = ''
    if results["slices"] and all(row["decision"] == "yes" for row in results["slices"]):
        warning = '<div class="warning"><b>Pilot failed to discriminate: every sampled plane was flagged.</b><p>Flagging all lesion planes is not useful detection when non-lesion and control planes are also all flagged. Do not interpret the private scan\'s model statements as confirmed findings.</p></div>'
    cases = []
    for case, row in results["per_case"].items():
        metric = row["metrics"]["flagged_lesion_planes"]
        cases.append(f'<tr><td><a href="{case}.html">{case} · input/output trace</a></td><td>{esc(row["label_kind"])}</td><td>{metric["numerator"]} / {metric["denominator"]}</td><td>{row["flagged_any_plane"]}</td></tr>')
    planes = []
    for row in results["slices"]:
        image = f'<a href="{row["ground_truth_overlay"]}"><img loading="lazy" src="{row["ground_truth_overlay"]}" width="220" alt="Expert stroke mask in orange"></a>' if "ground_truth_overlay" in row else "No expert mask"
        planes.append(f'<tr><td><a href="{row["case"]}.html#slice-{row["slice"]}">{row["case"]} · z={row["z"]}</a></td><td>{row["decision"]}</td><td>{"lesion present" if row["lesion_present"] else "no labelled lesion"}</td><td>{image}</td></tr>')
    private = '<p><a href="private.html">Open private scan input/output trace</a> — no ground-truth accuracy score.</p>' if (out / "private.html").exists() else ''
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MedGemma local pilot</title>
    <style>body{{background:#0c111a;color:#e6edf5;font:16px/1.5 system-ui;margin:30px auto;padding:0 20px;max-width:1100px}}a{{color:#8dc8ff}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #304158}}pre{{white-space:pre-wrap;background:#141e2d;padding:20px}}.note{{color:#b5c5d8}}img{{max-width:100%}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{flex:1;min-width:200px;padding:18px;background:#141e2d;border-radius:10px}}strong{{font-size:24px}}.warning{{background:#402c21;padding:18px;border:1px solid #9b6436;border-radius:10px}}</style></head><body>
    <h1>MedGemma · local pilot evaluation</h1>{warning}<p class="note">{esc(results['limitations'])}</p>{private}<div class="cards">{cards}</div>
    <p><a href="scores.json">Scores JSON</a> · <a href="FROZEN.json">Frozen prediction and image hashes</a></p>
    <details><summary>Full counts, abstentions and invalid responses</summary><h2>Expert-mask cases</h2><pre>{esc(json.dumps(results['labelled_cases'], indent=2))}</pre>
    <h2>Controls (assumed negative)</h2><pre>{esc(json.dumps(results['controls_assumed_negative'], indent=2))}</pre></details>
    <table><tr><th>Case</th><th>Reference labels</th><th>Flagged lesion planes</th><th>Any flag</th></tr>{''.join(cases)}</table>
    <h2>Inspect each decision against the reference mask</h2><p>Orange overlays were generated after predictions were frozen. Click the case link to see exactly what the model received.</p>
    <table><tr><th>Plane / model trace</th><th>Gemma decision</th><th>Ground truth</th><th>Post-run expert-mask overlay</th></tr>{''.join(planes)}</table></body></html>'''
    (out / "index.html").write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", default=["case_02", "case_03", "case_04", "case_05", "case_10", "case_15"])
    parser.add_argument("--private-study", type=Path)
    parser.add_argument("--model-dir", default=DEFAULT_MODEL)
    parser.add_argument("--step-mm", type=float, default=10)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()
    if not args.score_only:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "run-config.json").write_text(json.dumps({
            "cases": args.cases, "step_mm": args.step_mm, "max_tokens": args.max_tokens,
            "selection": "first four mask cases excluding development case_01, first two controls; selected before inference",
        }, indent=2))
        model = LocalModel(args.model_dir)
        review_args = argparse.Namespace(step_mm=args.step_mm, max_tokens=args.max_tokens, max_slices=None,
                                         sequences=["flair", "dwi", "adc"])
        # Each case is independent; no conversation or image cache is passed between calls.
        for case in args.cases:
            asyncio.run(review_slices(model, Study(args.root / case), review_args, args.out / f"{case}.json"))
        if args.private_study:
            review_args.sequences = None  # all available sequences, still local
            asyncio.run(review_slices(model, Study(args.private_study), review_args, args.out / "private.json"))
        freeze(args.out, args.cases)
    results = score(args.root, args.out, args.cases)
    print(json.dumps({k: v for k, v in results.items() if k not in ("slices", "per_case")}, indent=2))
    print(f"Open {args.out / 'index.html'}")


if __name__ == "__main__":
    main()
