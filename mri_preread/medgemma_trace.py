"""Observable slice review: exact local inputs, prompts, outputs and decisions."""
import hashlib
import html
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time

from .medgemma import unpack_result

WORKFLOW_VERSION = "aligned-slices-v3"
QUESTION = '''These are co-registered brain MRI images of ONE axial plane.
Images in order: {sequences}. Compare the images at the same location.
Radiological display: image left is the patient's RIGHT; image top is ANTERIOR.
Does this plane contain a focal signal abnormality that merits a radiologist's review?
Use "yes" only for a visible focal finding; use "no" when none is identified on these images;
use "uncertain" for ambiguous findings, artifacts, poor coverage or insufficient detail.
For diffusion, check bright DWI against low ADC; bright DWI alone is insufficient.
Do not infer a diagnosis, measurements, voxel coordinates, or a verdict about the entire scan.
Begin with exactly one decision word: yes, no, or uncertain.
On the next line explain the visible evidence in at most 35 words.'''


def parse_decision(text, truncated=False):
    lines = text.strip().split("\n", 1)
    if lines[0] in ("yes", "no", "uncertain") and len(lines) == 2 and lines[1].strip():
        return {"review": lines[0], "observation": lines[1].strip(), "observation_truncated": truncated}
    if lines[0] in ("A", "B", "C") and len(lines) == 2 and lines[1].strip():
        return {"review": {"A": "yes", "B": "no", "C": "uncertain"}[lines[0]],
                "observation": lines[1].strip(), "observation_truncated": truncated}
    if truncated:
        return {"review": "invalid", "observation": "Response reached the token limit"}
    text = text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    try:
        obj = json.loads(text)
        if not isinstance(obj, dict) or obj.get("review") not in ("yes", "no", "uncertain"):
            raise ValueError("Invalid decision")
        if not isinstance(obj.get("observation"), str) or not obj["observation"].strip():
            raise ValueError("Missing observation")
        return {"review": obj["review"], "observation": obj["observation"]}
    except (ValueError, TypeError):
        return {"review": "invalid", "observation": "Response did not match the required JSON schema"}


def write_trace(report, output, write_json=True):
    if write_json:
        temp = output.with_suffix(".json.tmp")
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        temp.replace(output)
    esc = lambda value: html.escape(str(value), quote=True)
    counts = {v: sum(r["decision"]["review"] == v for r in report["reviews"]) for v in ("yes", "no", "uncertain", "invalid")}
    quality = ''
    if len(report["reviews"]) >= 5 and counts["yes"] == len(report["reviews"]):
        quality = '<div class="banner"><b>Quality check: every sampled plane was flagged.</b><p>This run does not distinguish which planes need attention. These flags must not be interpreted as confirmed abnormalities.</p></div>'
    cards = []
    for i, row in enumerate(report["reviews"], 1):
        decision = row["decision"]
        images = ''.join(f'<figure><a href="{esc(im["path"])}"><img loading="lazy" src="{esc(im["path"])}" alt="{esc(im["sequence"])} slice {row["z"]}"></a><figcaption>{esc(im["sequence"].upper())}</figcaption></figure>' for im in row["images"])
        cards.append(f'''<article id="slice-{i}"><h2>Slice {i} · z = {row['z']:g}
        <span class="tag {decision['review']}">{esc(decision['review'])}</span></h2>
        <p>{esc(decision['observation'])}</p>{'<p class="muted">Explanation reached the token limit.</p>' if row.get('hit_token_limit') else ''}<div class="images">{images}</div>
        <p class="muted">Image left = patient RIGHT · top = ANTERIOR · {row['seconds']:.1f} seconds · {row.get('peak_mlx_memory_gb', 0):.2f} GB peak MLX allocation</p>
        <details><summary>Exact prompt and raw response</summary><h3>Prompt</h3><pre>{esc(row['prompt'])}</pre><h3>Raw response</h3><pre>{esc(row['text'])}</pre></details>
        <details><summary>Image geometry and contrast</summary><pre>{esc(json.dumps(row['image_metadata'], indent=2))}</pre></details></article>''')
    refresh = '<meta http-equiv="refresh" content="15">' if report["status"] == "in_progress" else ''
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
    <title>Local MedGemma review · {esc(report['study_name'])}</title><style>
    body{{background:#0c111a;color:#e6edf5;font:16px/1.5 system-ui;margin:0}}main{{max-width:1250px;margin:auto;padding:28px}}
    h1{{font-size:28px}}h2{{font-size:19px}}a{{color:#8dc8ff}}.muted,summary{{color:#aab9cd}}.banner,article{{background:#141e2d;border:1px solid #2a3b52;padding:20px;border-radius:12px;margin:18px 0}}
    .images{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}}figure{{margin:0}}img{{width:100%;display:block;background:black}}figcaption{{text-align:center;color:#b5c5d8;padding:6px}}
    .tag{{font-size:13px;border-radius:20px;padding:4px 12px;margin-left:10px;background:#34445c}}.yes{{background:#79421d}}.no{{background:#244657}}.uncertain,.invalid{{background:#62436e}}
    pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#0c111a;padding:14px;border-radius:8px;font-size:13px}}details{{margin-top:12px}}.metrics{{font-size:18px}}
    </style></head><body><main><p class="muted">LOCAL INFERENCE · INPUT / OUTPUT TRACE</p>
    <h1>MedGemma review · {esc(report['study_name'])}</h1>
    <div class="banner"><b>Research draft — not a diagnosis</b><p>{esc(report['limitations'])}</p></div>{quality}
    <p class="metrics">{len(report['reviews'])} / {report['planned_slices']} slices · {counts['yes']} flagged · {counts['uncertain']} uncertain · {counts['invalid']} invalid · {counts['no']} with no focal finding identified</p>
    <p>Status: <b>{esc(report['status'])}</b> · {esc(report['workflow'])} · {report['sampling']['step_mm_actual']:.1f} mm sampling</p>
    <p><a href="{esc(output.name)}">Download complete JSON trace</a></p>
    <details><summary>Sampling plan and acquisition limitations</summary><pre>{esc(json.dumps(report['sampling'], indent=2))}</pre></details>
    <details><summary>Model and decoding settings</summary><pre>{esc(json.dumps({'model': report['model_provenance'], 'decoding': report['decoding']}, indent=2))}</pre></details>
    {''.join(cards)}</main></body></html>'''
    temp = output.with_suffix(".html.tmp")
    temp.write_text(page)
    temp.replace(output.with_suffix(".html"))


async def review_slices(model, study, args, output):
    output = Path(output)
    if output.exists() or output.with_suffix(".html").exists() or output.with_suffix(".assets").exists():
        raise FileExistsError(f"Refusing to overwrite a trace: {output}")
    try:
        return await _review_slices(model, study, args, output)
    except BaseException:
        if output.exists():
            report = json.loads(output.read_text())
            report["status"] = "failed_or_interrupted"
            write_trace(report, output)
        raise


async def _review_slices(model, study, args, output):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    output = Path(output)
    if output.exists() or output.with_suffix(".html").exists():
        raise FileExistsError(f"Refusing to overwrite a trace: {output}")
    assets = output.with_suffix(".assets")
    assets.mkdir()  # also refuse to reuse another run's images
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "mri_preread", "serve", study.root],
        env={**os.environ, "BRAIN_VIEWER_PORT": "0"})
    report = {"workflow": WORKFLOW_VERSION, "study_name": Path(study.root).name,
              "model_provenance": model.provenance, "backend_version": version("mlx-vlm"),
              "decoding": {"temperature": 0, "repetition_penalty": 1.1, "max_tokens": args.max_tokens,
                           "assistant_prefix": "Review decision: ",
                           "constraint": "first token yes/no/uncertain, then newline; remaining text unconstrained"},
              "status": "in_progress", "reviews": [],
              "limitations": "A qualified radiologist must review the original scan. This is sampled axial screening, "
              "not a complete volumetric read. Findings between planes can be missed. Registration, thick slices "
              "and model errors limit interpretation. A 'no' decision concerns only the displayed plane. "
              "No ground truth was supplied to the model."}
    started = time.monotonic()
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            text, _ = unpack_result(await session.call_tool("get_slice_plan", {"step_mm": args.step_mm}))
            plan = json.loads(text)
            sequences = args.sequences or [s for s in ("flair", "dwi", "adc", "t2", "swi", "t1") if s in plan["sequences"]]
            if not sequences or any(s not in plan["sequences"] for s in sequences):
                raise ValueError(f"Requested sequences not available: {plan['sequences']}")
            zs = plan["z_indices"][:getattr(args, "max_slices", None)]
            report.update(sampling=plan, sequences=sequences, planned_slices=len(zs),
                          development_limit=getattr(args, "max_slices", None))
            write_trace(report, output)
            print(f"Watch the review: {output.with_suffix('.html')}", flush=True)
            for i, z in enumerate(zs):
                text, images = unpack_result(await session.call_tool("view_slice_images", {"z": z, "sequences": sequences}))
                metadata = json.loads(text)
                if len(images) != len(sequences):
                    raise RuntimeError("MCP image count does not match sequence count")
                saved = []
                for sequence, image in zip(sequences, images):
                    path = assets / f"slice-{i + 1:03d}-{sequence}.png"
                    image.save(path)
                    saved.append({"sequence": sequence, "path": f"{assets.name}/{path.name}",
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                prompt = QUESTION.format(sequences=", ".join(f"{j + 1}: {s.upper()}" for j, s in enumerate(sequences)))
                print(f"Slice {i + 1}/{len(zs)}, z={z}, {len(images)} images", file=sys.stderr, flush=True)
                result = model.infer_images(prompt, images, args.max_tokens, decision_mode=True)
                report["reviews"].append({"z": z, "images": saved, "image_metadata": metadata,
                    "prompt": prompt, **result,
                    "decision": parse_decision(result["text"], result.get("hit_token_limit", False))})
                report["elapsed_seconds"] = round(time.monotonic() - started, 2)
                write_trace(report, output)
            report["status"] = "complete"
            write_trace(report, output)
    return output
