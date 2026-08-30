# 이 앱의 가격은 "남이 검색해서 캐시에 남은 값" 이다.
# 언제 남은 값인지를 잃어버리면, 사흘 지난 값과 오늘 값이 같은 얼굴이 된다.
import sys, os
from datetime import date, timedelta, datetime, timezone
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

D = lambda n: (date.today() + timedelta(days=n)).strftime("%Y-%m-%d")
FOUND = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

def fake_call(path, params, retries=2):
    if path == "/v2/prices/latest":
        return True, {"data": [{
            "value": 980000, "origin": "ICN", "destination": "ZRH",
            "airline": "MU", "flight_number": "5041", "number_of_changes": 1,
            "depart_date": D(60), "return_date": D(70),
            "found_at": FOUND}]}, None
    raise AssertionError(path)

S.call = fake_call; S.REQ_SLEEP = 0; S.time.sleep = lambda *a: None
out, _ = S.fetch_latest("ICN", "ZRH", "취리히", "유럽",
                        S.SWISS_NIGHTS, S.SWISS_WINDOW)

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print(f"수집 {len(out)}건")
print("검사")
chk(len(out) == 1, "왕복 1건 수집")
chk(out[0].get("found_at") == FOUND,
    f"found_at 을 버리지 않고 싣는다 ({out[0].get('found_at')})")
chk("found_at" in S.OFFER_FIELDS, "deals.json 직렬화 필드에 포함된다")

# found_at 이 없는 소스(캘린더)에서는 None 으로 둔다
CAL = {"data": {D(60): {
    "price": 900000, "airline": "LX", "departure_at": D(60) + "T13:00:00+09:00",
    "return_at": D(70) + "T10:00:00+02:00", "number_of_changes": 0}}}
def routed(path, params, retries=2):
    if path == "/v1/prices/calendar":
        return True, CAL, None
    return True, {"data": []}, None          # v3 등은 빈 리스트
S.call = routed
S.ERRORS.clear()
cal, _ = S.fetch_route("ICN", "GVA", "제네바", "유럽",
                       flex=S.SWISS_NIGHTS, window=S.SWISS_WINDOW)
chk(len(cal) >= 1 and cal[0].get("found_at") is None,
    "안 주는 소스에서는 None 으로 둔다 (지어내지 않는다)")

# ★ 리스트를 줘야 할 엔드포인트가 dict 를 주면?
# 예전에는 rows[0] 에서 그대로 터져 스캔 전체가 죽었다. 한 노선의 응답
# 하나가 나머지 20개 노선 결과를 날리면 안 된다.
S.ERRORS.clear()
def wrong_shape(path, params, retries=2):
    if path == "/v1/prices/calendar":
        return True, CAL, None
    return True, {"data": {"ZRH": {"0": {"price": 1}}}}, None   # dict!
S.call = wrong_shape
try:
    got, _ = S.fetch_route("ICN", "GVA", "제네바", "유럽",
                           flex=S.SWISS_NIGHTS, window=S.SWISS_WINDOW)
    crashed = False
except Exception as e:
    crashed, got = True, []
chk(not crashed, "응답 모양이 이상해도 스캔이 죽지 않는다")
chk(len(got) >= 1, "그 노선의 정상 소스 결과는 살아남는다")
chk(any("모양이 예상과 다름" in e for e in S.ERRORS),
    "이상한 응답은 조용히 넘기지 않고 기록한다")
sys.exit(0 if ok else 1)
