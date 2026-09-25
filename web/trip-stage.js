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
    let spriteFrame = 3, travelStart = 0;
    function build() {
      pts = layout(steps.length);
      svg.setAttribute('viewBox', '0 0 600 700');
      svg.setAttribute('preserveAspectRatio', 'xMidYMid slice');
      svg.innerHTML = `<defs>${TRIP_CHARS.defs}</defs>
        <image href="assets/trip/coast.webp" width="600" height="700" preserveAspectRatio="xMidYMid slice"/>
        <path d="M180 600 Q270 550 370 400" fill="none" stroke="#d77350" stroke-width="5" stroke-dasharray="4 16" stroke-linecap="round" opacity=".75"/>
        <g class="nodes">${steps.map((s,i)=>node(s,i)).join('')}</g>
        <g class="car pr-car" style="display:none"><use href="#pr-car" x="-65" y="-70" width="130" height="65"/></g>
        <g class="chars"><ellipse cx="0" cy="-5" rx="79" ry="13" fill="#29352b" opacity=".16"/>
          <g class="pair"><g class="char man"><svg class="sprite" x="-136" y="-270" width="272" height="272" viewBox="0 512 512 512" overflow="hidden"><image href="assets/trip/couple.webp" width="1536" height="1024"/></svg></g></g>
          <g class="bubble" style="display:none"><rect x="-80" y="-302" width="160" height="34" rx="17" fill="#fffdf8"/><text x="0" y="-279" text-anchor="middle" font-size="17" font-weight="700" fill="#173c40"></text></g></g>`;
      chars=svg.querySelector('.chars'); car=svg.querySelector('.car');
    }
    function node(s,i) {
      return `<g class="node k-${s.k}${s.done?' done':''}" data-i="${i}" tabindex="0" role="button" aria-label="${esc(s.name)} 상세">
        <rect x="-126" y="-26" width="252" height="64" rx="18" fill="#fffdf8" stroke="#e6e5da"/>
        <circle cx="-104" cy="5" r="10" fill="#d66e4d"/>
        <text x="-84" y="0" font-size="16" font-weight="700" fill="#173c40">${esc(s.name.length>12?s.name.slice(0,12)+'…':s.name)}</text>
        <text class="nodehint" x="-84" y="23" font-size="13" fill="#697e7c">장소 자세히 보기 ↗</text></g>`;
    }
    function frame(n){const e=svg.querySelector('.sprite');if(e)e.setAttribute('viewBox',`${(n%3)*512} ${Math.floor(n/3)*512} 512 512`);}
    function place(i){if(!steps[i])return;chars.setAttribute('transform','translate(285,605)');chars.style.display='';car.style.display='none';}
    function face(dir) { /* Perspective stays consistent with the scene. */ }
    function pose(cls){const c=svg.querySelector('.char');if(c){c.setAttribute('class','char man '+(cls||''));}spriteFrame=cls==='eat'?4:cls==='rest'?5:3;frame(spriteFrame);}
    function bubble(text){const b=svg.querySelector('.bubble');if(!b)return;b.style.display=text?'':'none';b.querySelector('text').textContent=text||'';const w=Math.max(140,(text||'').length*17+30);b.querySelector('rect').setAttribute('x',-w/2);b.querySelector('rect').setAttribute('width',w);}
    function highlight(i){svg.querySelectorAll('.node').forEach(n=>n.classList.toggle('cur',Number(n.dataset.i)===i));positionNodes();}
    function positionNodes(){svg.querySelectorAll('.node').forEach((n,i)=>{
      n.style.display=fitAllMode||i===idx||i===idx+1?'':'none';
      n.setAttribute('transform',fitAllMode?`translate(${i%2?445:155},${90+Math.floor(i/2)*82})`:`translate(${i===idx?151:447},${i===idx?180:320})`);
      n.querySelector('.nodehint').textContent=fitAllMode?`${i+1}번째 장소 · 상세 ↗`:i===idx?'현재 장소 · 상세 ↗':'다음 장소 · 상세 ↗';
    });if(chars)chars.style.opacity=fitAllMode?'.25':'1';}
    function camera(y,instant){positionNodes();}
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
      const dur = (reduced() ? 1 : 1800) / speed, t0 = performance.now(); travelStart=t0; emit();
      const tick = now => {
        if (destroyed) return;
        const k = Math.min(1, (now - t0) / dur); const e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const x = a.x + (b.x - a.x) * e, y = a.y + (b.y - a.y) * e;
        moving.x = x; moving.y = y;
        (byCar ? car : chars).setAttribute('transform', `translate(${245+e*105},${615-e*75})`);
        if(!byCar)frame(Math.floor((now-travelStart)/150)%3);
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
