/* 내 여행 일정 · 식당 둘러보기 화면을 jsdom 으로 띄워 핵심 흐름을 검사한다.
   Leaflet 은 안 불러온다(지도 실패 상황) — 일정 선택·저장은 그래도 되어야 한다. */
import { JSDOM, VirtualConsole } from 'jsdom';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const TSn = require('../web/trip-state.js'), Dn = require('../web/trip-data.js');
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const read = f => fs.readFileSync(path.join(root, 'web', f), 'utf8');
const inline = html => [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
const PLAN = read('okinawa-2026-10.html'), FOOD = read('okinawa-2026-10-food.html');
const shared = read('trip-data.js') + '\n' + read('trip-state.js') + '\n';
const wait = () => new Promise(r => setTimeout(r, 30));
async function boot(html, { hash = '', storage = {} } = {}) {
  const errors = [], vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e));
  const dom = new JSDOM(html.replace(/<script src="[^"]+"><\/script>/g, ''), { url: 'https://example.test/Travel/x.html' + hash, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: vc });
  const w = dom.window;
  Object.entries(storage).forEach(([k, v]) => w.localStorage.setItem(k, v));
  w.fetch = async () => ({ ok: false, json: async () => null });
  w.scrollTo = () => {}; w.confirm = () => true;
  w.eval(shared + inline(html)); await wait();
  assert.equal(errors.length, 0, errors.map(e => e.message + '\n' + (e.detail && e.detail.stack)).join('\n'));
  const dump = () => Object.fromEntries(Object.keys(w.localStorage).map(k => [k, w.localStorage.getItem(k)]));
  return { w, d: w.document, dump, errors };
}
const txt = el => el.textContent.replace(/\s+/g, ' ').trim();
const names = d => [...d.querySelectorAll('#day .stop:not(.ex) h4')].map(h => txt(h).replace(/^\S+\s?/, ''));
let count = 0;
async function test(name, fn) { await fn(); console.log('ok', name); count++; }
let saved;

await test('2일차 점심 식당 변경 → 카드·길찾기 즉시 반영, 시트 닫힘, 저장됨 표시', async () => {
  const { d, dump } = await boot(PLAN, { hash: '#d2' });
  assert(d.querySelector('#map').textContent.includes('지도를 불러오지 못했습니다'), '지도 실패 안내');
  const btn = d.querySelector('[data-pick="r"][data-uid="d2-lunch"]'); btn.click();
  const sheet = d.querySelector('#sheet'); assert(!sheet.hidden);
  assert.equal(sheet.querySelector('[data-parea][aria-pressed="true"]').dataset.parea, 'north', '기본 지역 = 그 일정 지역');
  sheet.querySelector('[data-parea="naha"]').click();
  const opt = [...sheet.querySelectorAll('.opt')].find(o => txt(o).includes('슈리소바')); assert(opt);
  assert(txt(opt).includes('가격대 미확인') && txt(opt).includes('방문일 영업 확인 필요'), '없는 정보는 미확인');
  opt.querySelector('[data-choose]').click();
  assert(d.querySelector('#sheet').hidden, '시트 닫힘');
  assert(names(d).some(n => n.includes('슈리소바')), names(d).join('|'));
  const legs = [...d.querySelectorAll('.leg a')].map(a => a.href);
  assert(legs.some(u => u.includes('26.2185,127.7161')), '길찾기 구간이 새 식당 좌표로');
  assert(txt(d.querySelector('.dstat')).includes('저장됨'));
  assert(txt(d.querySelector('.dstat')).includes('일정을 바꿨습니다') && txt(d.querySelector('.dstat')).includes('미확인'), '고정 거리·시간을 더 이상 보여 주지 않는다');
  saved = dump();
});
await test('새로고침 → 선택 복원', async () => {
  const { d } = await boot(PLAN, { hash: '#d2', storage: saved });
  assert(names(d).some(n => n.includes('슈리소바')));
});
await test('식당 둘러보기에서 3일차 저녁 추가 → 교체 대상 표시 → 일정에서 확인', async () => {
  const { d, dump } = await boot(FOOD, { storage: saved });
  const r = [...d.querySelectorAll('[data-add]')].find(b => b.closest('.r').textContent.includes('류큐노우시')); r.click();
  const sh = d.querySelector('#addsheet'); assert(!sh.hidden);
  sh.querySelector('[data-aday="3"]').click(); sh.querySelector('[data-aslot="dinner"]').click();
  assert(txt(sh).includes('현재 이온몰 오키나와 라이카무 푸드코트 → 류큐노우시 온나점 으로 교체'), txt(sh));
  sh.querySelector('[data-asave]').click();
  assert(d.querySelector('#addsheet').hidden); assert(txt(d.querySelector('#toast')).includes('3일차 저녁'));
  assert(d.querySelector('#toast a').getAttribute('href').endsWith('#d3'), '일정 보기 링크는 3일차로');
  const card = [...d.querySelectorAll('#list .r')].find(c => c.textContent.includes('류큐노우시'));
  assert(txt(card).includes('3일차 저녁'), '카드에 들어간 자리 표시 (다시 그린 뒤)');
  saved = dump();
  const p = await boot(PLAN, { hash: '#d3', storage: saved });
  const dinner = p.d.querySelector('#s-d3-dinner'); assert(txt(dinner).includes('류큐노우시'));
});
await test('관광지 제외·순서 변경 → 완료 상태 유지, 지도(구간) 갱신, 다시 추가', async () => {
  const { d, dump } = await boot(PLAN, { hash: '#d2', storage: saved });
  d.querySelector('[data-done="d2-kouri"]').click();
  d.querySelector('[data-exclude="d2-bise"]').click();
  assert(txt(d.querySelector('.stop.ex')).includes('비세'), '제외 행');
  d.querySelector('[data-move="-1"][data-uid="d2-kouri"]').click();
  const n = names(d); assert(n.findIndex(x => x.includes('코우리')) < n.findIndex(x => x.includes('슈리소바')), n.join('|'));
  assert(d.querySelector('[data-done="d2-kouri"]').checked, '완료 유지');
  assert(txt(d.querySelector('#s-d2-lunch .t')).includes('시간 확인 필요'), '순서가 어긋난 항목은 시간 대신 확인 필요');
  d.querySelector('[data-restore="d2-bise"]').click(); assert(!d.querySelector('.stop.ex'));
  saved = dump();
});
await test('출발일 변경 → 날짜 갱신, 선택 유지', async () => {
  const { d, dump } = await boot(PLAN, { hash: '#d2', storage: saved });
  d.querySelector('[data-dep="2026-10-05"]').click();
  assert(txt(d.querySelector('[data-day="2"]')).includes('10/6(화)'));
  assert(names(d).some(n => n.includes('슈리소바')) && names(d).some(n => n.includes('코우리')));
  assert.equal(d.defaultView.localStorage.getItem('trip.dep'), '2026-10-05', '앱과 같은 키');
  saved = dump();
});
await test('해당 날짜 초기화 → 실행 취소', async () => {
  const { d } = await boot(PLAN, { hash: '#d2', storage: saved });
  assert(!d.querySelector('[data-reset]').disabled);
  d.querySelector('[data-reset]').click();
  assert(txt(d.querySelector('.dstat')).includes('추천 일정 그대로') && names(d).some(n => n.includes('기시모토')));
  d.querySelector('[data-undo]').click();
  assert(names(d).some(n => n.includes('슈리소바')), '실행 취소로 돌아옴');
});
await test('직접 입력(좌표·평점 없음)과 나쁜 링크 처리, 호텔에서 쉬기', async () => {
  const { d } = await boot(PLAN, { hash: '#d1' });
  d.querySelector('[data-pick="r"][data-uid="d1-dinner"]').click();
  d.querySelector('[data-custom]').click();
  d.querySelector('[data-cname]').value = '<b>동네 식당</b>'; d.querySelector('[data-curl]').value = 'javascript:alert(1)';
  d.querySelector('[data-csave]').click();
  assert(!d.querySelector('#sheet').hidden && txt(d.querySelector('[data-cerr]')).includes('https'), '나쁜 링크는 거부');
  d.querySelector('[data-curl]').value = ''; d.querySelector('[data-csave]').click();
  const card = d.querySelector('#s-d1-dinner');
  assert(card.querySelector('h4').innerHTML.includes('&lt;b&gt;동네 식당&lt;/b&gt;'), '입력은 이스케이프');
  assert(txt(card).includes('지도 위치 미등록') && txt(card).includes('정보 미확인'));
  d.querySelector('[data-rest="d1-manza"]').click();
  assert(txt(d.querySelector('#s-d1-manza')).includes('호텔 (예약한 곳)'));
  assert(txt(d.querySelector('#s-d1-manza h4')).includes('휴식'));
});
await test('깨진 저장본 → 추천 일정 + 알림 · 항공편은 뺄 수 없음', async () => {
  const { d } = await boot(PLAN, { storage: { 'trip.plan': '{broken' } });
  assert(!d.querySelector('#notice').hidden && txt(d.querySelector('#notice')).includes('추천 일정으로'));
  assert(!d.querySelector('[data-exclude="d1-arrive"]'));
  assert(txt(d.querySelector('#s-d1-arrive .t')).includes('항공권 확정 후'));
});
await test('다른 탭의 변경(storage 이벤트)을 받아 다시 그린다', async () => {
  const { w, d } = await boot(PLAN, { hash: '#d2' });
  let p = TSn.load(w.localStorage, Dn).plan; p = TSn.setExcluded(p, 2, 'd2-churaumi', true); TSn.save(w.localStorage, p);   // 다른 탭이 저장한 것처럼
  w.dispatchEvent(new w.StorageEvent('storage', { key: 'trip.plan' })); await wait();
  assert(txt(d.querySelector('.stop.ex')).includes('츄라우미'));
});
console.log(`${count} trip plan DOM scenarios passed (map not loaded)`);
