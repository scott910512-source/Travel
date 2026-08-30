# 신뢰도 우선순위: 실시간 확정 > 실시간 메타서치 > 캐시.
# 싼 캐시값이 실시간 확정가를 밀어내면, 눌렀을 때 없는 가격을 보여주게 된다.
import sys, os
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
from core.normalize import source_priority, SOURCE_META, make_offer
from core.merge import merge_offers

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("우선순위")
chk(source_priority("duffel") > source_priority("skyscanner") > source_priority("travelpayouts"),
    "Duffel > Skyscanner > Travelpayouts")
chk(source_priority("모르는provider") == 0, "모르는 provider 는 최하위")

print("\nconfidence 는 가격 등급과 별개")
chk(SOURCE_META["duffel"][0] == "A" and SOURCE_META["duffel"][1] is True,
    "Duffel = A · live")
chk(SOURCE_META["travelpayouts"][0] == "B" and SOURCE_META["travelpayouts"][1] is False,
    "Travelpayouts = B · cache")

print("\n싼 캐시가 비싼 실시간을 밀어내지 않는다")
def mk(src, price):
    return make_offer(src, "ICN", "ZRH", "2026-10-29T13:05:00+09:00", price,
                      return_at="2026-11-08T10:00:00+02:00", airline="EY",
                      outbound_stops=1, return_stops=0)
g = merge_offers([mk("travelpayouts", 500000), mk("duffel", 1200000)])[0]
chk(g["source"] == "duffel" and g["price"] == 1200000,
    "캐시가 70만원 싸도 대표는 실시간 확정가")
chk(g["best_price"] == 500000, "그래도 싼 값은 best_price 로 볼 수 있다")
chk(g["source_confidence"] == "A" and g["live"] is True,
    "대표의 confidence·live 가 함께 따라온다")

print("\n같은 신뢰도면 싼 쪽")
g2 = merge_offers([mk("duffel", 900000), mk("duffel", 800000)])[0]
chk(g2["price"] == 800000, "동일 provider 면 최저가가 대표")
sys.exit(0 if ok else 1)
