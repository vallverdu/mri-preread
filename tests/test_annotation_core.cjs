const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../mri_preread/annotation_core.js');
const meta = {study_id:'scan-a', dims1:[11,11,11], sp1:[1,2,3], affine:[[1,0,0,0],[0,2,0,0],[0,0,3,0],[0,0,0,1]]};
const item = () => ({id:'note-1', title:'Finding', note:'<script>not executable</script>', author:'Doctor', position:[5,5,5], created:'2026-09-28', updated:'2026-09-28', voxels:new Set([0,1,2,13,1000])});
test('brush uses millimetres and paints only the requested native plane', () => {
 const points=core.brush([5,5,5],2,2,meta.dims1,meta.sp1).map(n=>core.point(n,meta.dims1));
 assert(points.every(p=>p[2]===5));
 assert(points.some(p=>p[0]===7&&p[1]===5));
 assert(points.some(p=>p[0]===5&&p[1]===6));
 assert(!points.some(p=>p[1]===7));
 for(const p of points)assert.equal(core.index(p,meta.dims1),core.index(core.point(core.index(p,meta.dims1),meta.dims1),meta.dims1));
});
test('3D sphere spans slices using physical spacing and is clipped at volume boundaries',()=>{
 const points=core.brush([5,5,5],3,-1,meta.dims1,meta.sp1).map(n=>core.point(n,meta.dims1));
 assert(points.some(p=>p[2]===6));assert(!points.some(p=>p[2]===7));
 for(const n of core.brush([0,0,0],3,-1,meta.dims1,meta.sp1))assert(n>=0&&n<1331);
});
test('stroke interpolation does not leave gaps between pointer events',()=>{
 const painted=core.stroke([1,5,5],[9,5,5],.5,2,meta.dims1,meta.sp1);
 for(let x=1;x<=9;x++)assert(painted.has(core.index([x,5,5],meta.dims1)));
});
test('export/import preserves sparse masks, notes and physical coordinates',()=>{
 const before=item(), doc=core.documentFor([before],meta), after=core.validate(JSON.parse(JSON.stringify(doc)),meta)[0];
 assert.deepEqual(doc.items[0].mask_runs,[[0,3],[13,1],[1000,1]]);
 assert.deepEqual(after,before);
});
test('rejects a different patient even with identical geometry',()=>{
 const doc=core.documentFor([item()],meta);doc.study_id='scan-b';
 assert.throws(()=>core.validate(doc,meta),/different scan/);
});
test('rejects altered affine, invalid coordinates and malformed or oversized masks atomically',()=>{
 const cases=[doc=>doc.affine=[[0]],doc=>doc.items[0].position=[NaN,0,0],doc=>doc.items[0].mask_runs=[[0,2],[1,1]],doc=>doc.items[0].mask_runs=[[1330,2]],doc=>doc.items[0].mask_runs=[[-1,2]],doc=>doc.items[0].mask_runs=[[0,2.5]],doc=>doc.items.push({...doc.items[0]})];
 for(const mutate of cases){const doc=JSON.parse(JSON.stringify(core.documentFor([item()],meta)));mutate(doc);assert.throws(()=>core.validate(doc,meta));}
 const large={...meta,dims1:[200,200,200]};const doc=core.documentFor([item()],large);doc.items[0].mask_runs=[[0,core.MAX_VOXELS+1]];
 assert.throws(()=>core.validate(doc,large),/limit/);
});
