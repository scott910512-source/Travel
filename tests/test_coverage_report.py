# 커버리지 지표: 전체 건수가 아니라 "0건 노선이 줄었는가" 를 먼저 본다.
import sys, os, json, io
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
from core.quality import coverage, report, verdict, provider_log, cjj_coverage_log

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c

def offer(dep, arr, price=100000, stops=1):
    return {"dep": dep, "arr": arr, "price_krw": price, "stops": stops}

status = [{"destination": c, "route_status": "active"}
          for c in ("NRT", "KIX", "CTS", "TPE", "DPS")]

print("지표 계산")
before = coverage({"offers": [offer("CJJ", "NRT"), offer("CJJ", "KIX"),
                              offer("ICN", "ZRH", stops=1),
                              offer("ICN", "ZRH", stops=1)]}, status)
chk(before["cjj_zero_routes"] == 3, "가격 0건 노선을 센다 (CTS·TPE·DPS)")
chk(before["cjj_priced_destinations"] == 2, "가격 확인된 목적지 수")
chk(before["zrh_offers"] == 2 and before["zrh_1stop"] == 2, "ZRH 1회 환승")
chk(before["zrh_direct"] == 0, "직항 0")

after = coverage({"offers": [offer("CJJ", "NRT"), offer("CJJ", "KIX"),
                             offer("CJJ", "CTS"), offer("CJJ", "TPE"),
                             offer("ICN", "ZRH", stops=0),
                             *[offer("ICN", "ZRH", stops=1) for _ in range(25)]]},
                status)
chk(after["cjj_zero_routes"] == 1, "fallback 후 0건 노선 감소")
chk(after["zrh_direct"] == 1 and after["zrh_1stop"] == 25, "ZRH 직항/1회 분리")

print("\n리포트")
txt = report(before, after, {"input": 40, "duplicates": 9, "final": 31})
print("\n".join("   " + l for l in txt.splitlines()))
chk("DATA COVERAGE TEST" in txt, "표를 그린다")
chk("↓" in txt, "0건 노선 감소를 개선으로 표시")
chk("중복 제거 전" in txt, "merge 정보 포함")

print("\n판정")
st, checks = verdict(before, after)
print(f"   {st}")
for n, c in checks:
    print(f"   {'PASS' if c else 'FAIL'}  {n}")
chk(st in ("PASS", "PARTIAL", "FAIL"), "PASS/PARTIAL/FAIL 로 답한다")
st_same, _ = verdict(before, before)
chk(st_same != "PASS", "아무것도 안 늘었으면 PASS 가 아니다")

print("\n로그 형식")
pl = provider_log({"travelpayouts": {"calls": 153, "rows": 364},
                   "duffel": {"skipped": "missing DUFFEL_TOKEN"},
                   "skyscanner": {"calls": 8, "rows": 67, "errors": ["timeout"]}},
                  {"input": 462, "duplicates": 71, "final": 391})
print("\n".join("   " + l for l in pl.splitlines()))
chk("disabled: missing DUFFEL_TOKEN" in pl, "비활성 provider 를 숨기지 않는다")
chk("error: timeout" in pl, "provider 오류를 로그에 남긴다")
cl = cjj_coverage_log({"NRT": {"tp": 14, "sky": 0, "final": 14},
                       "TPE": {"tp": 0, "sky": 8, "final": 8}})
print("\n".join("   " + l for l in cl.splitlines()))
chk("TPE" in cl and "SKY   8" in cl, "노선별 provider 기여를 보여준다")

print("\n실제 baseline")
base = json.load(io.open("flight-deals/state/baseline.json", encoding="utf-8"))
cov = coverage(base)
print(f"   {cov}")
chk(cov["offers_total"] > 0, "실제 파일을 읽는다")
chk(isinstance(cov["cjj_zero_list"], list), "0건 노선 목록을 준다")
sys.exit(0 if ok else 1)
