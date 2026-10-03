/* An image-first MRI volume overview. No model, report or patient API requests. */
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
function scrollCut(cut, delta, mode = 0, height = 600) {
  const pixels = delta * (mode === 1 ? 16 : mode === 2 ? height : 1);
  return clamp(cut + pixels * .045, 0, 85);
}
function advanceSweep(cut, direction, elapsed) {
  // Reflect at either end, including after a delayed frame; never jump outside the scan.
  const phase = ((direction < 0 ? 170 - cut : cut) + clamp(elapsed, 0, 250) * .006) % 170;
  return { cut: phase <= 85 ? phase : 170 - phase, direction: phase < 85 ? 1 : -1 };
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
      // Keep the volume transfer function while cutting, rather than switching to a surface.
      gl.uniform1i(U.uMode, 1);
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
  const status = figure.querySelector('#heroStatus'), canvas = figure.querySelector('canvas');
  const controls = figure.querySelector('fieldset'), slider = figure.querySelector('#heroCutY');
  const play = figure.querySelector('#heroPlay'), motion = root.matchMedia('(prefers-reduced-motion: reduce)');
  if (!figure.dataset.volume) return;
  if (!root.WebGL2RenderingContext || !root.DecompressionStream || !root.fetch || !['http:', 'https:'].includes(root.location.protocol)) {
    status.textContent = 'MRI preview · Open the full viewer for more tools'; return;
  }
  let engine = null, state = initialState(), pointer = null, inView = true, ended = false;
  let loadController = null, generation = 0;
  let playing = !motion.matches, direction = 1, timer = null, previous = null;
  const sameOrigin = path => {
    const url = new URL(path, root.location.href);
    if (url.origin !== root.location.origin || !['http:', 'https:'].includes(url.protocol)) throw Error('Use a local static web server');
    return url.href;
  };
  function stopTimer() { clearTimeout(timer); timer = null; previous = null; }
  function updateControls() {
    slider.value = String(Math.round(state.cuts[1]));
    slider.nextElementSibling.value = Math.round(state.cuts[1]) + '%';
    play.textContent = playing ? 'Pause' : 'Play';
    play.setAttribute('aria-label', playing ? 'Pause front-to-back animation' : 'Play front-to-back animation');
    play.setAttribute('aria-pressed', String(playing));
  }
  function schedule() {
    stopTimer();
    if (engine && playing && inView && !root.document.hidden && !ended) timer = setTimeout(tick, 100);
  }
  function tick() {
    timer = null;
    if (!engine || !playing || !inView || root.document.hidden || ended) return;
    const now = root.performance.now();
    const next = advanceSweep(state.cuts[1], direction, previous === null ? 0 : now - previous);
    previous = now; direction = next.direction; state.cuts[1] = next.cut;
    updateControls(); engine.setState(state, true); timer = setTimeout(tick, 100);
  }
  function pause() { playing = false; stopTimer(); updateControls(); }
  function poster(message) {
    stopTimer(); engine?.destroy(); engine = null; pointer = null;
    figure.classList.remove('is-ready'); controls.hidden = true; controls.disabled = true; canvas.hidden = true;
    status.textContent = message;
  }
  async function load() {
    const run = ++generation;
    figure.setAttribute('aria-busy', 'true');
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 30000);
    loadController = controller;
    let script;
    try {
      const loadCore = () => {
        if (root.MriHeroRenderer) return Promise.resolve(root.MriHeroRenderer);
        return new Promise((resolve, reject) => {
          script = root.document.createElement('script'); script.src = sameOrigin(figure.dataset.renderer);
          script.onload = () => root.MriHeroRenderer ? resolve(root.MriHeroRenderer) : reject(Error('Renderer unavailable'));
          script.onerror = () => reject(Error('Renderer download failed'));
          controller.signal.addEventListener('abort', () => reject(Error('Renderer timeout')), { once: true });
          root.document.head.append(script);
        });
      };
      const loadData = async () => {
        const response = await root.fetch(sameOrigin(figure.dataset.volume), { signal: controller.signal, credentials: 'omit' });
        if (!response.ok || !response.body) throw Error('MRI download failed');
        const bytes = await readLimited(response.body, 8000000);
        const data = JSON.parse(new TextDecoder().decode(bytes));
        return { data, voxels: await decode(data) };
      };
      const [core, { data, voxels }] = await Promise.all([loadCore(), loadData()]);
      if (ended || run !== generation) return;
      canvas.hidden = false;
      engine = renderer(canvas, data, voxels, core, () => poster('MRI image preview · 3D is unavailable'));
      controls.hidden = false; controls.disabled = false;
      figure.classList.add('is-ready');
      status.textContent = 'Scroll over the head to move front to back · Drag to rotate';
      updateControls(); engine.setVisible(inView);
      // Show the complete volume briefly before demonstrating the coronal cut.
      if (playing && inView && !root.document.hidden) timer = setTimeout(tick, 1800);
    } catch {
      controller.abort(); script?.remove();
      if (run === generation) poster('MRI image preview · 3D is unavailable');
    } finally {
      clearTimeout(timeout);
      if (run === generation) { loadController = null; figure.removeAttribute('aria-busy'); }
    }
  }
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); poster('MRI image preview · 3D is paused by your browser'); });
  canvas.addEventListener('pointerdown', e => {
    if (!engine || (e.pointerType === 'mouse' && e.button !== 0)) return;
    pause(); pointer = { id: e.pointerId, x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => {
    if (!pointer || e.pointerId !== pointer.id) return;
    state = rotate(state, e.clientX - pointer.x, e.clientY - pointer.y);
    pointer.x = e.clientX; pointer.y = e.clientY; engine?.setState(state, true);
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(event, () => { pointer = null; });
  canvas.addEventListener('wheel', e => {
    if (!engine || e.ctrlKey || e.metaKey || !e.deltaY) return;
    e.preventDefault(); pause();
    state.cuts[1] = scrollCut(state.cuts[1], e.deltaY, e.deltaMode, canvas.clientHeight);
    updateControls(); engine.setState(state, true);
  }, { passive: false });
  canvas.addEventListener('keydown', e => {
    if (!engine || e.altKey || e.ctrlKey || e.metaKey || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', '=', 'Home', ' '].includes(e.key)) return;
    e.preventDefault();
    if (e.key === ' ') { toggle(); return; }
    pause();
    if (e.key === 'Home') reset();
    else if (['+', '=', '-'].includes(e.key)) zoom(e.key === '-' ? 1.12 : .88);
    else if (['ArrowUp', 'ArrowDown'].includes(e.key)) {
      state.cuts[1] = clamp(state.cuts[1] + (e.key === 'ArrowDown' ? 3 : -3), 0, 85);
      updateControls(); engine.setState(state, true);
    } else { state = rotate(state, e.key === 'ArrowRight' ? 12 : -12, 0); engine.setState(state, true); }
  });
  slider.addEventListener('input', () => {
    pause(); state.cuts[1] = Number(slider.value); updateControls(); engine?.setState(state, true);
  });
  function zoom(factor) { state.dist = clamp(state.dist * factor, .9, 3.5); engine?.setState(state, true); }
  function reset() { pause(); state = initialState(); direction = 1; updateControls(); engine?.setState(state); }
  function toggle() {
    if (!engine) return;
    playing = !playing;
    if (playing && state.cuts[1] > 75) direction = -1;
    updateControls(); schedule();
  }
  play.addEventListener('click', toggle);
  figure.querySelector('#heroReset').addEventListener('click', reset);
  motion.addEventListener('change', () => { if (motion.matches) pause(); });
  if (root.ResizeObserver) new ResizeObserver(() => engine?.request()).observe(canvas);
  if (root.IntersectionObserver) new IntersectionObserver(entries => {
    inView = entries[0].isIntersecting; engine?.setVisible(inView); schedule();
  }).observe(figure);
  root.document.addEventListener('visibilitychange', () => {
    if (!root.document.hidden) engine?.request(); schedule();
  });
  root.addEventListener('pagehide', () => {
    ended = true; generation++; loadController?.abort(); loadController = null;
    figure.removeAttribute('aria-busy'); poster('MRI image preview');
  });
  root.addEventListener('pageshow', e => { if (e.persisted) { ended = false; load(); } });
  load();
}

const api = { validate, clipBounds, initialState, rotate, scrollCut, advanceSweep, readLimited, decode };
if (typeof module === 'object' && module.exports) module.exports = api;
else if (root.document) { const figure = root.document.querySelector('.hero-viewer'); if (figure) mount(figure); }
})(typeof window === 'object' ? window : globalThis);
