/* 10월 여행 화면의 날짜 계산을 한국 시간대에서 돌린다.
   CI 와 개발 환경은 UTC 라서, toISOString 이 하루를 당기는 버그가 폰에서만 났다
   (연차 계산 루프가 끝나지 않아 탭이 얼었다). 이 파일은 TZ 를 먼저 고정한다. */
process.env.TZ = 'Asia/Seoul';
import { JSDOM, VirtualConsole } from 'jsdom';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const source = ['travel-state.js', 'compare.js', 'app.js'].map(f => fs.readFileSync(path.join(root, 'web', f), 'utf8')).join('\n');
const data = JSON.parse(fs.readFileSync(path.join(root, 'flight-deals/state/deals.json'), 'utf8'));
const wait = () => new Promise(r => setTimeout(r, 20));
async function boot(hash) {
  const errors = [], vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e));
  const dom = new JSDOM(html, { url: 'https://example.test/Travel/' + hash, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: vc });
  dom.window.fetch = async () => ({ ok: true, json: async () => structuredClone(data) });
  dom.window.scrollTo = () => {};
  dom.window.eval(source); await wait();
  assert.equal(errors.length, 0, errors.map(e => e.message).join('\n'));
  return { w: dom.window, d: dom.window.document };
}
let count = 0;
async function test(name, fn) { await fn(); console.log('ok', name); count++; }
assert.equal(new Date('2026-10-03T00:00:00').getTimezoneOffset(), -540, 'TZ 가 한국(UTC+9)으로 고정돼야 이 테스트가 뜻이 있다');

await test('한국 시간대에서 숙소 화면이 얼지 않고 10/3 체크인 → 10/6 체크아웃을 보여 준다', async () => {
  const { d } = await boot('#t=trip');
  assert(d.querySelector('.hub .tile'), '허브 타일');
  const t0 = Date.now();
  d.querySelector('[data-view="tripstay"]').click();
  assert(Date.now() - t0 < 2000, '화면 전환이 2초 안에 끝난다');
  assert(d.querySelector('.stay'), '숙소 화면');
  const head = d.querySelector('.concept').textContent.replace(/\s+/g, ' ');
  assert.match(head, /10\/03\(토\) → 10\/06\(화\)/, head);
  assert.match(head, /연차 1일/, '10/5 개천절 대체공휴일이 반영돼 연차 1일');
  const bk = d.querySelector('.stay.top a[href*="booking.com"]').getAttribute('href');
  assert.match(bk, /checkin=2026-10-03&checkout=2026-10-06/, bk);
});
await test('출발일을 10/5 로 바꾸면 10/8 귀국 · 연차 3일', async () => {
  const { d } = await boot('#t=trip&v=tripflights');
  d.querySelector('[data-tripdep="2026-10-05"]').click();
  const head = d.querySelector('.concept').textContent.replace(/\s+/g, ' ');
  assert.match(head, /10\/05\(월\) → 10\/08\(목\) · 연차 3일/, head);
  const av = [...d.querySelectorAll('a[href*="aviasales.com/search/"]')].map(a => a.getAttribute('href'));
  assert(av.some(u => /CJJ0510OKA0810/.test(u)), av.join(' '));
});
console.log(`${count} trip date scenarios passed (TZ=Asia/Seoul)`);
