/* Clinician annotation geometry and portable document validation. No DOM dependencies. */
const AnnotationCore = (() => {
  const MAX_ITEMS = 64, MAX_VOXELS = 2000000;
  const index = (p, dims) => p[0] + dims[0] * (p[1] + dims[1] * p[2]);
  const point = (n, dims) => [n % dims[0], Math.floor(n / dims[0]) % dims[1], Math.floor(n / (dims[0] * dims[1]))];
  function brush(center, radius, plane, dims, spacing) {
    if (!Number.isFinite(radius) || radius <= 0 || radius > 30 || ![-1, 0, 1, 2].includes(plane)) throw Error('Invalid brush');
    if (!center.every(Number.isFinite)) throw Error('Invalid brush position');
    const lo = center.map((c, a) => Math.max(0, Math.ceil(a === plane ? Math.round(c) : c - radius / spacing[a])));
    const hi = center.map((c, a) => Math.min(dims[a] - 1, Math.floor(a === plane ? Math.round(c) : c + radius / spacing[a])));
    const result = [];
    for (let z = lo[2]; z <= hi[2]; z++) for (let y = lo[1]; y <= hi[1]; y++) for (let x = lo[0]; x <= hi[0]; x++) {
      const p = [x, y, z];
      if (p.reduce((sum, v, a) => sum + (a === plane ? 0 : ((v - center[a]) * spacing[a]) ** 2), 0) <= radius ** 2) result.push(index(p, dims));
    }
    return result;
  }
  function stroke(from, to, radius, plane, dims, spacing) {
    const distance = Math.hypot(...from.map((x, a) => (to[a] - x) * spacing[a]));
    const steps = Math.max(1, Math.ceil(distance / Math.min(radius / 2, ...spacing)));
    const result = new Set();
    for (let i = 0; i <= steps; i++) for (const n of brush(from.map((x, a) => x + (to[a] - x) * i / steps), radius, plane, dims, spacing)) result.add(n);
    return result;
  }
  function encode(voxels) {
    const sorted = [...voxels].sort((a, b) => a - b), runs = [];
    for (const n of sorted) { const last = runs[runs.length - 1]; if (last && last[0] + last[1] === n) last[1]++; else runs.push([n, 1]); }
    return runs;
  }
  function documentFor(items, meta) {
    return { format: 'mri-preread-clinician', version: 1, study_id: meta.study_id, dims: meta.dims1,
      spacing_mm: meta.sp1, affine: meta.affine, voxel_order: 'x + nx * (y + ny * z)',
      items: items.map(item => ({ id: item.id, title: item.title, note: item.note, author: item.author,
        position: item.position, created: item.created, updated: item.updated, source: 'clinician', mask_runs: encode(item.voxels) })) };
  }
  function validate(doc, meta) {
    const fail = message => { throw Error(message); };
    if (!doc || doc.format !== 'mri-preread-clinician' || doc.version !== 1) fail('Unsupported annotation file');
    if (doc.study_id !== meta.study_id || JSON.stringify(doc.dims) !== JSON.stringify(meta.dims1) ||
        JSON.stringify(doc.spacing_mm) !== JSON.stringify(meta.sp1) || JSON.stringify(doc.affine) !== JSON.stringify(meta.affine)) fail('Annotations belong to a different scan or geometry');
    if (!Array.isArray(doc.items) || doc.items.length > MAX_ITEMS) fail('Too many annotations');
    let total = 0; const ids = new Set(), count = meta.dims1.reduce((a, b) => a * b, 1);
    return doc.items.map(item => {
      if (!item || typeof item.id !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(item.id) || ids.has(item.id)) fail('Invalid or duplicate annotation ID');
      ids.add(item.id);
      for (const [key, limit] of [['title', 200], ['note', 10000], ['author', 200], ['created', 80], ['updated', 80]]) {
        if (typeof item[key] !== 'string' || item[key].length > limit) fail('Invalid annotation text');
      }
      if (!item.title.trim()) fail('Annotation title is required');
      if (!Array.isArray(item.position) || item.position.length !== 3 || !item.position.every((n, a) => Number.isFinite(n) && n >= 0 && n <= meta.dims1[a] - 1)) fail('Annotation location is outside this scan');
      if (!Array.isArray(item.mask_runs) || item.mask_runs.length > MAX_VOXELS) fail('Invalid segmentation');
      const voxels = new Set(); let end = -1;
      for (const run of item.mask_runs) {
        if (!Array.isArray(run) || run.length !== 2 || !run.every(Number.isSafeInteger) || run[0] < 0 || run[1] < 1 || run[0] <= end || run[0] + run[1] > count) fail('Invalid or overlapping segmentation runs');
        total += run[1]; if (total > MAX_VOXELS) fail('Segmentation exceeds the two-million-voxel limit');
        end = run[0] + run[1] - 1;
        for (let n = run[0]; n <= end; n++) voxels.add(n);
      }
      return { id: item.id, title: item.title, note: item.note, author: item.author, position: [...item.position],
        created: item.created, updated: item.updated, voxels };
    });
  }
  return { MAX_ITEMS, MAX_VOXELS, index, point, brush, stroke, encode, documentFor, validate };
})();
if (typeof module !== 'undefined') module.exports = AnnotationCore;
