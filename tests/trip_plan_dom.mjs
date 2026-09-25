/* 내 여행(캐릭터 여행·일정표·상세) · 식당 둘러보기 화면을 jsdom 으로 띄워 핵심 흐름을 검사한다.
   Leaflet 은 안 불러온다(지도 실패 상황) — 일정 선택·저장·재생은 그래도 되어야 한다. */
import { JSDOM, VirtualConsole } from 'jsdom';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const TSn = require('../web/trip-state.js'), currentData = require('../web/trip-data.js');
const Dn={...currentData,template:currentData.legacyTemplate};
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const read = f => fs.readFileSync(path.join(root, 'web', f), 'utf8');
const inline = html => [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
const PLAN = read('okinawa-2026-10.html'), FOOD = read('okinawa-2026-10-food.html');
const shared = ['trip-data.js', 'trip-state.js', 'trip-chars.js', 'trip-stage.js'].map(read).join('\n') + '\n';
const wait = ms => new Promise(r => setTimeout(r, ms || 30));
const LIST = { 'trip.ui': JSON.stringify({ view: 'list', day: 1, speed: 1 }) };
async function boot(html, { hash = '', storage = {}, ratings = null, fresh = false } = {}) {
  const errors = [], vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e));
  const dom = new JSDOM(html.replace(/<script src="[^"]+"><\/script>/g, ''), { url: 'https://example.test/Travel/x.html' + hash, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: vc });
  const w = dom.window;
  if(!fresh && !storage['trip.plan']){const legacy=TSn.defaultPlan(Dn,'2026-10-03');legacy.recommendation='legacy';legacy.hotel={name:'테스트 숙소',ll:[26.488,127.842]};storage={'trip.plan':JSON.stringify(legacy),...storage};}
  Object.entries(storage).forEach(([k, v]) => w.localStorage.setItem(k, v));
  let resolveRatings; const ratingsP = new Promise(r => { resolveRatings = r; });
  w.fetch = async url => (ratings && /food\.json/.test(url)) ? { ok: true, json: () => ratingsP } : { ok: false, json: async () => null };
  w.scrollTo = () => {}; w.confirm = () => true;
  w.eval(shared + inline(html)); await wait();
  assert.equal(errors.length, 0, errors.map(e => e.message + '\n' + (e.detail && e.detail.stack)).join('\n'));
  const dump = () => Object.fromEntries(Object.keys(w.localStorage).map(k => [k, w.localStorage.getItem(k)]));
  return { w, d: w.document, dump, errors, deliverRatings: () => resolveRatings(ratings) };
}
const txt = el => el.textContent.replace(/\s+/g, ' ').trim();
const names = d => [...d.querySelectorAll('#day .stop:not(.ex) h4')].map(h => txt(h).replace(/^\S+\s?/, ''));
const edit = (d, uid) => d.querySelector(`[data-edit="${uid}"]`).click();
let count = 0;
async function test(name, fn) { await fn(); console.log('ok', name); count++; }
let saved;

await test('기존 저장 일정·방문 완료를 보존한 채 새 화면 진입 (처음은 캐릭터 보기 · 자동 재생 없음)', async () => {
  let p = TSn.defaultPlan(Dn, '2026-10-04'); p = TSn.setRef(p, 2, 'd2-lunch', { type: 'r', id: 'r-533774a8' }, Dn); p = TSn.setDone(p, 'd2-churaumi', true); p.hotel={name:'테스트 숙소',ll:[26.488,127.842]};
  const st = { 'trip.plan': JSON.stringify(p), 'trip.dep': '2026-10-04' };
  const { d } = await boot(PLAN, { hash: '#d2', storage: st });
  assert(d.querySelector('#v-chars').classList.contains('on'), '첫 보기는 캐릭터 여행');
  assert(txt(d.querySelector('#ctl .now')).includes('일시정지'), '자동 재생 없음');
  assert(d.querySelectorAll('#stage .node').length === 6, '2일차 스텝 6개가 맵에');
  assert(d.querySelector('#stage .node.done'), '방문 완료 표시 보존');
  assert(txt(d.querySelector('#hdsub')).includes('10/4(일) 출발'), '출발일은 저장값');
  assert([...d.querySelectorAll('#stage .node')].some(n => n.getAttribute('aria-label').includes('슈리소바')), '저장된 식당 선택 보존');
});
await test('2일차 재생 → 캐릭터 이동 → 도착 (걷기 동작 · 말풍선 · 방문 완료로 기록되지 않음)', async () => {
  const { d, w } = await boot(PLAN, { hash: '#d2' });
  d.querySelector('[data-speed]').value = '2'; d.querySelector('[data-speed]').dispatchEvent(new w.Event('change', { bubbles: true }));
  d.querySelector('[data-play]').click(); await wait(80);
  assert(txt(d.querySelector('#ctl .now')).includes('이동 중'));
  assert(d.querySelector('#stage .char.man').classList.contains('walk'), '걷기 동작');
  await wait(1450);
  assert(txt(d.querySelector('#ctl .now')).startsWith('2/6'), txt(d.querySelector('#ctl .now')));
  assert(d.querySelector('#stage .char.man').classList.contains('look'), '관광지 도착 → 둘러보기 동작');
  assert(txt(d.querySelector('#stage .bubble')).includes('둘러보자'));
  d.querySelector('[data-play]').click(); assert(txt(d.querySelector('#ctl .now')).includes('일시정지'));
  const savedPlan = JSON.parse(w.localStorage.getItem('trip.plan') || 'null'); assert(!savedPlan || Object.keys(savedPlan.done).length === 0, '재생은 방문 완료가 아니다');
});
await test('장소 클릭 → 상세보기(재생 일시정지) → 닫으면 재생 이어감, 정지 상태였으면 그대로', async () => {
  const { d } = await boot(PLAN, { hash: '#d2' });
  d.querySelector('[data-play]').click(); await wait(30);
  d.querySelector('#stage .node[data-i="2"]').dispatchEvent(new d.defaultView.MouseEvent('click', { bubbles: true }));
  assert(!d.querySelector('#sheet').hidden && txt(d.querySelector('#sheet .hd')).includes('기시모토'), '상세 열림');
  assert(txt(d.querySelector('#ctl .now')).includes('일시정지'), '상세 열면 일시정지');
  assert(txt(d.querySelector('#sheet')).includes('가격대 미확인') && txt(d.querySelector('#sheet')).includes('주소 미확인'), '없는 값은 미확인');
  d.querySelector('#sheet [data-close]').click(); await wait(30);
  assert(txt(d.querySelector('#ctl .now')).includes('재생 중') || txt(d.querySelector('#ctl .now')).includes('이동 중'), '닫으면 이어서 재생');
  d.querySelector('[data-play]').click();
  d.querySelector('[data-cur]').click(); d.querySelector('#sheet [data-close]').click(); await wait(30);
  assert(txt(d.querySelector('#ctl .now')).includes('일시정지'), '정지 중에 열었다 닫으면 정지 그대로');
});
await test('점심 식당 변경(상세 → 선택 시트) → 일정표·맵 노드·길찾기 동시 반영 · 시트가 상세로 돌아옴', async () => {
  const { d, dump } = await boot(PLAN, { hash: '#d2' });
  d.querySelector('#stage .node[data-i="2"]').dispatchEvent(new d.defaultView.MouseEvent('click', { bubbles: true }));
  d.querySelector('#sheet [data-pick="r"]').click();
  assert.equal(d.querySelector('[data-parea][aria-pressed="true"]').dataset.parea, 'north', '기본 지역 = 그 일정 지역');
  assert(txt(d.querySelector('#pbody')).includes('현재 선택'), '현재 선택 식당이 표시');
  d.querySelector('[data-parea="naha"]').click();
  assert(txt(d.querySelector('#pbody')).includes('현재 선택 (필터와 무관)'), '필터에 걸려도 현재 선택은 보인다');
  const opt = [...d.querySelectorAll('.opt')].find(o => txt(o).includes('슈리소바') && !txt(o).includes('현재 선택')); opt.querySelector('[data-choose]').click();
  assert(!d.querySelector('#sheet').hidden && txt(d.querySelector('#sheet .hd')).includes('슈리소바'), '상세로 돌아옴');
  assert([...d.querySelectorAll('#stage .node')].some(n => n.getAttribute('aria-label').includes('슈리소바')), '맵 노드 갱신');
  d.querySelector('#sheet [data-close]').click();
  d.querySelector('[data-view="list"]').click();
  assert(names(d).some(n => n.includes('슈리소바')));
  assert([...d.querySelectorAll('.leg a')].some(a => a.href.includes('26.2185,127.7161')), '길찾기 구간이 새 식당 좌표로');
  assert(txt(d.querySelector('.dstat')).includes('저장됨') && txt(d.querySelector('.dstat')).includes('미확인'));
  saved = dump();
});
await test('새로고침 → 선택·마지막 보기(일정표) 복원', async () => {
  const { d } = await boot(PLAN, { hash: '#d2', storage: saved });
  assert(d.querySelector('#v-list').classList.contains('on'), '마지막 보기 복원');
  assert(names(d).some(n => n.includes('슈리소바')));
});
await test('식당 둘러보기에서 3일차 저녁 추가 → 교체 대상 표시 → 해당 날짜·스텝으로 복귀', async () => {
  const { d, dump } = await boot(FOOD, { storage: saved });
  const r = [...d.querySelectorAll('[data-add]')].find(b => b.closest('.r').textContent.includes('류큐노우시')); r.click();
  const sh = d.querySelector('#addsheet'); sh.querySelector('[data-aday="3"]').click(); sh.querySelector('[data-aslot="dinner"]').click();
  assert(txt(sh).includes('현재 이온몰 오키나와 라이카무 푸드코트 → 류큐노우시 온나점 으로 교체'), txt(sh));
  sh.querySelector('[data-asave]').click();
  const link = d.querySelector('#toast a').getAttribute('href'); assert.equal(link, 'okinawa-2026-10.html#d3/d3-dinner', link);
  saved = dump();
  const p = await boot(PLAN, { hash: '#d3/d3-dinner', storage: saved });
  assert(txt(p.d.querySelector('#s-d3-dinner')).includes('류큐노우시'));
  assert(p.d.querySelector('[data-day="3"]').getAttribute('aria-selected') === 'true');
});
await test('제외·복원·순서 변경·실행 취소 → 맵 스텝 수 갱신, 완료 유지, 옛 이동 설명 숨김', async () => {
  const { d, dump } = await boot(PLAN, { hash: '#d2', storage: saved });
  d.querySelector('[data-done="d2-kouri"]').click();
  edit(d, 'd2-bise'); d.querySelector('[data-exclude="d2-bise"]').click();
  assert(txt(d.querySelector('.stop.ex')).includes('비세'));
  edit(d, 'd2-kouri'); d.querySelector('[data-move="-1"][data-uid="d2-kouri"]').click();
  const n = names(d); assert(n.findIndex(x => x.includes('코우리')) < n.findIndex(x => x.includes('슈리소바')), n.join('|'));
  assert(d.querySelector('[data-done="d2-kouri"]').checked, '완료 유지');
  assert(txt(d.querySelector('#s-d2-lunch .t')).includes('시간 확인 필요'));
  d.querySelector('[data-view="chars"]').click();
  assert.equal(d.querySelectorAll('#stage .node').length, 5, '제외 → 맵 스텝 5개');
  d.querySelector('[data-undo]') || d.querySelector('[data-view="list"]').click();
  d.querySelector('[data-view="list"]').click(); d.querySelector('[data-undo]').click(); d.querySelector('[data-undo]').click();
  assert(!d.querySelector('.stop.ex') && names(d).findIndex(x => x.includes('코우리')) > names(d).findIndex(x => x.includes('슈리소바')), '실행 취소 두 번');
  // 4일차: 슈리성을 바꾸면 '체크아웃 → 슈리성' 고정 이동 설명이 숨는다
  d.querySelector('[data-day="4"]').click();
  edit(d, 'd4-shuri'); d.querySelector('[data-pick="poi"][data-uid="d4-shuri"]').click(); d.querySelector('[data-parea="all"]').click();
  [...d.querySelectorAll('.opt')].find(o => txt(o).includes('세이파')).querySelector('[data-choose]').click();
  assert(txt(d.querySelector('#day')).includes('이동 · 거리·시간 미확인') && !txt(d.querySelector('#day')).includes('체크아웃 → 슈리성'), '옛 목적지 설명 숨김');
  saved = dump();
});
await test('출발일 변경 → 날짜 갱신, 선택 유지, 앱과 같은 키', async () => {
  const { d } = await boot(PLAN, { hash: '#d2', storage: saved });
  d.querySelector('[data-dep="2026-10-05"]').click();
  assert(txt(d.querySelector('[data-day="2"]')).includes('10/6(화)'));
  assert(names(d).some(n => n.includes('슈리소바')));
  assert.equal(d.defaultView.localStorage.getItem('trip.dep'), '2026-10-05');
});
await test('평점이 늦게 도착해도 재생 위치·열린 상세는 유지되고 값만 채워진다', async () => {
  const ratings = { ts: '2026-09-25T09:48:16Z', data: { '首里そば': { rating: 4.4, total: 1454, url: 'https://maps.google.com/?cid=1', photos: [] } } };
  const b = await boot(PLAN, { hash: '#d2', storage: saved, ratings });
  const { d } = b; d.querySelector('[data-view="chars"]').click(); d.querySelector('[data-next]').click(); d.querySelector('[data-next]').click();
  d.querySelector('[data-cur]').click(); assert(txt(d.querySelector('#sheet')).includes('평점 미확인'));
  b.deliverRatings(); await wait(50);
  assert(txt(d.querySelector('#ctl .now')).startsWith('3/'), '재생 위치 유지 ' + txt(d.querySelector('#ctl .now')));
  assert(!d.querySelector('#sheet').hidden && txt(d.querySelector('#sheet')).includes('★ 4.4') && txt(d.querySelector('#sheet')).includes('확인 9/25'), '상세에 평점·확인일 채워짐');
  d.querySelector('#sheet [data-done]').click(); await wait(20);
  assert(txt(d.querySelector('#ctl .now')).startsWith('3/'), '방문 완료 체크도 재생 위치를 건드리지 않는다');
  assert(d.querySelector('#stage .node[data-i="2"]').classList.contains('done'));
});
await test('이전·다음·일차 전환 연속 조작 → 캐릭터 한 쌍만, 타이머 중복 없음', async () => {
  const { d } = await boot(PLAN, { hash: '#d1' });
  for (let i = 0; i < 6; i++) { d.querySelector('[data-next]').click(); d.querySelector('[data-play]').click(); d.querySelector('[data-prev]').click(); }
  d.querySelector('[data-day="3"]').click(); d.querySelector('[data-day="2"]').click(); await wait(60);
  assert.equal(d.querySelectorAll('#stage .pair').length, 1); assert.equal(d.querySelectorAll('#stage .car').length, 1);
  assert(txt(d.querySelector('#ctl .now')).includes('일시정지'), '일차를 바꾸면 멈춘다');
  assert.equal(d.querySelectorAll('#stage .node').length, 6);
});
await test('직접 입력(좌표·평점 없음)·나쁜 링크·호텔에서 쉬기 · 깨진 저장본 · 항공편 고정', async () => {
  const { d } = await boot(PLAN, { hash: '#d1', storage: LIST });
  edit(d, 'd1-dinner'); d.querySelector('[data-pick="r"][data-uid="d1-dinner"]').click(); d.querySelector('[data-custom]').click();
  d.querySelector('[data-cname]').value = '<b>동네 식당</b>'; d.querySelector('[data-curl]').value = 'javascript:alert(1)'; d.querySelector('[data-csave]').click();
  assert(!d.querySelector('#sheet').hidden && txt(d.querySelector('[data-cerr]')).includes('https'));
  d.querySelector('[data-curl]').value = ''; d.querySelector('[data-csave]').click();
  const card = d.querySelector('#s-d1-dinner'); assert(card.querySelector('h4').innerHTML.includes('&lt;b&gt;동네 식당&lt;/b&gt;')); assert(txt(card).includes('지도 위치 미등록'));
  d.querySelector('[data-view="chars"]').click(); assert(txt(d.querySelector('#unknown-places')).includes('동네 식당'), 'unlocated custom place stays off the geographic map');
  d.querySelector('[data-view="list"]').click(); edit(d, 'd1-manza'); d.querySelector('[data-rest="d1-manza"]').click();
  assert(txt(d.querySelector('#s-d1-manza')).includes('테스트 숙소'));
  const b = await boot(PLAN, { storage: { 'trip.plan': '{broken', 'trip.ui': '{bad' } });
  assert(!b.d.querySelector('#notice').hidden); assert(!b.d.querySelector('[data-exclude="d1-arrive"]'));
});
await test('다른 탭의 변경(storage 이벤트)을 받아 다시 그린다', async () => {
  const { w, d } = await boot(PLAN, { hash: '#d2', storage: LIST });
  let p = TSn.load(w.localStorage, Dn).plan; p = TSn.setExcluded(p, 2, 'd2-churaumi', true); TSn.save(w.localStorage, p);
  w.dispatchEvent(new w.StorageEvent('storage', { key: 'trip.plan' })); await wait();
  assert(txt(d.querySelector('.stop.ex')).includes('츄라우미'));
});
console.log(`${count} trip plan DOM scenarios passed (map not loaded)`);

await test('새 추천 일정은 체험·북부·출국 선택을 제공하고 미정 숙소를 지도에 만들지 않는다', async()=>{
 const {d,w}=await boot(PLAN,{hash:'#d3',fresh:true});
 assert(txt(d.querySelector('#stage')).includes('시사'));
 assert(txt(d.querySelector('#unknown-places')).includes('호텔'));
 assert(![...d.querySelectorAll('#stage .node')].some(n=>n.getAttribute('aria-label').includes('호텔')));
 d.querySelector('[data-day="4"]').click();
 d.querySelector('[data-lastday="kokusai"]').click();
 let p=JSON.parse(w.localStorage.getItem('trip.plan'));
 assert.equal(p.days[4].items.filter(i=>!i.excluded&&i.kind==='poi').length,1);
 assert.equal(p.days[4].items.find(i=>i.uid==='d4-choice').ref.id,'kokusai');
 d.querySelector('[data-lastday="none"]').click();p=JSON.parse(w.localStorage.getItem('trip.plan'));
 assert(!p.days[4].items.some(i=>!i.excluded&&i.kind==='poi'));
});
await test('새 추천 코스 적용은 명시적이고 실행 취소하면 저장한 기존 선택이 복원된다', async()=>{
 const {d,w}=await boot(PLAN,{hash:'#d2'});
 const before=JSON.parse(w.localStorage.getItem('trip.plan'));
 d.querySelector('[data-apply-recommended]').click();
 let p=JSON.parse(w.localStorage.getItem('trip.plan'));
 assert(!p.days[2].items.some(i=>i.uid==='d2-bise'));
 assert(p.days[3].items.some(i=>i.uid==='d3-shisa'));
 d.querySelector('[data-undo]').click();p=JSON.parse(w.localStorage.getItem('trip.plan'));
 assert.deepEqual(p.days,before.days);
});
await test('숙소 설정·재방문은 한 랜드마크를 공유하며 저장·재로드된다',async()=>{
 const b=await boot(PLAN,{hash:'#d3',fresh:true});const {d}=b;
 d.querySelector('[data-hotel-name]').value='내 숙소';d.querySelector('[data-hotel-lat]').value='26.49';d.querySelector('[data-hotel-lon]').value='127.85';d.querySelector('[data-hotel-save]').click();
 const hotels=[...d.querySelectorAll('#stage .node')].filter(n=>n.getAttribute('aria-label').includes('내 숙소'));
 assert.equal(hotels.length,1);assert(txt(hotels[0].querySelector('.visit-number')).includes('1 · 3 · 4 · 7'));
 const re=await boot(PLAN,{hash:'#d3',storage:b.dump(),fresh:true});assert.equal(re.d.querySelector('[data-hotel-name]').value,'내 숙소');
});
await test('지리 좌표·이동선·캐릭터가 동일한 투영을 사용하고 멈춘 위치에서 이어진다',async()=>{
 const {d,w}=await boot(PLAN,{hash:'#d2',fresh:true});
 d.querySelector('[data-next]').click(); // aquarium; next destination is located restaurant
 const nodes=[...d.querySelectorAll('#stage .node')];
 const aquarium=nodes.find(n=>n.getAttribute('aria-label').includes('츄라우미'));const kouri=nodes.find(n=>n.getAttribute('aria-label').includes('코우리'));
 assert(+aquarium.querySelector('.anchor').getAttribute('cx')<+kouri.querySelector('.anchor').getAttribute('cx'),'Kouri east of aquarium');
 d.querySelector('[data-play]').click();await wait(180);d.querySelector('[data-play]').click();
 const p=d.querySelector('#stage .car').getAttribute('transform');await wait(80);assert.equal(d.querySelector('#stage .car').getAttribute('transform'),p);
 d.querySelector('[data-play]').click();await wait(80);d.querySelector('[data-play]').click();
 const q=d.querySelector('#stage .car').getAttribute('transform');assert.notEqual(q,p);
 const x=t=>Number(t.match(/translate\(([^,]+)/)[1]);assert(x(q)>x(p),'restaurant east of aquarium: resume advances, never resets');
 assert.equal(Object.keys(JSON.parse(w.localStorage.getItem('trip.plan')||'{"done":{}}').done).length,0);
});
