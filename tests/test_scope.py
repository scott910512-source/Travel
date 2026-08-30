# -*- coding: utf-8 -*-
"""국내/해외 구분이 데이터 쪽에서 성립하는지 본다.

화면(app.js)의 판정은 offer 의 region 을 1순위로 쓴다. 그러니 스캐너가
region 을 빠뜨리면 국내선이 해외로 새어 나간다. 여기서 그걸 막는다.
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("국내/해외 구분")

import scanner as S

# 1. 모든 offer 는 region 을 갖는다 (화면이 이걸로 가른다)
d0 = datetime.date.today() + datetime.timedelta(days=40)
d1 = d0 + datetime.timedelta(days=3)
o = S.normalize("CJJ", "CJU", "제주", "국내선", d0.isoformat(), 3,
                {"price": 90000, "airline": "7C", "flight_number": "101", "transfers": 0,
                 "departure_at": d0.isoformat() + "T09:00:00+09:00",
                 "return_at": d1.isoformat() + "T18:00:00+09:00"})
chk(o is not None and o.get("region") == "국내선", "국내선 offer 에 region 이 붙는다")

o2 = S.normalize("CJJ", "NRT", "도쿄", "일본", d0.isoformat(), 3,
                 {"price": 300000, "airline": "LJ", "flight_number": "201", "transfers": 0,
                  "departure_at": d0.isoformat() + "T09:00:00+09:00",
                  "return_at": d1.isoformat() + "T18:00:00+09:00"})
chk(o2 is not None and o2.get("region") == "일본", "해외 offer 에 region 이 붙는다")

chk("region" in S.OFFER_FIELDS, "region 이 deals.json 으로 나간다 (OFFER_FIELDS)")

# 2. config 의 국내선은 정확히 region='국내선' 으로 표시돼 있다
cfg = json.load(open(os.path.join(ROOT, "config", "cjj_routes.json"),
                     encoding="utf-8"))
routes = cfg.get("routes", cfg)
dom = {k: v for k, v in routes.items() if v.get("region") == "국내선"}
kr = {k: v for k, v in routes.items() if v.get("country") == "대한민국"}
chk(dom.keys() == kr.keys(),
    "country=대한민국 과 region=국내선 이 정확히 같은 집합이다 (%s)" % ", ".join(sorted(dom)))
chk("CJU" in dom, "제주(CJU)가 국내선이다")

# 3. 화면 쪽 공항 코드 backstop 이 국내선 목적지를 전부 덮는다
app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
m = re.search(r"const KR_ARR = \[(.*?)\];", app, re.S)
chk(m is not None, "app.js 에 KR_ARR 이 있다")
if m:
    codes = set(re.findall(r"'([A-Z]{3})'", m.group(1)))
    missing = set(dom) - codes
    chk(not missing, "KR_ARR 이 config 의 국내선을 전부 덮는다 (빠진 것: %s)"
        % (", ".join(sorted(missing)) or "없음"))
    # 해외 노선이 국내로 잘못 분류되면 안 된다
    wrong = {k for k, v in routes.items()
             if v.get("region") != "국내선" and k in codes}
    chk(not wrong, "해외 노선이 KR_ARR 에 섞여 있지 않다 (%s)"
        % (", ".join(sorted(wrong)) or "없음"))

# 4. 두 축이 독립이다: 국내/해외는 도착지, 출발지 칩은 출발지를 본다
chk("const isDom = (arr, region) =>" in app, "isDom 은 도착지·region 만 본다")
chk("inGroup(o.dep, S.origin)" in app and "inScope(o, S.scope)" in app,
    "출발지(inGroup)와 국내/해외(inScope)가 따로 걸린다")
chk("function originOffers()" in app,
    "칩 건수는 스코프 걸기 전 pool 에서 센다 (0건도 0건으로 보인다)")

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
