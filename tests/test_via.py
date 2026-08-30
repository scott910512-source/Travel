# 경유지. 확정(provider 실제 구간)과 추정(항공사 허브)을 절대 섞지 않는다.
import sys, os
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

print("추정 (허브)")
v = S._via_fields("EY", 1, {})
chk(v["via"] == ["AUH"] and v["via_src"] == "hub", "1회 환승은 항공사 허브로 추정")
chk(v["via_name"] == "아부다비", "한글 지명도 같이")
chk(S._via_fields("MU", 1, {})["via"] == ["PVG"], "중국동방 → 상하이")
lh = S._via_fields("LH", 1, {})
chk("/" in lh["via"][0], f"허브가 둘이면 둘 다 적는다 ({lh['via'][0]})")

print("\n추정하지 않는 경우")
chk(S._via_fields("EY", 0, {})["via"] is None, "직항은 경유지 없음")
chk(S._via_fields("EY", None, {})["via"] is None, "환승 정보가 없으면 추정 안 함")
chk(S._via_fields("CA", 2, {})["via"] is None,
    "2회 이상은 허브 하나로 설명 안 되므로 추정하지 않는다")
chk(S._via_fields("??", 1, {})["via"] is None, "모르는 항공사는 추정 안 함")

print("\n확정 (provider 실제 구간)")
seg = S._via_fields("EY", 1, {"via_airports": ["AUH"]})
chk(seg["via"] == ["AUH"] and seg["via_src"] == "segment",
    "provider 값이 있으면 추정을 쓰지 않는다")
chk(seg["via_name"] is None, "확정값에는 추정용 한글 지명을 붙이지 않는다")
seg2 = S._via_fields("XX", 2, {"via_airports": ["AUH", "FRA"]})
chk(seg2["via"] == ["AUH", "FRA"] and seg2["via_src"] == "segment",
    "2회 환승도 실제 구간이 있으면 그대로 (모르는 항공사여도)")

print("\n직렬화·항공사명")
chk(all(f in S.OFFER_FIELDS for f in ("via", "via_name", "via_src")),
    "deals.json 에 세 필드가 다 실린다")
chk(S.AIRLINES.get("EY") == "에티하드", "외항사 한글명 (전엔 'EY' 그대로 나왔다)")
chk(S.AIRLINES.get("MU") == "중국동방", "중국동방")

print("\nDuffel 이 실제 경유지를 준다")
import json, io
from sources.duffel import DuffelProvider
fx = {"KRW": 1, "USD": 1377}
FIX = json.load(io.open("tests/fixtures/duffel_zrh.json", encoding="utf-8"))
p = DuffelProvider(token="t", fx=fx)
got = [p._offer(r) for r in FIX["data"]["offers"]]
one = next(o for o in got if o and o.get("via_airports"))
chk(one["via_airports"] == ["AUH"], "세그먼트에서 실제 경유 공항을 뽑는다")
direct = next(o for o in got if o and o["outbound_stops"] == 0)
chk(not direct.get("via_airports"), "직항에는 경유지를 붙이지 않는다")
sys.exit(0 if ok else 1)
