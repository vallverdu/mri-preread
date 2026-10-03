"""MCP server: lets an LLM do an early, NON-diagnostic pre-read of one brain MRI study.

The LLM can look at the scan (rendered images), query statistics and the algorithmic heterogeneity maps, and write a
prioritised list of "areas for a doctor to review". It also serves the viewer on http://127.0.0.1:8765, which shows
those annotations live as clickable items and numbered markers.

Run (stdio):  mri-preread serve <study>      or   MRI_PREREAD_STUDY=<study> python -m mri_preread serve
Requires:     <study>/analysis/ produced by `mri-preread analyze`
"""
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image as PImage, ImageDraw, ImageFont
from mcp.server.fastmcp import FastMCP, Image

from . import build_viewer
from .study import ROLE_LABEL

PORT = int(os.environ.get("BRAIN_VIEWER_PORT", "8765"))
SHOWS = {  # what each role shows, for the LLM
    "t1": "anatomy; fat bright, CSF dark; grey/white matter contrast",
    "flair": "T2 with CSF suppressed; white-matter / tissue signal changes appear bright",
    "t2": "fluid and most signal changes bright",
    "swi": "susceptibility: veins, blood products, mineral/calcium appear dark",
    "dwi": "diffusion (high b): restricted diffusion appears bright (check ADC); prone to distortion near air/bone",
    "adc": "quantitative diffusion; true restriction is dark on ADC; CSF very bright",
}
UNITS = {"adc": "x1e-6 mm2/s"}
WINDOW = {"t1": (0.35, 0.7), "flair": (0.45, 0.8), "t2": (0.4, 0.8), "swi": (0.5, 0.9), "dwi": (0.4, 0.8), "adc": (0.4, 0.8)}

# filled by load()
STUDY = None; SEQS = {}; VOL = {}; HI = {}; MASK = None; OVL = {}; FINDINGS = []; SP1 = None; G1 = None; REFK = "t1"
MID_X = 0.0; BRAIN_BOX = []; REF = {}; THICK = []
SLICE_INPUTS = None


def load(study):
    global STUDY, SEQS, VOL, HI, MASK, OVL, FINDINGS, SP1, G1, MID_X, BRAIN_BOX, REF, THICK, REFK
    global SLICE_INPUTS
    STUDY = study
    SLICE_INPUTS = None
    d = np.load(os.path.join(study.analysis, "viewer_data.npz"))
    with open(os.path.join(study.analysis, "findings.json"), encoding="utf-8") as f: FINDINGS = json.load(f)
    mp = os.path.join(study.analysis, "meta.json")
    meta = json.load(open(mp, encoding="utf-8")).get("sequences", {}) if os.path.exists(mp) else {}
    REFK = str(d["ref"]) if "ref" in d.files else "t1"
    SP1 = np.array(d["sp1"], float); G1 = np.array(d[REFK].shape)
    SEQS, THICK = {}, []
    for k in [k for k in WINDOW if k in d.files]:
        m = meta.get(k, {}); thk = m.get("slice_mm")
        desc = m.get("description") or ""
        name = (f"{ROLE_LABEL[k]}: {desc}" if desc else ROLE_LABEL[k]) + (f" ({thk:g} mm slices)" if thk else "")
        SEQS[k] = (name, SHOWS[k], UNITS.get(k, "a.u."), WINDOW[k])
        if thk and thk >= 3: THICK.append((ROLE_LABEL[k], thk))
    VOL = {k: d[k] for k in SEQS}
    HI = {k: float(d[f"{k}_hi"]) for k in SEQS}
    MASK = d["mask"] > 127                                  # G2 grid
    OVL = {"outlier": d["outlier"], "asym": d["asym"]}      # uint8 = score*20
    MID_X = float(np.mean(np.where(MASK)[0]) * 2 + 0.5)     # mid-sagittal plane in G1 voxel x
    bb = [np.where(MASK.any(axis=tuple(b for b in range(3) if b != a)))[0] * 2 for a in range(3)]
    BRAIN_BOX = [[int(b[0]), int(b[-1] + 1)] for b in bb]
    REF = {}                                                # whole-brain robust reference per sequence (original units)
    for k, v in VOL.items():
        x = (v[::2, ::2, ::2][:MASK.shape[0], :MASK.shape[1], :MASK.shape[2]] if k == REFK else v)[MASK].astype(float) * HI[k] / 255
        q1, med, q3 = np.percentile(x, [25, 50, 75]); REF[k] = (float(med), float((q3 - q1) / 1.349 + 1e-6))


def study_info():
    info = STUDY.read_json("study.json")
    return info if info else {"note": "study.json not available (run `mri-preread extract`)"}


def sample(k, p):
    """Value of sequence k at G1 voxel p (nearest)."""
    v = VOL[k]; f = 1 if k == REFK else 2
    i = [int(np.clip(round((p[a] + 0.5) / f - 0.5), 0, v.shape[a] - 1)) for a in range(3)]
    return float(v[tuple(i)]) * HI[k] / 255


def ov_at(name, p):
    i = [int(np.clip(p[a] // 2, 0, OVL[name].shape[a] - 1)) for a in range(3)]
    return float(OVL[name][tuple(i)]) / 20


def in_brain(p):
    i = [int(np.clip(p[a] // 2, 0, MASK.shape[a] - 1)) for a in range(3)]
    return bool(MASK[tuple(i)])


def mm(p): return [round(float((p[a] - G1[a] / 2) * SP1[a]), 1) for a in range(3)]


def side(p):
    dx = (p[0] - MID_X) * SP1[0]
    return "midline" if abs(dx) < 6 else ("patient RIGHT" if dx > 0 else "patient LEFT")


# ---------------------------------------------------------------- annotations store
_lock = threading.Lock()
FOCUS = {"ts": 0}
VIEWER_STATE = {}


def load_ann():
    if os.path.exists(STUDY.annotations):
        try:
            with open(STUDY.annotations, encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {"summary": None, "items": []}


def save_ann(a):
    tmp = STUDY.annotations + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(a, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STUDY.annotations)


# ---------------------------------------------------------------- rendering
PLANES = {"axial": (2, 0, 1), "coronal": (1, 0, 2), "sagittal": (0, 1, 2)}   # fixed axis, screen-x axis, screen-y axis
LBL = {"axial": ("R", "L", "A", "P"), "coronal": ("R", "L", "S", "I"), "sagittal": ("A", "P", "S", "I")}
PRI = {"high": (255, 92, 92), "medium": (255, 176, 32), "low": (106, 167, 255), "info": (125, 134, 150)}


def font(sz):
    try: return ImageFont.load_default(size=sz)
    except TypeError: return ImageFont.load_default()


def slice_rgb(k, plane, p, ppmm, overlay=None, thr=None):
    """Full slice through G1 point p, radiological orientation, ppmm pixels per mm. Returns (PIL image, to_px fn)."""
    fa, ua, va = PLANES[plane]; v = VOL[k]; f = 1 if k == REFK else 2
    idx = int(np.clip(round((p[fa] + 0.5) / f - 0.5), 0, v.shape[fa] - 1))
    s = np.take(v, idx, axis=fa)                       # 2D with remaining axes in order
    s = s if ua < va else s.T                          # -> [u, v]
    lev, wid = SEQS[k][3]
    g = np.clip((s.astype(float) / 255 - (lev - wid / 2)) / wid, 0, 1)
    rgb = np.stack([g] * 3, -1)
    if overlay:
        o = np.take(OVL[overlay], int(np.clip(p[fa] // 2, 0, OVL[overlay].shape[fa] - 1)), axis=fa)
        o = (o if ua < va else o.T).astype(float) / 20
        if f == 1: o = np.kron(o, np.ones((2, 2)))[:s.shape[0], :s.shape[1]]
        t = thr if thr is not None else (5 if overlay == "outlier" else 4)
        a = np.clip((o - t) / 3 + 0.55, 0, 1) * (o >= t) * 0.75
        rgb = rgb * (1 - a[..., None]) + np.array([1.0, 0.35, 0.1]) * a[..., None]
    img = (rgb[::-1, ::-1].transpose(1, 0, 2) * 255).astype(np.uint8)   # rows: v descending, cols: u descending
    W_mm, H_mm = G1[ua] * SP1[ua], G1[va] * SP1[va]
    im = PImage.fromarray(img).resize((int(W_mm * ppmm), int(H_mm * ppmm)), PImage.BILINEAR)
    to_px = lambda q: ((1 - (q[ua] + 0.5) / G1[ua]) * im.width, (1 - (q[va] + 0.5) / G1[va]) * im.height)
    return im, to_px


def draw_ann_markers(dr, plane, p, to_px, ox=0, oy=0, near_mm=4):
    fa = PLANES[plane][0]
    for n, a in enumerate(load_ann()["items"], 1):
        if abs(a["pos"][fa] - p[fa]) * SP1[fa] > near_mm: continue
        x, y = to_px(a["pos"]); x -= ox; y -= oy; c = PRI.get(a.get("priority"), PRI["info"])
        dr.ellipse([x - 9, y - 9, x + 9, y + 9], outline=c, width=2); dr.text((x + 10, y - 16), f"#{n}", fill=c, font=font(13))


def png(im):
    b = io.BytesIO(); im.save(b, "PNG", optimize=True); return Image(data=b.getvalue(), format="png")


# ---------------------------------------------------------------- MCP
def instructions():
    thick = (f"- {', '.join(n for n, _ in THICK)} have thick slices ({', '.join(f'{t:g}' for _, t in THICK)} mm) resampled to a "
             f"{' x '.join(f'{s * 2:.1f}' for s in SP1)} mm grid: small things can be blurred or missed. Say so where relevant.\n") if THICK else ""
    sug = [s for s in ["flair axial", "swi axial", "dwi axial", "adc axial", "t2 axial", "t1 sagittal", "t1 coronal"] if s.split()[0] in SEQS]
    screen = ", ".join(sug) or ", ".join(f"{k} axial" for k in SEQS)
    return f"""You are helping with an EARLY, NON-DIAGNOSTIC pre-read of one brain MRI.
Your job is to produce a short, prioritised list of LOCATIONS a qualified doctor/radiologist should look at, so they
can review faster. A doctor must always make the actual assessment.

Rules:
- Never give a diagnosis, and never state that the brain is "normal", "healthy" or "clear". Phrase every item as an
  observation plus a location to review, e.g. "Focal FLAIR/T2-bright area in right frontal white matter - suggest review".
  If you mention possible explanations, present them as options for the doctor, and include normal variant / artifact.
- Verify every candidate visually with view_region before annotating it. Algorithmic candidates (list_candidate_regions)
  are statistics and are often normal anatomy (veins and sinuses on SWI, ventricles, choroid plexus) or artifacts
  (DWI distortion near sinuses and skull base, partial volume at the brain edge, slab edges).
- The algorithm misses things. Also screen systematically with view_overview (suggested: {screen}).
- Available sequences: {", ".join(SEQS)}. Missing sequences cannot be checked: say so in the summary.
{thick}- Priorities: high = the doctor should look at this soon; medium = should be looked at; low = probably normal or an
  artifact, but worth a glance; info = area checked on purpose.
- Keep the list short (roughly 3-12 items) and useful. Each rationale names the sequences and what is seen.
- Finish with set_summary: a neutral 2-5 sentence overview that states limitations and that a radiologist must review.
- Coordinates are viewer voxel indices (x, y, z): x increases towards patient RIGHT, y towards ANTERIOR, z towards SUPERIOR.
  Images use radiological convention (patient right on image left) with R/L/A/P/S/I letters on the edges.
- Use focus_viewer to show the doctor a location in the live viewer, and get_viewer_state to see where they are looking."""


def get_study_overview() -> str:
    """Study metadata (non-identifying), available sequences, coordinate system, brain extent, and suggested workflow."""
    return json.dumps({
        "study": study_info(),
        "sequences": {k: {"name": v[0], "shows": v[1], "unit": v[2]} for k, v in SEQS.items()},
        "grid": {"dims_xyz": G1.tolist(), "voxel_mm": SP1.round(3).tolist(),
                 "axes": "x -> patient RIGHT, y -> ANTERIOR, z -> SUPERIOR (voxel indices of the viewer)",
                 "brain_bounding_box_xyz": BRAIN_BOX, "midline_x": round(MID_X, 1)},
        "brain_volume_cm3": round(float(MASK.sum() * (SP1 * 2).prod() / 1000)),
        "algorithmic_maps": {
            "outlier": f"Gaussian-mixture model over ({', '.join(ROLE_LABEL[k] for k in SEQS)}); score = robust z of improbability",
            "asym": "difference from the mirrored hemisphere, in multiples of the typical L/R difference"},
        "viewer_url": f"http://127.0.0.1:{PORT}/",
        "workflow": ["get_study_overview", "list_candidate_regions", "view_region on each candidate",
                     "view_overview for systematic screening", "region_stats to compare with the mirror side",
                     "add_annotation for each location worth a doctor's look", "set_summary"],
    }, indent=1, ensure_ascii=False)


def list_candidate_regions(kind: str = "all", include_likely_artifacts: bool = True) -> str:
    """Algorithm-generated hotspots (kind: 'outlier', 'asym' or 'all'). Each has an id, position (x,y,z voxel),
    volume, peak score, depth below the brain surface, heuristic signature text and class. Unverified statistics."""
    out = []
    for i, f in enumerate(FINDINGS):
        if kind != "all" and f["kind"] != kind: continue
        if not include_likely_artifacts and f["cls"] in ("artifact", "normal-likely", "edge"): continue
        out.append({"id": i, **f, "side": side(f["pos"]), "mm": mm(f["pos"])})
    return json.dumps(out, indent=1, ensure_ascii=False)


def view_region(x: float, y: float, z: float, sequences: list[str] | None = None, fov_mm: float = 70,
                overlay: str | None = None) -> list:
    """Render axial, coronal and sagittal crops (fov_mm wide) centred on voxel (x,y,z) for each sequence
    (default: all available ones, see get_study_overview). overlay: None, 'outlier' or 'asym' draws that heat map in orange.
    Existing annotations within 4 mm are drawn as numbered rings. The crosshair gap marks the exact point."""
    p = [x, y, z]; seqs = [s for s in (sequences or list(SEQS)) if s in SEQS]
    ppmm, tile = 3.2, int(fov_mm * 3.2)
    cols = ["axial", "coronal", "sagittal"]; lab = 22
    out = PImage.new("RGB", (lab * 5 + tile * 3 + 8, lab + len(seqs) * (tile + 4)), (12, 13, 16))
    dr = ImageDraw.Draw(out)
    for c, pl in enumerate(cols): dr.text((lab * 5 + c * (tile + 4) + 4, 4), pl, fill=(200, 200, 200), font=font(14))
    for r, k in enumerate(seqs):
        y0 = lab + r * (tile + 4)
        dr.text((4, y0 + tile // 2 - 8), k.upper(), fill=(230, 230, 230), font=font(14))
        for c, pl in enumerate(cols):
            im, to_px = slice_rgb(k, pl, p, ppmm, overlay)
            cx, cy = to_px(p); ox, oy = int(cx - tile / 2), int(cy - tile / 2)
            crop = PImage.new("RGB", (tile, tile)); crop.paste(im.crop((max(ox, 0), max(oy, 0), ox + tile, oy + tile)), (max(-ox, 0), max(-oy, 0)))
            d2 = ImageDraw.Draw(crop); h = tile / 2
            for a, b in [((h - 22, h), (h - 7, h)), ((h + 7, h), (h + 22, h)), ((h, h - 22), (h, h - 7)), ((h, h + 7), (h, h + 22))]:
                d2.line([a, b], fill=(90, 220, 255), width=2)
            draw_ann_markers(d2, pl, p, to_px, ox, oy)
            l, rr, t, b = LBL[pl]; f12 = font(12)
            d2.text((3, h - 7), l, fill=(160, 170, 185), font=f12); d2.text((tile - 11, h - 7), rr, fill=(160, 170, 185), font=f12)
            d2.text((h - 4, 2), t, fill=(160, 170, 185), font=f12); d2.text((h - 4, tile - 15), b, fill=(160, 170, 185), font=f12)
            out.paste(crop, (lab * 5 + c * (tile + 4), y0))
    txt = (f"Point ({x:.0f},{y:.0f},{z:.0f}) = {mm(p)} mm from grid centre, {side(p)}, "
           f"{'inside' if in_brain(p) else 'OUTSIDE'} brain mask; outlier {ov_at('outlier', p):.1f}, asym {ov_at('asym', p):.1f}. "
           f"Field of view {fov_mm:.0f} mm; rows = {', '.join(seqs)}.")
    return [txt, png(out)]


def view_overview(sequence: str = "flair", plane: str = "axial", slices: int = 12, overlay: str | None = None) -> list:
    """Montage of evenly spaced slices through the whole brain for systematic screening. Each tile is labelled with
    its slice coordinate, and tick labels on the tile edges give the in-plane voxel coordinates, so you can read off
    (x,y,z) for view_region / add_annotation. Annotations near each slice are drawn as numbered rings."""
    if sequence not in SEQS or plane not in PLANES: return [f"unknown sequence/plane (sequences: {', '.join(SEQS)})"]
    fa, ua, va = PLANES[plane]; slices = int(np.clip(slices, 4, 24))
    # slices where this sequence actually covers a good part of the brain
    cov = MASK & (VOL[sequence] > 0) if sequence != REFK else MASK
    area = cov.sum(axis=tuple(a for a in range(3) if a != fa)); ok = np.where(area > 0.2 * area.max())[0]
    lo, hi = ok[0] * 2 + 1, ok[-1] * 2 + 1; ks = np.linspace(lo + (hi - lo) * 0.03, hi - (hi - lo) * 0.03, slices)
    ppmm = 2.0; cols = 4 if slices <= 12 else 6; tiles = []
    for k in ks:
        p = [G1[0] / 2, G1[1] / 2, G1[2] / 2]; p[fa] = float(k)
        im, to_px = slice_rgb(sequence, plane, p, ppmm, overlay)
        qa, qb = list(p), list(p)
        for ax in (ua, va): qa[ax], qb[ax] = BRAIN_BOX[ax][0], BRAIN_BOX[ax][1]
        (xa, ya), (xb, yb) = to_px(qa), to_px(qb)
        box = (int(min(xa, xb)) - 10, int(min(ya, yb)) - 10, int(max(xa, xb)) + 10, int(max(ya, yb)) + 10)
        t = im.crop(box); dr = ImageDraw.Draw(t); f11 = font(11)
        draw_ann_markers(dr, plane, p, to_px, box[0], box[1], near_mm=3)
        for g in range(0, int(G1[ua]), 40):          # ticks: screen-x axis
            q = [0, 0, 0]; q[ua] = g; px = to_px(q)[0] - box[0]
            if 8 < px < t.width - 8: dr.line([(px, 0), (px, 5)], fill=(120, 200, 255)); dr.text((px - 6, 6), str(g), fill=(120, 200, 255), font=f11)
        for g in range(0, int(G1[va]), 20):          # ticks: screen-y axis
            q = [0, 0, 0]; q[va] = g; py = to_px(q)[1] - box[1]
            if 14 < py < t.height - 8: dr.line([(0, py), (5, py)], fill=(120, 200, 255)); dr.text((7, py - 6), str(g), fill=(120, 200, 255), font=f11)
        dr.text((t.width - 70, t.height - 16), f"{'xyz'[fa]}={k:.0f}", fill=(255, 220, 120), font=font(13))
        tiles.append(t)
    tw, th = max(t.width for t in tiles), max(t.height for t in tiles); rows = int(np.ceil(len(tiles) / cols))
    out = PImage.new("RGB", (cols * (tw + 4), rows * (th + 4) + 24), (12, 13, 16))
    l, rr, tp, b = LBL[plane]
    ImageDraw.Draw(out).text((6, 4), f"{sequence.upper()} {plane} - image left = {l}, right = {rr}, top = {tp}. "
                                     f"Edge ticks: {'xyz'[ua]} (horizontal), {'xyz'[va]} (vertical).", fill=(220, 220, 220), font=font(14))
    for n, t in enumerate(tiles): out.paste(t, ((n % cols) * (tw + 4), 24 + (n // cols) * (th + 4)))
    return [f"{len(tiles)} {plane} slices of {sequence} at {'xyz'[fa]} = {', '.join(f'{k:.0f}' for k in ks)}", png(out)]


def region_stats(x: float, y: float, z: float, radius_mm: float = 5) -> str:
    """Mean/SD per sequence in a sphere around (x,y,z), a robust z-score versus the whole brain, and the same
    numbers at the mirrored point in the other hemisphere. Also the outlier/asymmetry scores and brain-mask status."""
    def sphere(c):
        r = [int(np.ceil(radius_mm / s)) for s in SP1]; pts = []
        for i in range(-r[0], r[0] + 1):
            for j in range(-r[1], r[1] + 1):
                for k in range(-r[2], r[2] + 1):
                    if (i * SP1[0]) ** 2 + (j * SP1[1]) ** 2 + (k * SP1[2]) ** 2 <= radius_mm ** 2:
                        pts.append([c[0] + i, c[1] + j, c[2] + k])
        return pts
    res = {}
    for label, c in [("point", [x, y, z]), ("mirror", [2 * MID_X - x, y, z])]:
        pts = sphere(c); row = {"voxel": [round(v, 1) for v in c], "mm": mm(c), "in_brain": in_brain(c)}
        for k in SEQS:
            vals = np.array([sample(k, q) for q in pts]); med, sc = REF[k]
            row[k] = {"mean": round(float(vals.mean()), 1), "sd": round(float(vals.std()), 1), "z_vs_brain": round(float((vals.mean() - med) / sc), 2)}
        row["outlier_score"] = round(ov_at("outlier", c), 1); row["asym_score"] = round(ov_at("asym", c), 1)
        res[label] = row
    res["units"] = {k: v[2] for k, v in SEQS.items()}
    res["note"] = "Intensities other than ADC are relative scanner units: compare with the mirror side and the z-scores, not with absolute values."
    return json.dumps(res, indent=1)


def add_annotation(x: float, y: float, z: float, title: str, rationale: str, priority: str = "medium",
                   sequences: list[str] | None = None) -> str:
    """Add a location for the doctor to review. title: short observation (no diagnosis). rationale: what is seen on
    which sequences and why it is worth a look. priority: high | medium | low | info.
    sequences: the ones to view it on, best first (e.g. ['flair','t2'])."""
    if priority not in PRI: return "priority must be one of: high, medium, low, info"
    if not all(0 <= v < G1[a] for a, v in enumerate([x, y, z])): return f"position out of range; grid is {G1.tolist()}"
    with _lock:
        a = load_ann(); nid = max([i["id"] for i in a["items"]], default=0) + 1
        a["items"].append({"id": nid, "pos": [round(x, 1), round(y, 1), round(z, 1)], "title": title.strip(),
                           "rationale": rationale.strip(), "priority": priority,
                           "sequences": [s for s in (sequences or []) if s in SEQS], "source": "llm",
                           "created": time.strftime("%Y-%m-%d %H:%M")})
        save_ann(a)
    return f"annotation #{nid} added at {mm([x, y, z])} mm ({side([x, y, z])})"


def update_annotation(id: int, title: str | None = None, rationale: str | None = None, priority: str | None = None,
                      x: float | None = None, y: float | None = None, z: float | None = None) -> str:
    """Edit an existing annotation."""
    with _lock:
        a = load_ann(); it = next((i for i in a["items"] if i["id"] == id), None)
        if not it: return f"no annotation {id}"
        if title: it["title"] = title
        if rationale: it["rationale"] = rationale
        if priority in PRI: it["priority"] = priority
        for ax, v in enumerate([x, y, z]):
            if v is not None: it["pos"][ax] = round(v, 1)
        save_ann(a)
    return f"annotation {id} updated"


def remove_annotation(id: int) -> str:
    """Delete one annotation."""
    with _lock:
        a = load_ann(); n = len(a["items"]); a["items"] = [i for i in a["items"] if i["id"] != id]; save_ann(a)
    return "removed" if len(a["items"]) < n else f"no annotation {id}"


def list_annotations() -> str:
    """Current summary and annotations."""
    return json.dumps(load_ann(), indent=1, ensure_ascii=False)


def clear_annotations(confirm: bool = False) -> str:
    """Remove ALL annotations and the summary (pass confirm=true)."""
    if not confirm: return "pass confirm=true to clear everything"
    with _lock: save_ann({"summary": None, "items": []})
    return "cleared"


def set_summary(text: str) -> str:
    """Set the short overall pre-read summary shown above the list. Neutral, 2-5 sentences, states limitations,
    no diagnosis, no 'normal' verdict, and says a radiologist must review."""
    with _lock:
        a = load_ann(); a["summary"] = {"text": text.strip(), "updated": time.strftime("%Y-%m-%d %H:%M")}; save_ann(a)
    return "summary saved"


def focus_viewer(x: float, y: float, z: float, sequence: str | None = None, overlay: str | None = None,
                 annotation_id: int | None = None) -> str:
    """Move the live viewer (the browser page served by this MCP server) to (x,y,z), optionally switching
    sequence and heat map ('off' | 'outlier' | 'asym') and highlighting an annotation."""
    FOCUS.update({"ts": time.time(), "pos": [x, y, z], "sequence": sequence if sequence in SEQS else None,
                  "overlay": overlay if overlay in ("off", "outlier", "asym") else None, "annotation_id": annotation_id})
    return "sent to viewer" + ("" if VIEWER_STATE else " (no viewer connected yet: open the URL in a browser)")


def get_viewer_state() -> str:
    """What the doctor is looking at in the live viewer: crosshair (x,y,z), sequence, heat map, measurements."""
    if not VIEWER_STATE: return "no viewer connected (open http://127.0.0.1:%d/)" % PORT
    s = dict(VIEWER_STATE); s["crosshair_mm"] = mm(s.get("cross", [0, 0, 0])); return json.dumps(s, indent=1)


def rebuild_standalone_viewer() -> str:
    """Re-generate the study's brain_viewer.html with the current annotations embedded, so it can be shared as one file."""
    try: return build_viewer.run(STUDY, log=lambda *a: None)
    except Exception as e: return f"build failed: {e}"


def _slice_inputs():
    global SLICE_INPUTS
    if SLICE_INPUTS is None:
        from .slice_input import SliceInputs
        SLICE_INPUTS = SliceInputs(STUDY)
    return SLICE_INPUTS


def get_slice_plan(step_mm: float = 10.0) -> str:
    """Label-free axial sampling plan, sequence availability and acquisition limitations for local model review."""
    return json.dumps(_slice_inputs().plan(step_mm))


def view_slice_images(z: float, sequences: list[str]) -> list:
    """Separate 896px images at the same reference plane, from float NIfTIs. No annotations, overlays or montage.
    Images follow sequences order. Metadata specifies orientation, contrast windows and resampling."""
    meta, images = _slice_inputs().render(z, sequences)
    return [json.dumps(meta), *[png(im) for im in images]]


TOOLS = [get_study_overview, list_candidate_regions, view_region, view_overview, region_stats, add_annotation,
         update_annotation, remove_annotation, list_annotations, clear_annotations, set_summary, focus_viewer,
         get_viewer_state, rebuild_standalone_viewer, get_slice_plan, view_slice_images]


# ---------------------------------------------------------------- live viewer HTTP server
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass                       # stdout belongs to MCP stdio

    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/brain_viewer.html"):
            if not os.path.exists(STUDY.viewer_html): build_viewer.run(STUDY, log=lambda *a: None)
            with open(STUDY.viewer_html, "rb") as f: self._send(f.read(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/annotations"):
            self._send(json.dumps(load_ann(), ensure_ascii=False).encode())
        elif self.path.startswith("/api/focus"):
            self._send(json.dumps(FOCUS).encode())
        else:
            self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        if self.path.startswith("/api/viewer_state"):
            n = int(self.headers.get("Content-Length", 0))
            try: VIEWER_STATE.clear(); VIEWER_STATE.update(json.loads(self.rfile.read(n))); VIEWER_STATE["ts"] = time.time()
            except Exception: pass
            self._send(b"{}")
        else:
            self._send(b"not found", "text/plain", 404)


def serve_http():
    try: ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
    except OSError as e: print(f"viewer HTTP server not started: {e}", file=sys.stderr)


def main(study):
    load(study)
    mcp = FastMCP("mri-preread", instructions=instructions())
    for fn in TOOLS: mcp.add_tool(fn)
    threading.Thread(target=serve_http, daemon=True).start()
    print(f"mri-preread: study {study.root}, viewer on http://127.0.0.1:{PORT}/", file=sys.stderr)
    mcp.run()
