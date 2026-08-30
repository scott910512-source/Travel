# CJJ fallback: Travelpayouts 가 얇을 때만 보조 provider 를 부른다.
# 데이터가 이미 충분한 노선(CJJ-NRT)에 호출을 낭비하면 안 된다.
import sys, os, json, io
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S
from sources.skyscanner import SkyscannerProvider, parse_rows

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

SKY = json.load(io.open("tests/fixtures/skyscanner_cjj.json", encoding="utf-8"))

def tp_rows(n, roundtrip=True):
    return [{"price_krw": 300000 + i, "roundtrip_verified": roundtrip,
             "dep": "CJJ", "arr": "TPE"} for i in range(n)]

INFO = {"city": "타이베이", "region": "중화권", "country": "대만"}

def fresh_sky():
    calls = []
    def http(req, d0, d1):
        calls.append((req.dep, req.arr, d0, d1, req.max_stops))
        return SKY
    p = SkyscannerProvider(token="test", http=http)
    return p, calls

print("fallback 발동 조건")
S.CJJ_PER_ROUTE.clear(); S.PROVIDER_ROWS.clear()
sky, calls = fresh_sky(); S.PROVIDERS["skyscanner"] = sky
got = S.fallback_cjj("NRT", INFO, tp_rows(14))
chk(got == [] and calls == [], "TP 14건 → fallback 생략 (호출 0)")
chk(S.CJJ_PER_ROUTE["NRT"]["tp"] == 14, "TP 유효 건수를 기록")

S.CJJ_PER_ROUTE.clear()
sky, calls = fresh_sky(); S.PROVIDERS["skyscanner"] = sky
got = S.fallback_cjj("CTS", INFO, tp_rows(1))
chk(len(calls) > 0, "TP 1건 → fallback 발동")
chk(len(got) > 0, f"보조 provider 결과가 들어온다 ({len(got)}건)")

S.CJJ_PER_ROUTE.clear()
sky, calls = fresh_sky(); S.PROVIDERS["skyscanner"] = sky
got = S.fallback_cjj("TPE", INFO, [])
chk(len(calls) > 0 and len(got) > 0, "TP 0건 → fallback 발동")
chk(all(c[4] == 0 for c in calls), "지방공항은 직항만 요청한다 (max_stops=0)")
chk(all(o["stops"] == 0 for o in got), "환승편은 CJJ 결과에 들어오지 않는다")

print("\n유효 왕복으로 센다 (단순 row 수가 아니라)")
S.CJJ_PER_ROUTE.clear()
sky, calls = fresh_sky(); S.PROVIDERS["skyscanner"] = sky
got = S.fallback_cjj("KIX", INFO, tp_rows(20, roundtrip=False))
chk(len(calls) > 0, "원본 20건이어도 전부 편도면 fallback 발동")
chk(S.CJJ_PER_ROUTE["KIX"]["tp"] == 0, "유효 왕복 0 으로 기록")

print("\n토큰 없으면 조용히 넘어간다")
S.CJJ_PER_ROUTE.clear()
S.PROVIDERS["skyscanner"] = SkyscannerProvider(token=None)
got = S.fallback_cjj("DPS", INFO, [])
chk(got == [], "provider 비활성 → 빈 결과, 예외 없음")
chk(S.CJJ_PER_ROUTE["DPS"]["sky"] == 0, "0 으로 기록")

print("\nprovider 가 터져도 스캔은 계속된다")
S.CJJ_PER_ROUTE.clear(); S.ERRORS.clear()
class Boom(SkyscannerProvider):
    def _search(self, req): raise RuntimeError("provider 폭발")
S.PROVIDERS["skyscanner"] = Boom(token="test")
got = S.fallback_cjj("KMG", INFO, [])
chk(got == [], "예외가 밖으로 안 나온다")
chk(any("skyscanner" in e for e in S.ERRORS), "조용히 넘기지 않고 ERRORS 에 남긴다")
sys.exit(0 if ok else 1)
