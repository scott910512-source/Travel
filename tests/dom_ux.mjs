/* DOM integration tests. These do not assert browser layout or touch behavior. */
import { JSDOM, VirtualConsole } from 'jsdom';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const source=['travel-state.js','compare.js','app.js'].map(f=>fs.readFileSync(path.join(root,'web',f),'utf8')).join('\n');
const data=JSON.parse(fs.readFileSync(path.join(root,'flight-deals/state/deals.json'),'utf8'));
const wait=()=>new Promise(resolve=>setTimeout(resolve,20));
async function boot(hash='') {
  const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e));
  const dom=new JSDOM(html,{url:'https://example.test/Travel/'+hash,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
  dom.window.fetch=async()=>({ok:true,json:async()=>structuredClone(data)});
  dom.window.scrollTo=()=>{};
  dom.window.eval(source);await wait();
  assert.equal(errors.length,0,errors.map(e=>e.message).join('\n'));
  assert(dom.window.document.querySelector('.hero'));
  return {dom,w:dom.window,d:dom.window.document,errors};
}
let count=0;
async function test(name,fn){await fn();console.log('ok',name);count++;}
await test('실제 템플릿으로 부팅·필터·입력·적용을 연결한다',async()=>{
  const {dom,w,d,errors}=await boot();
  d.querySelector('[data-sheetopen]').click();
  const originalMain=d.querySelector('.commuter-intro');
  d.querySelector('#long-trip-filter').open=true;
  d.querySelector('.sheet-body').scrollTop=380;
  const longButton=d.querySelector('[data-longstops="direct"]');longButton.focus();longButton.click();
  assert.equal(d.querySelector('.commuter-intro'),originalMain,'필터 변경으로 배경을 다시 만들지 않는다');
  assert.equal(d.querySelector('.sheet-body').scrollTop,380);
  assert(d.querySelector('#long-trip-filter').open);
  assert.equal(d.activeElement.getAttribute('data-longstops'),'direct');
  const input=d.querySelector('[data-q]');input.focus();input.value='후쿠오카';
  input.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal(d.activeElement,input);assert.equal(d.querySelector('[data-q]'),input);
  const expected=d.querySelector('[data-apply]').textContent;
  d.querySelector('[data-apply]').click();
  assert.equal(d.querySelector('.sheet'),null);
  assert.equal(d.querySelector('.sum-n').textContent,expected.replace(' 보기',''));
  assert.equal(d.querySelector('#destination-input').value,'후쿠오카');
  assert.equal(errors.length,0,errors.map(e=>e.message).join('\n'));dom.window.close();
});
await test('비교 담기·비교 화면·상세·뒤로가기를 DOM에서 연결한다',async()=>{
  const {dom,d,errors}=await boot();
  const first=d.querySelector('[data-compare]').getAttribute('data-compare');
  d.querySelector('[data-compare]').click();
  assert(d.querySelector('.compare-bar .cta').disabled);
  const second=Array.from(d.querySelectorAll('[data-compare]')).find(x=>x.getAttribute('data-compare')!==first);
  second.click();assert(!d.querySelector('.compare-bar .cta').disabled);
  d.querySelector('.compare-bar [data-view="compare"]').click();
  assert.equal(d.querySelectorAll('.compare-table thead th').length,3);
  d.querySelector('.compare-table [data-open]').click();
  assert(d.querySelector('[role="dialog"]'));
  d.querySelector('[data-close]').click();await wait();
  assert.equal(d.querySelector('[role="dialog"]'),null);
  assert(d.querySelector('.compare-table'));
  assert.equal(errors.length,0,errors.map(e=>e.message).join('\n'));dom.window.close();
});
await test('상세 URL 직접 진입 후 닫아도 앱에 남는다',async()=>{
  const id=data.offers.find(o=>!o.price_valid_until).id;
  const {dom,d,w,errors}=await boot('#o='+encodeURIComponent(id));
  assert(d.querySelector('[role="dialog"]'));
  d.querySelector('[data-close]').click();await wait();
  assert.equal(d.querySelector('[role="dialog"]'),null);assert(d.querySelector('.hero'));
  assert.equal(w.location.pathname,'/Travel/');assert.equal(errors.length,0);dom.window.close();
});
await test('찾기 검색창의 Enter 제출과 필터 취소가 정상 동작한다',async()=>{
  const {dom,d,w,errors}=await boot();
  d.querySelector('[data-tab="find"]').click();
  const input=d.querySelector('#destination-input');input.value='FUK';
  d.querySelector('#destination-search').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  assert.equal(d.querySelector('#destination-input').value,'FUK');
  const before=d.querySelector('.sum-n').textContent;
  d.querySelector('[data-sheetopen]').click();
  const q=d.querySelector('[data-q]');q.value='취리히';q.dispatchEvent(new w.Event('input',{bubbles:true}));
  d.querySelector('[data-close]').click();await wait();
  assert.equal(d.querySelector('#destination-input').value,'FUK');assert.equal(d.querySelector('.sum-n').textContent,before);
  assert.equal(errors.length,0,errors.map(e=>e.message).join('\n'));dom.window.close();
});
console.log(`${count} DOM integration scenarios passed (layout not simulated)`);
