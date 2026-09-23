"""web/brief-2026-10.json → web/brief-2026-10.pdf

아이폰에서 링크 한 번으로 열고 '파일'에 저장할 수 있게 리포트 부분만
PDF 로 굽는다. 항공편(실시간 캐시)은 넣지 않는다 — 굽는 순간 낡는다.

사진은 Wikimedia Commons(전부 CC BY / BY-SA)라 파일 안에 넣고 마지막
장에 저작자·라이선스·원본 페이지를 적는다.

사용:  python tools/build_brief_pdf.py <사진 폴더> <한글 폰트.ttf> [출력.pdf]
  사진 폴더에는 <ARR>-<i>.w.jpg (없으면 <ARR>-<i>.jpg) 가 있어야 한다.
렌더는 Playwright Chromium. 레포 CI 에서 돌리지 않는다(폰트·사진을
받아야 해서). 자료를 고쳤을 때 손으로 한 번 돌려서 PDF 를 커밋한다.
"""
import base64
import html
import json
import os
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = sys.argv[1] if len(sys.argv) > 1 else "pdfimg"
FONT = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = sys.argv[3] if len(sys.argv) > 3 else os.path.join(R, "web", "brief-2026-10.pdf")

b = json.load(open(os.path.join(R, "web", "brief-2026-10.json"), encoding="utf-8"))
e = html.escape


def img_uri(arr, i):
    for fn in (f"{arr}-{i}.w.jpg", f"{arr}-{i}.jpg"):
        p = os.path.join(IMG, fn)
        if os.path.exists(p):
            return "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()
    return None


font_face = ""
if FONT and os.path.exists(FONT):
    font_face = ("@font-face{font-family:'KR';src:url('file://%s') format('truetype');"
                 "font-weight:100 900}" % os.path.abspath(FONT))

css = f"""
{font_face}
*{{box-sizing:border-box}}
body{{font-family:'KR',-apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;
  color:#16181F;margin:0;font-size:11.5pt;line-height:1.55}}
.page{{page-break-after:always;padding:0}}
.page:last-child{{page-break-after:auto}}
.cover{{height:100%;display:flex;flex-direction:column;justify-content:flex-end;
  background:#5B4BE0;color:#fff;padding:28mm 18mm;min-height:250mm;border-radius:0}}
.cover h1{{font-size:30pt;margin:0 0 6mm;line-height:1.25;letter-spacing:-.02em}}
.cover p{{margin:2mm 0;font-size:12pt;opacity:.92}}
.cover .tag{{display:inline-block;background:rgba(255,255,255,.18);padding:2mm 4mm;
  border-radius:3mm;font-size:10.5pt;margin-bottom:8mm}}
h2{{font-size:19pt;margin:0 0 4mm;letter-spacing:-.02em;color:#16181F}}
h2 .n{{display:inline-block;width:9mm;height:9mm;border-radius:2.5mm;background:#5B4BE0;
  color:#fff;text-align:center;line-height:9mm;font-size:12pt;margin-right:3mm;vertical-align:middle}}
h3{{font-size:15pt;margin:0 0 2mm}}
h3 small{{font-size:10pt;color:#9096A8;font-weight:600;margin-left:2mm}}
h4{{font-size:11pt;margin:4mm 0 1.5mm;color:#5B6072}}
.sub{{color:#5B6072;font-size:10.5pt;margin:0 0 5mm}}
.note{{border-left:3px solid #D07C12;background:#FDF3E5;padding:3mm 4mm;border-radius:2mm;
  margin:0 0 5mm;font-size:10.5pt}}
.note b{{display:block;margin-bottom:1mm}}
ul{{margin:0;padding-left:5mm}}
li{{margin:1mm 0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:4mm}}
.card{{border:1px solid #E9EAF0;border-radius:3mm;overflow:hidden;break-inside:avoid}}
.card img{{width:100%;height:38mm;object-fit:cover;display:block}}
.card .b{{padding:2.5mm 3mm 3mm}}
.card b{{font-size:12pt}}
.card small{{display:block;color:#5B4BE0;font-weight:700;font-size:9.5pt;margin:.5mm 0 1mm}}
.card p{{margin:0;font-size:9.5pt;color:#5B6072;line-height:1.45}}
.ph2{{display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin:2mm 0 4mm}}
.ph2 figure{{margin:0}}
.ph2 img{{width:100%;height:52mm;object-fit:cover;border-radius:2.5mm;display:block}}
.ph2 figcaption{{font-size:8pt;color:#9096A8;margin-top:1mm;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}}
.why{{font-size:11.5pt;margin:0 0 2mm}}
.caution{{font-size:10pt;color:#8A4B00;background:#FDF3E5;padding:2mm 3mm;border-radius:2mm;
  margin-top:3mm}}
.credits{{font-size:9pt;color:#5B6072}}
.credits li{{margin:1.2mm 0;word-break:break-all}}
.foot{{font-size:9pt;color:#9096A8;margin-top:6mm}}
"""

parts = []
# ── 표지 ──
w = b["window"]
parts.append(f"""<div class="page cover">
  <span class="tag">임산부 여행 브리핑 · {e(w['from'][5:].replace('-', '/'))}~{e(w['to'][5:].replace('-', '/'))} · {w['nights']}박 {w['nights']+1}일</span>
  <h1>{e(b['title'])}</h1>
  <p>청주 직항 일본 9곳 + 인천 직항 타이베이 + 제주 — 11곳</p>
  <p>볼거리 · 음식 · 임산부 유의점</p>
  <p style="margin-top:10mm;font-size:10pt;opacity:.8">항공편 가격은 이 문서에 없습니다 — 매 6시간 바뀌므로 앱의 '10월 여행' 탭에서 보세요.</p>
</div>""")

# ── 1. 임산부 공통 체크 ──
pg = b["pregnancy"]
parts.append(f"""<div class="page">
  <h2><span class="n">1</span>임산부 공통 체크</h2>
  <p class="sub">{e(pg['lead'])}</p>
  <ul>{''.join(f'<li>{e(t)}</li>' for t in pg['items'])}</ul>
  <p class="foot">항공사 임산부 규정은 항공사·시기마다 다릅니다. 예약 전 해당 항공사 안내를 꼭 확인하세요. 이 문서는 참고 자료이며 의학적 조언이 아닙니다.</p>
</div>""")

# ── 2. 추천 여행지 요약 ──
dests = sorted(b["destinations"], key=lambda d: d["rank"])
cards = []
for d in dests:
    u = img_uri(d["arr"], 0)
    cards.append(f"""<div class="card">{f'<img src="{u}" alt="">' if u else ''}
      <div class="b"><b>{d['rank']}. {e(d['city'])}</b><small>{e(d['region'])}{' · 청주 직항 ✈' if d.get('cjj_direct') else ''}</small>
      <p>{e(d['why'])}</p></div></div>""")
parts.append(f"""<div class="page">
  <h2><span class="n">2</span>추천 여행지</h2>
  <p class="sub">임산부 기준 순서 — 비행이 짧고, 평지가 많고, 익힌 음식이 많은 곳부터.</p>
  <div class="grid">{''.join(cards)}</div>
</div>""")

# ── 3. 상세 브리핑 (여행지마다 한 장) ──
credits = []
for d in dests:
    figs = []
    for i, ph in enumerate(d.get("photos", [])[:2]):
        u = img_uri(d["arr"], i)
        if not u:
            continue
        figs.append(f"""<figure><img src="{u}" alt=""><figcaption>{e(ph.get('credit',''))} · {e(ph.get('license',''))} · Wikimedia Commons</figcaption></figure>""")
        credits.append((d["city"], ph))
    parts.append(f"""<div class="page">
  <h2><span class="n">3</span>상세 브리핑 — {e(d['city'])} <small style="font-size:10pt;color:#9096A8">{e(d['region'])}{' · 청주 직항 ✈' if d.get('cjj_direct') else ''}</small></h2>
  <div class="ph2">{''.join(figs)}</div>
  <p class="why">{e(d['why'])}</p>
  <h4>볼거리</h4><ul>{''.join(f'<li><b>{e(t)}</b> — {e(x)}</li>' for t, x in d['spots'])}</ul>
  <h4>음식</h4><ul>{''.join(f'<li><b>{e(t)}</b> — {e(x)}</li>' for t, x in d['foods'])}</ul>
  {f'<p class="caution">⚠ {e(d["caution"])}</p>' if d.get('caution') else ''}
</div>""")

# ── 사진 출처 ──
parts.append(f"""<div class="page">
  <h2>사진 출처</h2>
  <p class="sub">모두 Wikimedia Commons 의 크리에이티브 커먼즈 라이선스 사진입니다. 저작자와 라이선스를 그대로 표기합니다.</p>
  <ul class="credits">{''.join(f'<li><b>{e(c)}</b> — {e(p.get("credit",""))} · {e(p.get("license",""))} · {e(p.get("page",""))}</li>' for c, p in credits)}</ul>
  <p class="foot">만든 곳: 항공권 데일리 스캐너 · 여행지 설명은 사람이 쓴 참고 자료입니다.</p>
</div>""")

doc = f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(parts)}</body></html>"
html_path = os.path.splitext(OUT)[0] + ".src.html"
open(html_path, "w", encoding="utf-8").write(doc)
print("html", html_path, len(doc) // 1024, "KB")

# ── PDF ──
import subprocess  # noqa: E402
js = f"""
const pw = require('/opt/node22/lib/node_modules/playwright');
(async () => {{
  const b = await pw.chromium.launch({{ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' }});
  const p = await b.newPage();
  await p.goto('file://{html_path}', {{ waitUntil: 'load' }});
  await p.evaluate(() => document.fonts.ready);
  await p.pdf({{ path: '{OUT}', format: 'A4', printBackground: true,
    margin: {{ top: '14mm', bottom: '14mm', left: '14mm', right: '14mm' }} }});
  await b.close();
}})();
"""
subprocess.run(["node", "-e", js], check=True)
print("pdf", OUT, os.path.getsize(OUT) // 1024, "KB")
