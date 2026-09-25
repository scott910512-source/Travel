"""오키나와 3박 4일 · 청주 출발 · 임산부 렌터카 — 자동재생 시뮬레이션 브리핑.

사진을 파일 안에 넣은 단일 HTML 을 만든다(아이폰 '파일' 에서 열어도 됨).
슬라이드는 7초마다 자동으로 넘어가고, 화면을 누르면 멈춘다.

사용: python tools/build_okinawa_show.py <사진 폴더> <photos.json> [출력.html]
  사진 폴더에는 <key>.jpg, photos.json 에는 {key: {credit, license, page}}.
  사진이 없는 슬라이드는 단색 배경으로 나간다 — 지어내지 않는다.
CI 에서 돌리지 않는다. 손으로 굽고 산출물을 커밋한다.
"""
import base64
import html
import json
import os
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = sys.argv[1] if len(sys.argv) > 1 else "okiimg"
META = sys.argv[2] if len(sys.argv) > 2 else "photos3.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else os.path.join(R, "web", "okinawa-2026-10-show.html")
e = html.escape

try:
    photos = json.load(open(META, encoding="utf-8"))
except Exception:
    photos = {}


def uri(key):
    for fn in (f"{key}.w.jpg", f"{key}.jpg"):
        p = os.path.join(IMG, fn)
        if os.path.exists(p):
            return "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()
    return None


# ── 슬라이드 ──────────────────────────────────────────────
# (사진키, 상단 라벨, 제목, 본문, 임산부 메모) — 라벨 None 이면 표지
SLIDES = [
 ("cover", None, "오키나와 3박 4일", "청주 출발 · 임산부 · 렌터카 · 10월 초\n식사 포함 시뮬레이션 브리핑", ""),
 ("cjj", "1일차 · 아침", "청주공항 출발", "집에서 20~30분. 작은 공항이라 수속·보안검색이 빠릅니다. 국제선은 2시간 전 도착이면 충분합니다.\n청주→나하 직항 약 2시간 30분.",
  "탑승 전 항공사 임산부 규정 확인(32주 미만 제한 없음 · 32~36주 진단서). 복도석 요청."),
 ("oka", "1일차 · 낮", "나하공항 도착 · 렌터카", "수하물 → 렌터카 셔틀 10~15분 → 인수 30~40분. 국제운전면허증 + 한국 면허 + 여권.\n좌측통행·우핸들. 처음 10분은 천천히.",
  "인수 서류는 동행자가. 임산부는 대기실에서 물 한 잔."),
 ("umikaji", "1일차 · 점심", "우미카지 테라스 (세나가지마)", "공항에서 15분. 바다를 보는 계단식 카페 거리.\n타코라이스 · 오키나와 소바 · 익힌 재료 포케.",
  "아래층 가게로(계단 적게). 생선 포케는 익힌 참치·연어 메뉴."),
 ("hotel", "1일차 · 오후", "온나 리조트 체크인", "오키나와 자동차도 나하 IC → 이시카와 IC, 약 50분. 3박 한 곳 — 짐을 다시 싸지 않습니다.\n체크인 후 1~2시간 휴식.",
  "중간 휴게(이게이 PA)에서 한 번 걷기. 오후 4시 전엔 밖에 안 나감."),
 ("manza", "1일차 · 석양", "만자모", "호텔에서 10분. 코끼리 바위 절벽 위 평탄한 데크 한 바퀴 15~20분.",
  "난간 있는 데크만. 바람이 세니 얇은 겉옷."),
 ("nakamura", "1일차 · 저녁", "나카무라소바", "오키나와 소바 노포. 소키(돼지갈비)소바 · 아사(해초)소바. 국물까지 익힌 음식.\n19시 전 마감인 날이 있어 일찍.",
  "짠 편이라 국물은 반만. 대안: 호텔 레스토랑."),
 ("churaumi", "2일차 · 오전", "츄라우미 수족관", "호텔에서 55분. 개장 8:30, 10시 전이면 한산. 고래상어 대수조 앞 벤치.\n전부 실내·엘리베이터. 2시간.",
  "돌고래쇼는 야외 계단석 — 그늘 자리로. 원내 이동은 무료 전기차."),
 ("kishimoto", "2일차 · 점심", "기시모토 식당 (모토부)", "1905년 오키나와 소바 원조. 소바 + 주시(오키나와식 밥).\n줄이 길면 야치문 거리 분점.",
  "줄은 동행자가 서고 임산부는 차에서 대기."),
 ("bise", "2일차 · 오후", "비세 후쿠기 가로수길", "평탄한 흙길 그늘 산책 20~30분. 끝에 작은 해변.",
  "이 여행에서 임산부 산책에 가장 맞는 곳. 해변은 발만."),
 ("kouri", "2일차 · 늦은 오후", "코우리 대교 · 카페", "바다 위 2km 다리. 섬 초입 카페에서 주스·빙수.\n호텔까지 50분.",
  "카페인은 하루 1잔 이내. 오션타워 계단은 생략."),
 ("zanpa", "3일차 · 오전", "잔파곶", "호텔에서 25분. 등대 아래 잔디와 산책로만, 30분.",
  "등대 계단은 생략."),
 ("ryukyumura", "3일차 · 늦은 오전", "류큐무라", "옛 민가 · 에이사 공연 · 사탕수수 주스. 평지, 1시간, 그늘 많음.",
  "한낮 전에 나옵니다."),
 ("taco", "3일차 · 점심", "A&W 미하마점 · 타코라이스", "오키나와에만 있는 드라이브인 버거. 루트비어는 카페인 없음.\n대안: 포케 카페 · 타코스.",
  ""),
 ("amvillage", "3일차 · 오후", "아메리칸 빌리지 (실내)", "한낮은 실내. 아기용품(이온몰 라이카무는 통째로 실내) · 관람차 · 카페. 2~3시간 느긋하게.",
  "걷다 앉다 반복. 물 자주."),
 ("sunset", "3일차 · 석양", "선셋비치", "아메리칸 빌리지 바로 옆. 석양 18시 전후.\n저녁: 킨노쿠라(오키나와 가정식) 또는 이온몰 푸드코트. 호텔까지 35분.",
  "발만 담그기. 야간 운전은 천천히."),
 ("shuri", "4일차 · 오전", "슈리성 공원", "체크아웃 후 55분. 슈레이몬 · 성벽 산책, 경사가 있어 40분 이내.\n점심: 슈리소바(12시 전).",
  "컨디션이 별로면 이 항목은 빼고 국제거리로 바로."),
 ("kokusai", "4일차 · 낮", "국제거리 · 마키시 시장", "기념품(친스코 · 자색고구마 타르트 · 시콰사). 시장 2층 식당은 익힌 요리만.\n1시간 이내 → 주유 → 렌터카 반납 → 항공편 2시간 전 공항.",
  "사람이 많으니 짧게. 아케이드 안은 그늘."),
 ("cjj", "4일차 · 저녁", "청주공항 도착 · 집까지 20분", "인천이었으면 여기서 2시간을 더 갔을 겁니다.\n총 운전 약 265km · 한 번에 60분 넘는 구간 없음 · 식사 8끼 전부 익힌 메뉴.",
  "수고했어요. 다음 진료 때 여행 다녀온 걸 말해 두세요."),
]

css = """
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#0f1120;color:#fff;
font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",Pretendard,"Noto Sans KR",system-ui,sans-serif;overflow:hidden}
#stage{position:fixed;inset:0}
.sl{position:absolute;inset:0;opacity:0;transition:opacity .9s;pointer-events:none}
.sl.on{opacity:1;pointer-events:auto}
.sl .bg{position:absolute;inset:0;background-size:cover;background-position:center;transform:scale(1.06);
 transition:transform 9s linear}
.sl.on .bg{transform:scale(1.18)}
.sl .bg.none{background:linear-gradient(160deg,#5B4BE0,#1c1f3a)}
.sl .shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25) 0%,rgba(0,0,0,0) 35%,rgba(0,0,0,.72) 70%,rgba(0,0,0,.9) 100%)}
.sl .tx{position:absolute;left:0;right:0;bottom:0;padding:0 22px calc(72px + env(safe-area-inset-bottom));text-shadow:0 1px 4px rgba(0,0,0,.6)}
.lbl{display:inline-block;background:rgba(91,75,224,.9);padding:5px 10px;border-radius:8px;font-size:12.5px;font-weight:800;margin-bottom:10px}
.tx h1{margin:0 0 8px;font-size:30px;line-height:1.2;letter-spacing:-.03em}
.tx p{margin:0;font-size:15px;line-height:1.55;white-space:pre-line;color:#e8e8f0}
.preg{margin-top:10px;background:rgba(253,243,229,.92);color:#5a3a00;border-radius:10px;padding:8px 11px;font-size:13.5px;line-height:1.5;text-shadow:none}
.credit{position:absolute;left:14px;top:calc(12px + env(safe-area-inset-top));font-size:10.5px;color:rgba(255,255,255,.75);
 max-width:70%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-shadow:0 1px 3px rgba(0,0,0,.8)}
.cover .tx{bottom:auto;top:50%;transform:translateY(-50%);text-align:center;padding-bottom:0}
.cover h1{font-size:44px}
.cover p{font-size:17px}
#bar{position:fixed;left:0;right:0;top:0;height:4px;background:rgba(255,255,255,.2);z-index:5}
#bar i{display:block;height:100%;width:0;background:#fff;transition:width .2s linear}
#ctl{position:fixed;left:0;right:0;bottom:0;display:flex;gap:8px;align-items:center;justify-content:space-between;
 padding:10px 14px calc(12px + env(safe-area-inset-bottom));z-index:5;background:linear-gradient(0deg,rgba(0,0,0,.6),rgba(0,0,0,0))}
#ctl button{font:inherit;font-weight:800;font-size:13px;color:#fff;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);
 border-radius:999px;min-height:40px;padding:0 14px;cursor:pointer;backdrop-filter:blur(8px)}
#ctl .n{font-family:ui-monospace,Menlo,monospace;font-size:12px;opacity:.85}
#hint{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,.6);padding:12px 18px;border-radius:14px;
 font-size:14px;z-index:6;pointer-events:none;opacity:0;transition:opacity .3s}
#hint.on{opacity:1}
/* .sl .tx (0,2,0) 이 기본 패딩을 잡고 있어 .tx 만으로는 못 이긴다 — 같은 특이도로 쓴다 */
@media(min-width:800px){.tx h1{font-size:40px}.tx p{font-size:18px}.sl .tx{padding-left:6vw;padding-right:40vw}.sl.cover .tx{padding-right:6vw}}
@media(min-width:1400px){.tx h1{font-size:52px}.tx p{font-size:22px}.preg{font-size:17px}#ctl button{min-height:52px;font-size:16px;padding:0 20px}}
"""

sl_html = []
credits = []
for i, (key, lbl, h1, body, preg) in enumerate(SLIDES):
    title = h1
    u = uri(key)
    cred = photos.get(key)
    if u and cred:
        credits.append((title, cred))
    bg = f'<div class="bg" style="background-image:url({u})"></div>' if u else '<div class="bg none"></div>'
    cover = " cover" if lbl is None else ""
    sl_html.append(f"""<section class="sl{cover}" data-i="{i}">{bg}<div class="shade"></div>
  {f'<div class="credit">{e(cred["credit"])} · {e(cred["license"])} · Wikimedia Commons</div>' if (u and cred) else ''}
  <div class="tx">{f'<span class="lbl">{e(lbl)}</span><br>' if lbl else ''}<h1>{e(h1)}</h1><p>{e(body)}</p>
  {f'<div class="preg">🤰 {e(preg)}</div>' if preg else ''}</div></section>""")

# 출처 슬라이드
cred_list = "".join(f"<li>{e(t)} — {e(c['credit'])} · {e(c['license'])}</li>" for t, c in credits)
sl_html.append(f"""<section class="sl" data-i="{len(SLIDES)}"><div class="bg none"></div><div class="shade"></div>
  <div class="tx" style="bottom:auto;top:12%"><span class="lbl">사진 출처</span>
  <p style="font-size:12.5px;line-height:1.6">모두 Wikimedia Commons 의 크리에이티브 커먼즈 사진입니다.</p>
  <ul style="font-size:12px;line-height:1.55;padding-left:18px;margin:8px 0 0;max-height:60vh;overflow:auto">{cred_list}</ul>
  <p style="font-size:12px;margin-top:10px;opacity:.8">일정·식당은 참고 자료입니다. 영업시간과 항공사 임산부 규정은 예약 전 확인하세요.</p></div></section>""")

js = """
const sls=[...document.querySelectorAll('.sl')];let i=0,playing=true,t0=0,raf=null;const DUR=7000;
const bar=document.querySelector('#bar i'),num=document.getElementById('num'),btn=document.getElementById('play'),hint=document.getElementById('hint');
function show(n){i=(n+sls.length)%sls.length;sls.forEach((s,k)=>s.classList.toggle('on',k===i));num.textContent=(i+1)+' / '+sls.length;t0=performance.now();}
function tick(now){if(playing){const p=Math.min(1,(now-t0)/DUR);bar.style.width=(p*100)+'%';if(p>=1){if(i===sls.length-1){setPlay(false);}else show(i+1);}}raf=requestAnimationFrame(tick);}
function setPlay(v){playing=v;btn.textContent=v?'⏸ 멈춤':'▶ 재생';if(v)t0=performance.now()-(parseFloat(bar.style.width)||0)/100*DUR;
 hint.textContent=v?'자동 재생':'멈춤 — 화면을 누르면 재생';hint.classList.add('on');setTimeout(()=>hint.classList.remove('on'),900);}
document.getElementById('stage').addEventListener('click',()=>setPlay(!playing));
btn.addEventListener('click',ev=>{ev.stopPropagation();setPlay(!playing);});
document.getElementById('prev').addEventListener('click',ev=>{ev.stopPropagation();show(i-1);});
document.getElementById('next').addEventListener('click',ev=>{ev.stopPropagation();show(i+1);});
let sx=null;document.addEventListener('touchstart',e=>{sx=e.touches[0].clientX});
document.addEventListener('touchend',e=>{if(sx==null)return;const dx=e.changedTouches[0].clientX-sx;sx=null;if(Math.abs(dx)>50)show(dx<0?i+1:i-1);});
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')show(i+1);else if(e.key==='ArrowLeft')show(i-1);else if(e.key===' '){e.preventDefault();setPlay(!playing);}});
// 전체화면 — 테슬라·PC 브라우저용. 못 하는 브라우저(iOS 사파리)면 버튼을 숨긴다.
const fs=document.getElementById('fs');
if(!document.documentElement.requestFullscreen) fs.style.display='none';
fs.addEventListener('click',ev=>{ev.stopPropagation();document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen().catch(()=>{});});
show(0);raf=requestAnimationFrame(tick);
"""

doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="dark">
<title>오키나와 3박 4일 · 청주 출발 시뮬레이션</title><style>{css}</style></head><body>
<div id="bar"><i></i></div>
<div id="stage">{''.join(sl_html)}</div>
<div id="hint"></div>
<div id="ctl"><button id="prev">‹ 이전</button><span class="n"><span id="num"></span> · 7초마다 넘어감 · 화면 탭 = 멈춤/재생</span><button id="next">다음 ›</button><button id="play">⏸ 멈춤</button><button id="fs" title="전체화면">⛶</button></div>
<script>{js}</script></body></html>"""
open(OUT, "w", encoding="utf-8").write(doc)
print("out", OUT, os.path.getsize(OUT) // 1024, "KB · 슬라이드", len(sl_html), "· 사진", len(credits))
