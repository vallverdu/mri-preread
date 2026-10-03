const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');

test('slice rendering waits for selected and auxiliary volumes during asynchronous loading', () => {
  const source = fs.readFileSync('mri_preread/viewer_template.html', 'utf8');
  const start = source.indexOf('function draw2D() {'), end = source.indexOf('\nfor (const v of views)', start);
  const info = {innerHTML: ''};
  const context = vm.createContext({
    VOLS: {t1: {data: new Uint8Array(8), f: 1, dims: [2,2,2], hi: 255, name: 'T1', unit: 'a.u.'}, flair: {}},
    AUX: {}, AUX_KEYS: ['mask','outlier','asym'], views: [],
    S: {seq: 't1', win: {t1:[.5,1]}, ovMap: 'off', brain: false, cross: [0,0,0]},
    document: {getElementById: () => info}, Uint8ClampedArray,
    mmOf: () => [0,0,0],
    tri: volume => {assert.ok(volume?.data, 'must not sample a partially decoded volume'); return 0;}
  });
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext('draw2D()', context); assert.equal(info.innerHTML, '');
  for (const name of ['mask','outlier','asym']) {
    context.AUX[name] = {data:new Uint8Array(8)};
    if (name !== 'asym') {vm.runInContext('draw2D()', context); assert.equal(info.innerHTML, '');}
  }
  context.S.seq = 'flair'; vm.runInContext('draw2D()', context); assert.equal(info.innerHTML, '');
  context.S.seq = 't1'; vm.runInContext('draw2D()', context); assert.match(info.innerHTML, /T1/);
});
