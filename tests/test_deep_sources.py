# 3차 소스 파서 검증. 실제 API 대신 문서상의 응답 모양을 먹인다.
import sys, os
from datetime import date, timedelta
sys.path.insert(0, "/home/user/Travel")
os.chdir("/home/user/Travel")
import scanner as S

D = lambda n: (date.today() + timedelta(days=n)).strftime("%Y-%m-%d")
calls = []

def fake_call(path, params, retries=2):
    calls.append((path, params))
    if path == "/v1/prices/cheap":
        return True, {"data": {"ZRH": {
            "0": {"price": 1180000, "airline": "LX", "flight_number": factory_fn,
                  "departure_at": D(40) + "T13:05:00+09:00",
                  "return_at": D(47) + "T10:00:00+02:00",
                  "expires_at": D(1) + "T00:00:00Z"},
            "1": {"price": 1250000, "airline": "KE", "flight_number": 917,
                  "departure_at": D(60) + "T21:40:00+09:00",
                  "return_at": D(70) + "T12:00:00+02:00"}}}}, None
    if path == "/v1/prices/direct":
        return True, {"data": {"ZRH": {
            "0": {"price": 1420000, "airline": "LX", "flight_number": 953,
                  "departure_at": D(50) + "T13:05:00+09:00",
                  "return_at": D(56) + "T10:00:00+02:00"}}}}, None
    if path == "/v2/prices/month-matrix":
        return True, {"data": [
            {"value": 1090000, "origin": "SEL", "destination": "ZRH",
             "depart_date": D(80), "return_date": D(90),
             "number_of_changes": 2, "trip_class": 0, "duration": 10},
            {"value": 990000, "origin": "SEL", "destination": "ZRH",
             "depart_date": D(200), "return_date": D(210),   # 창 밖
             "number_of_changes": 1},
            {"value": 0, "origin": "SEL", "destination": "ZRH",   # 가격 없음
             "depart_date": D(85), "return_date": D(88), "number_of_changes": 1},
        ]}, None
    raise AssertionError("예상 못 한 경로 " + path)

factory_fn = 953
S.call = fake_call
S.REQ_SLEEP = 0
S.time.sleep = lambda *a: None

out, stop = S.fetch_deep("ICN", "ZRH", "취리히", "유럽",
                         S.SWISS_NIGHTS, S.SWISS_WINDOW)
print("호출한 엔드포인트:")
for p, q in calls:
    print("  ", p, {k: v for k, v in q.items() if k in ("month",)} or "")
print(f"\n수집 {len(out)}건 (stop={stop})")
for o in sorted(out, key=lambda x: x["price_krw"]):
    print(f"  {o['depart_date']}→{o['return_date']} {o['nights']:>2}박 "
          f"stops={o['stops']} {o['price_krw']:>9,}원 {o['airline']} "
          f"왕복검증={o['roundtrip_verified']}")

print("\n검사")
ok = True
def chk(cond, msg):
    global ok
    print(("  OK   " if cond else "  실패 ") + msg); ok = ok and cond

chk(len(calls) == 2 + S.DEEP_MONTHS, f"호출 수 = 2 + DEEP_MONTHS ({len(calls)})")
chk(all(o["roundtrip_verified"] for o in out), "전부 왕복 검증됨")
chk(any(o["stops"] == 0 for o in out), "direct 결과는 stops=0 으로 확정")
chk(any(o["stops"] == 2 for o in out), "matrix 의 number_of_changes 보존")
chk(not any(o["price_krw"] <= 0 for o in out), "가격 0 은 버림")
chk(all((__import__('datetime').date.fromisoformat(o["depart_date"])
         - date.today()).days <= S.SWISS_WINDOW[1] for o in out),
    "출발일 창 밖(D+200) 은 버림")
chk(len({o["id"] for o in out}) == len(out), "중복 없음")
chk(any(o["dep_hour"] == 13 for o in out), "출발 시각 파싱")
sys.exit(0 if ok else 1)
