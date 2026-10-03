'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { gzipSync } = require('node:zlib');
const { createHash, webcrypto } = require('node:crypto');
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const { validate, clipBounds, rotate, initialState, decode, readLimited } = require('../site/hero-volume.js');
const { M } = require('../site/hero-renderer.js');
const raw = Buffer.from([0, 20, 40, 80, 120, 180, 220, 255]);
const payload = { format: 'mri-hero-volume-v1', dims: [2,2,2], spacing_mm: [1,2,3], sequence: 't1',
  window: [.35,.7], appearance: 'volume', data_gzip_base64: gzipSync(raw).toString('base64'),
  voxel_sha256: createHash('sha256').update(raw).digest('hex') };

test('cuts retain a non-empty normalized volume, independently on each axis', () => {
  assert.deepEqual(clipBounds([0,0,0]), {min:[0,0,0],max:[1,1,1]});
  assert.deepEqual(clipBounds([50,25,0]), {min:[0,0,0],max:[.5,.75,1]});
  assert.ok(clipBounds([100,-10,85]).max.every(n=>n>=.149 && n<=1));
  assert.throws(()=>clipBounds([NaN,0,0]));
});
test('pointer and keyboard rotation remain finite at the poles', () => {
  const state = initialState(), changed = rotate(state, 100, 10000);
  assert.notEqual(changed.yaw, state.yaw);
  assert.equal(changed.pitch, 1.45);
  assert.equal(rotate(state, 0, -10000).pitch, -1.45);
  assert.deepEqual(state, initialState());
});
test('camera projection and its inverse round-trip the reference space', () => {
  const vp = M.mul(M.persp(.62,1.4,.05,20), M.look([1,1,.4],[0,0,0],[0,0,1]));
  const identity = M.mul(vp,M.inv(vp));
  identity.forEach((n,i)=>assert.ok(Math.abs(n-(i%5===0?1:0))<1e-10));
});
test('voxel decoding checks geometry, exact length and content checksum', async () => {
  assert.equal(validate(payload), 8);
  assert.deepEqual(Buffer.from(await decode(payload)), raw);
  assert.throws(()=>validate({...payload,patient:'must not be present'}));
  assert.throws(()=>validate({...payload,dims:[256,256,256]}));
  await assert.rejects(decode({...payload,voxel_sha256:'0'.repeat(64)}), /checksum/);
  await assert.rejects(decode({...payload,data_gzip_base64:gzipSync(Buffer.alloc(9)).toString('base64')}), /size limit/);
  await assert.rejects(decode({...payload,data_gzip_base64:gzipSync(Buffer.alloc(7)).toString('base64')}), /Incomplete/);
});
test('network/decompression streams are cancelled when their bound is exceeded', async () => {
  let cancelled = false;
  const stream = new ReadableStream({start(c){c.enqueue(new Uint8Array(11));},cancel(){cancelled=true;}});
  await assert.rejects(readLimited(stream,10), /size limit/);
  assert.equal(cancelled,true);
});
