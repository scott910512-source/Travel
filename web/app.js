/* ══════════════════════════════════════════════════════════
   항공권 데일리 스캐너 — 화면
   scanner.py 가 만든 deals.json 을 읽어 클라이언트에서 렌더한다.

   실부담가와 특가 등급을 여기서 계산하는 이유:
   교통비·출발지·특가 기준이 사용자 설정이라 빌드 시점에 굳힐 수 없다.
   판정식은 scanner.py 의 deal_tier()/deal_score() 와 같은 규칙이며,
   한쪽을 고치면 반드시 다른 쪽도 같이 고쳐야 한다.
   ══════════════════════════════════════════════════════════ */
'use strict';

const SETTINGS_KEY = 'fds.settings.v1';
const DAY = ['일', '월', '화', '수', '목', '금', '토'];

/* ── 상태 ─────────────────────────────────────────────── */
const S = {
  data: null,
  err: null,
  settings: null,
  tab: 'home',
  view: null,          // {name:'list'|'analysis', ...} — 탭 위에 얹히는 화면
  detail: null,        // 열려 있는 상세 offer
  range: 30,           // 그래프 구간(일)
  origin: 'all',       // 출발지 칩
  listFilter: null,    // 전체 특가 리스트 필터
  weekendSpan: 'all',
};

/* ── 유틸 ─────────────────────────────────────────────── */
const $ = (sel, root) => (root || document).querySelector(sel);
const won = n => (n == null ? '—' : Number(n).toLocaleString('ko-KR'));
const esc = t => String(t == null ? '' : t)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const md = d => (d || '').slice(5).replace('-', '/');
const dow = d => { const t = new Date(d + 'T00:00:00'); return DAY[t.getDay()] || ''; };
const leaveTxt = v => (v == null ? '—' : `연차 ${Number(v) % 1 ? v : Math.round(v)}일`);

function defaultSettings(data) {
  const acc = Object.assign({}, data.access_cost_default || {});
  return {
    access: acc,
    origins: {},           // 비어 있으면 전부 ON
    minNights: 2,
    maxNights: 8,
    strongPct: (data.meta && data.meta.strong_pct_default) || 30,
    stops: 'prefer',       // prefer | direct | any
  };
}

function loadSettings(data) {
  const base = defaultSettings(data);
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return base;
    const saved = JSON.parse(raw);
    return Object.assign(base, saved, {
      access: Object.assign(base.access, saved.access || {}),
      origins: saved.origins || {},
    });
  } catch (_) { return base; }
}

function saveSettings() {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(S.settings)); } catch (_) {}
}

/* ── 출발지 ───────────────────────────────────────────── */
// SEL 은 API 가 인천/김포를 도시코드로 접어 응답한 것이라 서울권으로 묶는다.
const GROUPS = [
  { key: 'all',   label: '전체 비교', codes: null },
  { key: 'CJJ',   label: '청주',      codes: ['CJJ'] },
  { key: 'SEOUL', label: '인천·김포', codes: ['ICN', 'GMP', 'SEL'] },
  { key: 'TAE',   label: '대구',      codes: ['TAE'] },
  { key: 'ETC',   label: '기타',      codes: null, rest: true },
];
const NAMED = ['CJJ', 'ICN', 'GMP', 'SEL', 'TAE'];
const DEP_CITY = {
  CJJ: '청주', ICN: '인천', GMP: '김포', SEL: '서울', TAE: '대구', PUS: '부산',
};
const depCity = c => DEP_CITY[c] || c;
// 지방공항은 수집 단계에서 직항만 남긴다 (scanner.py DIRECT_ONLY)
const directOnly = () => ((S.data.meta && S.data.meta.direct_only) || []);
const isRegional = dep => directOnly().indexOf(dep) !== -1;
const homeCity = () => depCity((S.data && S.data.home) || 'CJJ');

const bonusOf = dep => Number(((S.data && S.data.airport_bonus) || {})[dep] || 0);
const tieBreak = () => Number((S.data && S.data.tie_break_krw) || 0);
const accessOf = dep => Number(S.settings.access[dep] || 0);
const effective = o => o.price_krw + accessOf(o.dep);
const originOn = dep => S.settings.origins[dep] !== false;

function inGroup(dep, key) {
  if (key === 'all') return true;
  const g = GROUPS.find(x => x.key === key);
  if (!g) return true;
  if (g.rest) return NAMED.indexOf(dep) === -1;
  return g.codes.indexOf(dep) !== -1;
}

/* ── 판정 (scanner.py 와 동일 규칙) ───────────────────── */
function dealTier(o) {
  if (!o.data_ok || o.discount_pct == null) return 'unknown';
  const pct = o.discount_pct, n = o.baseline_n || 0, strong = S.settings.strongPct;
  if (pct >= strong && n >= 10) return 'strong';
  if (pct >= 20 && n >= 5) return 'deal';
  if (pct >= 10 && n >= 3) return 'candidate';
  if (pct >= strong) return 'candidate';
  return 'normal';
}
const TIER_LABEL = {
  strong: '🔥 강력 특가', deal: '🟠 특가',
  candidate: '🟡 특가 후보', normal: '⚪ 일반', unknown: '비교 불가',
};
// 이모지 없는 판. 앞에 순위 아이콘이 붙는 자리에서 쓴다.
const TIER_TEXT = {
  strong: '강력 특가', deal: '특가',
  candidate: '특가 후보', normal: '일반', unknown: '비교 불가',
};
const TIER_RANK = { strong: 0, deal: 1, candidate: 2, normal: 3, unknown: 4 };

function dealScore(o) {
  if (o.discount_pct == null) return 0;
  const strong = S.settings.strongPct;
  let s = Math.max(0, Math.min(o.discount_pct / Math.max(strong, 1), 1)) * 40;

  if (o.low_all) {
    const gap = (o.price_krw - o.low_all) / o.low_all;
    s += Math.max(0, 1 - gap / 0.30) * 15;
  }
  const base = (S.data.region_base || {})[o.region] || 300000;
  s += Math.max(0, Math.min((base - effective(o)) / base, 0.5)) / 0.5 * 15;

  s += o.stops === 0 ? 10 : (o.stops === 1 ? 5 : 0);
  s += bonusOf(o.dep);          // 편의성. 표시되는 실부담가는 건드리지 않는다
  if (o.change === 'new') s += 5;
  if (o.change === 'down') s += 7;
  if (o.weekend_trip) s += 8;

  const mult = { '높음': 1, '보통': 0.9, '낮음': 0.75 }[o.confidence] || 0.55;
  if (S.settings.stops === 'direct' && o.stops !== 0) return 0;
  if (S.settings.stops === 'one' && o.stops > 1) return 0;
  if (S.settings.stops === 'prefer' && o.stops > 1) s *= 0.8;
  return Math.round(Math.min(s * mult, 100));
}

/* 에러페어 "의심" — 확정이 아니라 사람이 확인할 후보를 올린다 */
function errorFareFlags(o) {
  const f = [];
  if (o.discount_pct != null && o.discount_pct >= 50) f.push('평균 대비 50% 이상 하락');
  if ((o.baseline_n || 0) >= 10) f.push(`표본 ${o.baseline_n}건 확보`);
  if (o.low_all && o.price_krw < o.low_all * 0.85) f.push('추적기간 최저보다 15% 이상 낮음');
  if (o.change === 'down' && o.delta && o.baseline &&
      Math.abs(o.delta) / o.baseline >= 0.25) f.push('하루 만에 25% 이상 급락');
  if (o.change === 'new' && o.discount_pct >= 45) f.push('신규 등장 + 대폭 저가');
  return f;
}
function isErrorFare(o) {
  if (!o.data_ok || o.discount_pct == null) return false;
  if (o.discount_pct < 50) return false;
  if ((o.baseline_n || 0) < 10) return false;
  return true;
}
function errorConfidence(o) {
  const n = errorFareFlags(o).length;
  return n >= 4 ? '높음' : (n >= 3 ? '보통' : '낮음');
}

/* ── 데이터 파생 ──────────────────────────────────────── */
function visibleOffers() {
  const st = S.settings;
  return S.data.offers.filter(o =>
    originOn(o.dep) &&
    o.nights >= st.minNights && o.nights <= st.maxNights &&
    (st.stops !== 'direct' || o.stops === 0) &&
    (st.stops !== 'one' || o.stops == null || o.stops <= 1));
}
function homeOffers() {
  return visibleOffers().filter(o => inGroup(o.dep, S.origin));
}
function ranked(list) {
  const home = (S.data && S.data.home) || 'CJJ';
  return list.slice().sort((a, b) => {
    const t = TIER_RANK[dealTier(a)] - TIER_RANK[dealTier(b)];
    if (t) return t;
    // 실부담가가 사실상 같으면 집 앞 공항을 위로. 이동시간·주차·스트레스.
    const gap = effective(a) - effective(b);
    if (Math.abs(gap) <= tieBreak() && (a.dep === home) !== (b.dep === home)) {
      return a.dep === home ? -1 : 1;
    }
    const s = dealScore(b) - dealScore(a);
    if (s) return s;
    return gap;
  });
}
const cheapest = list =>
  list.slice().sort((a, b) => effective(a) - effective(b))[0];

/* ── 조각 렌더 ────────────────────────────────────────── */
function cmpHTML(o) {
  if (o.diff_krw == null) return '';
  if (o.diff_krw > 0) {
    return `<div class="cmp-line is-down"><span class="t">평균보다 ${won(o.diff_krw)}원 저렴</span>
      <span class="p">▼ ${Math.round(o.discount_pct)}%</span></div>`;
  }
  if (o.diff_krw < 0) {
    return `<div class="cmp-line is-up"><span class="t">평균보다 ${won(-o.diff_krw)}원 비쌈</span>
      <span class="p">▲ ${Math.round(-o.discount_pct)}%</span></div>`;
  }
  return '<div class="cmp-line is-flat"><span class="t">평균과 같음</span></div>';
}

function badgesHTML(o) {
  const t = dealTier(o), b = [];
  if (t === 'unknown') {
    // "비교 불가 / 표본 0 / 비교할 표본 없음" 을 세 번 적지 않는다.
    b.push(`<span class="bg">${esc(o.data_note || '비교할 표본 없음')} · 가격만 참고</span>`);
  } else {
    b.push(`<span class="bg ${t}">${TIER_LABEL[t]}</span>`);
    b.push(`<span class="bg">표본 ${o.baseline_n || 0} · 신뢰도 ${esc(o.confidence || '참고')}</span>`);
  }
  if (o.weekend_trip) b.push(`<span class="bg pri">주말 · ${leaveTxt(o.annual_leave)}</span>`);
  if (o.holiday) b.push(`<span class="bg pri">${esc(o.holiday)}</span>`);
  if (o.change === 'new') b.push('<span class="bg pri">🆕 신규</span>');
  if (o.change === 'down' && o.delta) b.push(`<span class="bg down">📉 ${won(o.delta)}</span>`);
  if (o.change === 'up' && o.delta) b.push(`<span class="bg up">📈 +${won(o.delta)}</span>`);
  // 표본이 없으면 "최저"라는 말이 성립하지 않는다. 그 하나가 곧 최저일 뿐이다.
  if (o.low_all && o.price_krw <= o.low_all && (o.baseline_n || 0) >= 3) {
    b.push('<span class="bg down">추적 기간 최저</span>');
  }
  if (o.baseline_tier && o.baseline_tier.indexOf('누적') !== -1) {
    b.push(`<span class="bg">${esc(o.baseline_tier.split(' · ')[1])} 기준</span>`);
  }
  return `<div class="badges">${b.join('')}</div>`;
}

const stopTxt = s => (s === 0 ? '직항' : (s === 1 ? '1회 환승' : (s == null ? '환승 정보 없음' : `${s}회 환승`)));

function heroHTML(o, rank) {
  const acc = accessOf(o.dep);
  return `<button class="hero" data-open="${esc(o.id)}">
    <span class="rank">${o.data_ok
      ? `${rank === 1 ? '🥇' : '🏅'} ${esc(TIER_TEXT[dealTier(o)])}`
      : '💰 현재 최저가'}</span>
    <div class="route">${esc(depCity(o.dep))} <span style="color:var(--tx3)">→</span> ${esc(o.city)}</div>
    <div class="codes">${esc(o.dep)} → ${esc(o.arr)} · ${esc(o.airline_kr || o.airline)} · ${stopTxt(o.stops)}</div>
    <div class="when"><b>${md(o.depart_date)} ${dow(o.depart_date)}</b> → <b>${md(o.return_date)} ${dow(o.return_date)}</b></div>
    <div class="meta">${o.nights}박 ${o.nights + 1}일 · ${leaveTxt(o.annual_leave)}</div>
    <div class="grid">
      <div><div class="k">항공권</div><div class="v">${won(o.price_krw)}원</div></div>
      <div><div class="k">${acc ? `${esc(homeCity())} → ${esc(depCity(o.dep))} 이동비` : '공항 이동비'}</div>
        <div class="v">${won(acc)}원${acc ? '' : ' <span style="font-size:11px;color:var(--tx3)">집 앞</span>'}</div></div>
      <div class="total"><div class="k">실부담가</div><div class="v">${won(effective(o))}원</div></div>
      ${o.baseline
        ? `<div><div class="k">비교 기준가</div><div class="v">${won(o.baseline)}원</div></div>`
        : `<div><div class="k">비교 기준가</div>
             <div class="v" style="font-size:12.5px;font-family:var(--sans);color:var(--tx3)">
             표본 없음</div></div>`}
      <div class="cmp">${cmpHTML(o)}</div>
    </div>
    ${badgesHTML(o)}
    <span class="cta">항공권 확인</span>
  </button>`;
}

function cardHTML(o, rank) {
  const acc = accessOf(o.dep);
  const rk = rank ? `<span class="rk r${rank}">${rank}</span>` : '';
  return `<button class="cd" data-open="${esc(o.id)}">
    <div class="top">${rk}
      <div class="ttl">
        <div class="route">${esc(depCity(o.dep))} → ${esc(o.city)}</div>
        <div class="sub">${esc(o.dep)}→${esc(o.arr)} · ${md(o.depart_date)}(${dow(o.depart_date)}) → ${md(o.return_date)}(${dow(o.return_date)}) · ${o.nights}박 · ${stopTxt(o.stops)}</div>
      </div>
      <div class="price"><div class="v">${won(effective(o))}</div>
        <div class="k">실부담${acc ? ` · 이동 ${won(acc)}` : ''}</div></div>
    </div>
    <div class="foot">${cmpHTML(o)}</div>
    ${badgesHTML(o)}
  </button>`;
}

/* ── 화면: 홈 ─────────────────────────────────────────── */
function viewHome() {
  const pool = homeOffers();
  const ok = pool.filter(o => o.data_ok);
  const top = ranked(ok).slice(0, 5);
  const strong = ok.filter(o => dealTier(o) === 'strong');
  const st = S.data.stats || {};

  let deals;
  if (!pool.length) {
    deals = emptyBlock('조건에 맞는 항공권이 없습니다',
      '설정에서 출발지나 여행 기간 범위를 넓혀 보세요.');
  } else if (!top.length) {
    deals = emptyBlock('비교 가능한 항공권이 없습니다',
      '표본이 모자라 평균가를 만들지 못했습니다. 며칠 더 쌓이면 판정이 살아납니다.');
  } else if (!strong.length) {
    const c = cheapest(ok);
    const r = (S.data.routes || {})[`${c.dep}-${c.arr}`] || {};
    deals = `<div class="note hot"><b>🔥 오늘 강력 특가가 없습니다</b>
        <p>기준(평균 대비 ${S.settings.strongPct}% 이상 저렴 · 표본 10건 이상)을 넘는 항공권이 없습니다.
        지금 가장 저렴한 항공권은 아래와 같습니다.</p></div>
      <div style="margin-top:10px">${heroHTML(c, 1)}</div>
      <div class="panel">
        <div class="kv"><span class="k">현재 실부담가</span><span class="v">${won(effective(c))}원</span></div>
        <div class="kv"><span class="k">최근 30일 최저</span><span class="v">${won(r.low30)}원</span></div>
        <div class="kv"><span class="k">노선 평균가</span><span class="v">${won(r.avg)}원</span></div>
        <div class="kv"><span class="k">비교 기준가</span><span class="v">${won(c.baseline)}원</span></div>
        ${r.low30 && c.price_krw > r.low30
          ? `<div class="kv"><span class="k">30일 최저 대비</span><span class="v is-up">+${won(c.price_krw - r.low30)}원</span></div>`
          : ''}
      </div>` +
      lowList(ok.filter(o => o.id !== c.id), 3, '💰 저가 TOP 3',
              '실부담가 낮은 순 · 등급 무관') +
      (top.length > 1 ? `<div class="sec"><div class="sec-hd"><div><h2>그다음으로 볼 만한 것</h2></div></div>
        <div class="list two">${top.slice(1, 5).map((o, i) => cardHTML(o, i + 2)).join('')}</div></div>` : '');
  } else {
    deals = `<div class="top-grid">${heroHTML(top[0], 1)}
      <div class="list">${top.slice(1).map((o, i) => cardHTML(o, i + 2)).join('')}</div></div>`;
  }

  return `${headerHTML()}${chipsHTML()}
  <div class="wrap">
    <section class="sec">
      <div class="sec-hd">
        <div><h2>🔥 오늘의 강력 특가</h2>
          <p>청주 기준 이동비 포함 실부담가 순</p></div>
        <button class="more" data-view="list">전체 보기 →</button>
      </div>
      ${deals}
    </section>

    <section class="sec">
      <div class="sec-hd"><div><h2>오늘 변화</h2>
        <p>어제 스캔 대비</p></div></div>
      <div class="tiles">
        <button class="tile new" data-list="new"><div class="k">🆕 신규 특가</div>
          <div class="v">${st.new || 0}</div></button>
        <button class="tile dn" data-list="down"><div class="k">📉 가격 하락</div>
          <div class="v">${st.down || 0}</div></button>
        <button class="tile hot" data-list="strong"><div class="k">🔥 강력 특가</div>
          <div class="v">${strong.length}</div></button>
        <button class="tile mon" data-list="all"><div class="k">👀 모니터링</div>
          <div class="v">${pool.length}</div></button>
      </div>
    </section>

    ${S.origin === 'CJJ' ? cjjSection(ok) : ''}

    <section class="sec">
      <button class="btn-line" data-view="analysis">상세 분석 열기 (노선별·표본·진단)</button>
    </section>
    ${footerHTML()}
  </div>`;
}

/* ── 청주 전용 화면 ───────────────────────────────────────
   운항 노선 / 가격 데이터 / 특가를 절대 섞지 않는다.
   가격이 없는 노선은 0원이나 "-" 가 아니라 "가격 데이터 부족"으로 적는다. */
function cjjSection(pool) {
  const c = (S.data.cjj) || {};
  const cfg = c.config || {};
  const st = c.status || [];
  const total = Object.keys(cfg).length;
  if (!total) return '';

  const priced = st.filter(x => x.price_status === 'available');
  const missing = st.filter(x => x.price_status === 'missing');
  const errored = st.filter(x => x.price_status === 'error');
  const deals = pool.filter(o => ['strong', 'deal'].includes(dealTier(o)));

  // 목적지별 오늘 최저 실부담가
  const best = {};
  pool.forEach(o => {
    if (!best[o.arr] || effective(o) < effective(best[o.arr])) best[o.arr] = o;
  });

  // 국가별 묶기 (config 순서 유지 → 일본·대만·베트남… 순)
  const byCountry = [];
  Object.keys(cfg).forEach(code => {
    const info = cfg[code];
    let g = byCountry.find(x => x.country === info.country);
    if (!g) { g = { country: info.country, flag: info.flag || '', rows: [] }; byCountry.push(g); }
    const row = st.find(x => x.destination === code);
    g.rows.push({ code, info, row, offer: best[code] || null });
  });
  byCountry.forEach(g => g.rows.sort((a, b) =>
    (a.offer ? effective(a.offer) : Infinity) - (b.offer ? effective(b.offer) : Infinity)));

  const groups = byCountry.map(g => `<div class="panel">
      <h4>${esc(g.flag)} ${esc(g.country)}</h4>
      ${g.rows.map(r => {
        if (r.offer) {
          return `<button class="kv cjjrow" data-open="${esc(r.offer.id)}">
            <span class="k" style="color:var(--tx);font-weight:700">${esc(r.info.city)}
              <span style="font-family:var(--mono);color:var(--tx3);font-weight:600">${esc(r.code)}</span></span>
            <span class="v">${won(effective(r.offer))}원
              ${r.offer.discount_pct > 0
                ? `<span class="is-down" style="font-size:11.5px">▼${Math.round(r.offer.discount_pct)}%</span>`
                : ''}</span></button>`;
        }
        const why = !r.row ? '오늘 조회 대상 아님'
          : (r.row.price_status === 'error' ? '조회 오류' : '가격 데이터 부족');
        return `<div class="kv">
          <span class="k" style="color:var(--tx2);font-weight:700">${esc(r.info.city)}
            <span style="font-family:var(--mono);color:var(--tx3);font-weight:600">${esc(r.code)}</span></span>
          <span class="v" style="font-family:var(--sans);font-size:12px;color:var(--tx3);font-weight:600;text-align:right">
            ${esc(why)}<br><span style="font-size:11px">직항 운항 노선 · 최근 가격 없음</span></span></div>`;
      }).join('')}
    </div>`).join('');

  return `<section class="sec">
    <div class="sec-hd"><div><h2>🏠 청주공항 직항 스캐너</h2>
      <p>운항 노선과 가격 데이터는 별개입니다. 가격이 없다고 노선이 없어진 게 아닙니다.</p></div></div>
    <div class="strip">
      <div><div class="k">직항 목적지</div><div class="v num">${total}</div></div>
      <div><div class="k">오늘 가격 확인</div><div class="v num g">${priced.length}</div></div>
      <div><div class="k">가격 데이터 부족</div><div class="v num zero">${missing.length + errored.length}</div></div>
    </div>
    ${groups}
  </section>`;
}

/* 특가가 없어도 빈손으로 두지 않는다. 실부담가 낮은 순으로 몇 개는 정리해 준다. */
function lowList(pool, count, title, desc) {
  const items = pool.slice()
    .sort((a, b) => effective(a) - effective(b))
    .slice(0, count);
  if (!items.length) return '';
  return `<section class="sec"><div class="sec-hd"><div>
      <h2>${title}</h2><p>${esc(desc)}</p></div></div>
    <div class="list two">${items.map((o, i) => cardHTML(o, i + 1)).join('')}</div></section>`;
}

function emptyBlock(title, body) {
  return `<div class="note warn"><b>${esc(title)}</b><p>${esc(body)}</p></div>`;
}

function headerHTML() {
  const m = S.data.meta || {};
  return `<header class="hd"><div class="wrap"><div class="row">
    <img class="mark" src="icon.svg" alt="" width="34" height="34">
    <div class="grow"><h1>항공권 데일리 스캐너</h1>
      <div class="upd">마지막 업데이트 <b>${esc(m.ts || '—')}</b></div></div>
    <button class="iconbtn" data-reload aria-label="새로고침">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" width="20" height="20">
        <path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v6h-6"/></svg>
    </button></div></div></header>`;
}

function chipsHTML() {
  return `<div class="chips" role="group" aria-label="출발 공항">` +
    GROUPS.map(g => `<button class="chip" data-origin="${g.key}"
      aria-pressed="${S.origin === g.key}">${esc(g.label)}</button>`).join('') +
    `</div>`;
}

function footerHTML() {
  const m = S.data.meta || {};
  return `<footer>
    수집 ${m.count || 0}건 · 검색 ${m.used || 0}/${m.cap || 0}<br>
    소스 Travelpayouts 캐시 · 실시간 확정가가 아닙니다. 예약 전 판매처에서 확인하세요.<br>
    GitHub Actions 마지막 실행 ${esc(m.ts || '—')}
  </footer>`;
}

/* ── 화면: 전체 특가 리스트 ───────────────────────────── */
const LIST_FILTERS = [
  { k: 'all', l: '전체' }, { k: 'strong', l: '🔥 강력특가' },
  { k: 'deal', l: '🟠 특가' }, { k: 'new', l: '🆕 신규' },
  { k: 'down', l: '📉 하락' }, { k: 'direct', l: '직항만' },
  { k: 'weekend', l: '주말여행' },
];

function viewList() {
  const f = S.listFilter || 'all';
  let pool = homeOffers();
  if (f === 'strong') pool = pool.filter(o => dealTier(o) === 'strong');
  else if (f === 'deal') pool = pool.filter(o => ['strong', 'deal'].includes(dealTier(o)));
  else if (f === 'new') pool = pool.filter(o => o.change === 'new');
  else if (f === 'down') pool = pool.filter(o => o.change === 'down');
  else if (f === 'direct') pool = pool.filter(o => o.stops === 0);
  else if (f === 'weekend') pool = pool.filter(o => o.weekend_trip);

  const list = ranked(pool).slice(0, 120);
  return `${subHeader('전체 특가')}${chipsHTML()}
  <div class="wrap">
    <div class="filters"><div class="frow">
      ${LIST_FILTERS.map(x => `<button class="fchip" data-list="${x.k}"
        aria-pressed="${f === x.k}">${esc(x.l)}</button>`).join('')}
    </div></div>
    <p style="font-size:12px;color:var(--tx3);margin:2px 0 12px;font-weight:600">
      ${list.length}건 · 실부담가(항공권 + 청주 기준 이동비) 순</p>
    ${list.length
      ? `<div class="list two">${list.map(o => cardHTML(o)).join('')}</div>`
      : emptyBlock('조건에 맞는 항공권이 없습니다', '필터를 넓혀 보세요.')}
    ${footerHTML()}
  </div>`;
}

function subHeader(title) {
  return `<header class="hd"><div class="wrap"><div class="row">
    <button class="iconbtn" data-back aria-label="뒤로">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round" width="20" height="20">
        <path d="M15 18l-6-6 6-6"/></svg></button>
    <div class="grow"><h1>${esc(title)}</h1></div></div></div></header>`;
}

/* ── 화면: 주말 ───────────────────────────────────────── */
function weekendSpans() {
  const now = new Date();
  const sat = new Date(now); sat.setDate(now.getDate() + ((6 - now.getDay() + 7) % 7));
  const iso = d => d.toISOString().slice(0, 10);
  const next = new Date(sat); next.setDate(sat.getDate() + 7);
  const end1 = new Date(sat); end1.setDate(sat.getDate() + 2);
  const end2 = new Date(next); end2.setDate(next.getDate() + 2);
  return [
    { k: 'all', l: '전체' },
    { k: 'this', l: '이번 주말', a: iso(sat), b: iso(end1) },
    { k: 'next', l: '다음 주말', a: iso(next), b: iso(end2) },
    { k: 'm9', l: '9월', pre: '-09-' },
    { k: 'm10', l: '10월', pre: '-10-' },
    { k: 'hol', l: '연휴', holiday: true },
  ];
}

function viewWeekend() {
  const spans = weekendSpans();
  const sp = spans.find(x => x.k === S.weekendSpan) || spans[0];
  let pool = visibleOffers().filter(o => o.weekend_trip && o.data_ok);
  if (sp.a) pool = pool.filter(o => o.depart_date >= sp.a && o.depart_date <= sp.b);
  if (sp.pre) pool = pool.filter(o => o.depart_date.indexOf(sp.pre) === 4);
  if (sp.holiday) pool = pool.filter(o => o.holiday);

  // 연차 적은 순 → 점수 순
  pool.sort((a, b) => (a.annual_leave - b.annual_leave) || (dealScore(b) - dealScore(a)));

  const buckets = [
    { v: 0, l: '연차 0일', d: '금요일 밤 출발 등 — 휴가를 쓰지 않고 다녀올 수 있는 일정' },
    { v: 0.5, l: '연차 0.5일', d: '반차 한 번' },
    { v: 1, l: '연차 1일', d: '하루만 쓰면 되는 일정' },
  ];
  let body = '';
  buckets.forEach(b => {
    const items = pool.filter(o => o.annual_leave === b.v);
    if (!items.length) return;
    body += `<section class="sec"><div class="sec-hd"><div>
      <h2>📅 ${b.l}</h2><p>${esc(b.d)}</p></div></div>
      <div class="list two">${items.slice(0, 12).map(o => cardHTML(o)).join('')}</div></section>`;
  });
  if (!body) {
    // 조건을 만족하는 게 없어도 빈손으로 두지 않는다.
    // 주말이 걸리는 일정 중 저렴한 것부터 몇 개 보여준다.
    let near = visibleOffers().filter(o => o.weekend && o.data_ok);
    if (sp.a) near = near.filter(o => o.depart_date >= sp.a && o.depart_date <= sp.b);
    if (sp.pre) near = near.filter(o => o.depart_date.indexOf(sp.pre) === 4);
    if (sp.holiday) near = near.filter(o => o.holiday);
    near.sort((a, b) => (a.annual_leave - b.annual_leave) || (effective(a) - effective(b)));

    body = `<section class="sec">${emptyBlock(
      '이 구간에 연차 1일 이하 일정이 없습니다',
      '주말이 걸리면서 연차가 0~1일인 조합만 이 탭에 올립니다.')}</section>`
      + lowList(near.slice(0, 12), 3, '💰 주말 낀 일정 중 저가 3',
                '연차는 더 들지만 주말이 걸리는 일정입니다');
  }

  return `${plainHeader('주말여행', '연차를 거의 쓰지 않고 다녀올 수 있는 일정만')}
  <div class="wrap">
    <div class="filters"><div class="frow">
      ${spans.map(x => `<button class="fchip" data-wspan="${x.k}"
        aria-pressed="${sp.k === x.k}">${esc(x.l)}</button>`).join('')}
    </div></div>
    ${body}${footerHTML()}
  </div>`;
}

function plainHeader(title, sub) {
  return `<header class="hd"><div class="wrap"><div class="row">
    <div class="grow"><h1>${esc(title)}</h1>
      <div class="upd">${esc(sub)}</div></div></div></div></header>`;
}

/* ── 화면: 스위스 ─────────────────────────────────────── */
const SWISS_CITY = { ZRH: '취리히', GVA: '제네바', BSL: '바젤' };

function viewSwiss() {
  // 여행 기간 설정은 일부러 적용하지 않는다. 유럽은 캐시가 얇아 근거리용
  // 박수 범위를 씌우면 있는 것마저 사라진다. 출발지 ON/OFF 는 존중한다.
  const all = S.data.offers.filter(o =>
    ['ZRH', 'GVA', 'BSL'].includes(o.arr) && originOn(o.dep));

  if (!all.length) {
    return `${plainHeader('스위스', '취리히 우선 · 1회 환승 허용')}
      <div class="wrap">${swissDiag()}${swissNote()}${footerHTML()}</div>`;
  }

  // 1회 환승까지 허용. 가격 → 환승 → 여행기간 순.
  const pool = all.filter(o => o.stops == null || o.stops <= 1);
  const byPrice = pool.slice().sort((a, b) =>
    effective(a) - effective(b) ||
    (a.stops || 0) - (b.stops || 0) ||
    a.nights - b.nights);

  const strong = byPrice.filter(o => dealTier(o) === 'strong');
  const hero = strong.length
    ? (strong.find(o => o.arr === 'ZRH') || strong[0])
    : byPrice[0];

  // 건수가 적으면 쪼개지 않는다. 3건을 세 섹션에 나눠 담으면 같은 항공권을
  // 세 번 보여주게 된다. 얇을 땐 한 목록으로, 두꺼울 때만 환승별로 나눈다.
  const THIN = 5;
  const thin = byPrice.length <= THIN;

  let head, lowTop, byStops;

  if (strong.length) {
    head = `<section class="sec"><div class="sec-hd"><div>
        <h2>🏔 오늘 가장 좋은 옵션</h2><p>1회 환승까지 허용 · 취리히 우선</p></div></div>
        ${heroHTML(hero, 1)}</section>`;
    lowTop = lowList(byPrice.filter(o => o.id !== hero.id), 3,
                     '💰 저가 TOP 3', '실부담가 낮은 순 · 등급 무관');
  } else {
    head = `<section class="sec">
        <div class="note hot"><b>현재 강력 특가 없음</b>
          <p>가격만 보고 저렴한 순으로 정리했습니다. 스위스는 캐시 표본이
          얇아 "평균 대비 몇 %" 판정이 서지 않는 경우가 많습니다.</p></div>
        <div style="margin-top:10px">${heroHTML(hero, 1)}</div></section>`;
    // hero 가 이미 최저가이므로 그다음 것들만 이어 붙인다
    lowTop = lowList(byPrice.filter(o => o.id !== hero.id), 3,
                     '💰 그다음으로 저렴한 것', '실부담가 낮은 순 · 등급 무관');
  }

  if (thin) {
    // 얇을 땐 환승별로 또 나누지 않고, 카드마다 직항/환승만 표기한다
    byStops = '';
  } else {
    const shown = { [hero.id]: 1 };
    byPrice.filter(o => o.id !== hero.id).slice(0, 3).forEach(o => { shown[o.id] = 1; });
    const rest = byPrice.filter(o => !shown[o.id]);
    const direct = rest.filter(o => o.stops === 0);
    const one = rest.filter(o => o.stops === 1);
    byStops = [
      direct.length ? `<section class="sec"><div class="sec-hd"><div>
          <h2>🛫 직항</h2><p>위에 안 나온 ${direct.length}건</p></div></div>
          <div class="list two">${direct.slice(0, 8).map(o => cardHTML(o)).join('')}</div></section>` : '',
      one.length ? `<section class="sec"><div class="sec-hd"><div>
          <h2>✈️ 1회 환승</h2><p>위에 안 나온 ${one.length}건 · 총 여행시간과 환승 대기시간은 소스에 없습니다</p></div></div>
          <div class="list two">${one.slice(0, 8).map(o => cardHTML(o)).join('')}</div></section>` : '',
    ].join('');
  }

  // 도시별 최저 — 가격이 없는 도시도 목록에서 지우지 않는다
  const cityRows = Object.keys(SWISS_CITY).map(code => {
    const cands = pool.filter(o => o.arr === code);
    const best = cands.sort((a, b) => effective(a) - effective(b))[0];
    if (best) {
      return `<button class="kv cjjrow" data-open="${esc(best.id)}">
        <span class="k" style="color:var(--tx);font-weight:700">${esc(SWISS_CITY[code])}
          <span style="font-family:var(--mono);color:var(--tx3);font-weight:600">${code}</span></span>
        <span class="v">${won(effective(best))}원
          <span style="color:var(--tx3);font-size:11.5px">${stopTxt(best.stops)}</span></span></button>`;
    }
    const raw = ((S.data.meta && S.data.meta.raw_counts) || {});
    const got = Object.keys(raw).some(k => k.endsWith('-' + code) && raw[k]);
    return `<div class="kv">
      <span class="k" style="color:var(--tx2);font-weight:700">${esc(SWISS_CITY[code])}
        <span style="font-family:var(--mono);color:var(--tx3);font-weight:600">${code}</span></span>
      <span class="v" style="font-family:var(--sans);font-size:12px;color:var(--tx3);font-weight:600;text-align:right">
        가격 데이터 부족<br><span style="font-size:11px">${got ? '조회는 됐으나 조건에 맞는 편 없음' : '응답 자체가 빔'}</span></span></div>`;
  }).join('');

  // 가격 위치 (hero 기준)
  const r = (S.data.routes || {})[`${hero.dep}-${hero.arr}`] || {};
  const wait = r.low30 && hero.price_krw > r.low30;
  const pos = `<div class="panel"><h4>가격 위치 · ${esc(SWISS_CITY[hero.arr] || hero.arr)}</h4>
    <div class="kv"><span class="k">현재 항공권</span><span class="v">${won(hero.price_krw)}원</span></div>
    <div class="kv"><span class="k">최근 30일 최저</span><span class="v">${won(r.low30)}원</span></div>
    <div class="kv"><span class="k">추적 기간 최저</span><span class="v">${won(r.low_all)}원</span></div>
    <div class="kv"><span class="k">노선 평균가</span><span class="v">${won(r.avg)}원</span></div>
    <div class="kv"><span class="k">표본</span><span class="v">${r.n || 0}건 · 신뢰도 ${esc(hero.confidence || '참고')}</span></div>
    ${(r.series || []).length >= 3
      ? `<p style="margin:10px 0 0;font-size:13px;font-weight:700;color:${wait ? 'var(--warn)' : 'var(--down)'}">
         ${wait ? '조금 더 기다려볼 만함' : '최근 구간에서 낮은 편'}</p>`
      : `<p style="margin:10px 0 0;font-size:12.5px;color:var(--tx3);font-weight:600">
         기록이 ${(r.series || []).length || 1}일치뿐이라 아직 "싸다/비싸다"를 말할 수
         없습니다. 위 세 값이 같은 것도 그 때문입니다 — 오늘 가격이 곧 최저이자
         최고입니다. 며칠 쌓이면 30일 최저가 의미를 갖습니다.</p>`}
  </div>`;

  return `${plainHeader('스위스', '취리히 우선 · 1회 환승 허용')}
  <div class="wrap">
    ${head}${lowTop}${byStops}
    <section class="sec"><div class="sec-hd"><div>
      <h2>도시별 최저</h2><p>가격이 없어도 노선은 목록에 남깁니다</p></div></div>
      <div class="panel">${cityRows}</div></section>
    ${pos}${swissNote()}${footerHTML()}</div>`;
}

function swissNote() {
  return `<div class="note" style="margin-top:16px"><b>이 소스로 알 수 없는 것</b>
    <p>Travelpayouts 캘린더 응답에는 총 여행시간과 환승 대기시간이 들어 있지
    않습니다. 그래서 그 두 가지는 정렬에 넣지 못했고, 화면에도 지어내지
    않았습니다. 실제 소요시간은 예약 페이지에서 확인하세요.</p></div>`;
}

function swissDiag() {
  const raw = (S.data.meta && S.data.meta.raw_counts) || {};
  const drops = (S.data.meta && S.data.meta.drops) || {};
  const rows = Object.keys(raw).filter(k => /-(ZRH|GVA|BSL)$/.test(k)).sort()
    .map(k => {
      const d = drops[k] || {};
      const why = Object.keys(d).length
        ? Object.entries(d).sort((a, b) => b[1] - a[1]).slice(0, 2)
            .map(([a, b]) => `${a} ${b}건`).join(', ')
        : (raw[k] ? '—' : '응답 자체가 빔');
      return `<div class="kv"><span class="k">${esc(k)}</span>
        <span class="v">원본 ${raw[k]}건 · ${esc(why)}</span></div>`;
    }).join('');
  return `<section class="sec">
    <div class="note warn"><b>스위스 항공권이 없습니다</b>
      <p>조회 실패가 아니라 소스(Travelpayouts) 캐시에 한국→스위스 왕복이 거의 없습니다.
      노선별 실제 응답은 아래와 같습니다.</p></div>
    <div class="panel"><h4>🔍 노선별 응답 진단</h4>${rows || '<p>진단 정보 없음</p>'}</div>
  </section>`;
}

/* ── 화면: 에러페어 ───────────────────────────────────── */
function viewError() {
  const pool = visibleOffers().filter(isErrorFare)
    .sort((a, b) => b.discount_pct - a.discount_pct);

  const body = pool.length
    ? `<div class="list two">${pool.slice(0, 30).map(o => {
        const r = (S.data.routes || {})[`${o.dep}-${o.arr}`] || {};
        return `<button class="cd" data-open="${esc(o.id)}">
          <div class="top"><span class="rk r1">⚡</span>
            <div class="ttl"><div class="route">${esc(depCity(o.dep))} → ${esc(o.city)}</div>
              <div class="sub">${esc(o.dep)}→${esc(o.arr)} · ${md(o.depart_date)} → ${md(o.return_date)} · ${o.nights}박 · ${stopTxt(o.stops)}</div></div>
            <div class="price"><div class="v">${won(effective(o))}</div>
              <div class="k">실부담</div></div></div>
          <div class="foot">${cmpHTML(o)}</div>
          <div class="badges">
            <span class="bg strong">⚡ 에러페어 의심</span>
            <span class="bg">평균 ${won(r.avg || o.baseline)}원</span>
            <span class="bg">표본 ${o.baseline_n}</span>
            <span class="bg">신뢰도 ${esc(errorConfidence(o))}</span>
          </div></button>`;
      }).join('')}</div>`
    : emptyBlock('지금 에러페어 의심 건이 없습니다',
        '평균 대비 50% 이상 저렴하면서 표본이 10건 이상인 항공권만 여기 올립니다.');

  // 의심 건이 없어도 "그럼 오늘 제일 많이 빠진 건 뭔데"에는 답한다.
  const steep = visibleOffers()
    .filter(o => o.data_ok && o.discount_pct != null && o.discount_pct > 0)
    .sort((a, b) => b.discount_pct - a.discount_pct)
    .slice(0, 3);
  const steepBlock = (!pool.length && steep.length)
    ? `<section class="sec"><div class="sec-hd"><div>
        <h2>📉 오늘 가장 많이 빠진 것</h2>
        <p>에러페어 기준에는 못 미치지만 할인율 상위</p></div></div>
        <div class="list two">${steep.map((o, i) => cardHTML(o, i + 1)).join('')}</div></section>`
    : '';

  return `${plainHeader('에러페어', '오류운임 "의심" 탐지 — 확정이 아닙니다')}
  <div class="wrap">
    <div class="note warn" style="margin-top:16px"><b>⚡ 의심이지 확정이 아닙니다</b>
      <p>항공사 오류운임인지 이 데이터만으로는 확정할 수 없습니다.
      캐시가 오래됐거나 특가 프로모션일 수도 있습니다. 반드시 판매처에서 직접 확인하세요.</p></div>
    <section class="sec"><div class="sec-hd"><div><h2>의심 건</h2>
      <p>평균 대비 50%+ 하락 · 표본 10건 이상</p></div></div>${body}</section>
    ${steepBlock}
    <div class="panel"><h4>판정 조건</h4>
      <div class="kv"><span class="k">필수</span><span class="v">평균 대비 50% 이상 하락</span></div>
      <div class="kv"><span class="k">필수</span><span class="v">표본 10건 이상</span></div>
      <div class="kv"><span class="k">가점</span><span class="v">추적기간 최저보다 15% 이상 낮음</span></div>
      <div class="kv"><span class="k">가점</span><span class="v">하루 만에 25% 이상 급락</span></div>
      <div class="kv"><span class="k">가점</span><span class="v">신규 등장 + 대폭 저가</span></div>
    </div>
    ${footerHTML()}</div>`;
}

/* ── 화면: 설정 ───────────────────────────────────────── */
function viewSettings() {
  const st = S.settings;
  const codes = Object.keys(S.data.access_cost_default || {});
  const seen = {};
  S.data.offers.forEach(o => { seen[o.dep] = true; });
  Object.keys(seen).forEach(c => { if (codes.indexOf(c) === -1) codes.push(c); });

  const originRows = codes.map(c => `<div class="set-row">
      <div class="lb">${esc(c)}<small>${seen[c] ? '오늘 결과 있음' : '오늘 결과 없음'}</small></div>
      <button class="sw" role="switch" data-origin-toggle="${esc(c)}"
        aria-checked="${originOn(c)}" aria-label="${esc(c)} 표시"></button>
    </div>`).join('');

  const costRows = codes.map(c => `<div class="set-row">
      <div class="lb">청주 ↔ ${esc(c)}<small>왕복 교통비 (1인)</small></div>
      <input type="number" inputmode="numeric" step="1000" min="0"
        value="${Number(st.access[c] || 0)}" data-cost="${esc(c)}"
        aria-label="${esc(c)} 왕복 교통비">
    </div>`).join('');

  return `${plainHeader('설정', '바꾸면 실부담가와 순위가 즉시 다시 계산됩니다')}
  <div class="wrap">
    <div class="panel"><h4>출발지 표시</h4>${originRows}</div>

    <div class="panel"><h4>청주 기준 왕복 교통비</h4>
      <p style="margin:0 0 6px;font-size:12px;color:var(--tx3);font-weight:600">
        실부담가 = 항공권 + 여기 값. 실제 이동수단·인원에 맞게 고치세요.</p>
      ${costRows}
    </div>

    <div class="panel"><h4>여행 기간</h4>
      <div class="set-row"><div class="lb">최소<small>박</small></div>
        <input type="number" inputmode="numeric" min="1" max="30"
          value="${st.minNights}" data-set="minNights" aria-label="최소 박수"></div>
      <div class="set-row"><div class="lb">최대<small>박</small></div>
        <input type="number" inputmode="numeric" min="1" max="30"
          value="${st.maxNights}" data-set="maxNights" aria-label="최대 박수"></div>
    </div>

    <div class="panel"><h4>강력 특가 기준</h4>
      <div class="set-row"><div class="lb">평균 대비<small>% 이상 저렴할 때 강력 특가</small></div>
        <input type="number" inputmode="numeric" min="5" max="80"
          value="${st.strongPct}" data-set="strongPct" aria-label="강력 특가 기준 퍼센트"></div>
      <p style="margin:6px 0 0;font-size:12px;color:var(--tx3);font-weight:600">
        표본 10건 이상이라는 조건은 함께 적용됩니다. 표본이 적으면 아무리 싸도
        강력 특가로 올리지 않습니다.</p>
    </div>

    <div class="panel"><h4>환승</h4>
      <div class="seg">
        ${[['prefer', '직항 우선'], ['direct', '직항만'],
           ['one', '1회 환승'], ['any', '제한 없음']]
          .map(([k, l]) => `<button data-stops="${k}"
            aria-pressed="${st.stops === k}">${l}</button>`).join('')}
      </div>
      <p style="margin:10px 0 0;font-size:12px;color:var(--tx3);font-weight:600">
        ${directOnly().length
          ? `${esc(directOnly().map(depCity).join('·'))} 출발은 이 설정과 무관하게
             <b>항상 직항만</b> 수집합니다. 환승편 가격이 섞이면 기준선까지
             오염되기 때문입니다.`
          : ''}
        서울권(인천·김포)과 스위스에만 위 설정이 적용됩니다.</p>
    </div>

    <div class="panel"><h4>표본이 얇은 노선</h4>
      <p style="margin:0;font-size:12.5px;color:var(--tx2);line-height:1.65">
        하루 표본이 ${(S.data.meta && S.data.meta.thin_sample) || 10}건 미만인
        노선은 과거 가격을 끌어와 기준선을 만듭니다.
        보관 기간은 <b>${esc(directOnly().map(depCity).join('·'))} 90일</b>,
        그 외 ${(S.data.meta && S.data.meta.thin_retention
                 && S.data.meta.thin_retention['기본']) || 30}일입니다.
        누적을 쓴 항공권에는 카드에 <b>90일 누적 기준</b> 배지가 붙습니다.</p>
      <div class="kv" style="margin-top:8px"><span class="k">오늘 누적을 쓴 버킷</span>
        <span class="v">${Object.keys((S.data.meta && S.data.meta.pooled_buckets) || {}).length}개</span></div>
    </div>

    <button class="btn-line" data-reset>설정 초기화</button>
    ${footerHTML()}
  </div>`;
}

/* ── 화면: 상세 분석 (홈에서 내린 것들) ───────────────── */
function viewAnalysis() {
  const routes = Object.values(S.data.routes || {})
    .sort((a, b) => (a.today_low / a.avg) - (b.today_low / b.avg));
  const rows = routes.map(r => `<div class="kv">
    <span class="k">${esc(r.city)} <span style="font-family:var(--mono)">${esc(r.dep)}→${esc(r.arr)}</span></span>
    <span class="v">${won(r.today_low)} / 평균 ${won(r.avg)} · 표본 ${r.n}</span></div>`).join('');

  const raw = (S.data.meta && S.data.meta.raw_counts) || {};
  const drops = (S.data.meta && S.data.meta.drops) || {};
  const diag = Object.keys(raw).sort().map(k => {
    const d = drops[k] || {};
    const why = Object.keys(d).length
      ? Object.entries(d).sort((a, b) => b[1] - a[1]).slice(0, 2)
          .map(([a, b]) => `${a} ${b}`).join(', ') : '—';
    return `<div class="kv"><span class="k">${esc(k)}</span>
      <span class="v">원본 ${raw[k]} · ${esc(why)}</span></div>`;
  }).join('');

  const errs = (S.data.meta && S.data.meta.errors) || [];

  return `${subHeader('상세 분석')}
  <div class="wrap">
    <p style="font-size:12px;color:var(--tx3);margin:12px 0 0;font-weight:600">
      홈에서 내린 원시 분석입니다. 예약 판단이 아니라 데이터 점검용입니다.</p>
    <div class="panel"><h4>노선별 (오늘 최저 / 평균 / 표본)</h4>${rows || '<p>없음</p>'}</div>
    <div class="panel"><h4>수집 진단 (원본 건수 · 탈락 사유)</h4>${diag || '<p>없음</p>'}</div>
    <div class="panel"><h4>누적 표본으로 기준선을 세운 버킷</h4>
      ${(() => {
        const pb = (S.data.meta && S.data.meta.pooled_buckets) || {};
        const ks = Object.keys(pb).sort();
        return ks.length
          ? ks.map(k => `<div class="kv"><span class="k">${esc(k)}</span>
              <span class="v">${pb[k]}일 누적</span></div>`).join('')
          : '<p style="margin:0;font-size:13px;color:var(--tx2)">오늘은 없습니다.</p>';
      })()}</div>
    ${errs.length ? `<div class="panel"><h4>오류 ${errs.length}건</h4>
      ${errs.map(e => `<div class="kv"><span class="k">·</span><span class="v">${esc(e)}</span></div>`).join('')}</div>` : ''}
    ${footerHTML()}
  </div>`;
}

/* ── 상세 시트 ────────────────────────────────────────── */
function detailHTML(o) {
  const r = (S.data.routes || {})[`${o.dep}-${o.arr}`] || {};
  const acc = accessOf(o.dep);
  const series = pickSeries(o, r);

  return `<div class="sheet" data-sheet><div class="sheet-in" role="dialog" aria-modal="true">
    <div class="sheet-hd">
      <h3>${esc(depCity(o.dep))} → ${esc(o.city)}
        <span style="font-family:var(--mono);font-size:13px;color:var(--tx3);font-weight:700">${esc(o.dep)}→${esc(o.arr)}</span></h3>
      <button class="iconbtn" data-close aria-label="닫기">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" width="20" height="20"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button></div>

    <div class="panel">
      ${badgesHTML(o)}
      <div style="margin-top:12px">${cmpHTML(o)}</div>
    </div>

    <div class="panel"><h4>일정</h4>
      <div class="kv"><span class="k">가는 날</span><span class="v">${o.depart_date} (${dow(o.depart_date)})${o.dep_hour != null ? ` ${String(o.dep_hour).padStart(2, '0')}시대` : ''}</span></div>
      <div class="kv"><span class="k">오는 날</span><span class="v">${o.return_date} (${dow(o.return_date)})</span></div>
      <div class="kv"><span class="k">숙박</span><span class="v">${o.nights}박 ${o.nights + 1}일</span></div>
      <div class="kv"><span class="k">필요 연차</span><span class="v">${leaveTxt(o.annual_leave)}${o.night_departure ? ' · 퇴근 후 출발' : ''}</span></div>
      <div class="kv"><span class="k">항공사</span><span class="v">${esc(o.airline_kr || o.airline)}</span></div>
      <div class="kv"><span class="k">경유</span><span class="v">${stopTxt(o.stops)}</span></div>
    </div>

    <div class="panel"><h4>비용</h4>
      <div class="kv"><span class="k">항공권</span><span class="v">${won(o.price_krw)}원</span></div>
      <div class="kv"><span class="k">${acc ? `${esc(homeCity())} → ${esc(depCity(o.dep))} 왕복 이동비` : '공항 이동비 (집 앞 공항)'}</span><span class="v">${won(acc)}원</span></div>
      <div class="kv"><span class="k" style="color:var(--hot)">실부담가</span>
        <span class="v" style="color:var(--hot);font-size:16px">${won(effective(o))}원</span></div>
    </div>

    <div class="panel"><h4>가격 위치</h4>
      <div class="kv"><span class="k">오늘 최저가</span><span class="v">${won(r.today_low)}원</span></div>
      <div class="kv"><span class="k">노선 평균가</span><span class="v">${won(r.avg)}원 <span style="color:var(--tx3);font-size:11px">전 박수</span></span></div>
      <div class="kv"><span class="k">비교 기준가</span><span class="v">${won(o.baseline)}원 <span style="color:var(--tx3);font-size:11px">이 항공편 판정에 쓴 값</span></span></div>
      <div class="kv"><span class="k">최근 30일 최저</span><span class="v">${won(r.low30)}원${r.low30_date ? ` <span style="color:var(--tx3)">${md(r.low30_date)}</span>` : ''}</span></div>
      <div class="kv"><span class="k">추적 기간 최저</span><span class="v">${won(r.low_all)}원${r.low_all_date ? ` <span style="color:var(--tx3)">${md(r.low_all_date)}</span>` : ''}</span></div>
      <div class="kv"><span class="k">표본 수</span><span class="v">${o.baseline_n || 0}건 · 신뢰도 ${esc(o.confidence || '참고')}</span></div>
      <div class="kv"><span class="k">평균 산출 기준</span><span class="v">${esc(o.baseline_tier || '—')}</span></div>
    </div>

    <div class="panel"><h4>가격 변화</h4>
      ${series.pts.length > 1
        ? chartSVG(series.pts, acc) + `<div class="legend">
            <span class="a"><i></i>항공권</span>
            ${acc ? '<span class="b"><i></i>실부담가</span>' : ''}
          </div><p style="margin:8px 0 0;font-size:11.5px;color:var(--tx3);font-weight:600">
            ${esc(series.label)}</p>`
        : `<p style="margin:0;font-size:13px;color:var(--tx2)">
            아직 그래프를 그릴 만큼 기록이 쌓이지 않았습니다.
            매일 실행되면서 점이 하나씩 늘어납니다.</p>`}
      <div class="rangebtns">
        ${[7, 30, 90].map(n => `<button data-range="${n}"
          aria-pressed="${S.range === n}">${n}일</button>`).join('')}
      </div>
    </div>

    <a class="cta" href="${esc(o.link)}" target="_blank" rel="noopener">항공권 확인 →</a>
    <p style="margin:10px 0 0;font-size:11.5px;color:var(--tx3);text-align:center;font-weight:600">
      캐시 기반 참고값입니다. 판매처에서 최종 가격을 확인하세요.</p>
  </div></div>`;
}

function pickSeries(o, r) {
  const cut = new Date(Date.now() - S.range * 86400000).toISOString().slice(0, 10);
  const route = (r.series || []).filter(x => x.d >= cut);
  if (route.length > 1) return { pts: route, label: `노선 일별 최저가 · 최근 ${S.range}일` };
  const log = (o.price_log || []).filter(x => x.d >= cut);
  return { pts: log, label: `이 항공편 가격 · 최근 ${S.range}일` };
}

function chartSVG(pts, acc) {
  const W = 320, H = 170, PL = 46, PR = 8, PT = 12, PB = 22;
  const vals = pts.map(p => p.p);
  const hi = Math.max.apply(null, vals.concat(acc ? vals.map(v => v + acc) : []));
  const lo = Math.min.apply(null, vals);
  const span = hi - lo || 1;
  const x = i => PL + (W - PL - PR) * (pts.length === 1 ? 0.5 : i / (pts.length - 1));
  const y = v => PT + (H - PT - PB) * (1 - (v - lo) / span);

  const line = f => pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(f(p.p)).toFixed(1)}`).join('');
  const ticks = [hi, lo + span / 2, lo].map(v =>
    `<line class="grid-l" x1="${PL}" y1="${y(v).toFixed(1)}" x2="${W - PR}" y2="${y(v).toFixed(1)}"/>
     <text x="${PL - 5}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end">${Math.round(v / 1000)}k</text>`).join('');
  const last = pts[pts.length - 1];
  const xlab = `<text x="${PL}" y="${H - 6}">${md(pts[0].d)}</text>
    <text x="${W - PR}" y="${H - 6}" text-anchor="end">${md(last.d)}</text>`;

  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"
    role="img" aria-label="가격 변화 그래프">
    ${ticks}${xlab}
    ${acc ? `<path class="ln2" d="${line(v => v + acc)}"/>` : ''}
    <path class="ln" d="${line(v => v)}"/>
    <circle class="dot" cx="${x(pts.length - 1).toFixed(1)}" cy="${y(last.p).toFixed(1)}" r="3.5"/>
  </svg>`;
}

/* ── 탭바 ─────────────────────────────────────────────── */
const ICONS = {
  home: '<path d="M3 10.5L12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
  weekend: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 11h18"/>',
  swiss: '<path d="M3 20l6.5-11 4 6 2.5-4L21 20z"/>',
  error: '<path d="M13 2L4.5 13H11l-1 9 8.5-11H12l1-9z"/>',
  settings: '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.6 1.6 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.6 1.6 0 00-1.8-.3 1.6 1.6 0 00-1 1.5V21a2 2 0 11-4 0v-.1A1.6 1.6 0 008 19.4a1.6 1.6 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.6 1.6 0 00.3-1.8 1.6 1.6 0 00-1.5-1H2a2 2 0 110-4h.1A1.6 1.6 0 003.6 8a1.6 1.6 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.6 1.6 0 001.8.3H8a1.6 1.6 0 001-1.5V2a2 2 0 114 0v.1a1.6 1.6 0 001 1.5 1.6 1.6 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.6 1.6 0 00-.3 1.8V8a1.6 1.6 0 001.5 1H22a2 2 0 110 4h-.1a1.6 1.6 0 00-1.5 1z"/>',
};
const TABS = [
  { k: 'home', l: '홈' }, { k: 'weekend', l: '주말' }, { k: 'swiss', l: '스위스' },
  { k: 'error', l: '에러페어' }, { k: 'settings', l: '설정' },
];

function renderTabs() {
  const el = $('#tabbar');
  el.hidden = false;
  el.innerHTML = TABS.map(t => `<button role="tab" data-tab="${t.k}"
    aria-selected="${S.tab === t.k && !S.view}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round"
      stroke-linejoin="round">${ICONS[t.k]}</svg>
    <span>${t.l}</span></button>`).join('');
}

/* ── 렌더 ─────────────────────────────────────────────── */
function render() {
  const app = $('#app');
  if (S.err) { app.innerHTML = errorScreen(); $('#tabbar').hidden = true; return; }
  let html;
  if (S.view === 'list') html = viewList();
  else if (S.view === 'analysis') html = viewAnalysis();
  else if (S.tab === 'weekend') html = viewWeekend();
  else if (S.tab === 'swiss') html = viewSwiss();
  else if (S.tab === 'error') html = viewError();
  else if (S.tab === 'settings') html = viewSettings();
  else html = viewHome();

  app.innerHTML = html + (S.detail ? detailHTML(S.detail) : '');
  app.setAttribute('aria-busy', 'false');
  renderTabs();
  document.body.style.overflow = S.detail ? 'hidden' : '';
}

function errorScreen() {
  return `<div class="wrap"><div class="sec">
    <div class="note warn" style="margin-top:60px"><b>데이터를 불러오지 못했습니다</b>
      <p>${esc(S.err)}</p></div>
    <button class="btn-line" data-retry>다시 시도</button>
  </div></div>`;
}

/* ── 이벤트 ───────────────────────────────────────────── */
document.addEventListener('click', ev => {
  const t = ev.target.closest('[data-tab],[data-origin],[data-open],[data-view],'
    + '[data-list],[data-back],[data-close],[data-sheet],[data-range],[data-wspan],'
    + '[data-origin-toggle],[data-stops],[data-reset],[data-reload],[data-retry]');
  if (!t) return;

  if (t.hasAttribute('data-sheet') && ev.target === t) { S.detail = null; return render(); }
  if (t.hasAttribute('data-close')) { S.detail = null; return render(); }
  if (t.hasAttribute('data-reload') || t.hasAttribute('data-retry')) return location.reload();
  if (t.hasAttribute('data-back')) { S.view = null; return render(); }

  const tab = t.getAttribute('data-tab');
  if (tab) { S.tab = tab; S.view = null; S.detail = null; window.scrollTo(0, 0); return render(); }

  const og = t.getAttribute('data-origin');
  if (og) { S.origin = og; return render(); }

  const open = t.getAttribute('data-open');
  if (open) {
    S.detail = S.data.offers.find(o => o.id === open) || null;
    return render();
  }

  const view = t.getAttribute('data-view');
  if (view) { S.view = view; window.scrollTo(0, 0); return render(); }

  const lf = t.getAttribute('data-list');
  if (lf) { S.listFilter = lf; S.view = 'list'; window.scrollTo(0, 0); return render(); }

  const ws = t.getAttribute('data-wspan');
  if (ws) { S.weekendSpan = ws; return render(); }

  const rg = t.getAttribute('data-range');
  if (rg) { S.range = Number(rg); return render(); }

  const ot = t.getAttribute('data-origin-toggle');
  if (ot) {
    S.settings.origins[ot] = !originOn(ot);
    saveSettings(); return render();
  }

  const sp = t.getAttribute('data-stops');
  if (sp) { S.settings.stops = sp; saveSettings(); return render(); }

  if (t.hasAttribute('data-reset')) {
    try { localStorage.removeItem(SETTINGS_KEY); } catch (_) {}
    S.settings = defaultSettings(S.data);
    return render();
  }
});

document.addEventListener('change', ev => {
  const el = ev.target;
  const cost = el.getAttribute && el.getAttribute('data-cost');
  if (cost) {
    S.settings.access[cost] = Math.max(0, Number(el.value) || 0);
    saveSettings(); return render();
  }
  const key = el.getAttribute && el.getAttribute('data-set');
  if (key) {
    let v = Number(el.value) || 0;
    if (key === 'minNights') v = Math.max(1, Math.min(30, v));
    if (key === 'maxNights') v = Math.max(1, Math.min(30, v));
    if (key === 'strongPct') v = Math.max(5, Math.min(80, v));
    S.settings[key] = v;
    if (S.settings.minNights > S.settings.maxNights) {
      S.settings.maxNights = S.settings.minNights;
    }
    saveSettings(); return render();
  }
});

document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape' && S.detail) { S.detail = null; render(); }
});

/* ── 부팅 ─────────────────────────────────────────────── */
fetch('deals.json', { cache: 'no-cache' })
  .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
  .then(d => {
    S.data = d;
    S.settings = loadSettings(d);
    render();
  })
  .catch(e => {
    S.err = String(e && e.message ? e.message : e);
    render();
  });
