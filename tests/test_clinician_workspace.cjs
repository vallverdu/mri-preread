// Integration tests for the browser workspace using an in-memory DOM/storage adapter.
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), {webcrypto} = require('node:crypto');
const meta = {study_id:'test-study',dims1:[16,16,16],sp1:[1,2,3],affine:[[1,0,0,0],[0,2,0,0],[0,0,3,0],[0,0,0,1]]};
const tick = () => new Promise(resolve => setImmediate(resolve));
class Element {
 constructor(){this.children=[];this.value='';this.dataset={};this.classList={add(){},remove(){},toggle(){}};this.textContent='';}
 append(...els){this.children.push(...els);} replaceChildren(){this.children=[];} focus(){} select(){} click(){this.onclick?.();}
}
function browser(storage = new Map(), unavailable = false) {
 const els = new Map(), el = id => {if(!els.has(id))els.set(id,new Element());return els.get(id);};
 const tools=['clin-point','clin-paint','clin-erase'].map(ct=>{const x=new Element();x.dataset.ct=ct;return x;});
 const regular=['nav','ruler','roi'].map(t=>{const x=new Element();x.dataset.t=t;return x;});
 const db={transaction(_,mode){
  const tx={aborted:false,abort(){this.aborted=true;queueMicrotask(()=>this.onabort?.());},objectStore(){return {
   get(key){const req={};queueMicrotask(()=>{req.result=structuredClone(storage.get(key));req.onsuccess?.();if(mode==='readwrite'&&!tx.aborted)tx.oncomplete?.();});return req;},
   put(value,key){storage.set(key,structuredClone(value));}
  };}};return tx;
 }};
 const indexedDB={open(){const req={};queueMicrotask(()=>{if(unavailable){req.error=Error('quota');req.onerror();}else{req.result=db;req.onsuccess();}});return req;}};
 const S={cross:[8,8,8],tool:'nav',pend3:null};
 let uploaded;
 const context=vm.createContext({console,setTimeout,clearTimeout,structuredClone,crypto:webcrypto,indexedDB,
  META:structuredClone(meta),G1:[16,16,16],SP1:[1,2,3],W:16,H:16,D:16,S,cv:new Element(),
  document:{getElementById:el,createElement:()=>new Element(),querySelectorAll:sel=>sel==='#clinTools button'?tools:regular,activeElement:null},
  window:{addEventListener(){}},clamp:(v,a,b)=>Math.max(a,Math.min(b,v)),draw2D(){},redraw(){},hud(){},cutFromSlice(){},
  mkTex(){},bindTex(){},U:{},gl:{TEXTURE_3D:1,TEXTURE_MIN_FILTER:2,TEXTURE_MAG_FILTER:3,NEAREST:4,RED:5,UNSIGNED_BYTE:6,texParameteri(){},uniform1i(){},uniform3fv(){},texSubImage3D(...args){uploaded=Array.from(args.at(-1));}}
 });
 vm.runInContext(fs.readFileSync('mri_preread/annotation_core.js','utf8')+'\n'+fs.readFileSync('mri_preread/clinician_viewer.js','utf8'),context);
 const c=vm.runInContext('Clinician',context);
 return {c,S,el,storage,uploaded:()=>uploaded,context,async init(){await c.init();},async settle(){await tick();await tick();},doc(){return storage.get(meta.study_id)?.doc;}};
}
test('create, edit, paint, erase, undo/redo, cancel and reload preserve clinician work',async()=>{
 const b=browser();await b.init();b.el('clinNew').onclick();
 b.el('clinTitle').onchange({target:{value:'<img src=x onerror=bad()> finding'}});
 b.el('clinNote').onchange({target:{value:'Follow-up note'}});
 b.S.tool='clin-paint';b.c.begin([4,4,4],2);b.c.paint([8,4,4]);b.c.end();await b.settle();
 const painted=JSON.stringify(b.doc().items[0].mask_runs);assert.notEqual(painted,'[]');
 assert.equal(b.doc().items[0].note,'Follow-up note');assert.equal(b.doc().items[0].position.join(','),'4,4,4');
 assert.equal(b.el('clinList').children[0].children[0].textContent,'D1 · <img src=x onerror=bad()> finding');
 b.c.undo();await b.settle();assert.deepEqual(b.doc().items[0].mask_runs,[]);
 b.c.undo(true);await b.settle();assert.equal(JSON.stringify(b.doc().items[0].mask_runs),painted);
 b.S.tool='clin-erase';b.c.begin([4,4,4],2);b.c.end();await b.settle();assert.notEqual(JSON.stringify(b.doc().items[0].mask_runs),painted);
 b.c.undo();await b.settle();assert.equal(JSON.stringify(b.doc().items[0].mask_runs),painted);
 b.S.tool='clin-paint';b.c.begin([12,12,12],-1);b.c.end(true);await b.settle();assert.equal(JSON.stringify(b.doc().items[0].mask_runs),painted);
 const reload=browser(b.storage);await reload.init();assert.equal(reload.el('clinNote').value,'Follow-up note');
 assert.equal(reload.el('clinList').children.length,1);
 reload.el('clinDelete').onclick();await reload.settle();assert.equal(reload.doc().items.length,0);assert.equal(reload.S.tool,'nav');
 reload.c.undo();await reload.settle();assert.equal(JSON.stringify(reload.doc().items[0].mask_runs),painted);
});
test('overlapping annotations retain separate masks when selected mask is erased',async()=>{
 const b=browser();await b.init();
 for(let i=0;i<2;i++){b.el('clinNew').onclick();b.S.tool='clin-paint';b.c.begin([8,8,8],2);b.c.end();}
 b.S.tool='clin-erase';b.c.begin([8,8,8],2);b.c.end();await b.settle();
 assert(b.doc().items[0].mask_runs.length>0);assert.deepEqual(b.doc().items[1].mask_runs,[]);
 b.c.texture();assert.equal(b.uploaded()[8+16*(8+16*8)],128);
});
test('Save note preserves all draft fields when the first edit re-renders the form',async()=>{
 const b=browser();await b.init();b.el('clinNew').onclick();
 b.el('clinTitle').value='Updated title';b.el('clinNote').value='Written observation';b.el('clinAuthor').value='Test reader';
 b.el('clinSave').onclick();await b.settle();
 assert.equal(b.doc().items[0].title,'Updated title');
 assert.equal(b.doc().items[0].note,'Written observation');
 assert.equal(b.doc().items[0].author,'Test reader');
});
test('imports round-trip masks and reject conflicting IDs and foreign studies without mutation',async()=>{
 const source=browser();await source.init();source.el('clinNew').onclick();source.S.tool='clin-paint';source.c.begin([5,5,5],-1);source.c.end();await source.settle();
 const dest=browser();await dest.init();
 const load=async doc=>{await dest.el('clinImport').onchange({target:{files:[{size:100,text:async()=>JSON.stringify(doc)}],value:'file'}});await dest.settle();};
 await load(source.doc());assert.equal(dest.doc().items.length,1);assert.deepEqual(dest.doc().items[0].mask_runs,source.doc().items[0].mask_runs);
 await load(source.doc());assert.match(dest.el('clinStatus').textContent,/already exists/);assert.equal(dest.doc().items.length,1);
 await load({...source.doc(),study_id:'another-person'});assert.match(dest.el('clinStatus').textContent,/different scan/);assert.equal(dest.doc().items.length,1);
});
test('concurrent tabs cannot silently overwrite another clinician draft',async()=>{
 const shared=new Map(), a=browser(shared), b=browser(shared);await a.init();await b.init();
 a.el('clinNew').onclick();await a.settle();const doc=JSON.stringify(a.doc());
 b.el('clinNew').onclick();await b.settle();assert.match(b.el('clinStatus').textContent,/Another tab changed/);assert.equal(JSON.stringify(a.doc()),doc);
});
test('unavailable browser storage keeps editing usable and clearly reports unsaved state',async()=>{
 const b=browser(new Map(),true);await b.init();assert.equal(b.el('clinControls').disabled,false);
 b.el('clinNew').onclick();assert.equal(b.el('clinList').children.length,1);assert.match(b.el('clinStatus').textContent,/Not saved/);
});
