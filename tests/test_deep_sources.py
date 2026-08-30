# 3차 소스 파서 검증. 실제 API 대신 문서상의 응답 모양을 먹인다.
import sys, os
from datetime import date, timedelta
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

D = lambda n: (date.today() + timedelta(days=n)).strftime("%Y-%m-%d")
calls = []

def fake_call(path, params, retries=2):
    calls.append((path, params))
    if path == "/v1/prices/cheap":
        return True, {"data": {"ZRH": {
            "0": {"price": 1180000, "airline": "LX", "flight_number": 953,
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
             "number_of_changes": 2},
            {"value": 990000, "origin": "SEL", "destination": "ZRH",
             "depart_date": D(200), "return_date": D(210),   # 창 밖
             "number_of_changes": 1},
            {"value": 0, "origin": "SEL", "destination": "ZRH",   # 가격 없음
             "depart_date": D(85), "return_date": D(88), "number_of_changes": 1},
        ]}, None
    raise AssertionError("예상 못 한 경로 " + path)

S.call = fake_call; S.REQ_SLEEP = 0; S.time.sleep = lambda *a: None
S.DEEP_SPENT.clear()

out, stop = S.fetch_deep("ICN", "ZRH", "취리히", "유럽",
                         S.SWISS_NIGHTS, S.SWISS_WINDOW)
paths = [p for p, _ in calls]
print("호출한 엔드포인트:", [p.rsplit("/", 1)[-1] for p in paths])
print(f"\n수집 {len(out)}건 (stop={stop})")
for o in sorted(out, key=lambda x: x["price_krw"]):
    print(f"  {o['depart_date']}→{o['return_date']} {o['nights']:>2}박 "
          f"stops={o['stops']} {o['price_krw']:>9,}원 {o['airline']}")

ok = True
def chk(cond, msg):
    global ok
    print(("  OK   " if cond else "  실패 ") + msg); ok = ok and cond

print("\n검사")
# ★ 이걸 안 넘겨서 취리히 23건이 전부 편도로 왔다
chk(all(q.get("depart_date") and q.get("return_date")
        for p, q in calls if "cheap" in p or "direct" in p),
    "cheap·direct 에 출발월·귀국월을 넘긴다 (안 넘기면 편도가 온다)")
chk(len(out) >= S.DEEP_ENOUGH and "/v2/prices/month-matrix" not in paths,
    "앞 단계가 충분히 주면 month-matrix 는 건너뛴다 (조기 종료)")
chk(all(o["roundtrip_verified"] for o in out), "전부 왕복 검증됨")
chk(any(o["stops"] == 0 for o in out), "direct 결과는 stops=0 으로 확정")
chk(not any(o["price_krw"] <= 0 for o in out), "가격 0 은 버림")
chk(len({o["id"] for o in out}) == len(out), "중복 없음")
chk(any(o["dep_hour"] == 13 for o in out), "출발 시각 파싱")
chk(S.DEEP_SPENT.get("유럽", 0) > 0, "3차 예산이 집행된다")

# 앞 단계가 비면 month-matrix 까지 간다
calls.clear()
S.DEEP_SPENT.clear()
def empty_first(path, params, retries=2):
    calls.append((path, params))
    if path == "/v2/prices/month-matrix":
        return True, {"data": [
            {"value": 1090000, "origin": "SEL", "destination": "ZRH",
             "depart_date": D(80), "return_date": D(90),
             "number_of_changes": 2}]}, None
    return True, {"data": {}}, None
S.call = empty_first
out2, _ = S.fetch_deep("ICN", "ZRH", "취리히", "유럽",
                       S.SWISS_NIGHTS, S.SWISS_WINDOW)
chk("/v2/prices/month-matrix" in [p for p, _ in calls],
    "앞 단계가 비면 month-matrix 까지 간다")
chk(any(o["stops"] == 2 for o in out2), "matrix 의 number_of_changes 보존")
sys.exit(0 if ok else 1)
