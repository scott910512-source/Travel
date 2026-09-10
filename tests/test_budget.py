# 모든 노선이 0건을 주는 최악의 경우, 예산 안에서 끝나고 스위스가
# 왕복 소스(v3)와 3차 소스를 실제로 받는가.
import sys, os
# 레포 위치에 상관없이 돈다. 절대경로를 박아 두면 CI 러너에서 깨진다
# (실제로 그랬다 — verify 가 생기고 나서야 드러났다).
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R); os.chdir(_R)
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

# ★ 예전에는 청주 + 스위스만 재고 "152회" 라고 했다. main() 은 그 사이에
#   출발지별 노선(ICN/TAE/PUS)과 관심 노선까지 돈다. 그걸 빼고 재니 실제
#   지출(217회)의 70%만 보고 있었고, 관심 노선을 15개 늘렸을 때 예산이
#   정확히 소진되는 것을 놓칠 뻔했다. main() 과 같은 순서·같은 dedupe 로 잰다.
targets = []
for g in ("icn", "tae", "pus"):
    targets += S.ROUTES.get(g, [])
targets += S.SWISS
watch = S.load_watchlist()
targets += watch
seen = set()
targets = [t for t in targets if not (t[:2] in seen or seen.add(t[:2]))]
print(f"출발지별+스위스+관심 {len(targets)}개 (관심 {len(watch)})")
for org, dst, city, region in targets:
    if region == "유럽":
        S.fetch_route(org, dst, city, region,
                      flex=S.SWISS_NIGHTS, window=S.SWISS_WINDOW, latest=True)
    else:
        S.fetch_route(org, dst, city, region, nights=S.NIGHTS, latest=True)
print(f"전체 누적 {n['total']}회 · 3차 지출 {S.DEEP_SPENT}")

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
# 정확히 소진되면 목록 뒤쪽(새 탐색 노선)이 조용히 잘린다. 여유를 남긴다.
chk(n["total"] <= S.SEARCH_BUDGET * 0.92,
    f"최악의 경우에도 여유가 남는다 ({n['total']}/{S.SEARCH_BUDGET})")
chk(all(v <= S.DEEP_BUDGET[k] for k, v in S.DEEP_SPENT.items()),
    f"3차 호출 상한 지킴 {S.DEEP_SPENT}")
chk(len(sw_v3) == 6, "스위스 6개 노선 전부 왕복 소스(v3)를 받는다")
chk(len(sw_deep) >= 4, "스위스가 3차까지 도달 (청주가 예산을 다 먹지 않음)")
chk(S.DEEP_SPENT.get("_other", 0) <= S.DEEP_BUDGET["_other"],
    "유럽 밖은 통짜 한 바구니로 제한된다")
sys.exit(0 if ok else 1)
