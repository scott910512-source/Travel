# "며칠째 가격이 안 들어오는가" — 다시 채워야 할 시점을 화면이 알려면 필요하다.
# route_stats 는 오늘 offer 가 있는 노선만 만들어서, 끊긴 노선은 거기서 사라진다.
import sys, os
from datetime import date, timedelta
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

D = lambda n: str(date.today() - timedelta(days=n))
ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

daily = {
    "CJJ-NRT": {D(0): 210000, D(1): 215000, D(3): 230000},   # 오늘도 들어옴
    "CJJ-CTS": {D(6): 340000, D(8): 355000},                 # 6일째 끊김
    "ICN-ZRH": {D(0): 845617},                               # 오늘 처음
    "CJJ-DSN": {},                                           # 빈 기록
    "BROKEN":  {"날짜아님": 1},                                # 파싱 불가
}
f = S.route_freshness(daily)
print("결과:", {k: v["days_ago"] for k, v in f.items()})

print("검사")
chk(f["CJJ-NRT"]["days_ago"] == 0, "오늘 들어온 노선은 0일")
chk(f["CJJ-CTS"]["days_ago"] == 6, "6일 전이 마지막이면 6일")
chk(f["CJJ-CTS"]["days_tracked"] == 2, "기록된 날짜 수도 센다")
chk(f["ICN-ZRH"]["days_ago"] == 0, "오늘 처음 들어온 노선도 잡는다")
chk("CJJ-DSN" not in f, "기록이 비어 있으면 넣지 않는다")
chk("BROKEN" not in f, "날짜가 깨져도 죽지 않고 건너뛴다")

print("\n오늘 offer 가 없어도 남는가 (이게 핵심)")
# route_stats 는 오늘 offer 기준이라 CTS 가 빠진다
routes = S.route_stats([{"dep": "CJJ", "arr": "NRT", "city": "도쿄",
                         "region": "일본", "price_krw": 210000}], daily, {})
chk("CJJ-CTS" not in routes, "route_stats 에서는 끊긴 노선이 사라진다")
chk("CJJ-CTS" in f, "route_freshness 에는 남는다 — 그래서 '6일째 없음' 을 말할 수 있다")

print("\n방어")
chk(S.route_freshness({}) == {}, "빈 입력")
chk(S.route_freshness(None) == {}, "None 입력")
chk(S.route_freshness({"X": "문자열"}) == {}, "dict 가 아닌 값이 와도 죽지 않는다")
sys.exit(0 if ok else 1)
