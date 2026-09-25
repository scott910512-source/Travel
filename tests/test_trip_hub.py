"""10월 여행 탭 — 컨셉이 정해진 뒤의 큰 메뉴.
허브는 메뉴 7줄이고, 항공편·숙소·준비물은 각각 뒤로가기가 있는 화면이며,
예전 목적지 비교 화면과 PDF 는 그대로 남아 있어야 한다."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "web/app.js"), encoding="utf-8").read()
TS = open(os.path.join(ROOT, "web/travel-state.js"), encoding="utf-8").read()
fails = 0
def chk(c, m):
    global fails
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c: fails += 1

hub = re.search(r"function viewTrip\(\) \{(.*?)\n\}", JS, re.S).group(1)
chk(hub.count("row(") == 7, "허브 메뉴가 7줄이다")
for v in ("tripflights", "tripstay", "tripprep", "tripall"):
    chk(f"'{v}'" in hub, f"허브에 {v} 가 있다")
    chk(f"S.view === '{v}'" in JS, f"render 가 {v} 를 그린다")
    chk(f"'{v}'" in TS, f"공유 링크 허용 목록에 {v} 가 있다")
for page in ("okinawa-2026-10.html", "okinawa-2026-10-show.html", "okinawa-2026-10-food.html"):
    chk(page in JS, f"허브가 {page} 로 연결한다")

trip = re.search(r"const TRIP = \{(.*?)\n\};", JS, re.S).group(1)
chk("dep: 'CJJ'" in trip and "arr: 'OKA'" in trip and "nights: 3" in trip, "컨셉이 청주 → 오키나와 3박으로 고정돼 있다")
chk(re.findall(r"'2026-10-0[345]'", trip) == ["'2026-10-03'", "'2026-10-04'", "'2026-10-05'"], "출발일 후보가 10/3·4·5 다")

stays = re.search(r"const TRIP_STAYS = \[(.*?)\n\];", JS, re.S).group(1)
names = re.findall(r"\{ n: '([^']+)'", stays)
chk(len(names) >= 8, f"숙소 후보가 8곳 이상이다 ({len(names)})")
chk(len(set(names)) == len(names), "숙소 이름이 겹치지 않는다")
for key in ("q:", "area:", "tier:", "band:", "hosp:", "pro:", "con:"):
    chk(stays.count(key) == len(names), f"모든 숙소에 {key} 가 있다")
chk("온나" in names[0] or "온나" in stays.split("},")[0], "1순위가 온나(일정표 기준)다")
chk("대략값" in JS, "숙소 요금이 대략값임을 화면이 말한다")
chk("checkin=${ci}&checkout=${co}" in JS, "예약 링크에 체크인·체크아웃 날짜가 들어간다")
chk("leaveDays(" in JS and "S.data.holidays" in JS, "연차 계산이 스캐너의 공휴일표를 쓴다")
chk("S.tab = (S.view && S.view.indexOf('trip') === 0) ? 'trip' : 'home'" in JS, "여행 하위 화면의 뒤로가기는 여행 허브로 간다")
chk("function viewTripAll()" in JS and 'href="brief-2026-10.pdf"' in JS, "예전 목적지 비교 화면과 PDF 링크가 남아 있다")
print("실패", fails)
sys.exit(1 if fails else 0)
