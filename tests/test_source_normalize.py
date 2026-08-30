# provider 응답 → 공통 Offer 변환. 통화·왕복 날짜·환승 수를 본다.
import sys, os, json, io
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
from core.normalize import make_offer, trip_stops, sum_stops, nights_between, day
from sources.duffel import DuffelProvider
from sources.skyscanner import parse_rows

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

FX = {"KRW": 1, "USD": 1377}
fixture = json.load(io.open("tests/fixtures/duffel_zrh.json", encoding="utf-8"))
rows = fixture["data"]["offers"]
p = DuffelProvider(token="test", fx=FX)
got = [x for x in (p._offer(r) for r in rows) if x]

print("Duffel")
for o in got:
    print(f"   {o['airline']} {day(o['departure_at'])}→{day(o['return_at'])} "
          f"stops={trip_stops(o)} {o['price']:,}{o['currency']} conf={o['source_confidence']}")

direct = next(o for o in got if o["airline"] == "LX")
one = next(o for o in got if o["price"] == 845617)
usd = next(o for o in got if o.get("fx"))

chk(len(got) == 3, f"환율표에 없는 통화(XYZ)는 버린다 ({len(rows)}→{len(got)})")
chk(p.dropped_fx == 1, "버린 건수를 센다")
chk(direct["outbound_stops"] == 0 and direct["return_stops"] == 0,
    "세그먼트 1개 = 직항 (stops 0)")
# ★ 편도 기준으로 센다. 합(2)으로 세면 "1회 환승" 왕복이 max_stops=1 에
#   걸려 사라진다 — 사용자가 스크린샷으로 보여준 그 편이 정확히 이것이었다.
chk(trip_stops(one) == 1, "가는 편 1회 + 오는 편 1회 = '1회 환승' (합이 아님)")
chk(sum_stops(one) == 2, "합이 필요하면 sum_stops 로 따로 얻는다")
chk(one["outbound_stops"] == 1 and one["return_stops"] == 1,
    "가는 편·오는 편 환승 수를 따로 센다")
chk(nights_between(one["departure_at"], one["return_at"]) == 10, "10박으로 계산")
chk(usd["price"] == int(614 * 1377) and usd["fx"]["from"] == "USD",
    f"USD → KRW 환산 ({usd['price']:,}원)")
chk(usd["fx"]["rate"] == 1377, "환산에 쓴 환율을 기록한다 (감사 가능해야 한다)")
chk(all(o["source"] == "duffel" and o["source_confidence"] == "A"
        and o["live"] for o in got),
    "Duffel = 실시간 · confidence A")

print("\nSkyscanner")
sky = json.load(io.open("tests/fixtures/skyscanner_cjj.json", encoding="utf-8"))
srows = parse_rows(sky, "CJJ", "TPE")
for o in srows:
    print(f"   {o['airline']} {day(o['departure_at'])}→{day(o['return_at'])} "
          f"stops={trip_stops(o)} {o['price']:,}")
chk(len(srows) == 3, f"legIds 가 빈 항목은 버린다 (4→{len(srows)})")
it1 = next(o for o in srows if o["airline"] == "TW" and o["price"] == 398000)
chk(it1["price"] == 398000, "pricingOptions 중 최저가를 쓴다")
chk(it1["booking_url"] == "https://sky.example/it1b", "그 최저가의 딥링크를 쓴다")
chk(all(o["source"] == "skyscanner" and o["source_confidence"] == "B"
        and o["live"] for o in srows),
    "Skyscanner = 실시간 · confidence B")
chk(any(trip_stops(o) == 1 for o in srows), "stopCount 를 보존한다")

print("\n방어")
chk(parse_rows(None, "CJJ", "TPE") == [], "응답이 None 이어도 죽지 않는다")
chk(parse_rows({"content": {}}, "CJJ", "TPE") == [], "빈 응답이어도 죽지 않는다")
o = make_offer("travelpayouts", "CJJ", "NRT", "2026-09-02T09:00:00", 218703)
chk(trip_stops(o) is None, "환승 정보가 없으면 None (0 으로 지어내지 않는다)")
chk(nights_between(o["departure_at"], None) is None, "귀국일 없으면 박수도 None")
sys.exit(0 if ok else 1)
