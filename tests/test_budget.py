# 모든 노선이 0건을 주는 최악의 경우, 예산 안에서 끝나고 스위스가
# 3차 소스를 실제로 받는가.
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
    return True, ({"data": {}} if path != "/v2/prices/month-matrix"
                  else {"data": []}), None
S.call = fake_call; S.REQ_SLEEP = 0; S.time.sleep = lambda *a: None

# 청주 먼저 (main() 과 같은 순서)
S.CJJ_ROUTES = S.load_cjj_routes()
todays = S.cjj_targets_today(force_all=False)
print(f"오늘 청주 대상 {len(todays)}개")
for code, info in todays:
    S.fetch_route("CJJ", code, info.get("city", code), info.get("region", ""),
                  flex=S.CJJ_FLEX, window=S.CJJ_WINDOW, latest=True)
after_cjj = n["total"]
print(f"청주까지 호출 {after_cjj}회 · 3차 사용 노선 {S.DEEP_USED}")

for org, dst, city, region in S.SWISS:
    S.fetch_route(org, dst, city, region,
                  flex=S.SWISS_NIGHTS, window=S.SWISS_WINDOW, latest=True)
print(f"스위스까지 누적 {n['total']}회 · 3차 사용 노선 {S.DEEP_USED}")

sw_deep = [k for k in S.SWISS
           if "month-matrix" in by_route.get(f"{k[0]}-{k[1]}", [])]
print(f"3차까지 받은 스위스 노선 {len(sw_deep)}개: "
      f"{[f'{a}-{b}' for a,b,_,_ in sw_deep]}")

ok = True
def chk(c, m):
    global ok; print(("  OK   " if c else "  실패 ")+m); ok = ok and c
print("\n검사")
chk(n["total"] <= S.SEARCH_BUDGET, f"예산 {S.SEARCH_BUDGET} 이내 ({n['total']}회)")
chk(S.DEEP_USED.get("유럽", 0) <= S.DEEP_MAX["유럽"], "유럽 3차 상한 지킴")
chk(all(v <= S.DEEP_MAX.get(k, S.DEEP_MAX_DEFAULT)
        for k, v in S.DEEP_USED.items()), "모든 지역 상한 지킴")
chk(len(sw_deep) >= 4, "스위스 4개 노선이 3차까지 받음 (청주가 다 먹지 않음)")
sys.exit(0 if ok else 1)
