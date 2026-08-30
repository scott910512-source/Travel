# 편도는 offers 와 섞이면 안 된다. 섞이면 노선 평균가가 절반으로 내려앉아
# 멀쩡한 왕복이 전부 "평균보다 비쌈" 이 된다. 구조적으로 막혔는지 본다.
import sys, os, json
from datetime import date, timedelta
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

D = lambda n: (date.today() + timedelta(days=n)).strftime("%Y-%m-%d")
S.ONEWAY.clear()

# 귀국일이 있는 건(왕복) + 없는 건(편도) 을 같은 노선에 섞어 넣는다
rt = S.normalize("ICN", "ZRH", "취리히", "유럽", D(40), None, {
    "price": 1400000, "airline": "LX", "departure_at": D(40) + "T13:00:00+09:00",
    "return_at": D(47) + "T10:00:00+02:00", "number_of_changes": 0},
    S.SWISS_NIGHTS, S.SWISS_WINDOW)
ow = S.normalize("ICN", "ZRH", "취리히", "유럽", D(41), None, {
    "price": 610000, "airline": "LX", "departure_at": D(41) + "T13:00:00+09:00",
    "return_at": None, "number_of_changes": 0},
    S.SWISS_NIGHTS, S.SWISS_WINDOW)

offers = [o for o in (rt, ow) if o]
print(f"normalize 가 offers 로 돌려준 것 {len(offers)}건")
print(f"ONEWAY 로 따로 담긴 것 {len(S.ONEWAY)}건")

# 근거리는 편도를 받지 않아야 한다
S.ONEWAY.clear()
S.normalize("CJJ", "KIX", "오사카", "일본", D(20), None, {
    "price": 200000, "airline": "7C", "departure_at": D(20) + "T09:00:00+09:00",
    "return_at": None, "number_of_changes": 0}, S.CJJ_FLEX, S.CJJ_WINDOW)
near = len(S.ONEWAY)

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("\n검사")
chk(len(offers) == 1 and offers[0]["price_krw"] == 1400000,
    "offers 에는 왕복만 들어간다")
chk(ow is None, "편도는 normalize 가 offers 로 돌려주지 않는다")
chk(near == 0, "근거리(청주)는 편도를 받지 않는다 — ALLOW_ONEWAY 는 유럽만")

# 기준선이 편도에 오염되지 않는가
S.ONEWAY.clear()
base = S.build_baselines(offers, thin={})
avg = [v for k, v in (base or {}).items()]
chk(not any(isinstance(v, dict) and v.get("avg", 9e9) < 700000 for v in avg),
    "기준선 평균가가 편도 값으로 내려가지 않는다")

# deals.json 직렬화에서 분리되어 있는가
S.ONEWAY.clear()
S.ONEWAY.append(S._oneway_offer("ICN", "ZRH", "취리히", "유럽",
    date.today() + timedelta(days=41),
    {"price": 610000, "airline": "LX", "number_of_changes": 0,
     "departure_at": D(41) + "T13:00:00+09:00"}))
row = S._dedup_oneway(S.ONEWAY)[0]
chk(row["oneway"] is True, "편도 행은 oneway=True 로 표시된다")
chk("effective_krw" not in row and "baseline" not in row,
    "편도 행에는 실부담가·기준가 필드가 아예 없다")
chk(row["link"].endswith("ZRH1"), "편도 링크는 귀국일 없이 만든다")
sys.exit(0 if ok else 1)
