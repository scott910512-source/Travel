/* Regression scenarios for a Cheongju-area commuter. Fixed data, no API calls. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const events = {}, saved = new Map();
const noop = () => {};
const el = { hidden: false, innerHTML: '', style: {}, setAttribute: noop,
  querySelector: () => null, querySelectorAll: () => [], focus: noop };
let renders = 0, backs = 0;
const ctx = {
  URLSearchParams, console,
  document: { addEventListener: (k, v) => { events[k] = v; },
    querySelector: () => el, getElementById: () => null,
    body: { style: {}, classList: { toggle: noop } } },
  window: { addEventListener: noop, scrollTo: noop, scrollY: 180 },
  history: { state: null, back: () => { backs++; },
    replaceState(st) { this.state = st; }, pushState(st) { this.state = st; } },
  location: { hash: '', pathname: '/Travel/', search: '' },
  localStorage: { getItem: k => saved.get(k) || null, setItem: (k,v) => saved.set(k,v), removeItem: k => saved.delete(k) },
  requestAnimationFrame: noop,
  fetch: () => ({ then: () => ({ then: () => ({ catch: noop }) }) }),
};
vm.createContext(ctx);
const source = ['travel-state.js','compare.js','app.js'].map(f => fs.readFileSync(path.join(root,'web',f),'utf8')).join('\n');
vm.runInContext(source + '\n;globalThis.api={TravelState,S,defaultSettings,defaultF,queryNow,applyQuery,poolOf,summaryHTML,filterSheetHTML,encState,decState,restore,closeTop,goBack,loadComparison,compareUI};',ctx);
ctx.renderCounter = () => { renders++; };
vm.runInContext('render = renderCounter;',ctx);
const a=ctx.api, S=a.S, plain=v=>JSON.parse(JSON.stringify(v));
const offer=(id, region, nights, stops, extra={})=>({id,region,nights,stops,dep:'ICN',arr:'ZRH',city:'취리히',
  depart_date:'2099-10-01',return_date:'2099-10-11',price_krw:1000000,data_ok:false,...extra});
const reset=()=>{
  S.data={offers:[offer('long','유럽',10,1),offer('near','일본',3,0,{arr:'FUK',city:'후쿠오카'}),
    offer('confirmed','일본',3,0,{annual_leave:1,annual_leave_confirmed:true}),
    offer('uncertain','일본',3,0,{annual_leave:0,annual_leave_confirmed:false})],home:'CJJ',meta:{},access_cost_default:{ICN:80000,CJJ:10000},routes:{}};
  S.settings=a.defaultSettings(S.data);S.f=a.defaultF();S.origin='all';S.scope='all';S.month=null;
  S.detail=null;S.sheet=null;S.pending=null;S.view=null;S.tab='home';S.compared=[];S.sort='deal';
  ctx.history.state=null;backs=0;renders=0;saved.clear();
};
let tests=0;
const test=(name,fn)=>{reset();fn();tests++;console.log('ok',name);};
const click=(key,value='')=>{
  const attrs={['data-'+key]:value};
  const t={getAttribute:k=>Object.hasOwn(attrs,k)?attrs[k]:null,hasAttribute:k=>Object.hasOwn(attrs,k)};
  t.closest=()=>t;events.click({target:t});
};
test('근거리와 장거리 조건을 따로 명시하고 실제 장거리 선택을 적용한다',()=>{
  S.settings.stops='direct';S.settings.minNights=2;S.settings.maxNights=5;
  assert(a.summaryHTML().includes('근거리 2~5박 · 장거리 2~21박'));
  assert(a.filterSheetHTML().includes('위 근거리 조건과 별개입니다'));
  S.sheet='filter';S.pending=a.queryNow();click('longstops','direct');click('longnights','2-5');
  assert.equal(S.settings.longStops,'any','적용 전 설정은 보존');
  assert.equal(a.poolOf(S.pending).some(o=>o.id==='long'),false);
  click('apply','1');assert.equal(S.settings.longStops,'direct');assert.equal(S.settings.longMaxNights,5);
});
test('공유 링크가 근거리·장거리·연차·검색어·예산을 모두 복원한다',()=>{
  S.settings={...S.settings,minNights:2,maxNights:5,stops:'direct',longMinNights:7,longMaxNights:14,longStops:'one'};
  S.f={...S.f,q:'일본 & FUK',cap:500000,leave:0,weekend:true};S.sort='leave';S.month='2099-10';
  const before=plain(a.queryNow());ctx.location.hash=a.encState();
  S.settings=a.defaultSettings(S.data);S.f=a.defaultF();a.restore(a.decState());
  assert.deepEqual(plain(a.queryNow()),before);assert.equal(S.sort,'leave');
});
test('잘못된 공유값을 제한하고 예전 링크도 읽는다',()=>{
  const bad=a.TravelState.decode('#mn=-1&mx=999&st=broken&leave=NaN&m=2026-99&wk=0');
  assert.equal(bad.mn,undefined);assert.equal(bad.mx,undefined);assert.equal(bad.st,undefined);
  assert.equal(bad.f.leave,null);assert.equal(bad.m,null);assert.equal(bad.f.weekend,false);
  const old=a.TravelState.decode('#t=find&st=direct&q=FUK');assert.equal(old.st,'direct');assert.equal(old.f.q,'FUK');
});
test('빠른 조건 클릭은 목적지·예산·등급을 지우지 않는다',()=>{
  S.f={...S.f,q:'후쿠오카',cap:500000,tier:'deal'};click('list','weekend');
  assert.equal(S.f.q,'후쿠오카');assert.equal(S.f.cap,500000);assert.equal(S.f.tier,'deal');assert.equal(S.f.weekend,true);
  click('list','home-direct');assert.equal(S.origin,'CJJ');assert.equal(S.settings.longStops,'direct');assert.equal(S.f.q,'후쿠오카');
});
test('청주·수도권 바로가기는 해당 공항만 남기고 링크에서도 복원한다',()=>{
  S.data.offers.push(offer('daegu','일본',3,0,{dep:'TAE'}));
  click('origin','NEAR');assert.equal(a.poolOf(a.queryNow()).some(o=>o.dep==='TAE'),false);
  ctx.location.hash=a.encState();S.origin='all';a.restore(a.decState());assert.equal(S.origin,'NEAR');
});
test('연차 제한은 한국 도착일 미확인 일정을 유리하게 취급하지 않는다',()=>{
  S.f.leave=1;assert.deepEqual(a.poolOf(a.queryNow()).map(o=>o.id),['confirmed']);
  S.f.leave=0;assert.equal(a.poolOf(a.queryNow()).length,0);
  S.f.leave=null;assert.equal(a.poolOf(a.queryNow()).length,4);
});
test('직접 접속한 상세·보조 화면의 닫기는 외부 페이지로 나가지 않는다',()=>{
  S.detail=S.data.offers[0];a.closeTop();assert.equal(backs,0);assert.equal(S.detail,null);assert.equal(renders,1);
  S.view='settings';a.goBack();assert.equal(backs,0);assert.equal(S.view,null);assert.equal(S.tab,'home');
});
test('앱 내부에서 연 상세는 브라우저 뒤로가기를 사용한다',()=>{
  ctx.history.state={inside:true};S.detail=S.data.offers[0];a.closeTop();assert.equal(backs,1);
});
test('검색어 입력 후 첫 적용 클릭으로 결과를 확정한다',()=>{
  S.sheet='filter';S.pending=a.queryNow();
  events.input({target:{value:'후쿠오카',getAttribute:k=>k==='data-q'?'1':null}});
  assert.equal(renders,0);assert.equal(S.pending.f.q,'후쿠오카');
  click('apply','1');assert.equal(S.f.q,'후쿠오카');assert.equal(S.sheet,null);assert.equal(S.tab,'find');
  assert.equal(a.poolOf(a.queryNow()).length,1);
});
test('비교는 중복 없이 3개까지 담고 다시 누르면 제거한다',()=>{
  click('compare','long');click('compare','near');click('compare','confirmed');click('compare','uncertain');
  assert.deepEqual(plain(S.compared),['long','near','confirmed']);
  click('compare','near');assert.deepEqual(plain(S.compared),['long','confirmed']);
  assert.deepEqual(plain(a.loadComparison()),['long','confirmed']);
});
test('비교 저장값이 손상되거나 후보가 사라져도 안전하게 정리한다',()=>{
  saved.set('fds.compare.v1','{}');assert.deepEqual(plain(a.loadComparison()),[]);
  saved.set('fds.compare.v1',JSON.stringify(['missing','near','near','long']));
  assert.deepEqual(plain(a.loadComparison()),['near','long']);
});
test('비교는 이동비를 합산하고 다른 일정·미확인 연차를 표시한다',()=>{
  S.compared=['long','near'];const html=a.compareUI.viewHTML();
  assert(html.includes('1,080,000원'));assert(html.includes('목적지나 일정이 서로 다릅니다'));
  assert(html.includes('한국 도착일 확인 필요'));assert(html.includes('세금 미확인'));
});
console.log(`${tests} worker UX scenarios passed`);
