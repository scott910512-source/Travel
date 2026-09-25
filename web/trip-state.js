/* 10월 여행 · 내 일정 상태. 순수 함수 + localStorage 만 쓴다(화면 없음).
   내 여행 일정(okinawa-2026-10.html)과 식당 둘러보기(okinawa-2026-10-food.html), 앱(app.js)이 같이 쓴다.
   - 기본 추천(trip-data.js 의 template)과 사용자 선택(plan)을 분리한다. plan 에는 항목 순서·참조·제외·완료만 있다.
   - 저장 키 두 개: trip.dep(출발일 · 앱과 공유) / trip.plan(일정). 버전이 다르거나 깨져 있으면 기본으로 돌아가고 그 사실을 알린다.
   - 저장은 실패할 수 있다(용량·사파리 비공개 모드). save() 는 성공 여부를 돌려주고 화면은 그때만 '저장됨' 이라고 말한다.
   - 기기 간 동기화는 없다. 같은 브라우저의 다른 탭에는 storage 이벤트로 전해진다. */
'use strict';
const TripState = (() => {
  const VERSION = 1;
  const DEP_KEY = 'trip.dep', PLAN_KEY = 'trip.plan', LEGACY_DONE_KEY = 'okinawa-2026-10.done';
  const DEPS = ['2026-10-03', '2026-10-04', '2026-10-05'];
  const NIGHTS = 3, DAYS = 4;
  const DAY = ['일', '월', '화', '수', '목', '금', '토'];
  const SLOTS = ['breakfast', 'lunch', 'dinner', 'cafe'];
  const SLOT_LABEL = { breakfast: '아침', lunch: '점심', dinner: '저녁', cafe: '카페·간식' };

  /* 날짜: toISOString(UTC) 을 쓰지 않는다. 한국 시간대 폰에서 하루가 밀린다. */
  function addDays(d, n) {
    const t = new Date(d + 'T00:00:00'); t.setDate(t.getDate() + n);
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
  }
  const dow = d => DAY[new Date(d + 'T00:00:00').getDay()] || '';
  const md = d => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
  const fmt = d => `${md(d)}(${dow(d)})`;
  const dayDate = (dep, k) => addDays(dep, k - 1);
  const validDep = d => DEPS.indexOf(d) !== -1;

  function getDep(storage) {
    let v = null; try { v = storage.getItem(DEP_KEY); } catch (_) {}
    return validDep(v) ? v : DEPS[0];
  }
  function putDep(storage, d) { if (!validDep(d)) return false; try { storage.setItem(DEP_KEY, d); return true; } catch (_) { return false; } }

  /* ── 참조 ── */
  const clone = o => JSON.parse(JSON.stringify(o));
  function safeUrl(u) {
    if (!u) return '';
    const s = String(u).trim().slice(0, 500);
    return /^https?:\/\/[^\s]+$/i.test(s) ? s : '';
  }
  function validRef(ref, data) {
    if (!ref || typeof ref !== 'object') return null;
    if (ref.type === 'poi') return data.pois.some(p => p.id === ref.id) ? { type: 'poi', id: ref.id } : null;
    if (ref.type === 'r') return data.restaurants.some(r => r.id === ref.id) ? { type: 'r', id: ref.id } : null;
    if (ref.type === 'hotel') return { type: 'hotel' };
    if (ref.type === 'tbd') return { type: 'tbd' };
    if (ref.type === 'custom') {
      const name = String(ref.name || '').trim().slice(0, 60);
      if (!name) return null;
      const out = { type: 'custom', name }; const url = safeUrl(ref.url); if (url) out.url = url;
      return out;
    }
    return null;
  }
  function resolve(ref, data) {
    if (!ref) return { name: '미정', a: null, ll: null, kind: 'tbd' };
    if (ref.type === 'poi') { const p = data.pois.find(x => x.id === ref.id); return p ? { name: p.n, a: p.a, ll: p.ll || null, poi: p, kind: 'poi' } : { name: '(삭제된 장소)', a: null, ll: null, kind: 'poi' }; }
    if (ref.type === 'r') { const r = data.restaurants.find(x => x.id === ref.id); return r ? { name: r.n, a: r.a, ll: r.ll || null, r, kind: 'r' } : { name: '(삭제된 식당)', a: null, ll: null, kind: 'r' }; }
    if (ref.type === 'hotel') return { name: data.hotel.n, a: data.hotel.a, ll: data.hotel.ll, hotel: true, kind: 'hotel' };
    if (ref.type === 'custom') return { name: ref.name, a: null, ll: null, url: ref.url || '', kind: 'custom' };
    return { name: '나중에 정하기', a: null, ll: null, kind: 'tbd' };
  }

  /* ── 기본 일정 ── */
  function templateDay(data, k) { return data.template.find(d => d.k === k); }
  function defaultItems(data, k) {
    return templateDay(data, k).items.map(it => ({ uid: it.uid, kind: it.kind, slot: it.slot || null, ref: it.ref ? clone(it.ref) : null, tpl: it.uid, excluded: false }));
  }
  function defaultPlan(data, dep) {
    const days = {};
    for (let k = 1; k <= DAYS; k++) days[k] = { items: defaultItems(data, k) };
    return { recommendation:data.recommendation || 'legacy', v: VERSION, dep: validDep(dep) ? dep : DEPS[0], days, done: {} };
  }

  /* ── 불러오기 · 저장 ── */
  function normalize(raw, data) {
    if (!raw || typeof raw !== 'object' || raw.v !== VERSION || !raw.days) return null;
    const plan = defaultPlan(data, raw.dep);
    for (let k = 1; k <= DAYS; k++) {
      const src = raw.days[k] && Array.isArray(raw.days[k].items) ? raw.days[k].items : null;
      if (!src) continue;
      const items = [], seen = {};
      src.forEach(it => {
        if (!it || typeof it.uid !== 'string' || seen[it.uid]) return;
        const kind = ['flight', 'move', 'poi', 'meal', 'rest'].indexOf(it.kind) !== -1 ? it.kind : null;
        if (!kind) return;
        const sourceItems = templateDay(data,k).items.concat((data.legacyTemplate || []).find(d=>d.k===k)?.items || []);
        const tpl = typeof it.tpl === 'string' && sourceItems.some(t => t.uid === it.tpl) ? it.tpl : null;
        if ((kind === 'flight' || kind === 'move') && !tpl) return;       // 고정 항목은 기본 일정에 있는 것만
        const ref = (kind === 'flight' || kind === 'move') ? (sourceItems.find(t => t.uid === tpl).ref || null) : validRef(it.ref, data);
        if (!ref && kind !== 'flight' && kind !== 'move') return;
        seen[it.uid] = true;
        items.push({ uid: it.uid.slice(0, 40), kind, slot: SLOTS.indexOf(it.slot) !== -1 ? it.slot : null, ref: ref ? clone(ref) : null, tpl, excluded: !!it.excluded });
      });
      // 기본 일정에 있는데 저장본에 빠진 고정 항목(항공·이동)은 되살린다 — 사용자가 뺄 수 없는 것들
      templateDay(data, k).items.forEach((t, i) => {
        if ((t.kind === 'flight' || t.kind === 'move') && !seen[t.uid]) items.splice(Math.min(i, items.length), 0, { uid: t.uid, kind: t.kind, slot: null, ref: t.ref ? clone(t.ref) : null, tpl: t.uid, excluded: false });
      });
      plan.days[k].items = items;
    }
    plan.recommendation = raw.recommendation || 'legacy';
    if(raw.hotel && Array.isArray(raw.hotel.ll) && raw.hotel.ll.length===2 && raw.hotel.ll.every(Number.isFinite) && raw.hotel.ll[0]>=25 && raw.hotel.ll[0]<=28 && raw.hotel.ll[1]>=126 && raw.hotel.ll[1]<=130) plan.hotel={name:String(raw.hotel.name||'내 숙소').slice(0,60),ll:raw.hotel.ll.slice()};
    plan.done = {};
    if (raw.done && typeof raw.done === 'object') Object.keys(raw.done).forEach(u => { if (raw.done[u] === true) plan.done[u] = true; });
    return plan;
  }
  function load(storage, data) {
    let txt = null; try { txt = storage.getItem(PLAN_KEY); } catch (_) {}
    let note = 'fresh', plan = null;
    if (txt) {
      try { plan = normalize(JSON.parse(txt), data); note = plan ? 'ok' : 'recovered'; }
      catch (_) { note = 'recovered'; }
    }
    if (!plan) {
      plan = defaultPlan(data, null);
      // 예전 일정표의 완료 체크를 옮긴다 (연결되는 항목만)
      let legacy = null; try { legacy = JSON.parse(storage.getItem(LEGACY_DONE_KEY) || 'null'); } catch (_) {}
      if (legacy && typeof legacy === 'object') {
        let n = 0;
        Object.keys(legacy).forEach(key => { const uid = data.legacyDone[key]; if (legacy[key] && uid) { plan.done[uid] = true; n++; } });
        if (n && note === 'fresh') note = 'migrated';
      }
    }
    plan.dep = getDep(storage);          // 출발일은 앱과 같은 키가 기준
    return { plan, note };
  }
  function save(storage, plan) {
    try {
      storage.setItem(PLAN_KEY, JSON.stringify(plan));
      storage.setItem(DEP_KEY, plan.dep);
      return true;
    } catch (_) { return false; }
  }

  /* ── 바꾸기 (전부 새 plan 을 돌려준다) ── */
  const dayOf = (plan, k) => plan.days[k];
  function setRef(plan, k, uid, ref, data) {
    const r = validRef(ref, data); if (!r) return plan;
    const next = clone(plan); const it = dayOf(next, k).items.find(x => x.uid === uid);
    if (!it || it.kind === 'flight' || it.kind === 'move') return plan;
    it.ref = r; return next;
  }
  function setKind(plan, k, uid, kind) {        // 관광 ↔ 휴식 전환
    if (kind !== 'poi' && kind !== 'rest') return plan;
    const next = clone(plan); const it = dayOf(next, k).items.find(x => x.uid === uid);
    if (!it || it.kind === 'flight' || it.kind === 'move' || it.kind === 'meal') return plan;
    it.kind = kind; return next;
  }
  function setExcluded(plan, k, uid, on) {
    const next = clone(plan); const it = dayOf(next, k).items.find(x => x.uid === uid);
    if (!it || it.kind === 'flight') return plan;
    it.excluded = !!on; return next;
  }
  function move(plan, k, uid, dir) {              // dir: -1 위 / +1 아래. 제외된 항목은 건너뛴다. 항공편은 양 끝에 고정.
    const next = clone(plan); const items = dayOf(next, k).items;
    const i = items.findIndex(x => x.uid === uid); if (i < 0 || items[i].kind === 'flight') return plan;
    let j = i + dir;
    while (j >= 0 && j < items.length && items[j].excluded) j += dir;
    if (j < 0 || j >= items.length || items[j].kind === 'flight') return plan;
    const [it] = items.splice(i, 1); items.splice(j, 0, it);
    return next;
  }
  function setDone(plan, uid, on) { const next = clone(plan); if (on) next.done[uid] = true; else delete next.done[uid]; return next; }
  function resetDay(plan, k, data) {
    const next = clone(plan); next.days[k] = { items: defaultItems(data, k) };
    // 완료 표시는 기본 항목에 남는 것만 유지
    const keep = new Set(next.days[k].items.map(x => x.uid));
    const gone = new Set(dayOf(plan, k).items.map(x => x.uid).filter(u => !keep.has(u)));
    gone.forEach(u => delete next.done[u]);
    return next;
  }
  function setDep(plan, dep) { if (!validDep(dep)) return plan; const next = clone(plan); next.dep = dep; return next; }
  /* 식당 둘러보기 → '일정에 넣기'. 그 날 그 식사 자리가 있으면 교체, 없으면 새 식사 항목을 만든다. */
  function setMeal(plan, k, slot, ref, data) {
    const r = validRef(ref, data); if (!r || SLOTS.indexOf(slot) === -1 || !plan.days[k]) return { plan, replaced: null, uid: null };
    const next = clone(plan); const items = dayOf(next, k).items;
    let it = items.find(x => x.kind === 'meal' && x.slot === slot);
    let replaced = null;
    if (it) { replaced = it.excluded ? null : clone(it.ref); it.ref = r; it.excluded = false; }
    else {
      it = { uid: `m-${slot}-${Date.now().toString(36)}`, kind: 'meal', slot, ref: r, tpl: null, excluded: false };
      // 대략 자리: 아침은 앞, 카페는 점심 뒤, 저녁은 출발 앞
      let at = items.length; const last = items[items.length - 1];
      if (last && last.kind === 'flight') at = items.length - 1;
      if (slot === 'breakfast') at = items[0] && items[0].kind === 'flight' ? 1 : 0;
      if (slot === 'cafe') { const li = items.findIndex(x => x.kind === 'meal' && x.slot === 'lunch'); if (li >= 0) at = li + 1; }
      items.splice(at, 0, it);
    }
    return { plan: next, replaced, uid: it.uid };
  }
  function mealOf(plan, k, slot) { const it = plan.days[k] && plan.days[k].items.find(x => x.kind === 'meal' && x.slot === slot && !x.excluded); return it ? it.ref : null; }

  /* ── 보기용 계산 ── */
  function isDayDefault(plan, k, data) {
    const cur = dayOf(plan, k).items.filter(x => !x.excluded), def = defaultItems(data, k);
    if (cur.length !== def.length) return false;
    return cur.every((x, i) => x.uid === def[i].uid && x.kind === def[i].kind && JSON.stringify(x.ref) === JSON.stringify(def[i].ref));
  }
  /* 시각: 추천 일정의 시각은 참고값이다. 현재 순서가 추천 순서와 어긋나는 항목(앞에 원래 뒤였던 항목이 있음)은
     시각 대신 '시간 확인 필요' 로 표시한다. 새로 넣은 항목(tpl 없음)은 시각이 없다. */
  function timeFlags(plan, k, data) {
    const tplOrder = {}; templateDay(data, k).items.forEach((t, i) => { tplOrder[t.uid] = i; });
    const tplT = {}; templateDay(data, k).items.forEach(t => { tplT[t.uid] = { t: t.t, lbl: t.lbl || null }; });
    const out = {}; let maxSeen = -1;
    dayOf(plan, k).items.forEach(it => {
      if (it.excluded) return;
      const o = it.tpl != null ? tplOrder[it.tpl] : null;
      if (o == null) { out[it.uid] = { t: null, lbl: null, check: true }; return; }
      const check = o < maxSeen;
      out[it.uid] = { t: check ? null : tplT[it.tpl].t, lbl: tplT[it.tpl].lbl, check };
      if (o > maxSeen) maxSeen = o;
    });
    return out;
  }

  /* ── 실행 취소 (화면이 스택을 들고 있는다) ── */
  function pushUndo(stack, plan, max) { const s = stack.concat([clone(plan)]); return s.length > (max || 20) ? s.slice(s.length - (max || 20)) : s; }
  function popUndo(stack) { return stack.length ? { stack: stack.slice(0, -1), plan: clone(stack[stack.length - 1]) } : { stack, plan: null }; }

  return { VERSION, DEP_KEY, PLAN_KEY, LEGACY_DONE_KEY, DEPS, NIGHTS, DAYS, SLOTS, SLOT_LABEL,
    addDays, dow, md, fmt, dayDate, validDep, getDep, putDep, safeUrl, validRef, resolve,
    defaultPlan, normalize, load, save, setRef, setKind, setExcluded, move, setDone, resetDay, setDep, setMeal, mealOf,
    isDayDefault, timeFlags, pushUndo, popUndo, clone };
})();
if (typeof module !== 'undefined') module.exports = TripState;
