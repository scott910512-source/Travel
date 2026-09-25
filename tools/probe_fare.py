#!/usr/bin/env python3
"""특정 노선·날짜의 캐시 최저가를 빡세게 훑는다 (검토용 · 로그에만 남긴다).
   Travelpayouts 데이터 API 는 '남이 검색한 결과의 캐시' 라 실시간 확정가가 아니다. 값은 1인 기준.
   입력: 환경변수 FARE_Q = "CJJ-OKA 2026-10-06 2026-10-09" (출발지-도착지 출발일 귀국일)
   훑는 것: ① 그 날짜 정확히(직항/전체) ② 출발·귀국 ±2일 조합 ③ 인천 출발 같은 날짜 ④ 월 매트릭스 ⑤ 최신 캐시 목록
   토큰은 Secrets 에서만. 출력에 토큰을 찍지 않는다."""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import date, timedelta

BASE = "https://api.travelpayouts.com"
TOKEN = os.environ.get("TP_TOKEN", "")
Q = os.environ.get("FARE_Q", "CJJ-OKA 2026-10-06 2026-10-09").split()
if not TOKEN:
    print("::error::TP_TOKEN 없음"); sys.exit(1)
route, d0, d1 = Q[0], Q[1], Q[2]
ORG, DST = route.split("-")
won = lambda v: f"{int(v):,}원"

def call(path, params):
    q = dict(params); q["token"] = TOKEN; q.setdefault("currency", "krw")
    req = urllib.request.Request(f"{BASE}{path}?{urllib.parse.urlencode(q)}", headers={"X-Access-Token": TOKEN, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip; raw = gzip.decompress(raw)
            return json.loads(raw)
    except Exception as e:
        return {"error": str(e).replace(TOKEN, "***")}

def dates_rows(org, dst, dep, ret, direct):
    j = call("/aviasales/v3/prices_for_dates", {"origin": org, "destination": dst, "departure_at": dep, "return_at": ret, "direct": "true" if direct else "false", "sorting": "price", "limit": 30, "one_way": "false"})
    if "error" in j: return None, j["error"]
    return j.get("data", []), None

def show(rows, label):
    if rows is None: print(f"  {label}: 오류"); return
    if not rows: print(f"  {label}: 캐시 없음"); return
    for r in rows[:8]:
        print(f"  {label}: {r.get('departure_at','')[:16]} → {r.get('return_at','')[:16]} · {r.get('airline','?')}{r.get('flight_number','')} · 경유 {r.get('transfers',0)}/{r.get('return_transfers',0)} · 1인 {won(r['price'])} · 2인 {won(r['price']*2)} · 갱신 {r.get('found_at','')[:16]}")

print(f"== {ORG}→{DST} {d0} 출발 / {d1} 귀국 (1인 기준 · 캐시값) ==")
rows, err = dates_rows(ORG, DST, d0, d1, True); show(rows, "정확히 · 직항")
rows, err = dates_rows(ORG, DST, d0, d1, False); show(rows, "정확히 · 전체")
if err: print("  오류:", err)

print(f"\n== 출발·귀국 ±2일 조합 (직항) ==")
D0, D1 = date.fromisoformat(d0), date.fromisoformat(d1)
best = []
for a in range(-2, 3):
    for b in range(-2, 3):
        dd, rr = D0 + timedelta(a), D1 + timedelta(b)
        if rr <= dd: continue
        rows, _ = dates_rows(ORG, DST, dd.isoformat(), rr.isoformat(), True)
        if rows: best.append((rows[0]["price"], dd.isoformat(), rr.isoformat(), rows[0].get("airline", "?")))
        time.sleep(0.15)
for p, dd, rr, al in sorted(best)[:10]:
    print(f"  {dd} → {rr} ({(date.fromisoformat(rr)-date.fromisoformat(dd)).days}박) · {al} · 1인 {won(p)} · 2인 {won(p*2)}")
if not best: print("  캐시 없음")

print(f"\n== 인천 출발 같은 날짜 (비교) ==")
rows, _ = dates_rows("ICN", DST, d0, d1, True); show(rows, "ICN 직항")
rows, _ = dates_rows("ICN", DST, d0, d1, False); show(rows, "ICN 전체")

print(f"\n== 월 매트릭스 ({d0[:7]}, 출발일별 최저 · 왕복) ==")
j = call("/v2/prices/month-matrix", {"origin": ORG, "destination": DST, "month": d0[:7] + "-01", "show_to_affiliates": "false"})
if "error" in j: print("  오류:", j["error"])
else:
    rows = [r for r in j.get("data", []) if r.get("return_date")]
    rows.sort(key=lambda r: r["value"])
    for r in rows[:12]:
        print(f"  {r['depart_date']} → {r['return_date']} · 경유 {r.get('number_of_changes',0)} · 1인 {won(r['value'])} · 갱신 {r.get('found_at','')[:16]}")
    if not rows: print("  캐시 없음")

print(f"\n== 최신 캐시 목록 (latest · {ORG}→{DST}) ==")
j = call("/aviasales/v3/get_latest_prices", {"origin": ORG, "destination": DST, "period_type": "month", "beginning_of_period": d0[:7] + "-01", "limit": 30, "sorting": "price", "one_way": "false"})
if "error" in j: print("  오류:", j["error"])
else:
    for r in j.get("data", [])[:12]:
        print(f"  {r.get('depart_date')} → {r.get('return_date')} · 경유 {r.get('number_of_changes',0)} · 1인 {won(r['value'])} · 갱신 {r.get('found_at','')[:16]}")
    if not j.get("data"): print("  캐시 없음")
print("\n주의: 전부 캐시값(1인). 판매처에서 최종 확인. 캐시가 비면 그 날짜를 아무도 검색하지 않은 것이다.")
