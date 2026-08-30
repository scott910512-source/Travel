# ICN-ZRH Duffel 경로: 직항/1회환승 분류, 날짜 폭발 방지, 2회 이상 제외.
import sys, os, json, io
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S
from sources.duffel import DuffelProvider, SEED_MAX
from sources.skyscanner import SkyscannerProvider
from sources.base import SearchRequest

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

FIX = json.load(io.open("tests/fixtures/duffel_zrh.json", encoding="utf-8"))

def fresh(payload=None):
    seen = []
    def http(body):
        seen.append(body)
        return payload if payload is not None else FIX
    return DuffelProvider(token="test", fx={"KRW": 1, "USD": 1377}, http=http), seen

print("요청 구성")
p, seen = fresh()
p.search(SearchRequest("ICN", "ZRH", window=(3, 180), nights=(4, 14),
                       max_stops=1, budget=6))
b0 = seen[0]["data"]
chk(len(b0["slices"]) == 2, "왕복으로 요청한다 (slice 2개)")
chk(b0["slices"][0]["origin"] == "ICN" and b0["slices"][1]["origin"] == "ZRH",
    "가는 편·오는 편 방향이 맞다")
chk(b0["cabin_class"] == "economy", "이코노미")
chk(b0["max_connections"] == 1, "2회 이상 환승은 요청 단계에서 제외")
chk(len(seen) <= 6, f"예산을 지킨다 ({len(seen)}회 ≤ 6)")

print("\n날짜 폭발 방지")
p, seen = fresh()
p.search(SearchRequest("ICN", "ZRH", window=(3, 180), nights=(4, 14), budget=99))
chk(len(seen) <= SEED_MAX + 8,
    f"180일 창에도 호출이 폭발하지 않는다 ({len(seen)}회)")
days = [b["data"]["slices"][0]["departure_date"] for b in seen]
chk(len(set(days)) == len(days) or len(days) > SEED_MAX,
    "seed 날짜가 서로 다르다")

print("\n직항 / 1회 환승 분류")
S.PROVIDERS["duffel"] = fresh()[0]
S.PROVIDERS["skyscanner"] = SkyscannerProvider(token=None)
S.ZRH_COVER.clear(); S.PROVIDER_ROWS.clear()
rows = S.scan_zrh()
direct = [o for o in rows if o["stops"] == 0]
one = [o for o in rows if o["stops"] == 1]
two = [o for o in rows if o["stops"] is not None and o["stops"] >= 2]
print(f"   총 {len(rows)}건 · 직항 {len(direct)} · 1회 {len(one)} · 2회+ {len(two)}")
chk(len(rows) > 0, "결과가 들어온다")
chk(len(direct) > 0, "직항이 분류된다")
chk(len(one) > 0, "1회 환승도 남는다 (편도 기준 1회 = 왕복 각 1회)")
chk(len(two) == 0, "2회 이상 환승은 최종 결과에 없다 (provider 가 무시해도 막는다)")
chk(all(o["dep"] == "ICN" and o["arr"] == "ZRH" for o in rows), "노선이 맞다")
chk(all(o["source"] == "duffel" for o in rows), "source 꼬리표가 붙는다")
chk(all(o["source_confidence"] == "A" and o["live"] for o in rows),
    "confidence A · live 로 표시된다")
chk(all(o.get("price_krw", 0) > 0 for o in rows), "가격이 원화로 들어온다")

print("\nDuffel 이 죽으면 Skyscanner 로 넘어간다")
class Boom(DuffelProvider):
    def _search(self, req): raise RuntimeError("duffel down")
S.ERRORS.clear(); S.ZRH_COVER.clear()
S.PROVIDERS["duffel"] = Boom(token="test")
S.PROVIDERS["skyscanner"] = SkyscannerProvider(token=None)
rows = S.scan_zrh()
chk(rows == [], "둘 다 못 쓰면 빈 결과 (예외 없음)")
chk(any("duffel" in e for e in S.ERRORS), "실패를 기록한다")

print("\n토큰이 하나도 없을 때")
S.PROVIDERS["duffel"] = DuffelProvider(token=None)
S.PROVIDERS["skyscanner"] = SkyscannerProvider(token=None)
S.ZRH_COVER.clear()
chk(S.scan_zrh() == [], "전부 비활성 → 빈 결과, 스캔 계속")
sys.exit(0 if ok else 1)
