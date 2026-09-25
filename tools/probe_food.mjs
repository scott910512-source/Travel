#!/usr/bin/env node
/* 식당 리스트의 구글 평점·리뷰 수·리뷰 사진을 *한 번* 조회해 저장본으로 남긴다.
   - 입력: web/okinawa-2026-10-food.html 안의 식당 배열 R
   - 출력: web/okinawa-2026-10-food.json (평점·리뷰 수·지도 링크·사진 경로)
           web/food-photos/<id>-<n>.jpg (이용자 사진, 최대 2장, 폭 400)
   - 키: MAPS_SERVER_KEY (Places API 웹서비스용 · 리퍼러 제한 없는 키). 없으면
         MAPS_BROWSER_KEY 로 Referer 를 붙여 시도하고, 거부되면 왜 안 되는지 적는다.
   - 키는 로그·파일에 절대 쓰지 않는다. 결과 JSON 에도 키가 들어가지 않는다.
   워크플로의 probe=food 에서만 돈다(사람이 누를 때). 자동 반복 조회는 없다. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const ROOT = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const HTML = path.join(ROOT, 'web/okinawa-2026-10-food.html');
const OUT = path.join(ROOT, 'web/okinawa-2026-10-food.json');
const PHOTO_DIR = path.join(ROOT, 'web/food-photos');
const SITE = 'https://scott910512-source.github.io/Travel/';
const MAX_PHOTOS = 2, PHOTO_W = 400;

const serverKey = (process.env.MAPS_SERVER_KEY || '').trim();
const browserKey = (process.env.MAPS_BROWSER_KEY || '').trim();
if (!serverKey && !browserKey) {
  console.error('::error::MAPS_SERVER_KEY (권장) 또는 MAPS_BROWSER_KEY 가 없습니다. Settings > Secrets > Actions.');
  process.exit(1);
}
const key = serverKey || browserKey;
const headers = serverKey ? {} : { Referer: SITE };
if (!serverKey) console.log('::notice::MAPS_SERVER_KEY 없음 — 브라우저 키로 시도합니다 (웹서비스는 리퍼러 제한 키를 거부할 수 있음)');

export function extractList(html) {
  const i = html.indexOf('const R = [');
  if (i < 0) throw new Error('식당 배열(const R = [)을 못 찾았다');
  const j = html.indexOf('\n];', i);
  const lit = html.slice(i + 'const R = '.length, j + 2);
  return new Function('return ' + lit)();
}
const idOf = k => crypto.createHash('md5').update(k).digest('hex').slice(0, 10);

async function gjson(url) {
  const r = await fetch(url, { headers });
  const j = await r.json();
  if (j.status === 'REQUEST_DENIED') {
    const msg = j.error_message || '';
    console.error('::error::구글이 요청을 거부했습니다: ' + msg.replace(key, '***'));
    if (/referer|referrer/i.test(msg)) console.error('::error::리퍼러 제한 키는 Places 웹서비스에서 못 씁니다. 제한 없는(또는 IP 제한) 키를 MAPS_SERVER_KEY 로 등록하세요.');
    process.exit(1);
  }
  return j;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const R = extractList(fs.readFileSync(HTML, 'utf8'));
  fs.mkdirSync(PHOTO_DIR, { recursive: true });
  const prev = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, 'utf8')) : null;
  const data = {}; let done = 0, fail = 0, photos = 0;
  for (const x of R) {
    const k = x.j || x.n, id = idOf(k);
    const q = encodeURIComponent(k + ' 沖縄');
    const f = await gjson(`https://maps.googleapis.com/maps/api/place/findplacefromtext/json?input=${q}&inputtype=textquery&fields=place_id&language=ko&key=${key}`);
    const pid = f.candidates && f.candidates[0] && f.candidates[0].place_id;
    if (!pid) { data[k] = { err: f.status || 'ZERO_RESULTS' }; fail++; console.log(`  못 찾음  ${x.n}`); continue; }
    const d = await gjson(`https://maps.googleapis.com/maps/api/place/details/json?place_id=${pid}&fields=name,rating,user_ratings_total,url,photos&language=ko&key=${key}`);
    const p = d.result;
    if (!p) { data[k] = { err: d.status || 'NO_RESULT' }; fail++; console.log(`  상세 실패 ${x.n}`); continue; }
    const rec = { rating: p.rating || 0, total: p.user_ratings_total || 0, url: p.url || '', gname: p.name || '', photos: [] };
    for (const [n, ph] of (p.photos || []).slice(0, MAX_PHOTOS).entries()) {
      try {
        const r = await fetch(`https://maps.googleapis.com/maps/api/place/photo?maxwidth=${PHOTO_W}&photo_reference=${ph.photo_reference}&key=${key}`, { headers });
        if (!r.ok) continue;
        const buf = Buffer.from(await r.arrayBuffer());
        const file = `${id}-${n}.jpg`;
        fs.writeFileSync(path.join(PHOTO_DIR, file), buf);
        rec.photos.push({ url: `food-photos/${file}`, attr: (ph.html_attributions || []).join(' ').replace(/<[^>]+>/g, '') });
        photos++;
      } catch (e) { console.log(`  사진 실패 ${x.n}: ${String(e.message).replace(key, '***')}`); }
    }
    data[k] = rec; done++;
    console.log(`  ${String(rec.rating).padEnd(4)} 리뷰 ${String(rec.total).padStart(5)}  ${x.n}`);
    await sleep(80);
  }
  // 이전 저장본에만 있던 사진 파일은 지운다(목록에서 빠진 식당).
  const keep = new Set(Object.values(data).flatMap(r => (r.photos || []).map(p => path.basename(p.url))));
  for (const f of fs.readdirSync(PHOTO_DIR)) if (!keep.has(f)) fs.unlinkSync(path.join(PHOTO_DIR, f));
  const out = { ts: new Date().toISOString(), source: 'Google Places API (web service)', by: 'workflow probe=food',
    min_reviews: 10, min_rating: 4.3, count: R.length, found: done, missing: fail, photos, data };
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1) + '\n');
  const kb = Math.round(fs.statSync(OUT).size / 1024);
  console.log(`저장본: ${done} 찾음 · ${fail} 못 찾음 · 사진 ${photos}장 · ${kb}KB${prev ? ` (이전 저장본 ${prev.ts})` : ''}`);
  if (JSON.stringify(out).includes(key)) { console.error('::error::결과에 키가 들어갔다'); process.exit(1); }
}
if (process.argv[1] && process.argv[1].endsWith('probe_food.mjs')) main().catch(e => { console.error('::error::' + String(e.message).replace(key, '***')); process.exit(1); });
