# -*- coding: utf-8 -*-
"""소스가 "직항" 이라고 한 것을 우리가 확인한 것처럼 쓰지 않는지 본다.

/v1/prices/direct 는 직항만 준다고 계약돼 있다. 예전 코드는 그 말을 믿고
stops=0 을 덮어썼다. 그런데 실제로 직항편이 없는 노선을 직항으로 답한
사례가 있다(대구→괌: 스카이스캐너에 "직항 운항 항공사 없음" 이라고
적힌 노선이 대한항공 직항 -40% 특가로 잡혀 있었다).
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("직항 표기의 출처")

import scanner as S

d0 = datetime.date.today() + datetime.timedelta(days=40)
d1 = d0 + datetime.timedelta(days=3)
BASE = {"price": 300000, "airline": "KE", "flight_number": "1",
        "departure_at": d0.isoformat() + "T09:00:00+09:00",
        "return_at": d1.isoformat() + "T18:00:00+09:00"}

def go(extra, org="ICN", dst="GUM"):
    v = dict(BASE); v.update(extra)
    o = S.normalize(org, dst, "괌", "동남아", d0.isoformat(), 3, v)
    return o and (o["stops"], o["stops_src"], o["stops_conflict"])

S.STOPS_CONFLICT.clear()

chk(go({"number_of_changes": 0}) == (0, "row", False),
    "행이 직항이라고 주면 확인된 값으로 쓴다")
chk(go({"_direct_claim": True}) == (0, "endpoint", False),
    "행이 침묵하면 stops=0 이되 근거는 'endpoint' 로 남는다")
chk(go({"_direct_claim": True, "number_of_changes": 1}) == (1, "row", True),
    "★ direct 엔드포인트가 환승편을 주면 행을 믿고 불일치를 남긴다")
chk(go({}) == (None, None, False), "아무 정보도 없으면 None (직항이라고 하지 않는다)")
chk(len(S.STOPS_CONFLICT) == 1 and "환승 1회" in S.STOPS_CONFLICT[0],
    "불일치가 기록으로 남는다 (%s)" % (S.STOPS_CONFLICT[:1] or "없음"))

# 지방공항 직항 전용 필터가 이 값을 그대로 쓴다.
# 예전이라면 forced_stops=0 덕에 통과했을 환승편이 이제는 걸러져야 한다.
S.STOPS_CONFLICT.clear()
chk(go({"_direct_claim": True, "number_of_changes": 1, "transfers": 1},
       org="CJJ", dst="TAO") is None,
    "청주는 direct 엔드포인트가 줬어도 환승편이면 버린다")

# 필드가 화면까지 나가는가
chk("stops_src" in S.OFFER_FIELDS and "stops_conflict" in S.OFFER_FIELDS,
    "두 필드가 deals.json 으로 나간다")

app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
chk("'직항(소스 주장)'" in app, "화면이 소스 주장과 확인된 직항을 다르게 쓴다")
chk("소스 불일치" in app, "불일치는 화면에도 뜬다")

scan = open(os.path.join(ROOT, "scanner.py"), encoding="utf-8").read()
chk("forced_stops" not in scan, "stops 를 덮어쓰던 코드가 남아 있지 않다")
chk('"stops_conflict": STOPS_CONFLICT[:30]' in scan, "meta 에 불일치를 싣는다")

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
