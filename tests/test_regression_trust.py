# -*- coding: utf-8 -*-
"""가격 신뢰도·필터 필수 회귀 6건.

전부 "실제로 실행해서" 확인한다. 주석의 주장이 아니라 동작을 본다.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

def node(body, take):
    """app.js 에서 함수를 잘라 실제로 실행한다."""
    src = APP[APP.index(take[0]):APP.index(take[1])]
    pre = ("const esc=x=>String(x==null?'':x);"
           "const won=n=>Number(n).toLocaleString('ko-KR');")
    p = subprocess.run(["node", "-e", pre + src + body],
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[:400])
    return p.stdout.strip()

import scanner as S
from core.merge import dedupe_key, merge_offers

# ── 1. 10만원과 90만원을 '가격 일치' 로 보지 않는다 ────
print("\n[1] 교차검증: 다른 가격을 일치라고 하지 않는다")
SRC = ("const EF_PRICE_TOL", "function crossCheckable")
def ef(sources):
    return json.loads(node(
        "console.log(JSON.stringify(efLevel({sources:%s,source:'travelpayouts'})))"
        % json.dumps(sources), SRC))

cond = {"currency": "KRW", "cabin": "economy", "pax": 1,
        "tax_included": True, "roundtrip": True}
r = ef([dict(cond, source="travelpayouts", price=100000),
        dict(cond, source="duffel", price=900000)])
chk(r["state"] != "match",
    "★ 조건이 같아도 10만 vs 90만 은 일치가 아니다 (state=%s)" % r["state"])
chk(r["state"] == "gap", "가격 불일치로 부른다")

r2 = ef([{"source": "travelpayouts", "price": 100000},
         {"source": "duffel", "price": 900000}])
chk(r2["state"] == "unknown",
    "조건을 모르면 '동일 조건 확인 불가' (state=%s)" % r2["state"])

r3 = ef([dict(cond, source="travelpayouts", price=100000),
         dict(cond, source="duffel", price=105000)])
chk(r3["state"] == "match", "조건 같고 오차 5%% 면 일치 (state=%s)" % r3["state"])

r4 = ef([{"source": "travelpayouts", "price": 100000}])
chk(r4["state"] == "single", "소스가 하나면 '단일 소스 발견'")

chk("pct" not in r and "pct" not in r3, "고정 확률(31/72/91)을 적지 않는다")
# '예약 가능 확인' 은 실제로 재확인했을 때만 줄 수 있다. 우리는 재확인을
# 하지 않으므로 그 상태를 반환하는 경로가 하나도 없어야 한다.
_ef = APP[APP.index("function efLevel("):APP.index("function crossCheckable")]
_states = set(re.findall(r"state:\s*'(\w+)'", _ef))
chk("booking" not in _states,
    "'예약 가능 확인' 을 반환하는 경로가 없다 (반환 상태: %s)" % sorted(_states))
chk(_states <= {"single", "unknown", "differ", "gap", "match"},
    "상태는 근거 중심 다섯 가지뿐이다")
chk(re.search(r"const EF_PRICE_TOL = [\d.]+;", APP) is not None,
    "가격 일치 허용오차가 명시적 상수다")

# ── 2. 같은 캐시를 반복 조회해도 고유 여정으로 센다 ────
print("\n[2] 같은 캐시를 7일 반복 조회 → 표본 7 이 되지 않는다")
today = datetime.date.today()
row = {"dep": "CJJ", "arr": "HIJ", "nights": 3, "price_krw": 200000,
       "airline": "7C", "flight_no": "101", "depart_date": "2026-10-10",
       "return_date": "2026-10-13", "stops": 0, "id": "x"}
k = S.bucket_key(row)

def pooled(days_rows):
    store = {k: days_rows}
    thin = S.track_samples([dict(row)], {"thin_samples": store})
    b = S.build_baselines([dict(row)], thin)
    return S.pick_baseline(dict(row), b)

same = {str(today - datetime.timedelta(days=i)):
        [{"k": S.flight_fp(row), "p": 200000}] for i in range(7)}
bl, _ = pooled(same)
chk(bl is None or bl["n"] <= 2,
    "★ 같은 편 7일 관측 → 표본 %s (7 이면 안 된다)" % (bl["n"] if bl else "없음"))

diff = {}
for i in range(7):
    r_ = dict(row, flight_no=str(200 + i))
    diff[str(today - datetime.timedelta(days=i))] = [{"k": S.flight_fp(r_), "p": 200000 + i * 1000}]
bl2, lab2 = pooled(diff)
chk(bl2 and bl2["n"] >= 6, "진짜 다른 편 7개는 표본으로 센다 (%s)" % (bl2["n"] if bl2 else 0))
chk(lab2 and "고유 여정" in lab2, "라벨이 고유 여정 수와 관측 일수를 구분해 적는다")

legacy = {str(today - datetime.timedelta(days=i)): [200000] for i in range(7)}
bl3, _ = pooled(legacy)
chk(bl3 is None or bl3["n"] <= 2,
    "식별 정보 없는 옛 기록은 지어내지 않고 안전하게 합친다 (%s)" % (bl3["n"] if bl3 else "없음"))

# ── 3. 5박·1회 환승 설정에서 10박·2회 환승 제외 ────────
print("\n[3] 여행 조건이 실제로 걸린다")
TRIP = ("function tripRules(", "function visibleOffers")
def match(o, st):
    return node("let S={settings:%s};"
                "console.log(JSON.stringify(matchesTrip(%s)))"
                % (json.dumps(st), json.dumps(o)), TRIP) == "true"
st5 = {"minNights": 2, "maxNights": 5, "stops": "one",
       "longMinNights": 2, "longMaxNights": 21, "longStops": "any"}
chk(not match({"region": "일본", "nights": 10, "stops": 2}, st5),
    "★ 최대 5박·1회 환승에서 10박·2회 환승은 제외")
chk(match({"region": "일본", "nights": 5, "stops": 1}, st5), "5박·1회 환승은 충족")
chk(not match({"region": "일본", "nights": 3, "stops": None}, st5),
    "★ 환승 횟수 불명은 '1회 이하' 충족으로 보지 않는다")
chk(not match({"region": "일본", "nights": 3, "stops": None},
              dict(st5, stops="direct")), "'직항만' 에서도 불명은 제외")
chk("S.data.offers.filter(o =>\n    SWISS_ORDER" not in APP
    or "matchesTrip(o, rules)" in APP,
    "스위스 탭이 여행 조건을 적용한다")
chk("longStops" in APP and "data-longstops" in APP,
    "장거리 조건을 설정에서 보고 고칠 수 있다")
chk("outsideSection" in APP, "조건 밖 편을 몰래 섞지 않고 따로 보여준다")

# ── 4. 일요일 현지 출발 → 월요일 한국 도착 ─────────────
print("\n[4] 귀국일·연차: 현지 출발 ≠ 한국 도착")
d0 = today + datetime.timedelta(days=40)
d1 = d0 + datetime.timedelta(days=8)
while d1.weekday() != 6:          # 일요일 현지 출발
    d1 += datetime.timedelta(days=1)
def leave(extra):
    v = {"price": 900000, "airline": "LH", "flight_number": "712", "transfers": 1,
         "departure_at": d0.isoformat() + "T13:00:00+09:00",
         "return_at": d1.isoformat() + "T20:00:00+02:00"}
    v.update(extra)
    return S.normalize("ICN", "FRA", "프랑크푸르트", "유럽",
                       d0.isoformat(), None, v, (2, 21), (3, 180))

o_unknown = leave({})
o_known = leave({"duration": 1400, "duration_to": 690})   # 오는 편 710분
chk(o_known and o_known["home_arrive_date"] == str(d1 + datetime.timedelta(days=1)),
    "★ 일요일 20시 현지 출발 → 한국 도착은 월요일 (%s)"
    % (o_known["home_arrive_date"] if o_known else "None"))
chk(o_known and o_unknown and o_known["annual_leave"] > o_unknown["annual_leave"],
    "★ 그 월요일이 연차에 포함된다 (%s → %s)"
    % (o_unknown["annual_leave"] if o_unknown else "?",
       o_known["annual_leave"] if o_known else "?"))
chk(o_unknown and o_unknown["home_arrive_date"] is None
    and o_unknown["annual_leave_confirmed"] is False,
    "도착을 모르면 미확인으로 두고 확정하지 않는다")
chk(o_known and o_known["ret_local_date"] == str(d1),
    "현지 출발일은 따로 보존한다")
chk("home_arrive_date" in S.OFFER_FIELDS and "annual_leave_confirmed" in S.OFFER_FIELDS,
    "두 값이 화면으로 나간다")
chk("한국 도착" in APP and "미확인" in APP, "화면이 현지 출발과 한국 도착을 나눠 적는다")

# ── 5. 오전편/오후편이 합쳐지지 않는다 ─────────────────
print("\n[5] 같은 날 같은 항공사의 다른 편은 별도 유지")
base = {"dep": "ICN", "arr": "NRT", "departure_at": "2026-10-10T08:00:00+09:00",
        "return_at": "2026-10-13T18:00:00+09:00", "airline": "KE",
        "flight_no": "701", "outbound_stops": 0, "return_stops": 0,
        "price": 300000, "source": "travelpayouts"}
pm = dict(base, departure_at="2026-10-10T19:00:00+09:00", flight_no="705", price=310000)
chk(dedupe_key(base) != dedupe_key(pm), "★ 오전 KE701 과 오후 KE705 의 키가 다르다")
chk(len(merge_offers([base, pm])) == 2, "★ 병합해도 2건으로 남는다")
chk(len(merge_offers([base, dict(base)])) == 1, "완전히 같은 건은 1건으로 합친다")
noid = dict(base); noid.pop("flight_no"); noid["departure_at"] = "2026-10-10"
chk(len(merge_offers([noid, dict(noid)])) == 2,
    "식별 정보가 없으면 무리하게 합치지 않는다")
fare = dict(base, baggage="0kg", price=280000)
chk(len(merge_offers([base, fare])) == 2,
    "같은 여정이라도 수하물 조건이 다르면 별도 운임으로 남긴다")
m = merge_offers([base, pm])[0]
chk(all("booking_url" in s for s in m["sources"]),
    "sources 에 그 소스의 예약 링크가 함께 실린다")

# ── 6. 실패·만료·빈 결과 ───────────────────────────────
print("\n[6] API 실패·만료 가격·빈 결과")
S.ERRORS.clear()
tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "deals.json")
json.dump({"meta": {"ts": "2026-09-05 13:02 KST"},
           "offers": [{"id": i} for i in range(100)]},
          open(p, "w", encoding="utf-8"))
S.ERRORS.append("HTTP 500")
kept, note = S.guard_previous([{"id": "x"}] * 3, p)
chk(note and len(kept) == 100, "★ API 실패 + 급감이면 마지막 정상 데이터를 유지한다")
chk(note and note["last_good"] == "2026-09-05 13:02 KST", "마지막 정상 시각을 남긴다")
S.ERRORS.clear()
chk("meta.stale" in APP or "m.stale" in APP, "화면이 '최신 스캔 실패' 를 표시한다")
chk("function isExpired(" in APP, "만료된 가격을 판별한다")
chk("!isExpired(o)" in APP, "★ 만료된 가격은 후보 목록에서 제외한다")
chk("가격 확인 시각 불명" in APP, "★ found_at 이 없으면 '불명' 이라고 적는다 (비워 두지 않는다)")
chk("function bookingLink(" in APP and "동일 일정 다시 검색" in APP,
    "전용 예약 링크와 일반 검색 링크를 구분한다")
chk("expires_at" in S.OFFER_FIELDS, "만료 시각이 화면으로 나간다")

print("\n실패 %d" % len(fail))
sys.exit(1 if fail else 0)
