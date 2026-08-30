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
  // 소요시간은 sub 줄 끝에 붙이면 말줄임으로 잘려 안 보인다. 배지는
  // 줄바꿈되므로 여기 둔다. 없는 편에는 아예 안 붙인다.
  // 가는 편 / 왕복 총합을 구분해 쓴다. 소스의 duration 은 왕복 총합이라
  // 그냥 "비행시간" 이라고 붙이면 편도 20시간짜리가 41시간으로 읽힌다.
  if (o.duration_min) {
    b.push(`<span class="bg">✈ 가는 편 ${durTxt(o.duration_min)}</span>`);
  } else if (o.duration_rt_min) {
    b.push(`<span class="bg">✈ 왕복 합 ${durTxt(o.duration_rt_min)}</span>`);
  }
  // 출처는 항상 표시한다. 어디서 온 값인지 모르면 판단할 수 없다.
  b.push(srcBadge(o));
  // provider 마다 값이 다르면 그것도 보여준다. 하나로 뭉개지 않는다.
  if (Array.isArray(o.sources) && o.sources.length > 1 &&
      o.best_price && o.best_price !== o.price_krw) {
    b.push(`<span class="bg">다른 곳 최저 ${won(o.best_price)}원</span>`);
  }
  // 오래된 캐시값은 그렇다고 말한다. 이틀 넘으면 눈에 띄게.
  const age = ageTxt(o.found_at);
  if (age) {
    const stale = (Date.now() - Date.parse(o.found_at)) > 48 * 3600000;
    b.push(`<span class="bg${stale ? ' deal' : ''}">🕐 ${age}</span>`);
  }
  if (o.baseline_tier && o.baseline_tier.indexOf('누적') !== -1) {
    b.push(`<span class="bg">${esc(o.baseline_tier.split(' · ')[1])} 기준</span>`);
  }
  return `<div class="badges">${b.join('')}</div>`;
}

// v3 소스에서만 온다. 없으면 아무것도 그리지 않는다 — 지어내지 않는다.
const durTxt = m => {
  if (!m || m <= 0) return '';
  const h = Math.floor(m / 60), mm = m % 60;
  return mm ? `${h}시간 ${mm}분` : `${h}시간`;
};
// 출처 배지. 가격 등급(강력특가/특가/…)과 다른 축이다 — 저건 "싸냐",
// 이건 "얼마나 믿을 수 있냐". 그래서 등급 배지와 색을 공유하지 않는다.
const SRC_NAME = { duffel: 'Duffel', skyscanner: 'Skyscanner',
                   travelpayouts: 'Travelpayouts' };
function srcBadge(o) {
  const src = o.source || 'travelpayouts';
  const live = !!o.live;
  const label = SRC_NAME[src] || src;
  return `<span class="bg src${live ? ' live' : ''}">${
    live ? 'LIVE' : 'CACHE'} · ${esc(label)}</span>`;
}

// 이 앱의 가격은 "남이 검색해서 캐시에 남은 값" 이다. 언제 남은 값인지를
// 숨기면, 사흘 지난 값과 오늘 값이 같은 얼굴로 보인다.
function ageTxt(iso) {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (!t) return '';
  const h = Math.floor((Date.now() - t) / 3600000);
  if (h < 0) return '';
  if (h < 1) return '방금 검색된 값';
  if (h < 24) return `${h}시간 전 검색된 값`;
  return `${Math.floor(h / 24)}일 전 검색된 값`;
}
const stopTxt = s => (s === 0 ? '직항' : (s === 1 ? '1회 환승' : (s == null ? '환승 정보 없음' : `${s}회 환승`)));

function heroHTML(o, rank, plainLabel) {
  const acc = accessOf(o.dep);
  // 메달은 특가일 때만 붙인다. 표본이 있어도 등급이 '일반'이면
  // "🥇 일반" 같은 말이 되어 버린다. 그럴 땐 이 자리가 왜 1등인지를
  // 부르는 이름(호출한 화면이 정한다)을 쓴다.
  const t = dealTier(o);
  const medal = o.data_ok && t !== 'normal' && t !== 'unknown';
  return `<button class="hero" data-open="${esc(o.id)}">
    <span class="rank">${medal
      ? `${rank === 1 ? '🥇' : '🏅'} ${esc(TIER_TEXT[t])}`
      : esc(plainLabel || '💰 현재 최저가')}</span>
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
    deals = `<div class="top-grid">${heroHTML(top[0], 1, '🥇 오늘 1순위')}
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
// 스위스는 취리히가 1순위다. 이 순서가 화면 구성과 대표편 선택을 지배한다.
const SWISS_ORDER = ['ZRH', 'GVA', 'BSL'];
const SWISS_CITY = { ZRH: '취리히', GVA: '제네바', BSL: '바젤' };
const SWISS_RANK = { ZRH: 0, GVA: 1, BSL: 2 };

// 이 노선에 소스를 몇 군데까지 물어봤는지. 3차까지 갔으면 5곳이다.
// 숫자를 코드에 박아 두면 소스를 늘렸을 때 화면이 조용히 거짓말을 한다.
function srcTried(code) {
  const deep = (S.data.meta && S.data.meta.deep_tried) || [];
  return deep.some(k => k.endsWith('-' + code)) ? 5 : 2;
}

// 편도 카드. cardHTML 을 쓰지 않는다 — 그쪽은 실부담가·비교 기준가·특가
// 등급을 그린다. 편도에 그걸 붙이면 왕복과 나란히 놓였을 때 반값짜리가
// "특가" 로 보인다. 편도는 항공권 값과 편도라는 사실만 말한다.
function owCardHTML(o) {
  return `<a class="cd ow" href="${esc(o.link)}" target="_blank" rel="noopener">
    <div class="top">
      <div class="ttl">
        <div class="route">${esc(depCity(o.dep))} → ${esc(o.city)}</div>
        <div class="sub">${esc(o.dep)}→${esc(o.arr)} ·
          ${md(o.depart_date)}(${dow(o.depart_date)}) ·
          ${esc(o.airline_kr || o.airline)} · ${stopTxt(o.stops)}</div>
      </div>
      <div class="price"><div class="v">${won(o.price_krw)}</div>
        <div class="k">편도 · 가는 편만</div></div>
    </div>
    <div class="badges"><span class="bg deal">편도</span>
      <span class="bg">왕복가 아님 · 실부담가 계산 안 함</span></div>
  </a>`;
}

// 도시별 편도. 왕복이 하나도 없을 때 이게 그 도시의 유일한 단서가 된다.
function owOf(code) {
  // 위쪽 왕복 그룹과 같은 순서 규칙을 쓴다: 직항 → 환승, 그다음 값.
  // 같은 탭 안에서 정렬 기준이 두 가지면 읽는 사람이 헷갈린다.
  return (S.data.oneway || [])
    .filter(o => o.arr === code && originOn(o.dep))
    .sort((x, y) =>
      (x.stops == null ? 9 : x.stops) - (y.stops == null ? 9 : y.stops) ||
      x.price_krw - y.price_krw);
}

function owGroupHTML(list) {
  if (!list.length) return '';
  return `<p style="margin:14px 0 8px;font-size:12.5px;font-weight:800;color:var(--tx2)">
      🎫 편도만 확인됨 ${list.length}건</p>
    <div class="note" style="margin-bottom:8px"><p>이 노선은 소스에 <b>왕복
      캐시가 없고 편도만</b> 있습니다. 아래는 <b>가는 편 값</b>이라 위의
      왕복 가격과 직접 비교할 수 없습니다. 실부담가·특가 판정에도 넣지
      않았습니다.</p></div>
    <div class="list two">${list.slice(0, 6).map(owCardHTML).join('')}</div>`;
}

// 이 소스에 없는 노선은 여기서 끝내지 않는다. 실시간 검색으로 넘겨준다.
//
// Travelpayouts Data API 는 "남이 검색해서 캐시에 남은 값" 이다. aviasales.com
// 웹 검색은 그때그때 항공사·GDS 를 찔러보는 메타서치라 결과가 다르다. 같은
// 회사 제품인데 우리가 쓸 수 있는 건 캐시 쪽뿐이다(실시간 API 는 MAU 5만
// 이상만 승인). 2026-08-30 실측: 이 링크로 연 화면에서 취리히 왕복 $614 가
// 나왔다 — 우리 캐시에는 0건인 노선이다.
//
// 그래서 "없습니다" 로 끝내지 않고, 날짜를 바꿔 가며 눌러볼 수 있게 한다.
// 가격은 출발일에 따라 크게 달라서 창을 하나만 주면 쓸모가 적다.
const LIVE_NIGHTS = 10;                 // 유럽 왕복의 현실적인 기본값
const LIVE_OFFSETS = [45, 75, 105];     // 출발일 후보 (오늘로부터)

function liveSearchURL(dep, arr, offset, nights) {
  const d0 = new Date(); d0.setDate(d0.getDate() + offset);
  const d1 = new Date(d0); d1.setDate(d1.getDate() + nights);
  const dm = d => String(d.getDate()).padStart(2, '0') +
                  String(d.getMonth() + 1).padStart(2, '0');
  return {
    url: `https://www.aviasales.com/search/${dep}${dm(d0)}${arr}${dm(d1)}1`,
    label: `${d0.getMonth() + 1}/${d0.getDate()} 출발`,
    sub: `${LIVE_NIGHTS}박`,
  };
}

function liveSearchHTML(dep, arr, cityName) {
  const btns = LIVE_OFFSETS.map(off => {
    const l = liveSearchURL(dep, arr, off, LIVE_NIGHTS);
    return `<a class="live-btn" href="${esc(l.url)}" target="_blank" rel="noopener">
      <span class="d">${l.label}</span><span class="n">${l.sub}</span></a>`;
  }).join('');
  return `<div class="live">
    <p class="live-hd">${esc(cityName)} 실시간으로 검색하기</p>
    <div class="live-row">${btns}</div>
    <p class="live-note">이 앱의 가격은 <b>캐시</b>라 실제로 파는 표가 빠질 수
      있습니다. 위 버튼은 aviasales 실시간 검색을 엽니다 — 날짜는 그 화면에서
      바꾸세요.</p>
    <p class="live-note" style="margin-top:6px">💡 <b>한 번 검색해 두면 다음
      스캔부터 이 앱이 자동으로 추적합니다.</b> 이 소스는 사람들이 검색한
      기록을 모아 두는 곳이라, 아무도 안 찾는 노선은 비어 있습니다.
      직접 한 번 찾으면 그 기록이 남습니다.</p>
  </div>`;
}

function viewSwiss() {
  // 여행 기간·환승 설정을 일부러 적용하지 않는다. 유럽은 캐시가 얇아
  // 근거리용 조건을 씌우면 있는 것마저 사라진다. 환승은 제한 없이 다 본다.
  const all = S.data.offers.filter(o =>
    SWISS_ORDER.includes(o.arr) && originOn(o.dep));

  if (!all.length) {
    return `${plainHeader('스위스', '취리히 우선 · 환승 제한 없음')}
      <div class="wrap">${swissDiag()}${swissNote()}${footerHTML()}</div>`;
  }

  // 도시 안에서는 직항 → 1회 → 2회+ , 그다음 실부담가
  const inCity = (a, b) =>
    (a.stops == null ? 9 : a.stops) - (b.stops == null ? 9 : b.stops) ||
    effective(a) - effective(b) ||
    a.nights - b.nights;

  // 대표편: 취리히 우선, 그 안에서 강력특가 → 최저가
  let hero = null;
  for (const code of SWISS_ORDER) {
    const c = all.filter(o => o.arr === code);
    if (!c.length) continue;
    hero = c.filter(o => dealTier(o) === 'strong').sort(inCity)[0]
        || c.slice().sort((a, b) => effective(a) - effective(b))[0];
    break;
  }

  const heroStrong = dealTier(hero) === 'strong';
  const head = heroStrong
    ? `<section class="sec"><div class="sec-hd"><div>
        <h2>🏔 오늘 가장 좋은 옵션</h2>
        <p>취리히 우선 · 환승 제한 없음</p></div></div>
        ${heroHTML(hero, 1)}</section>`
    : `<section class="sec">
        <div class="note hot"><b>현재 강력 특가 없음</b>
          <p>취리히를 먼저 보고, 없으면 제네바·바젤 순으로 내려갑니다.
          가격만 보고 정리했습니다.</p></div>
        <div style="margin-top:10px">${heroHTML(hero, 1)}</div></section>`;

  // 도시별 섹션 — 취리히부터. 가격이 없는 도시도 지우지 않는다.
  const raw = (S.data.meta && S.data.meta.raw_counts) || {};
  const sections = SWISS_ORDER.map((code, idx) => {
    const cityAll = all.filter(o => o.arr === code);
    // 대표편은 위에 크게 이미 있다. 아래 목록에 또 넣지 않는다.
    const cands = cityAll.filter(o => o !== hero).sort(inCity);
    const label = `${idx === 0 ? '🥇 ' : ''}${SWISS_CITY[code]} <span
      style="font-family:var(--mono);font-size:13px;color:var(--tx3)">${code}</span>`;

    const ow = owOf(code);
    if (!cityAll.length) {
      const got = Object.keys(raw).some(k => k.endsWith('-' + code) && raw[k]);
      return `<section class="sec"><div class="sec-hd"><div>
          <h2>${label}</h2><p>${idx === 0 ? '1순위 도시 · ' : ''}${
            ow.length ? `왕복 없음 · 편도 ${ow.length}건` : '가격 없음'}</p>
        </div></div>
        <div class="note warn"><b>${ow.length
          ? '왕복 가격이 없습니다' : '가격 데이터 부족'}</b>
          <p>${got
            ? '조회는 됐지만 왕복으로 확인되는 편이 없습니다.'
            : `소스 ${srcTried(code)}곳을 모두 확인했지만 응답이 비었습니다.
               캐시에 이 노선이 없습니다.`}
          운항이 없다는 뜻은 아닙니다.</p>
          ${liveSearchHTML('ICN', code, SWISS_CITY[code])}</div>
        ${owGroupHTML(ow)}</section>`;
    }

    // 이 도시에 있는 게 대표편 하나뿐이면 빈 목록 대신 그렇다고 말한다.
    if (!cands.length) {
      return `<section class="sec"><div class="sec-hd"><div>
          <h2>${label}</h2>
          <p>${idx === 0 ? '1순위 도시 · ' : ''}1건 · 위 대표편이 전부입니다</p>
        </div></div></section>`;
    }

    const d0 = cands.filter(o => o.stops === 0);
    const d1 = cands.filter(o => o.stops === 1);
    const d2 = cands.filter(o => o.stops != null && o.stops >= 2);
    const dU = cands.filter(o => o.stops == null);
    const grp = (list, title) => list.length
      ? `<p style="margin:14px 0 8px;font-size:12.5px;font-weight:800;color:var(--tx2)">
           ${title} ${list.length}건</p>
         <div class="list two">${list.slice(0, 6).map(o => cardHTML(o)).join('')}</div>`
      : '';

    return `<section class="sec"><div class="sec-hd"><div>
        <h2>${label}</h2>
        <p>${idx === 0 ? '1순위 도시 · ' : ''}${cityAll.length}건${
          hero.arr === code ? ' (대표편 1건은 위에)' : ''} · 직항 → 환승 순</p></div></div>
      ${grp(d0, '🛫 직항')}${grp(d1, '✈️ 1회 환승')}${grp(d2, '🔁 2회 이상 환승')}
      ${grp(dU, '❔ 환승 정보 없음')}${owGroupHTML(ow)}</section>`;
  }).join('');

  // 가격 위치 (대표편 기준)
  const r = (S.data.routes || {})[`${hero.dep}-${hero.arr}`] || {};
  const wait = r.low30 && hero.price_krw > r.low30;
  // 값이 없을 때 "—원" 을 찍지 않는다. 대시는 0원처럼 읽히거나 고장으로
  // 보인다. 없으면 없다고 쓴다.
  const kvw = (k, v) => `<div class="kv"><span class="k">${k}</span>${
    v == null
      ? '<span class="v" style="font-size:12.5px;font-family:var(--sans);color:var(--tx3)">아직 기록 없음</span>'
      : `<span class="v">${won(v)}원</span>`}</div>`;
  const pos = `<div class="panel"><h4>가격 위치 · ${esc(SWISS_CITY[hero.arr] || hero.arr)}</h4>
    ${kvw('현재 항공권', hero.price_krw)}
    ${kvw('최근 30일 최저', r.low30)}
    ${kvw('추적 기간 최저', r.low_all)}
    ${kvw('노선 평균가', r.avg)}
    <div class="kv"><span class="k">표본</span><span class="v">${r.n || 0}건 · 신뢰도 ${esc(hero.confidence || '참고')}</span></div>
    ${(r.series || []).length >= 3
      ? `<p style="margin:10px 0 0;font-size:13px;font-weight:700;color:${wait ? 'var(--warn)' : 'var(--down)'}">
         ${wait ? '조금 더 기다려볼 만함' : '최근 구간에서 낮은 편'}</p>`
      : `<p style="margin:10px 0 0;font-size:12.5px;color:var(--tx3);font-weight:600">
         기록이 ${(r.series || []).length || 1}일치뿐이라 아직 "싸다/비싸다"를 말할 수
         없습니다. 위 세 값이 같은 것도 그 때문입니다 — 오늘 가격이 곧 최저이자
         최고입니다.</p>`}
  </div>`;

  // 데이터가 있는 도시라도 실제 예약 전에는 실시간을 보는 게 맞다.
  // 대표편 도시 기준으로 맨 아래 한 번 더 둔다.
  const liveAll = liveSearchHTML('ICN', hero.arr, SWISS_CITY[hero.arr] || hero.arr);
  return `${plainHeader('스위스', '취리히 우선 · 환승 제한 없음')}
  <div class="wrap">${head}${sections}${pos}${liveAll}${swissNote()}${footerHTML()}</div>`;
}

function swissNote() {
  const withDur = S.data.offers.filter(o =>
    SWISS_ORDER.includes(o.arr) && (o.duration_min || o.duration_rt_min)).length;
  return `<div class="note" style="margin-top:16px"><b>이 소스로 알 수 있는 것과 없는 것</b>
    <p>비행시간은 <b>일부 편에만</b> 들어옵니다(현재 ${withDur}건). 소스가
    주는 값은 <b>왕복 총합</b>이라, 가는 편 값이 따로 올 때만 "가는 편"으로
    적고 아니면 "왕복 합"으로 적습니다. 없는 편은 비워 둡니다.
    <b>환승 대기시간은 어느 응답에도 없습니다.</b> 그래서 정렬 기준으로는
    쓰지 않았습니다. 실제 일정은 예약 페이지에서 확인하세요.</p></div>`;
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
      <p>조회 실패가 아닙니다. 이 앱이 쓰는 Travelpayouts 는 <b>실시간 검색이
      아니라 남이 검색해서 캐시에 남은 값</b>을 줍니다. 그래서 실제로 파는
      표가 여기 없을 수 있습니다. 여섯 엔드포인트를 다 훑은 결과가
      아래입니다.</p></div>
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
