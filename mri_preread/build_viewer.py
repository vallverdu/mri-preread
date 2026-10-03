"""Pack <study>/analysis into one self-contained HTML viewer (<study>/brain_viewer.html).

The result embeds the images, so it is as private as the scan itself.
"""
import base64
import gzip
import hashlib
import json
import os

import numpy as np

from .study import ROLE_LABEL

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_template.html")
DISPLAY = {"t1": ("a.u.", 0.35, 0.7), "flair": ("a.u.", 0.45, 0.8), "t2": ("a.u.", 0.4, 0.8),
           "swi": ("a.u.", 0.5, 0.9), "dwi": ("a.u.", 0.4, 0.8), "adc": ("×10⁻⁶ mm²/s", 0.4, 0.8)}


def pack(a):  # (i,j,k) uint8 -> gz base64 with x fastest
    return base64.b64encode(gzip.compress(np.ascontiguousarray(a.transpose(2, 1, 0)).tobytes(), 9, mtime=0)).decode()


def seq_label(k, meta):
    s = (meta.get("sequences") or {}).get(k) or {}
    desc = s.get("description")
    return f"{ROLE_LABEL[k]} · {desc}" if desc and desc.upper().replace(" ", "") != ROLE_LABEL[k] else ROLE_LABEL[k]


def run(study, log=print, medgemma_report=None):
    A = study.analysis
    d = np.load(os.path.join(A, "viewer_data.npz"))
    with open(os.path.join(A, "findings.json"), encoding="utf-8") as f: findings = json.load(f)
    annotations = "null"
    if os.path.exists(study.annotations):
        with open(study.annotations, encoding="utf-8") as f: annotations = f.read()
    meta_p = os.path.join(A, "meta.json")
    seqmeta = {}
    if os.path.exists(meta_p):
        with open(meta_p, encoding="utf-8") as stream:
            seqmeta = json.load(stream)

    ref = str(d["ref"]) if "ref" in d.files else "t1"
    G1 = list(d[ref].shape); G2 = list(d["mask"].shape); sp1 = [round(float(s), 4) for s in d["sp1"]]
    vols = []
    for k in [ref] + [k for k in ["t1", "flair", "t2", "swi", "dwi", "adc"] if k != ref and k in d.files]:
        unit, lev, wid = DISPLAY[k]
        vols.append(dict(key=k, name=seq_label(k, seqmeta), dims=G1 if k == ref else G2, f=1 if k == ref else 2,
                         hi=float(d[f"{k}_hi"]), unit=unit, lev=lev, wid=wid))
    meta = dict(dims1=G1, dims2=G2, sp1=sp1, ref=ref, vols=vols, findings=findings)
    # Bind clinician drafts to the actual reference image and its physical geometry,
    # never just a filename or dimensions shared by unrelated patients.
    import nibabel as nib
    reference = nib.load(os.path.join(A, 'ref_grid.nii.gz'))
    meta['affine'] = reference.affine.tolist()
    identity = hashlib.sha256(np.ascontiguousarray(reference.dataobj).tobytes())
    identity.update(json.dumps({'shape': reference.shape, 'affine': meta['affine'], 'ref': ref}, sort_keys=True).encode())
    meta['study_id'] = identity.hexdigest()
    aux = {k: d[k] for k in ["mask", "outlier", "asym"]}
    gt_p = os.path.join(A, "reference_lesion.nii.gz")      # optional: dataset's own lesion mask on the reference grid
    if os.path.exists(gt_p):
        import nibabel as nib
        g = np.asanyarray(nib.load(gt_p).dataobj) > 0; I, J, K = G2
        aux["gt"] = (g[:2 * I, :2 * J, :2 * K].reshape(I, 2, J, 2, K, 2).max((1, 3, 5)) * 255).astype(np.uint8)
        meta["gt"] = True

    blobs = "\n".join(f'<script type="application/octet-stream" id="d-{k}">{pack(a)}</script>'
                      for k, a in [(v["key"], d[v["key"]]) for v in vols] + list(aux.items()))
    with open(TEMPLATE, encoding="utf-8") as f: tpl = f.read()
    for name in ['annotation_core', 'clinician_viewer']:
        with open(os.path.join(os.path.dirname(TEMPLATE), name + '.js'), encoding='utf-8') as f:
            tpl = tpl.replace('__' + name.upper() + '__', f.read())
    from .viewer_review import load_review
    review = load_review(study, medgemma_report)
    if review['status'] == 'unavailable':
        log(review['message'])
    html = (tpl.replace("__META__", json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__MEDGEMMA__", json.dumps(review, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__ANNOTATIONS__", annotations.replace("</", "<\\/"))
            .replace("<!--__DATA__-->", blobs))
    with open(study.viewer_html, "w", encoding="utf-8") as f: f.write(html)
    msg = f"{study.viewer_html}: {ref.upper()} grid {G1} @ {sp1} mm, {len(findings)} findings, {len(html) / 1e6:.1f} MB"
    log(msg)
    return msg
