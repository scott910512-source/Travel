/* 내 여행 일정 상태(trip-state.js)의 저장·복원·교체·이동·초기화·실행취소를 화면 없이 검사한다. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const currentData = require('../web/trip-data.js');
// The existing scenarios exercise the saved pre-redesign itinerary.
const data = {...currentData, template:currentData.legacyTemplate};
const TS = require('../web/trip-state.js');
let count = 0;
function test(name, fn) { fn(); console.log('ok', name); count++; }
function mem(init) { const m = { ...(init || {}) }; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; }, dump: () => ({ ...m }) }; }
const boom = { getItem: () => null, setItem: () => { throw new Error('QuotaExceeded'); } };

test('기본 일정은 template 과 같고 출발일은 첫 후보', () => {
  const p = TS.defaultPlan(data, null);
  assert.equal(p.dep, '2026-10-03'); assert.equal(p.v, TS.VERSION);
  for (let k = 1; k <= 4; k++) assert.equal(p.days[k].items.length, data.template[k - 1].items.length);
  assert(TS.isDayDefault(p, 2, data));
});
test('저장 → 불러오기 왕복, 출발일은 trip.dep 키가 기준', () => {
  const st = mem(); let p = TS.defaultPlan(data, '2026-10-04');
  p = TS.setRef(p, 2, 'd2-lunch', { type: 'r', id: 'r-533774a8' }, data);
  assert(TS.save(st, p)); assert.equal(st.getItem('trip.dep'), '2026-10-04');
  const { plan, note } = TS.load(st, data);
  assert.equal(note, 'ok'); assert.equal(plan.dep, '2026-10-04');
  assert.deepEqual(plan.days[2].items.find(x => x.uid === 'd2-lunch').ref, { type: 'r', id: 'r-533774a8' });
});
test('깨진 JSON · 다른 버전 · 이상한 참조는 기본으로 돌아가고 recovered 라고 말한다', () => {
  assert.equal(TS.load(mem({ 'trip.plan': '{oops' }), data).note, 'recovered');
  assert.equal(TS.load(mem({ 'trip.plan': JSON.stringify({ v: 99, days: {} }) }), data).note, 'recovered');
  const st = mem(); const p = TS.defaultPlan(data, null);
  p.days[1].items[1].ref = { type: 'r', id: 'nope' };          // 없는 식당
  p.days[1].items.push({ uid: 'x', kind: 'poi', ref: { type: 'poi', id: 'ghost' } });
  st.setItem('trip.plan', JSON.stringify(p));
  const { plan, note } = TS.load(st, data);
  assert.equal(note, 'ok');
  assert(!plan.days[1].items.some(x => x.uid === 'd1-lunch'), '없는 식당을 가리키는 항목은 버린다');
  assert(!plan.days[1].items.some(x => x.uid === 'x'));
  assert(plan.days[1].items.some(x => x.uid === 'd1-arrive'), '고정 항목은 남는다');
});
test('저장 실패는 false 를 돌려준다', () => { assert.equal(TS.save(boom, TS.defaultPlan(data, null)), false); });
test('예전 완료 체크(일차-순번)는 연결되는 항목만 옮긴다', () => {
  const st = mem({ 'okinawa-2026-10.done': JSON.stringify({ '2-2': true, '2-1': true, '9-9': true }) });
  const { plan, note } = TS.load(st, data);
  assert.equal(note, 'migrated'); assert.equal(plan.done['d2-churaumi'], true); assert.equal(Object.keys(plan.done).length, 1);
});
test('교체 · 제외 · 복원 · 완료는 서로 독립이다', () => {
  let p = TS.defaultPlan(data, null);
  p = TS.setDone(p, 'd2-lunch', true);
  p = TS.setRef(p, 2, 'd2-lunch', { type: 'custom', name: ' 동네 소바 ', url: 'javascript:alert(1)' }, data);
  const it = p.days[2].items.find(x => x.uid === 'd2-lunch');
  assert.deepEqual(it.ref, { type: 'custom', name: '동네 소바' }, '이름은 다듬고 http(s) 아닌 링크는 버린다');
  assert.equal(p.done['d2-lunch'], true, '완료는 그대로');
  p = TS.setExcluded(p, 2, 'd2-lunch', true); assert(p.days[2].items.find(x => x.uid === 'd2-lunch').excluded);
  p = TS.setExcluded(p, 2, 'd2-lunch', false); assert(!p.days[2].items.find(x => x.uid === 'd2-lunch').excluded);
  assert.equal(TS.setRef(p, 2, 'd2-lunch', { type: 'custom', name: '' }, data), p, '이름 없는 직접 입력은 거부');
  assert.equal(TS.setExcluded(p, 1, 'd1-arrive', true), p, '항공편은 뺄 수 없다');
  p = TS.setKind(p, 2, 'd2-bise', 'rest'); assert.equal(p.days[2].items.find(x => x.uid === 'd2-bise').kind, 'rest');
});
test('위·아래 이동은 제외된 항목을 건너뛰고 항공편을 넘지 않는다', () => {
  let p = TS.defaultPlan(data, null);
  p = TS.setExcluded(p, 1, 'd1-manza', true);
  p = TS.move(p, 1, 'd1-dinner', -1);
  const ids = p.days[1].items.map(x => x.uid);
  assert.deepEqual(ids, ['d1-arrive', 'd1-lunch', 'd1-drive', 'd1-dinner', 'd1-checkin', 'd1-manza'], ids.join(','));
  assert.equal(TS.move(p, 1, 'd1-lunch', -1), p, '도착편 위로는 못 간다');
});
test('순서를 바꾸면 모순되는 시각은 확인 필요가 된다', () => {
  let p = TS.defaultPlan(data, null);
  assert.equal(TS.timeFlags(p, 2, data)['d2-lunch'].t, '12:30');
  p = TS.move(p, 2, 'd2-dinner', -1); p = TS.move(p, 2, 'd2-dinner', -1);   // 저녁을 점심 앞으로... (bise, kouri 를 넘어)
  const f = TS.timeFlags(p, 2, data);
  assert.equal(f['d2-dinner'].t, '18:30'); assert(f['d2-kouri'].check && f['d2-kouri'].t === null, '저녁 뒤로 밀린 카페는 시간 확인 필요');
  assert(!f['d2-lunch'].check);
});
test('해당 날짜 초기화는 그 날만 되돌리고 남은 항목의 완료는 유지', () => {
  let p = TS.defaultPlan(data, null);
  p = TS.setRef(p, 3, 'd3-lunch', { type: 'hotel' }, data); p = TS.setDone(p, 'd3-zanpa', true); p = TS.setDone(p, 'd2-bise', true);
  const r = TS.setMeal(p, 3, 'cafe', { type: 'r', id: data.restaurants[0].id }, data); p = r.plan; p = TS.setDone(p, r.uid, true);
  p = TS.resetDay(p, 3, data);
  assert(TS.isDayDefault(p, 3, data)); assert.equal(p.done['d3-zanpa'], true); assert.equal(p.done['d2-bise'], true); assert.equal(p.done[r.uid], undefined);
});
test('식당 둘러보기의 일정에 넣기: 있는 자리는 교체(교체 대상 반환), 없는 자리는 새 항목', () => {
  let p = TS.defaultPlan(data, null);
  const a = TS.setMeal(p, 3, 'dinner', { type: 'r', id: 'r-533774a8' }, data);
  assert.deepEqual(a.replaced, { type: 'r', id: 'r-07ea30c4' }); assert.equal(a.uid, 'd3-dinner');
  const b = TS.setMeal(a.plan, 3, 'cafe', { type: 'r', id: 'r-533774a8' }, data);
  assert.equal(b.replaced, null); assert(b.uid.startsWith('m-cafe-'));
  const ids = b.plan.days[3].items.map(x => x.uid); assert.equal(ids[ids.indexOf('d3-lunch') + 1], b.uid, '카페는 점심 뒤에');
  assert.deepEqual(TS.mealOf(b.plan, 3, 'dinner'), { type: 'r', id: 'r-533774a8' });
  const c = TS.setMeal(b.plan, 9, 'dinner', { type: 'hotel' }, data); assert.equal(c.plan, b.plan);
});
test('출발일을 바꾸면 날짜만 바뀌고 선택은 유지', () => {
  let p = TS.defaultPlan(data, null); p = TS.setRef(p, 2, 'd2-lunch', { type: 'tbd' }, data);
  const q = TS.setDep(p, '2026-10-05');
  assert.equal(TS.dayDate(q.dep, 4), '2026-10-08'); assert.equal(TS.fmt(TS.dayDate(q.dep, 1)), '10/5(월)');
  assert.deepEqual(q.days, p.days); assert.equal(TS.setDep(p, '2026-12-25'), p);
});
test('실행 취소 스택', () => {
  let stack = [], p = TS.defaultPlan(data, null);
  stack = TS.pushUndo(stack, p); const q = TS.setExcluded(p, 2, 'd2-bise', true);
  const u = TS.popUndo(stack); assert.deepEqual(u.plan, p); assert.equal(u.stack.length, 0); assert.notDeepEqual(q, p);
  assert.equal(TS.popUndo([]).plan, null);
  let s = []; for (let i = 0; i < 30; i++) s = TS.pushUndo(s, p, 20); assert.equal(s.length, 20);
});
test('참조 풀기: 좌표 없는 식당·직접 입력은 ll 이 null', () => {
  const r = data.restaurants.find(x => !x.ll);
  assert.equal(TS.resolve({ type: 'r', id: r.id }, data).ll, null);
  assert.equal(TS.resolve({ type: 'custom', name: 'x' }, data).ll, null);
  assert.equal(TS.resolve({ type: 'hotel' }, data).ll, null, 'unbooked hotel has no invented location');
});
console.log(`${count} trip state scenarios passed`);
