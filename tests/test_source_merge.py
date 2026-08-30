# 같은 항공편이 여러 provider 에서 온다. 합치되 정보를 잃지 않아야 한다.
import sys, os
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
from core.normalize import make_offer
from core.merge import merge_offers, merge_stats, dedupe_key

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

def mk(src, price, air="EY", d0="2026-10-29T13:05:00+09:00",
       d1="2026-11-08T10:00:00+02:00", ob=1, rb=0):
    return make_offer(src, "ICN", "ZRH", d0, price, return_at=d1, airline=air,
                      outbound_stops=ob, return_stops=rb)

print("병합")
rows = [mk("travelpayouts", 845617), mk("duffel", 910000), mk("skyscanner", 880000)]
got = merge_offers(rows)
chk(len(got) == 1, "같은 편 3건이 1건으로")
g = got[0]
chk(g["source"] == "duffel", "대표는 신뢰도 우선 (Duffel)")
chk(g["price"] == 910000, "대표 가격은 대표 provider 의 값")
chk(g["best_price"] == 845617, "최저가는 best_price 로 따로 보존")
chk(len(g["sources"]) == 3, "provider 별 가격을 전부 남긴다")
chk({s["source"] for s in g["sources"]} == {"duffel", "skyscanner", "travelpayouts"},
    "어느 provider 에서 얼마였는지 추적 가능")
print("  ", merge_stats(rows, got))

print("\n같은 편으로 안 묶어야 하는 것")
chk(len(merge_offers([mk("duffel", 900000, ob=1), mk("duffel", 900000, ob=0)])) == 2,
    "환승 수가 다르면 다른 편")
chk(len(merge_offers([mk("duffel", 900000), mk("duffel", 900000, air="LX")])) == 2,
    "항공사가 다르면 다른 편")
chk(len(merge_offers([mk("duffel", 900000),
                      mk("duffel", 900000, d1="2026-11-09T10:00:00+02:00")])) == 2,
    "귀국일이 다르면 다른 편")

print("\n타임존")
a = mk("duffel", 900000, d0="2026-10-29T13:05:00+09:00")
b = mk("travelpayouts", 845617, d0="2026-10-29T04:05:00+00:00")
chk(dedupe_key(a) == dedupe_key(b),
    "같은 날짜면 시각 표기가 달라도 같은 편 (provider 마다 타임존이 다르다)")

print("\n이름 없는 행")
c = mk("travelpayouts", 845000, air="?")
d = mk("duffel", 910000, air="EY")
# '?' 는 키가 달라 따로 묶인다 — 이름 채우기는 같은 키로 묶였을 때만
got = merge_offers([mk("duffel", 910000, air="?"), mk("duffel", 905000, air="?")])
chk(len(got) == 2 or got[0]["airline"] == "?", "이름 없는 값을 지어내지 않는다")

print("\n빈 입력")
chk(merge_offers([]) == [], "빈 리스트도 처리")
sys.exit(0 if ok else 1)
