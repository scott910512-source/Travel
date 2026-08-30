# /aviasales/v3/prices_for_dates 파서 검증.
# 이 엔드포인트만 one_way=false 를 받는다 — 왕복을 명시적으로 요구할 수
# 있는 유일한 곳이라, 파라미터가 실제로 실려 나가는지까지 본다.
import sys, os
from datetime import date, timedelta
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

D = lambda n: (date.today() + timedelta(days=n)).strftime("%Y-%m-%d")
sent = []

def fake_call(path, params, retries=2):
    sent.append((path, params))
    assert path == "/aviasales/v3/prices_for_dates", path
    return True, {"data": [
        # 중국동방항공 10박 왕복 — 사용자가 말한 80만원대
        {"origin": "ICN", "destination": "ZRH", "price": 812400,
         "airline": "MU", "flight_number": "5041", "transfers": 1,
         "return_transfers": 1, "duration": 2510, "duration_to": 1250,
         "departure_at": D(70) + "T13:05:00+09:00",
         "return_at": D(80) + "T10:20:00+02:00"},
        # 중국국제항공 14박
        {"origin": "ICN", "destination": "ZRH", "price": 878000,
         "airline": "CA", "flight_number": "126", "transfers": 1,
         "duration": 2625,   # 왕복 총합만 오고 가는 편이 없는 경우
         "departure_at": D(72) + "T09:00:00+09:00",
         "return_at": D(86) + "T12:00:00+02:00"},
        # 편도 (return_at 없음) — 왕복 요청에도 섞여 올 수 있다
        {"origin": "ICN", "destination": "ZRH", "price": 401000,
         "airline": "MU", "transfers": 1,
         "departure_at": D(75) + "T13:05:00+09:00", "return_at": None},
    ]}, None

S.call = fake_call; S.REQ_SLEEP = 0; S.time.sleep = lambda *a: None
S.ONEWAY.clear()
out, stop = S.fetch_v3("ICN", "ZRH", "취리히", "유럽",
                       S.SWISS_NIGHTS, S.SWISS_WINDOW)

print(f"호출 {len(sent)}회 · 수집 {len(out)}건 (stop={stop})")
for o in sorted(out, key=lambda x: x["price_krw"]):
    print(f"  {o['airline']} {o['depart_date']}→{o['return_date']} "
          f"{o['nights']:>2}박 stops={o['stops']} {o['price_krw']:>9,}원 "
          f"가는편={o['duration_min']} 왕복합={o['duration_rt_min']}")

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("\n검사")
p0 = sent[0][1]
chk(p0.get("one_way") == "false", "one_way=false 를 실제로 넘긴다")
chk(p0.get("departure_at") and not p0.get("return_at"),
    "출발월만 넘긴다 — return_at 을 박으면 달을 넘는 여행이 빠진다")
chk(len(sent) == S.V3_MONTHS, f"달 수만큼 호출 ({len(sent)})")
chk(len(out) == 2, "왕복 2건만 offers 로 (편도는 제외)")
chk(len({o["id"] for o in out}) == len(out),
    "여러 달에 걸쳐 같은 편이 와도 한 번만 담는다")
chk(all(o["roundtrip_verified"] for o in out), "전부 왕복 검증됨")
chk(all(o["nights"] >= 10 for o in out),
    "10박·14박이 살아남는다 — 3박만 잡히던 문제의 반대편")
chk(any(o["airline"] == "MU" for o in out) and any(o["airline"] == "CA" for o in out),
    "중국동방(MU)·중국국제(CA) 둘 다 잡힌다")
# duration 은 왕복 총합이다. 그걸 "비행시간" 으로 쓰면 편도 20시간짜리가
# 41시간으로 읽힌다. 가는 편(duration_to)과 총합(duration)을 갈라 담는다.
chk(any(o["duration_min"] == 1250 for o in out),
    "duration_to 를 '가는 편' 으로 싣는다")
chk(any(o["duration_rt_min"] == 2510 for o in out),
    "duration 은 '왕복 총합' 으로 따로 싣는다")
chk(all(o["duration_min"] != o["duration_rt_min"] or o["duration_min"] is None
        for o in out if o["duration_min"]),
    "가는 편과 왕복 총합을 같은 값으로 섞지 않는다")
ca = [o for o in out if o["airline"] == "CA"][0]
chk(ca["duration_min"] is None and ca["duration_rt_min"] == 2625,
    "duration_to 가 없으면 '가는 편' 은 비우고 총합만 남긴다")
chk(len(S.ONEWAY) > 0, "왕복 요청에 섞여 온 편도는 편도 배열로 간다")
chk(all(not o.get("duration_min") or o["duration_min"] > 0 for o in out),
    "소요시간이 있으면 양수")

# 진단이 실제로 쌓이는가 — 응답이 빌 때 이유를 추측하지 않으려면 필요하다
st = S.V3STAT.get("ICN-ZRH") or {}
chk(st.get("calls") == S.V3_MONTHS, f"호출 수를 기록한다 ({st.get('calls')})")
chk(st.get("rows") == 3 * S.V3_MONTHS, f"원본 행 수를 기록한다 ({st.get('rows')})")
chk(bool(st.get("sample")), "응답 샘플을 한 건 남긴다 (필드명 확인용)")
sys.exit(0 if ok else 1)
