"""Clean, aligned model inputs from the analysis NIfTIs; no annotations or labels."""
from functools import lru_cache
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image, ImageOps
from scipy.ndimage import map_coordinates


class SliceInputs:
    def __init__(self, study):
        self.root = Path(study.analysis)
        self.meta = json.loads((self.root / "meta.json").read_text())
        self.reference = self.meta["reference"]
        self.ref = nib.load(self.root / "ref_grid.nii.gz")
        if nib.aff2axcodes(self.ref.affine) != ("R", "A", "S"):
            raise ValueError("Slice inputs require the pipeline's RAS reference grid")
        self.spacing = np.linalg.norm(self.ref.affine[:3, :3], axis=0)
        self.mask = np.asarray(nib.load(self.root / "brain_mask.nii.gz").dataobj) > 0
        if self.mask.shape != self.ref.shape:
            raise ValueError("Brain mask and reference grid shapes differ")
        self.available = self.meta["available"]
        self.windows = {}

    @lru_cache(maxsize=6)
    def volume(self, sequence):
        if sequence not in self.available:
            raise ValueError(f"Unavailable sequence: {sequence}")
        path = self.root / ("ref_grid.nii.gz" if sequence == self.reference else f"{sequence}_in_ref_space.nii.gz")
        obj = nib.load(path)
        data = np.asarray(obj.dataobj, dtype=np.float32)
        # Fixed per-volume contrast, never per-slice auto-contrast.
        if sequence == "adc":
            hi = 2400.0  # pipeline stores ADC as x1e-6 mm2/s
        else:
            vals = data[np.isfinite(data) & (data > 0)]
            if not vals.size:
                raise ValueError(f"Sequence {sequence} contains no positive finite values")
            hi = float(np.percentile(vals, 99.5))
        self.windows[sequence] = [0.0, hi]
        return data, np.linalg.inv(obj.affine) @ self.ref.affine

    def plan(self, step_mm=10.0):
        if not 1 <= step_mm <= 30:
            raise ValueError("step_mm must be between 1 and 30")
        area = self.mask.sum(axis=(0, 1))
        indices = np.flatnonzero(area > max(0, area.max() * 0.05))
        if not indices.size:
            raise ValueError("Brain mask is empty")
        step = max(1, int(round(step_mm / self.spacing[2])))
        zs = list(range(int(indices[0]), int(indices[-1]) + 1, step))
        if zs[-1] != int(indices[-1]):
            zs.append(int(indices[-1]))
        return {"z_indices": zs, "step_mm_requested": step_mm,
                "step_mm_actual": float(step * self.spacing[2]),
                "sequences": self.available, "reference": self.reference,
                "shape": list(self.ref.shape), "spacing_mm": self.spacing.tolist(),
                "sequence_details": self.meta["sequences"],
                "orientation": "radiological: image left = patient RIGHT; image top = ANTERIOR",
                "selection": "brain-mask extent only; no lesion masks, candidates or prior annotations"}

    def render(self, z, sequences):
        if not np.isfinite(z) or not 0 <= z < self.ref.shape[2]:
            raise ValueError("z lies outside the reference volume")
        if not sequences or len(set(sequences)) != len(sequences):
            raise ValueError("Provide distinct available sequences")
        xx, yy = np.meshgrid(np.arange(self.ref.shape[0]), np.arange(self.ref.shape[1]), indexing="ij")
        pts = np.stack([xx.ravel(), yy.ravel(), np.full(xx.size, z), np.ones(xx.size)])
        images, frames = [], []
        for sequence in sequences:
            data, transform = self.volume(sequence)
            plane = map_coordinates(data, (transform @ pts)[:3], order=1, mode="constant", cval=0).reshape(xx.shape)
            lo, hi = self.windows[sequence]
            plane = np.nan_to_num(plane, nan=lo, posinf=hi, neginf=lo)
            pixels = (np.clip((plane - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
            image = Image.fromarray(pixels[::-1, ::-1].T).convert("RGB")
            # Preserve physical aspect ratio, including anisotropic reference pixels.
            physical = np.asarray(self.ref.shape[:2]) * self.spacing[:2]
            size = tuple(int(v) for v in np.maximum(1, np.round(physical / physical.max() * 896)))
            image = ImageOps.pad(image.resize(size, Image.Resampling.BILINEAR), (896, 896), color="black")
            images.append(image)
            frames.append({"sequence": sequence, "z": float(z), "window": [lo, hi],
                           "size": [896, 896], "content_size": list(size),
                           "source": "reference NIfTI" if sequence == self.reference else "registered NIfTI"})
        return {"z": float(z), "plane": "axial reference-grid", "frames": frames,
                "orientation": "image left = patient RIGHT; image top = ANTERIOR",
                "interpolation": "linear, evaluated at the same reference plane for every sequence",
                "markers": "none"}, images
