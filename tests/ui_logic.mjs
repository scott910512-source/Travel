/* 화면 없이 app.js 의 조건·정렬 로직만 돌린다.
   ★ 이 앱에서 반복해서 난 사고는 "안내에 적힌 건수와 눌렀을 때 나오는
     건수가 다르다" 였다. 그 불변식을 여기서 고정한다. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const R = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const src = ['travel-state.js', 'compare.js', 'app.js']
  .map(f => fs.readFileSync(path.join(R, 'web', f), 'utf8')).join('\n');
const data = JSON.parse(fs.readFileSync(path.join(R, 'flight-deals/state/deals.json'), 'utf8'));

const noop = () => {};
const el = { hidden: false, innerHTML: '', textContent: '', style: {},
  setAttribute: noop, getAttribute: () => null, hasAttribute: () => false,
  querySelector: () => null, querySelectorAll: () => [], focus: noop, contains: () => false };
const ctx = {
  console,
  document: { addEventListener: noop, querySelector: () => el,
    querySelectorAll: () => [], getElementById: () => null, body: { style: {} },
    activeElement: null },
  window: { addEventListener: noop, scrollTo: noop, scrollY: 0,
    requestAnimationFrame: noop },
  history: { state: null, pushState: noop, replaceState: noop, back: noop },
  location: { hash: '', pathname: '/', search: '' },
  localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
  fetch: () => ({ then: () => ({ then: () => ({ catch: noop }) }) }),
  requestAnimationFrame: noop,
  URLSearchParams,
  Date, Math, JSON, Object, Array, Number, String, Set, Boolean, isFinite, parseInt,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
/* app.js 의 최상위 const 는 스크립트 렉시컬 스코프에 있어 밖에서 안 보인다.
   같은 스크립트 끝에서 필요한 것만 내보낸다. */
const NAMES = ['S', 'loadSettings', 'defaultF', 'defaultQuery', 'queryNow',
  'countOf', 'poolOf', 'applyQuery', 'altOptions', 'sortList', 'effective',
  'dealTier', 'pctOf', 'queryChips', 'isExpired', 'whenLine', 'whyLine',
  'matchesF', 'visibleOffers'];
vm.runInContext(src + `\n;globalThis.__ui = {${NAMES.join(',')}};`,
  ctx, { filename: 'app.js' });
Object.assign(ctx, ctx.__ui);

const { S } = ctx;
S.data = data;
S.settings = ctx.loadSettings(data);
S.f = ctx.defaultF();

let fails = 0;
const t = (name, fn) => {
  try { fn(); console.log('ok  ', name); }
  catch (e) { fails++; console.log('FAIL', name, '→', e.message); }
};
const eq = (a, b, m) => { if (a !== b) throw new Error(`${m}: ${a} ≠ ${b}`); };
const reset = () => {
  S.origin = 'all'; S.scope = 'all'; S.month = null; S.f = ctx.defaultF();
  S.settings = ctx.loadSettings(data); S.sort = 'deal'; S.listCap = 60;
};

/* ── 1. 적용 전 예상 건수 = 적용 후 실제 건수 ── */
t('조건 시트의 예상 건수 = 적용 후 실제 건수 (모든 축 조합)', () => {
  const axes = [
    { origin: 'CJJ' }, { origin: 'ICN' }, { scope: 'dom' }, { scope: 'out' },
    { f: { tier: 'strong' } }, { f: { tier: 'deal' } }, { f: { change: 'down' } },
    { f: { change: 'new' } }, { f: { weekend: true } }, { f: { cap: 500000 } },
    { stops: 'direct' }, { stops: 'one' }, { minNights: 2, maxNights: 5 },
    { f: { q: '일본' } }, { f: { q: 'FUK' } },
  ];
  let checked = 0;
  for (const a of axes) for (const b of axes) {
    reset();
    const q = Object.assign({}, ctx.queryNow(), a, b);
    q.f = Object.assign({}, ctx.defaultF(), a.f || {}, b.f || {});
    const before = ctx.countOf(q);
    ctx.applyQuery(q);
    const after = ctx.poolOf(ctx.queryNow()).length;
    eq(before, after, `${JSON.stringify(a)}+${JSON.stringify(b)}`);
    checked++;
  }
  console.log(`     ${checked}개 조합 확인`);
});

/* ── 2. 축이 서로 곱해서 걸리는가 (예전 listFilter 한 칸 문제) ── */
t('변화 조건 + 직항을 동시에 걸 수 있다', () => {
  reset();
  const base = ctx.countOf(ctx.queryNow());
  // 그날 데이터에 실제로 있는 변화 축을 고른다. 0건짜리로 재면 아무것도
  // 검증하지 못한 채 통과한다.
  const ch = ['down', 'new'].find(k =>
    ctx.countOf(Object.assign({}, ctx.queryNow(),
      { f: Object.assign(ctx.defaultF(), { change: k }) })) > 0);
  if (!ch) throw new Error('오늘 데이터에 신규도 하락도 없다');
  const q1 = Object.assign({}, ctx.queryNow(), { f: Object.assign(ctx.defaultF(), { change: ch }) });
  const q2 = Object.assign({}, ctx.queryNow(), { stops: 'direct' });
  const both = Object.assign({}, q1, { stops: 'direct' });
  const n1 = ctx.countOf(q1), n2 = ctx.countOf(q2), nb = ctx.countOf(both);
  if (!(nb <= n1 && nb <= n2)) throw new Error(`조합 ${nb} > 단일 ${n1}/${n2}`);
  if (n1 >= base && n2 >= base) throw new Error('조건이 아무것도 안 거른다');
  // 실제로 두 조건이 다 걸렸는지 항목으로 확인
  if (!nb) throw new Error('조합이 0건이라 검증이 안 된다');
  for (const o of ctx.poolOf(both)) {
    if (o.change !== ch) throw new Error(`${ch} 가 아닌 건이 섞임`);
    if (o.stops !== 0) throw new Error('직항이 아닌 건이 섞임');
  }
  console.log(`     전체 ${base} / ${ch} ${n1} / 직항 ${n2} / 둘 다 ${nb}`);
});

/* ── 3. 0건 대안 버튼의 숫자 = 누른 뒤 실제 건수 ── */
t('0건 대안 버튼의 숫자 = 적용 후 건수', () => {
  reset();
  S.origin = 'CJJ'; S.f.tier = 'strong'; S.settings.stops = 'direct'; S.month = '2026-12';
  const q = ctx.queryNow();
  const alts = ctx.altOptions(q);
  if (!alts.length) throw new Error('대안이 하나도 없다 (조합을 다시 골라라)');
  for (const a of alts) {
    const applied = Object.assign({}, ctx.queryNow(), a.patch);
    if (a.patch.f) applied.f = Object.assign({}, ctx.queryNow().f, a.patch.f);
    ctx.applyQuery(applied);
    eq(a.n, ctx.poolOf(ctx.queryNow()).length, a.label);
    S.origin = 'CJJ'; S.f = ctx.defaultF(); S.f.tier = 'strong';
    S.settings.stops = 'direct'; S.month = '2026-12';
  }
  console.log(`     대안 ${alts.length}개 모두 일치`);
});

/* ── 3.5 도착지 글자 검색 ── */
t('도착지 검색은 도시·공항코드·지역 아무거나 받는다', () => {
  reset();
  const by = k => {
    const q = Object.assign({}, ctx.queryNow(), { f: Object.assign(ctx.defaultF(), { q: k }) });
    return ctx.poolOf(q);
  };
  const jp = by('일본'), fuk = by('후쿠오카'), code = by('FUK');
  if (!jp.length || !fuk.length) throw new Error('검색이 아무것도 못 찾는다');
  if (fuk.length !== code.length) throw new Error(`도시 ${fuk.length} ≠ 코드 ${code.length}`);
  for (const o of fuk) if (o.arr !== 'FUK') throw new Error('다른 도시가 섞임: ' + o.arr);
  for (const o of jp) if (o.region !== '일본') throw new Error('다른 지역이 섞임: ' + o.region);
  if (!(fuk.length < jp.length)) throw new Error('도시가 지역보다 넓다');
  console.log(`     일본 ${jp.length} / 후쿠오카 ${fuk.length} / FUK ${code.length}`);
});
t('검색어가 없으면 아무것도 거르지 않는다', () => {
  reset();
  const all = ctx.countOf(ctx.queryNow());
  const q = Object.assign({}, ctx.queryNow(), { f: Object.assign(ctx.defaultF(), { q: '   ' }) });
  eq(ctx.countOf(q), all, '공백만 있는 검색어');
});

/* ── 4. 정렬 ── */
t('예상 부담액 낮은순 = 오름차순', () => {
  reset(); S.sort = 'price';
  const l = ctx.sortList(ctx.poolOf(ctx.queryNow()));
  for (let i = 1; i < l.length; i++) {
    if (ctx.effective(l[i]) < ctx.effective(l[i - 1])) throw new Error(`${i}번째에서 역전`);
  }
});
t('할인율 높은순 = 내림차순 · 판정 보류는 맨 뒤', () => {
  reset(); S.sort = 'deal';
  const l = ctx.sortList(ctx.poolOf(ctx.queryNow()));
  let seenUnknown = false;
  for (let i = 1; i < l.length; i++) {
    if (ctx.dealTier(l[i]) === 'unknown') seenUnknown = true;
    else if (seenUnknown) throw new Error('판정 보류 뒤에 판정된 건이 나온다');
    if (ctx.pctOf(l[i]) > ctx.pctOf(l[i - 1])) throw new Error(`${i}번째에서 역전`);
  }
});

/* ── 5. 검색 조건 초기화가 기기 설정을 건드리지 않는다 ── */
t('검색 조건 초기화는 교통비·강력특가 기준을 지우지 않는다', () => {
  reset();
  S.settings.access.ICN = 77777; S.settings.strongPct = 41;
  S.origin = 'CJJ'; S.f.tier = 'strong'; S.settings.stops = 'direct';
  ctx.applyQuery(ctx.defaultQuery());
  eq(S.settings.access.ICN, 77777, '교통비');
  eq(S.settings.strongPct, 41, '강력특가 기준');
  eq(S.origin, 'all', '출발지');
  eq(S.f.tier, 'all', '등급');
  eq(S.settings.stops, 'prefer', '환승');
});

/* ── 6. 조건 칩 개별 해제 ── */
t('칩 하나를 떼어도 나머지 조건은 남는다', () => {
  reset();
  S.origin = 'CJJ'; S.f.change = 'down'; S.settings.stops = 'direct';
  const chips = ctx.queryChips(ctx.queryNow()).map(c => c.k);
  for (const k of ['origin', 'change', 'stops']) {
    if (chips.indexOf(k) === -1) throw new Error(`${k} 칩이 안 만들어짐: ${chips}`);
  }
  eq(chips.length, 3, '칩 개수');
});

/* ── 7. 만료 기준이 화면마다 같은가 ── */
t('만료 판정은 모든 목록이 같은 함수를 쓴다', () => {
  const expired = data.offers.filter(o => ctx.isExpired(o));
  const pool = ctx.poolOf(ctx.queryNow());
  for (const o of pool) if (ctx.isExpired(o)) throw new Error('만료 건이 목록에 남음');
  console.log(`     만료 ${expired.length}건 / 전체 ${data.offers.length}건`);
});

/* ── 8. 카드가 미확인 값을 확정처럼 쓰지 않는가 ── */
t('한국 도착일이 없으면 현지 출발일을 도착일처럼 쓰지 않는다', () => {
  const noArr = data.offers.find(o => !o.home_arrive_date);
  if (!noArr) return console.log('     (해당 사례 없음)');
  const w = ctx.whenLine(noArr);
  if (w.indexOf('한국 도착') !== -1) throw new Error('미확인인데 한국 도착이라 적음: ' + w);
  if (w.indexOf('현지 출발') === -1) throw new Error('현지 출발 표시가 없다: ' + w);
  const withArr = data.offers.find(o => o.home_arrive_date);
  if (withArr && ctx.whenLine(withArr).indexOf('한국 도착') === -1) {
    throw new Error('도착일이 있는데 안 쓴다');
  }
});
t('표본이 모자라면 할인율을 근거로 내세우지 않는다', () => {
  const u = data.offers.filter(o => ctx.dealTier(o) === 'unknown');
  for (const o of u.slice(0, 50)) {
    const w = ctx.whyLine(o);
    if (/% 저렴/.test(w)) throw new Error('판정 보류인데 할인율을 적음: ' + w);
  }
  console.log(`     판정 보류 ${u.length}건`);
});

process.exit(fails ? 1 : 0);
