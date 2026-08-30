# 모든 노선이 0건을 주는 최악의 경우, 예산 안에서 끝나고 스위스가
# 왕복 소스(v3)와 3차 소스를 실제로 받는가.
import sys, os
sys.path.insert(0, "/home/user/Travel"); os.chdir("/home/user/Travel")
import scanner as S

n = {"total": 0}
by_route = {}
def fake_call(path, params, retries=2):
    if not S.BUDGET.take():
        return False, None, "BUDGET_EXCEEDED"
    n["total"] += 1
    k = f"{params.get('origin')}-{params.get('destination')}"
    by_route.setdefault(k, []).append(path.rsplit("/", 1)[-1])
    return True, ({"data": []} if path.endswith(("month-matrix", "prices_for_dates"))
                  else {"data": {}}), None
S.call = fake_call; S.REQ_SLEEP = 0; S.time.sleep = lambda *a: None

S.CJJ_ROUTES = S.load_cjj_routes()
todays = S.cjj_targets_today(force_all=False)
print(f"오늘 청주 대상 {len(todays)}개")
for code, info in todays:
    S.fetch_route("CJJ", code, info.get("city", code), info.get("region", ""),
                  flex=S.CJJ_FLEX, window=S.CJJ_WINDOW, latest=True)
print(f"청주까지 {n['total']}회 · 3차 지출 {S.DEEP_SPENT}")

for org, dst, city, region in S.SWISS:
    S.fetch_route(org, dst, city, region,
                  flex=S.SWISS_NIGHTS, window=S.SWISS_WINDOW, latest=True)
print(f"스위스까지 누적 {n['total']}회 · 3차 지출 {S.DEEP_SPENT}")

sw_v3 = [k for k in S.SWISS
         if "prices_for_dates" in by_route.get(f"{k[0]}-{k[1]}", [])]
sw_deep = [k for k in S.SWISS
           if "month-matrix" in by_route.get(f"{k[0]}-{k[1]}", [])]
print(f"v3(왕복) 받은 스위스 노선 {len(sw_v3)}개 · 3차까지 간 노선 {len(sw_deep)}개")

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c
print("\n검사")
chk(n["total"] <= S.SEARCH_BUDGET, f"예산 {S.SEARCH_BUDGET} 이내 ({n['total']}회)")
chk(all(v <= S.DEEP_BUDGET[k] for k, v in S.DEEP_SPENT.items()),
    f"3차 호출 상한 지킴 {S.DEEP_SPENT}")
chk(len(sw_v3) == 6, "스위스 6개 노선 전부 왕복 소스(v3)를 받는다")
chk(len(sw_deep) >= 4, "스위스가 3차까지 도달 (청주가 예산을 다 먹지 않음)")
chk(S.DEEP_SPENT.get("_other", 0) <= S.DEEP_BUDGET["_other"],
    "유럽 밖은 통짜 한 바구니로 제한된다")
sys.exit(0 if ok else 1)
