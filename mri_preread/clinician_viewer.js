/* Browser-only clinician workspace. Kept separate from model/MCP annotations. */
const Clinician = (() => {
  const $ = id => document.getElementById(id);
  const C = { items: [], selected: null, history: [], future: [], stroke: null, texture: null,
    mask: new Uint8Array(W * H * D), dirty: true, ready: false, db: null, revision: 0, conflict: false,
    saves: Promise.resolve(), pending: 0, shown: true, brush: 3 };
  const selected = () => C.items.find(x => x.id === C.selected);
  const status = text => { $('clinStatus').textContent = text; };
  const snapshot = () => AnnotationCore.documentFor(C.items, META);
  const count = () => C.items.reduce((n, item) => n + item.voxels.size, 0);
  function persist() {
    if (!C.db || C.conflict) { status('Not saved in this browser. Export JSON to keep your work.'); return; }
    const doc = snapshot(); C.pending++; status('Saving in this browser…');
    C.saves = C.saves.then(() => new Promise(resolve => {
      if (C.conflict) { C.pending--; resolve(); return; }
      const tx = C.db.transaction('studies', 'readwrite'), store = tx.objectStore('studies');
      const req = store.get(META.study_id); let next;
      req.onsuccess = () => {
        if ((req.result?.revision || 0) !== C.revision) { C.conflict = true; tx.abort(); return; }
        next = C.revision + 1; store.put({ revision: next, doc }, META.study_id);
      };
      tx.oncomplete = () => { C.revision = next; C.pending--; if (!C.pending) status('Saved in this browser only. Export JSON for a portable copy.'); resolve(); };
      tx.onabort = () => {
        C.pending = Math.max(0, C.pending - 1);
        status(C.conflict ? 'Another tab changed this scan. Export your work, then reload before continuing.' : 'Browser save failed. Export JSON to keep your work.'); resolve();
      };
    }));
  }
  function mask() {
    C.mask.fill(0);
    for (const item of C.items) for (const n of item.voxels) C.mask[n] = 128;
    if (selected()) for (const n of selected().voxels) C.mask[n] = 255;
    C.dirty = true;
  }
  function refresh() { mask(); render(); draw2D(); redraw(); }
  function commit(undo, redo, cost = 1) {
    C.history.push({ undo, redo, cost }); C.future = [];
    while (C.history.length > 1 && (C.history.length > 30 || C.history.reduce((n, action) => n + action.cost, 0) > AnnotationCore.MAX_VOXELS)) C.history.shift();
    refresh(); persist();
  }
  function render() {
    const list = $('clinList'); list.replaceChildren();
    C.items.forEach((item, i) => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'item gemma-row' + (item.id === C.selected ? ' active' : '');
      const title = document.createElement('div'); title.textContent = `D${i + 1} · ${item.title}`;
      const sub = document.createElement('div'); sub.className = 'note';
      sub.textContent = item.voxels.size ? `${item.voxels.size} voxels · ${(item.voxels.size * SP1.reduce((a, b) => a * b, 1)).toFixed(1)} mm³` : 'Point annotation';
      b.append(title, sub); b.onclick = () => { C.selected = item.id; S.cross = item.position.map(Math.round); cutFromSlice(2); refresh(); }; list.append(b);
    });
    const item = selected(); $('clinEditor').hidden = !item;
    if (!item && S.tool.startsWith('clin-')) {
      S.tool = 'nav'; cv.classList.remove('pick');
      document.querySelectorAll('#tool button').forEach(b => b.classList.toggle('on', b.dataset.t === 'nav'));
      hud();
    }
    if (item) {
      for (const [id, key] of [['clinTitle', 'title'], ['clinNote', 'note'], ['clinAuthor', 'author']]) if (document.activeElement !== $(id)) $(id).value = item[key];
      $('clinPosition').textContent = `Reference voxel: ${item.position.map(v => v.toFixed(1)).join(', ')} · ${item.voxels.size} painted voxels`;
    }
    $('clinUndo').disabled = !C.history.length; $('clinRedo').disabled = !C.future.length;
    $('clinNew').disabled = !C.ready || C.items.length >= AnnotationCore.MAX_ITEMS;
    document.querySelectorAll('#clinTools button').forEach(b => { b.disabled = !item; b.classList.toggle('on', S.tool === b.dataset.ct); });
  }
  function newItem() {
    if (!C.ready || C.items.length >= AnnotationCore.MAX_ITEMS) return;
    const time = new Date().toISOString(), item = { id: crypto.randomUUID(), title: `Annotation ${C.items.length + 1}`, note: '', author: '', position: [...S.cross], created: time, updated: time, voxels: new Set() };
    C.items.push(item); C.selected = item.id;
    commit(() => { C.items = C.items.filter(x => x.id !== item.id); C.selected = C.items[0]?.id || null; }, () => { C.items.push(item); C.selected = item.id; });
    setTool('clin-point'); $('clinTitle').focus(); $('clinTitle').select();
  }
  function edit(key, value) {
    const item = selected(); if (!item || item[key] === value) return;
    if (key === 'title' && !value.trim()) { $('clinTitle').value = item.title; return; }
    const old = item[key], time = item.updated, now = new Date().toISOString(); item[key] = value; item.updated = now;
    commit(() => { item[key] = old; item.updated = time; }, () => { item[key] = value; item.updated = now; });
  }
  function setTool(tool) {
    if (!selected() || !C.ready) return;
    S.tool = tool; S.pend3 = null;
    C.shown = true; $('clinShow').checked = true;
    document.querySelectorAll('#tool button').forEach(b => b.classList.remove('on'));
    cv.classList.add('pick'); render(); hud();
  }
  function place(p) {
    const item = selected(); if (!item) return;
    const old = item.position, next = p.map((v, a) => clamp(v, 0, G1[a] - 1));
    const previous = item.updated, now = new Date().toISOString(); item.position = next; item.updated = now; S.cross = next.map(Math.round);
    commit(() => { item.position = old; item.updated = previous; }, () => { item.position = next; item.updated = now; });
  }
  function begin(p, plane) {
    const item = selected(); if (!C.ready || !item || C.stroke) return;
    C.stroke = { item, plane, last: p, changes: new Map(), erase: S.tool === 'clin-erase', limit: false, oldPosition: item.position };
    if (!item.voxels.size && S.tool === 'clin-paint') item.position = p.map((v, a) => clamp(v, 0, G1[a] - 1));
    paint(p);
  }
  function paint(p) {
    const stroke = C.stroke; if (!stroke) return;
    const last = stroke.last || p;
    // A jump between disconnected 3D surfaces must not paint a chord through unseen tissue.
    const start = stroke.plane === -1 && Math.hypot(...p.map((v, a) => (v - last[a]) * SP1[a])) > C.brush * 4 ? p : last;
    const indices = AnnotationCore.stroke(start, p, C.brush, stroke.plane, G1, SP1);
    let total = count();
    for (const n of indices) {
      const had = stroke.item.voxels.has(n);
      if (had === !stroke.erase) continue;
      if (!stroke.erase && total >= AnnotationCore.MAX_VOXELS) { stroke.limit = true; continue; }
      if (!stroke.changes.has(n)) stroke.changes.set(n, had);
      if (stroke.erase) { stroke.item.voxels.delete(n); total--; } else { stroke.item.voxels.add(n); total++; }
      C.mask[n] = stroke.erase ? (C.items.some(i => i !== stroke.item && i.voxels.has(n)) ? 128 : 0) : 255;
    }
    stroke.last = p; C.dirty = true; draw2D(); redraw(true);
  }
  function end(cancel = false) {
    const stroke = C.stroke; if (!stroke) return; C.stroke = null;
    const apply = backwards => { for (const [n, had] of stroke.changes) { if (backwards ? had : !stroke.erase) stroke.item.voxels.add(n); else stroke.item.voxels.delete(n); } };
    if (cancel) { apply(true); stroke.item.position = stroke.oldPosition; refresh(); return; }
    if (stroke.changes.size) {
      const previous = stroke.item.updated, position = stroke.item.position, now = new Date().toISOString(); stroke.item.updated = now;
      commit(() => { apply(true); stroke.item.updated = previous; stroke.item.position = stroke.oldPosition; }, () => { apply(false); stroke.item.updated = now; stroke.item.position = position; }, stroke.changes.size);
    }
    if (stroke.limit) status('Two-million-voxel limit reached. Some brush voxels were not added. Export or reduce the segmentation.');
  }
  function undo(redo = false) {
    end(true); const from = redo ? C.future : C.history, to = redo ? C.history : C.future, action = from.pop();
    if (!action) return; action[redo ? 'redo' : 'undo'](); to.push(action); refresh(); persist();
  }
  function exportDoc() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot())], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = `clinician-${META.study_id.slice(0, 12)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function importDoc(file) {
    try {
      if (file.size > 64 * 1024 * 1024) throw Error('Annotation file exceeds 64 MB');
      const incoming = AnnotationCore.validate(JSON.parse(await file.text()), META);
      if (incoming.some(x => C.items.some(y => y.id === x.id))) throw Error('An annotation with this ID already exists. Import into a fresh workspace or remove the duplicate first.');
      if (C.items.length + incoming.length > AnnotationCore.MAX_ITEMS || count() + incoming.reduce((n, x) => n + x.voxels.size, 0) > AnnotationCore.MAX_VOXELS) throw Error('Combined annotations exceed workspace limits');
      const before = C.items.slice(), after = [...before, ...incoming]; C.items = after; C.selected = incoming[0]?.id || C.selected;
      commit(() => { C.items = before; C.selected = before[0]?.id || null; }, () => { C.items = after; C.selected = incoming[0]?.id || before[0]?.id || null; }, 1 + incoming.reduce((n, item) => n + item.voxels.size, 0));
    } catch (e) { status(`Import rejected: ${e.message}`); }
  }
  function initTexture() {
    C.texture = mkTex(5, C.mask, G1); bindTex(5, C.texture);
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, p, gl.NEAREST);
    gl.uniform1i(U.uClin, 5);
  }
  function texture() {
    bindTex(5, C.texture);
    if (C.dirty) { gl.texSubImage3D(gl.TEXTURE_3D, 0, 0, 0, 0, W, H, D, gl.RED, gl.UNSIGNED_BYTE, C.mask); C.dirty = false; }
    gl.uniform1i(U.uClinOn, C.shown && C.items.some(x => x.voxels.size) ? 1 : 0);
    gl.uniform3fv(U.uClinVox, G1.map(n => 1 / n));
  }
  function draw2(v, L) {
    if (!C.shown) return;
    const c = v.ctx, { u, vv, dpr } = L, slice = Math.round(S.cross[v.p]);
    if (C.items.some(x => x.voxels.size)) {
      const canvas = document.createElement('canvas'); canvas.width = G1[u]; canvas.height = G1[vv];
      const ctx = canvas.getContext('2d'), image = ctx.createImageData(canvas.width, canvas.height), p = [0, 0, 0]; p[v.p] = slice;
      for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) {
        p[u] = canvas.width - 1 - x; p[vv] = canvas.height - 1 - y; const label = C.mask[AnnotationCore.index(p, G1)]; if (!label) continue;
        const at = (y * canvas.width + x) * 4; image.data[at] = label === 255 ? 255 : 40; image.data[at + 1] = label === 255 ? 174 : 220; image.data[at + 2] = label === 255 ? 65 : 230; image.data[at + 3] = 130;
      }
      ctx.putImageData(image, 0, 0); c.save(); c.imageSmoothingEnabled = false; c.drawImage(canvas, L.ox, L.oy, L.dw, L.dh); c.restore();
    }
    C.items.forEach((item, i) => {
      if (Math.abs(item.position[v.p] - S.cross[v.p]) * SP1[v.p] > 4) return;
      const p = toScr(L, item.position[u], item.position[vv]); marker(c, p[0], p[1], 10 * dpr, item.id === C.selected ? '#ffae41' : '#28dce6', `D${i + 1}`, item.id === C.selected);
    });
  }
  function draw3(c) {
    if (!C.shown) return;
    C.items.forEach((item, i) => { const p = project(item.position); if (p) marker(c, p[0], p[1], 11, item.id === C.selected ? '#ffae41' : '#28dce6', `D${i + 1}`, item.id === C.selected); });
  }
  async function init() {
    $('clinNew').onclick = newItem;
    for (const [id, key] of [['clinTitle', 'title'], ['clinNote', 'note'], ['clinAuthor', 'author']]) $(id).onchange = e => edit(key, e.target.value);
    $('clinSave').onclick = () => {
      // A commit re-renders the editor. Read every draft before the first edit.
      const values = [['clinTitle', 'title'], ['clinNote', 'note'], ['clinAuthor', 'author']].map(([id, key]) => [key, $(id).value]);
      for (const [key, value] of values) edit(key, value);
    };
    $('clinDelete').onclick = () => {
      const item = selected(); if (!item) return; const before = C.items.slice(), after = before.filter(x => x !== item);
      C.items = after; C.selected = after[0]?.id || null;
      commit(() => { C.items = before; C.selected = item.id; }, () => { C.items = after; C.selected = after[0]?.id || null; }, item.voxels.size + 1);
    };
    $('clinAtCross').onclick = () => place(S.cross);
    $('clinUndo').onclick = () => undo(); $('clinRedo').onclick = () => undo(true);
    $('clinExport').onclick = exportDoc;
    $('clinImport').onchange = async e => { const file = e.target.files[0]; if (file) await importDoc(file); e.target.value = ''; };
    $('clinBrush').oninput = e => { C.brush = +e.target.value; $('clinBrushValue').textContent = C.brush + ' mm'; };
    $('clinShow').onchange = e => { C.shown = e.target.checked; draw2D(); redraw(); };
    document.querySelectorAll('#clinTools button').forEach(b => b.onclick = () => setTool(b.dataset.ct));
    window.addEventListener('beforeunload', e => {
      const editing = ['clinTitle', 'clinNote', 'clinAuthor'].includes(document.activeElement?.id);
      if (C.pending || C.stroke || editing || (C.items.length && (!C.db || C.conflict))) { e.preventDefault(); e.returnValue = ''; }
    });
    try {
      C.db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('mri-preread-clinician', 1);
        req.onupgradeneeded = () => req.result.createObjectStore('studies'); req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error); req.onblocked = () => reject(Error('Browser storage is blocked'));
      });
      const record = await new Promise((resolve, reject) => { const r = C.db.transaction('studies').objectStore('studies').get(META.study_id); r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
      C.revision = record?.revision || 0; if (record) C.items = AnnotationCore.validate(record.doc, META);
      C.selected = C.items[0]?.id || null; status('Local browser workspace. Nothing is sent to a server. Export JSON to share or back up.');
    } catch (e) { C.db = null; status('Browser storage unavailable. Use Export JSON before closing this page.'); }
    C.ready = true; $('clinControls').disabled = false; refresh();
  }
  const active = () => C.ready && !!selected() && S.tool.startsWith('clin-');
  const hint = () => S.tool === 'clin-point' ? 'Clinician point: click a slice or the visible 3D surface. Add text in Clinician annotations.' : `Clinician ${S.tool === 'clin-erase' ? 'eraser' : 'brush'}: drag on 2D slices or the 3D surface. 3D uses a spherical brush (${C.brush} mm radius). Shift/right-drag pans; use Navigate to rotate. Esc cancels the stroke.`;
  return { init, initTexture, texture, draw2, draw3, active, hint, render, place, begin, paint, end, undo, breakStroke: () => { if (C.stroke) C.stroke.last = null; }, hasStroke: () => !!C.stroke };
})();
