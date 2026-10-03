/* An optional, on-demand MRI overview. No model, report or patient API requests. */
(function (root) {
'use strict';
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const keys = ['format', 'dims', 'spacing_mm', 'sequence', 'window', 'appearance', 'data_gzip_base64', 'voxel_sha256'];
function validate(data) {
  if (!data || Object.keys(data).sort().join() !== [...keys].sort().join() || data.format !== 'mri-hero-volume-v1') throw Error('Invalid MRI overview');
  const vector = (a, test) => Array.isArray(a) && a.length === 3 && a.every(test);
  if (!vector(data.dims, n => Number.isInteger(n) && n >= 2 && n <= 256) || data.dims.reduce((a, b) => a * b, 1) > 16000000 ||
      !vector(data.spacing_mm, n => Number.isFinite(n) && n > 0 && n <= 20) ||
      !['t1', 't2', 'flair', 'swi', 'dwi', 'adc'].includes(data.sequence) || !['surface', 'volume'].includes(data.appearance) ||
      !Array.isArray(data.window) || data.window.length !== 2 || !data.window.every(Number.isFinite) ||
      data.window[0] < 0 || data.window[0] > 1 || data.window[1] <= 0 || data.window[1] > 2 ||
      typeof data.data_gzip_base64 !== 'string' || data.data_gzip_base64.length > 24000000 ||
      !/^[a-f0-9]{64}$/.test(data.voxel_sha256)) throw Error('Invalid MRI overview geometry');
  return data.dims.reduce((a, b) => a * b, 1);
}
function clipBounds(cuts) {
  if (!Array.isArray(cuts) || cuts.length !== 3 || !cuts.every(Number.isFinite)) throw Error('Invalid cuts');
  return { min: [0, 0, 0], max: cuts.map(n => 1 - clamp(n, 0, 85) / 100) };
}
function initialState() { return { yaw: Math.PI / 2 + .75, pitch: .3, dist: 1.88, cuts: [0, 0, 0] }; }
function rotate(state, dx, dy) {
  return { ...state, yaw: state.yaw - dx * .008, pitch: clamp(state.pitch + dy * .008, -1.45, 1.45) };
}
// A bounded read also protects browsers when a static export is malformed.
async function readLimited(stream, limit) {
  const reader = stream.getReader(), parts = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > limit) throw Error('MRI overview exceeds its size limit');
      parts.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.length; }
  return bytes;
}
async function decode(data) {
  const count = validate(data);
  const compressed = Uint8Array.from(atob(data.data_gzip_base64), c => c.charCodeAt(0));
  const voxels = await readLimited(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip')), count);
  if (voxels.length !== count) throw Error('Incomplete MRI overview');
  if (root.crypto?.subtle) {
    const digest = Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256', voxels)), n => n.toString(16).padStart(2, '0')).join('');
    if (digest !== data.voxel_sha256) throw Error('MRI overview checksum mismatch');
  }
  return voxels;
}

function renderer(canvas, data, voxels, core, onError) {
  const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, powerPreference: 'low-power' });
  if (!gl) throw Error('WebGL2 unavailable');
  if (Math.max(...data.dims) > gl.getParameter(gl.MAX_3D_TEXTURE_SIZE)) throw Error('MRI texture unsupported');
  const shaders = [], textures = [];
  let program, buffer, destroyed = false, pending = null, settle = null, low = false, visible = true;
  const destroy = () => {
    destroyed = true; clearTimeout(pending); clearTimeout(settle);
    for (const t of textures) gl.deleteTexture(t);
    for (const s of shaders) gl.deleteShader(s);
    if (buffer) gl.deleteBuffer(buffer);
    if (program) gl.deleteProgram(program);
  };
  try {
    const shader = (type, source) => {
      const s = gl.createShader(type); shaders.push(s); gl.shaderSource(s, source); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw Error('MRI shader unavailable');
      return s;
    };
    program = gl.createProgram();
    gl.attachShader(program, shader(gl.VERTEX_SHADER, core.VS)); gl.attachShader(program, shader(gl.FRAGMENT_SHADER, core.FS));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error('MRI renderer unavailable');
    gl.useProgram(program);
    buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'p');
    gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    function texture(unit, bytes, dims) {
      const t = gl.createTexture(); textures.push(t); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_3D, t);
      gl.texImage3D(gl.TEXTURE_3D, 0, gl.R8, ...dims, 0, gl.RED, gl.UNSIGNED_BYTE, bytes);
      for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, p, gl.LINEAR);
      for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(gl.TEXTURE_3D, p, gl.CLAMP_TO_EDGE);
      return t;
    }
    const volume = texture(0, voxels, data.dims);
    texture(1, new Uint8Array(1), [1, 1, 1]);
    const U = {};
    for (let i = 0; i < gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS); i++) {
      const u = gl.getActiveUniform(program, i); U[u.name] = gl.getUniformLocation(program, u.name);
    }
    for (const name of ['uVol', 'uSeq']) gl.uniform1i(U[name], 0);
    for (const name of ['uMask', 'uOv', 'uClin']) gl.uniform1i(U[name], 1);
    const physical = data.dims.map((n, a) => n * data.spacing_mm[a]);
    const half = physical.map(n => n / Math.max(...physical) * .5);
    gl.uniform3fv(U.uHalf, half);
    gl.uniform3fv(U.uVox, data.dims.map(n => 1 / n)); gl.uniform3fv(U.uVox2, data.dims.map(n => 1 / n));
    gl.uniform1f(U.uIso, .14); gl.uniform1f(U.uLo, .22); gl.uniform1f(U.uHi, .75); gl.uniform1f(U.uOp, .35); gl.uniform1i(U.uCmap, 1);
    gl.uniform1f(U.uLev, data.window[0]); gl.uniform1f(U.uWid, data.window[1]);
    let state = initialState();
    function draw() {
      pending = null;
      if (destroyed || !visible || root.document.hidden || !canvas.clientWidth || gl.isContextLost()) return;
      const dpr = Math.min(root.devicePixelRatio || 1, 1.25) * (low ? .55 : 1);
      const width = Math.max(1, Math.round(canvas.clientWidth * dpr)), height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      canvas.width = width; canvas.height = height; gl.viewport(0, 0, width, height);
      gl.useProgram(program); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, volume);
      const cp = Math.cos(state.pitch), eye = [state.dist * cp * Math.cos(state.yaw), state.dist * cp * Math.sin(state.yaw), state.dist * Math.sin(state.pitch)];
      const vp = core.M.mul(core.M.persp(.62, width / height, .05, 20), core.M.look(eye, [0, 0, 0], [0, 0, 1]));
      const bounds = clipBounds(state.cuts);
      gl.uniformMatrix4fv(U.uInvVP, false, core.M.inv(vp)); gl.uniform3fv(U.uCam, eye);
      gl.uniform3fv(U.uCMin, bounds.min); gl.uniform3fv(U.uCMax, bounds.max);
      // Solid grayscale cut faces use the full viewer's surface ray marcher.
      gl.uniform1i(U.uMode, state.cuts.some(n => n > 0) || data.appearance === 'surface' ? 0 : 1);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (gl.getError() !== gl.NO_ERROR) throw Error('MRI rendering failed');
    }
    function request(interactive = false) {
      if (destroyed) return;
      if (interactive) {
        low = true; clearTimeout(settle);
        settle = setTimeout(() => { low = false; request(); }, 180);
      }
      if (pending === null) pending = setTimeout(() => { try { draw(); } catch { onError(); } }, 16);
    }
    draw();
    return { request, destroy, setState(s, interactive = false) { state = s; request(interactive); },
      setVisible(v) { visible = v; if (v) request(); } };
  } catch (error) { destroy(); throw error; }
}

function mount(figure) {
  const button = figure.querySelector('#heroActivate'), status = figure.querySelector('#heroStatus');
  const canvas = figure.querySelector('canvas'), controls = figure.querySelector('fieldset');
  if (!figure.dataset.volume) return;
  if (!root.WebGL2RenderingContext || !root.DecompressionStream || !root.fetch || !['http:', 'https:'].includes(root.location.protocol)) {
    status.textContent = 'MRI volume preview · Open the full viewer for more tools'; return;
  }
  button.hidden = false;
  let loading = false, active = false, engine = null, cached = null, state = initialState(), pointer = null;
  const sameOrigin = path => {
    const url = new URL(path, root.location.href);
    if (url.origin !== root.location.origin || !['http:', 'https:'].includes(url.protocol)) throw Error('Use a local static web server');
    return url.href;
  };
  let scriptPromise;
  const loadRenderer = () => {
    if (root.MriHeroRenderer) return Promise.resolve(root.MriHeroRenderer);
    if (!scriptPromise) scriptPromise = new Promise((resolve, reject) => {
      const script = root.document.createElement('script'); script.src = sameOrigin(figure.dataset.renderer);
      const fail = () => { clearTimeout(deadline); script.remove(); scriptPromise = null; reject(Error('Renderer download failed')); };
      const deadline = setTimeout(fail, 30000);
      script.onload = () => { clearTimeout(deadline); if (root.MriHeroRenderer) resolve(root.MriHeroRenderer); else fail(); };
      script.onerror = fail;
      root.document.head.append(script);
    });
    return scriptPromise;
  };
  function poster(message = 'Interactive MRI overview · Load on demand') {
    active = false; pointer = null; engine?.destroy(); engine = null;
    figure.classList.remove('is-ready'); controls.hidden = true; controls.disabled = true; canvas.hidden = true;
    button.textContent = 'Explore in 3D'; button.setAttribute('aria-pressed', 'false'); status.textContent = message;
  }
  button.addEventListener('click', async () => {
    if (loading) return;
    if (active) { poster(); return; }
    loading = true; button.disabled = true; button.textContent = 'Loading MRI…'; status.textContent = 'Loading the display volume…';
    figure.setAttribute('aria-busy', 'true');
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const loadData = async () => {
        if (cached) return cached;
        const response = await root.fetch(sameOrigin(figure.dataset.volume), { signal: controller.signal, credentials: 'omit' });
        if (!response.ok || !response.body) throw Error('MRI download failed');
        const bytes = await readLimited(response.body, 8000000);
        const data = JSON.parse(new TextDecoder().decode(bytes));
        cached = { data, voxels: await decode(data) };
        return cached;
      };
      const [core] = await Promise.all([loadRenderer(), loadData()]);
      canvas.hidden = false; state = initialState();
      engine = renderer(canvas, cached.data, cached.voxels, core, () => poster('3D unavailable. The MRI image remains available.'));
      for (const slider of controls.querySelectorAll('[data-axis]')) { slider.value = '0'; slider.nextElementSibling.value = '0%'; }
      controls.hidden = false; controls.disabled = false; active = true;
      figure.classList.add('is-ready'); button.textContent = 'Show image'; button.setAttribute('aria-pressed', 'true');
      status.textContent = 'Drag to rotate · Display-resolution MRI';
    } catch {
      poster('3D unavailable. The MRI image remains available.'); button.textContent = 'Retry 3D';
    } finally {
      clearTimeout(timeout); loading = false; button.disabled = false; figure.removeAttribute('aria-busy');
    }
  });
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); poster('3D paused by your browser. Reload 3D to continue.'); });
  canvas.addEventListener('pointerdown', e => {
    if (!active || (e.pointerType === 'mouse' && e.button !== 0)) return;
    pointer = { id: e.pointerId, x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => {
    if (!pointer || e.pointerId !== pointer.id) return;
    state = rotate(state, e.clientX - pointer.x, e.clientY - pointer.y);
    pointer.x = e.clientX; pointer.y = e.clientY; engine?.setState(state, true);
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(event, () => { pointer = null; });
  canvas.addEventListener('keydown', e => {
    if (!active || e.altKey || e.ctrlKey || e.metaKey || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', '=', 'Home'].includes(e.key)) return;
    e.preventDefault();
    if (e.key === 'Home') reset();
    else if (['+', '=', '-'].includes(e.key)) zoom(e.key === '-' ? 1.12 : .88);
    else { state = rotate(state, e.key === 'ArrowRight' ? 12 : e.key === 'ArrowLeft' ? -12 : 0, e.key === 'ArrowDown' ? 12 : e.key === 'ArrowUp' ? -12 : 0); engine.setState(state, true); }
  });
  for (const slider of controls.querySelectorAll('[data-axis]')) slider.addEventListener('input', () => {
    state.cuts[Number(slider.dataset.axis)] = Number(slider.value);
    slider.nextElementSibling.value = slider.value + '%'; engine?.setState(state, true);
  });
  function zoom(factor) { state.dist = clamp(state.dist * factor, .9, 3.5); engine?.setState(state, true); }
  function reset() {
    state = initialState();
    for (const slider of controls.querySelectorAll('[data-axis]')) { slider.value = '0'; slider.nextElementSibling.value = '0%'; }
    engine?.setState(state);
  }
  figure.querySelector('#heroReset').addEventListener('click', reset);
  for (const b of figure.querySelectorAll('[data-zoom]')) b.addEventListener('click', () => zoom(Number(b.dataset.zoom)));
  if (root.ResizeObserver) new ResizeObserver(() => engine?.request()).observe(canvas);
  if (root.IntersectionObserver) new IntersectionObserver(entries => engine?.setVisible(entries[0].isIntersecting)).observe(figure);
  root.document.addEventListener('visibilitychange', () => { if (!root.document.hidden) engine?.request(); });
  root.addEventListener('pagehide', () => { poster(); cached = null; });
}

const api = { validate, clipBounds, initialState, rotate, readLimited, decode };
if (typeof module === 'object' && module.exports) module.exports = api;
else if (root.document) { const figure = root.document.querySelector('.hero-viewer'); if (figure) mount(figure); }
})(typeof window === 'object' ? window : globalThis);
