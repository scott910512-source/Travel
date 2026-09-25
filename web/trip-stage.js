/* 캐릭터 여행 무대. 그 날의 선택된 스텝(TripState 의 항목)을 축약 일러스트 맵에 순서대로 놓고, 두 캐릭터가 따라 움직인다.
   - 지리·거리를 나타내지 않는다(뱀 모양 경로). 정확한 위치는 Leaflet 지도·길찾기로.
   - 재생 상태(스텝·진행·속도)는 일정 상태와 별개다. 재생해도 방문 완료로 기록하지 않는다.
   - setSteps 는 스텝 서명이 같으면 위치를 유지하고 라벨만 바꾼다. 현재 스텝이 사라지면 가까운 스텝으로 가고 멈춘다.
   - 타이머·rAF 는 한 번에 하나. 날짜 바꾸기·이전·다음·destroy 에서 정리한다. */
'use strict';
const TripStage = (() => {
  const W = 1000, ROW_H = 190, COLS = 3, XS = [180, 500, 820], TOP = 150;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ICON = { flight: 'ic-airport', hotel: 'ic-hotel', poi: 'ic-poi', meal: 'ic-meal', rest: 'ic-rest', custom: 'ic-custom' };
  const POSE = { flight: 'wait', hotel: 'rest', poi: 'look', meal: 'eat', rest: 'rest', custom: 'look', tbd: 'wait' };
  const BUBBLE = { poi: '둘러보자!', meal: '맛있겠다 😋', rest: '좀 쉬자~', hotel: '오늘도 고생했어', flight: '출발!', custom: '여기야!', tbd: '어디로 갈까?' };
  const GO = { car: '차 타고 가자 🚗', walk: '걸어가자!' };
  const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  function layout(n) {
    const pts = [];
    for (let i = 0; i < n; i++) { const row = Math.floor(i / COLS), c = i % COLS; const x = row % 2 ? XS[COLS - 1 - c] : XS[c]; pts.push({ x, y: TOP + row * ROW_H }); }
    return pts;
  }
  const H = n => TOP + Math.max(0, Math.ceil(n / COLS) - 1) * ROW_H + 160;
  /* 배경: 바다·섬·야자수. 스텝 수가 달라도 같은 씨앗으로 그린다. */
  function background(h) {
    const isles = [[120, 90, 170, 60], [700, 60, 220, 70], [880, 340, 150, 55], [80, 520, 190, 65], [600, 760, 230, 70], [300, 980, 200, 60], [820, 1200, 170, 60], [150, 1400, 210, 65]].filter(i => i[1] < h + 40);
    return `<defs><linearGradient id="sea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8FD3F4"/><stop offset="1" stop-color="#3FA9E0"/></linearGradient>
      <linearGradient id="sand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FBEFD3"/><stop offset="1" stop-color="#F1DDB0"/></linearGradient></defs>
      <rect x="-200" y="-3000" width="${W + 400}" height="${h + 8000}" fill="url(#sea)"/>
      <g class="waves" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="3" stroke-linecap="round">${Array.from({ length: Math.ceil(h / 120) + 2 }, (_, i) => `<path d="M${(i % 3) * 140 - 200} ${60 + i * 120}q20-10 40 0t40 0t40 0t40 0"/>`).join('')}</g>
      ${isles.map(([x, y, rx, ry], i) => `<g><ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="url(#sand)"/><ellipse cx="${x}" cy="${y - 8}" rx="${rx * .8}" ry="${ry * .6}" fill="#8CCB6A"/><use href="#pr-palm" x="${x - rx * .6}" y="${y - 70}" width="48" height="64"/>${i % 2 ? `<use href="#pr-palm" x="${x + rx * .3}" y="${y - 60}" width="40" height="54"/>` : ''}</g>`).join('')}`;
  }
  function pathD(pts) {
    if (pts.length < 2) return '';
    let d = `M${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length; i++) { const a = pts[i - 1], b = pts[i]; const mx = (a.x + b.x) / 2; d += a.y === b.y ? ` L${b.x} ${b.y}` : ` C${a.x} ${(a.y + b.y) / 2} ${b.x} ${(a.y + b.y) / 2} ${b.x} ${b.y}`; void mx; }
    return d;
  }
  function create(svg, opts) {
    const o = Object.assign({ onStep: () => {}, onState: () => {}, onOpen: () => {} }, opts || {});
    let steps = [], pts = [], sig = '', idx = 0, playing = false, speed = 1, phase = 'at', raf = 0, timer = 0, moving = null, chars = null, car = null, cam = null, fitAllMode = false, destroyed = false;
    const clearTimers = () => { if (raf) cancelAnimationFrame(raf); if (timer) clearTimeout(timer); raf = 0; timer = 0; moving = null; };
    const state = () => ({ idx, playing, speed, phase, n: steps.length, step: steps[idx] || null });
    const emit = () => o.onState(state());
    function build() {
      const h = H(steps.length); pts = layout(steps.length);
      svg.setAttribute('viewBox', `0 0 ${W} ${h}`); svg.dataset.h = h;
      svg.innerHTML = `<defs>${TRIP_CHARS.defs}</defs><g class="cam">${background(h)}
        <path class="route" d="${pathD(pts)}" fill="none" stroke="#fff" stroke-width="5" stroke-dasharray="2 14" stroke-linecap="round" opacity=".9"/>
        <g class="nodes">${steps.map((s, i) => node(s, i)).join('')}</g>
        <g class="car pr-car" style="display:none"><use href="#pr-car" x="-60" y="-70" width="120" height="60"/></g>
        <g class="chars"><g class="pair"><g class="char man" transform="translate(-52,-96)"><use href="#ch-man" width="64" height="96"/></g><g class="char woman" transform="translate(-8,-86)"><use href="#ch-woman" width="58" height="86"/></g></g>
          <g class="bubble" style="display:none"><rect x="-80" y="-150" width="160" height="34" rx="12" fill="#fff" stroke="#5B4BE0" stroke-width="2"/><path d="M-6 -116l6 10 6-10z" fill="#fff"/><text x="0" y="-127" text-anchor="middle" font-size="17" font-weight="800" fill="#16181F"></text></g></g></g>`;
      cam = svg.querySelector('.cam'); chars = svg.querySelector('.chars'); car = svg.querySelector('.car');
    }
    function node(s, i) {
      const p = pts[i]; const name = s.name.length > 16 ? s.name.slice(0, 15) + '…' : s.name;
      const w = Math.min(280, Math.max(120, name.length * 15 + 40));
      const ly = 40;   // 이름표는 항상 아이콘 아래(캐릭터가 위에 서므로)
      return `<g class="node k-${s.k}${s.done ? ' done' : ''}" data-i="${i}" transform="translate(${p.x},${p.y})" tabindex="0" role="button" aria-label="${esc(s.name)} 상세">
        <ellipse cx="0" cy="8" rx="30" ry="10" fill="#000" opacity=".12"/>
        <use href="#${ICON[s.k] || 'ic-poi'}" x="-24" y="-24" width="48" height="48"/>
        <g class="lbl" transform="translate(0,${ly})"><rect x="${-w / 2}" y="-16" width="${w}" height="34" rx="12" fill="#fff" stroke="#D9D3FA" stroke-width="2"/>
          <text x="${-w / 2 + 14}" y="7" font-size="17" font-weight="800" fill="#16181F">${esc(name)}</text>
          <g class="info" transform="translate(${w / 2 - 20},0)"><circle r="12" fill="#5B4BE0"/><text y="5" text-anchor="middle" font-size="14" font-weight="800" fill="#fff">i</text></g></g>
        ${s.done ? '<circle cx="18" cy="-18" r="9" fill="#0F9D58"/><path d="M13 -18l4 4 7-8" stroke="#fff" stroke-width="2.5" fill="none"/>' : ''}
      </g>`;
    }
    function place(i) { const p = pts[i]; if (!p) return; chars.setAttribute('transform', `translate(${p.x - 44},${p.y + 4})`); car.style.display = 'none'; chars.style.display = ''; }
    function face(dir) { const pair = svg.querySelector('.pair'); if (pair) pair.setAttribute('transform', dir < 0 ? 'scale(-1,1)' : ''); }
    function pose(cls) { svg.querySelectorAll('.char').forEach(c => { c.classList.remove('walk', 'wait', 'look', 'eat', 'rest'); if (cls) c.classList.add(cls); }); }
    function bubble(text) { const b = svg.querySelector('.bubble'); if (!b) return; if (!text) { b.style.display = 'none'; return; } b.style.display = ''; b.querySelector('text').textContent = text; const w = Math.max(120, text.length * 17 + 30); b.querySelector('rect').setAttribute('x', -w / 2); b.querySelector('rect').setAttribute('width', w); }
    function highlight(i) { svg.querySelectorAll('.node').forEach(n => n.classList.toggle('cur', Number(n.dataset.i) === i)); }
    /* 카메라: 스텝이 4개 넘으면 캐릭터를 따라간다. 전체보기면 그대로. */
    function camera(y, instant) {
      const h = Number(svg.dataset.h) || H(steps.length);
      const box = svg.getBoundingClientRect ? svg.getBoundingClientRect() : { width: 400, height: 500 };
      const vh = box.width && box.height ? (box.height / box.width) * W : 600;   // 화면 비율에 맞춘 보이는 높이(뷰박스 단위) · 크기를 모르면 600
      if (fitAllMode) { const fh = Math.max(h, vh); svg.setAttribute('viewBox', `0 ${(h - fh) / 2} ${W} ${fh}`); return; }
      if (h <= vh + 40) { svg.setAttribute('viewBox', `0 ${(h - vh) / 2} ${W} ${vh}`); return; }   // 짧은 맵: 세로 가운데, 폭은 꽉
      const top = Math.max(0, Math.min(h - vh, y - vh * 0.55));
      if (instant || reduced()) { svg.setAttribute('viewBox', `0 ${top} ${W} ${vh}`); return; }
      const from = (svg.getAttribute('viewBox') || '0 0').split(' ').map(Number)[1] || 0; const t0 = performance.now();
      const step = now => { const k = Math.min(1, (now - t0) / 500); const e = 1 - Math.pow(1 - k, 3); svg.setAttribute('viewBox', `0 ${from + (top - from) * e} ${W} ${vh}`); if (k < 1 && !destroyed) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    }
    function arrive(i, opt) {
      idx = i; phase = 'at'; place(i); highlight(i);
      const s = steps[i]; pose(POSE[s.k] || 'wait'); bubble(BUBBLE[s.k] || '');
      camera(pts[i].y, opt && opt.instant);
      o.onStep(state());
      if (playing && i < steps.length - 1) timer = setTimeout(() => { timer = 0; go(i + 1); }, 1600 / speed);
      else if (playing && i >= steps.length - 1) { playing = false; }
      emit();
    }
    let paused = null;   // 이동 중 멈춘 자리 {to, x, y}
    function go(to, fromXY) {
      clearTimers(); if (to < 0 || to >= steps.length || destroyed) return;
      const from = idx, a = fromXY || pts[from], b = pts[to]; if (!a || !b || (from === to && !fromXY)) { arrive(to); return; }
      paused = null; phase = 'moving'; const byCar = !!steps[to].car; highlight(-1);
      face(b.x < a.x ? -1 : 1); bubble(byCar ? GO.car : GO.walk); pose('walk');
      if (byCar) { chars.style.display = 'none'; car.style.display = ''; car.querySelector('use').setAttribute('transform', b.x < a.x ? 'scale(-1,1)' : ''); }
      const dur = (reduced() ? 1 : 1800) / speed, t0 = performance.now(); emit();
      const tick = now => {
        if (destroyed) return;
        const k = Math.min(1, (now - t0) / dur); const e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const x = a.x + (b.x - a.x) * e, y = a.y + (b.y - a.y) * e;
        moving.x = x; moving.y = y;
        (byCar ? car : chars).setAttribute('transform', `translate(${x - (byCar ? 0 : 44)},${y + (byCar ? -6 : 4)})`);
        if (k < 1) raf = requestAnimationFrame(tick); else { raf = 0; moving = null; arrive(to); }
      };
      moving = { to, x: a.x, y: a.y }; raf = requestAnimationFrame(tick);
    }
    const api = {
      setSteps(next, opt) {
        const s2 = next.map(s => `${s.uid}|${s.k}|${s.ref}`).join(';');
        const curUid = steps[idx] && steps[idx].uid;
        if (s2 === sig && !(opt && opt.force)) { steps = next; steps.forEach((s, i) => { const n = svg.querySelector(`.node[data-i="${i}"]`); if (n) n.classList.toggle('done', !!s.done); }); return; }
        const wasPlaying = playing; clearTimers(); playing = false; paused = null;
        steps = next; sig = s2; build();
        let ni = steps.findIndex(s => s.uid === curUid);
        if (ni < 0) { ni = Math.max(0, Math.min(idx, steps.length - 1)); }      // 현재 스텝이 사라짐 → 가까운 스텝, 멈춤
        else if (wasPlaying && !(opt && opt.keepPause)) playing = true;
        if (steps.length) arrive(ni, { instant: true }); else emit();
      },
      play() { if (!steps.length) return; playing = true;
        if (paused) { const p = paused; go(p.to, { x: p.x, y: p.y }); }
        else if (phase === 'at') { if (idx >= steps.length - 1) { idx = -1; go(0); } else go(idx + 1); }
        emit(); },
      pause() { playing = false;
        if (phase === 'moving' && moving) { paused = { to: moving.to, x: moving.x, y: moving.y }; clearTimers(); phase = 'paused'; pose('wait'); }
        else clearTimers();
        emit(); },
      toggle() { playing ? api.pause() : api.play(); },
      next() { playing = false; paused = null; clearTimers(); if (idx < steps.length - 1) arrive(idx + 1, { instant: true }); emit(); },
      prev() { playing = false; paused = null; clearTimers(); if (idx > 0) arrive(idx - 1, { instant: true }); emit(); },
      goto(i) { playing = false; paused = null; clearTimers(); if (i >= 0 && i < steps.length) arrive(i, { instant: true }); emit(); },
      gotoUid(uid) { const i = steps.findIndex(s => s.uid === uid); if (i >= 0) api.goto(i); },
      setSpeed(v) { speed = Number(v) || 1; emit(); },
      fitAll(on) { fitAllMode = on == null ? !fitAllMode : !!on; camera(pts[idx] ? pts[idx].y : 0, true); emit(); return fitAllMode; },
      state, isPlaying: () => playing,
      destroy() { destroyed = true; clearTimers(); svg.innerHTML = ''; },
    };
    svg.addEventListener('click', ev => { const n = ev.target.closest('.node'); if (n) { ev.preventDefault(); o.onOpen(Number(n.dataset.i)); } });
    svg.addEventListener('keydown', ev => { const n = ev.target.closest('.node'); if (n && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); o.onOpen(Number(n.dataset.i)); } });
    return api;
  }
  return { create, layout, H, POSE, BUBBLE };
})();
if (typeof module !== 'undefined') module.exports = TripStage;
