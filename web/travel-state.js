/* Search links and comparison selection. Pure functions; no DOM or storage. */
'use strict';
const TravelState = (() => {
  const tripKeys = ['stops', 'minNights', 'maxNights', 'longStops', 'longMinNights', 'longMaxNights'];
  const integer = (v, min, max) => v != null && v !== '' && Number.isInteger(Number(v))
    && Number(v) >= min && Number(v) <= max ? Number(v) : undefined;
  const oneOf = (v, choices) => choices.includes(v) ? v : undefined;
  function encode(st) {
    const p = new URLSearchParams();
    const put = (k, v) => { if (v !== undefined && v !== null && v !== '') p.set(k, String(v)); };
    put('t', st.t); put('v', st.v); put('o', st.o);
    put('from', st.from); put('to', st.to); put('m', st.m); put('sort', st.sort);
    const f = st.f || {};
    put('tier', f.tier); put('ch', f.change); put('q', f.q);
    put('wk', f.weekend ? '1' : null); put('cap', f.cap); put('leave', f.leave);
    put('st', st.st); put('mn', st.mn); put('mx', st.mx);
    put('lst', st.lst); put('lmn', st.lmn); put('lmx', st.lmx);
    put('span', st.span);
    return '#' + p.toString();
  }
  function decode(hash) {
    if (!hash || hash === '#') return null;
    const p = new URLSearchParams(hash.replace(/^#/, ''));
    const st = {
      t: oneOf(p.get('t'), ['home', 'find', 'swiss', 'more']),
      v: oneOf(p.get('v'), ['analysis', 'settings', 'error', 'weekend', 'seed', 'compare']),
      o: (p.get('o') || '').slice(0, 200) || null,
      from: oneOf(p.get('from'), ['all', 'CJJ', 'NEAR', 'SEOUL', 'TAE', 'ETC']),
      to: oneOf(p.get('to'), ['all', 'dom', 'intl']),
      m: /^\d{4}-(0[1-9]|1[0-2])$/.test(p.get('m') || '') ? p.get('m') : null,
      sort: oneOf(p.get('sort'), ['deal', 'price', 'date', 'rank', 'leave']),
      f: { tier: oneOf(p.get('tier'), ['all', 'candidate', 'deal', 'strong']) || 'all',
        change: oneOf(p.get('ch'), ['all', 'new', 'down']) || 'all',
        weekend: p.get('wk') === '1', cap: integer(p.get('cap'), 0, 100000000) || 0,
        q: (p.get('q') || '').slice(0, 40), leave: integer(p.get('leave'), 0, 30) ?? null },
      st: oneOf(p.get('st'), ['prefer', 'direct', 'one', 'any']),
      lst: oneOf(p.get('lst'), ['prefer', 'direct', 'one', 'any']),
      mn: integer(p.get('mn'), 1, 30), mx: integer(p.get('mx'), 1, 30),
      lmn: integer(p.get('lmn'), 1, 40), lmx: integer(p.get('lmx'), 1, 40),
      span: oneOf(p.get('span'), ['all', 'this', 'next', 'm9', 'm10']),
    };
    if (st.mn > st.mx) st.mx = st.mn;
    if (st.lmn > st.lmx) st.lmx = st.lmn;
    return st;
  }
  function quickQuery(q, kind, home) {
    const next = { ...q, f: { ...q.f } };
    if (['strong', 'deal'].includes(kind)) next.f.tier = kind;
    if (['down', 'new'].includes(kind)) next.f.change = kind;
    if (kind === 'weekend') next.f.weekend = true;
    if (kind === 'leave-one') next.f.leave = 1;
    if (kind === 'direct' || kind === 'home-direct') {
      next.stops = 'direct'; next.longStops = 'direct';
    }
    if (kind === 'home-direct') next.origin = home;
    return next;
  }
  function toggleCompare(ids, id) {
    const clean = [...new Set(ids)].slice(0, 3);
    return clean.includes(id) ? clean.filter(x => x !== id)
      : clean.length < 3 ? [...clean, id] : clean;
  }
  function eligibleLeave(o, limit) {
    return limit == null || (o.annual_leave_confirmed === true
      && Number.isFinite(o.annual_leave) && o.annual_leave <= limit);
  }
  return { tripKeys, encode, decode, quickQuery, toggleCompare, eligibleLeave };
})();
