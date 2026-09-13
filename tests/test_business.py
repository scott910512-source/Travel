"""비즈니스석 참고 수집. '특가' 파이프라인과 섞이지 않는지가 핵심이다.

실측(2026-09-13): 좌석 등급을 요청으로 받는 곳은 month-matrix 뿐이고,
한 달에 노선당 0~5행, 전부 편도. 그래서 이 블록은 offers 밖에 따로 살고
등급·할인율·예상 부담액을 붙이지 않는다.
"""
import datetime
import json
import os
import sys

_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)
os.chdir(_R)

import scanner as S  # noqa: E402

TODAY = datetime.date.today()
FUT = (TODAY + datetime.timedelta(days=40)).isoformat()
PAST = (TODAY - datetime.timedelta(days=3)).isoformat()


def rows_for(org, dst):
    return [
        {"origin": "SEL", "destination": dst, "depart_date": FUT, "return_date": "",
         "value": 1814275, "trip_class": 1, "found_at": "2026-09-11T14:51:25Z"},
        {"origin": "SEL", "destination": dst, "depart_date": FUT, "return_date": "",
         "value": 1700000, "trip_class": 1, "found_at": "2026-09-12T01:00:00Z"},  # 같은 편 더 싼 값
        {"origin": "SEL", "destination": dst, "depart_date": FUT, "return_date": "",
         "value": 400000, "trip_class": 0},                                        # 이코노미 섞임
        {"origin": "SEL", "destination": dst, "depart_date": PAST, "return_date": "",
         "value": 1500000, "trip_class": 1},                                       # 지난 날짜
        {"origin": "SEL", "destination": dst, "depart_date": FUT, "return_date": "",
         "value": 0, "trip_class": 1},                                             # 0원
    ]


def fake_call_factory(log):
    def fake(path, params, retries=2):
        log.append((path, dict(params)))
        assert path == "/v2/prices/month-matrix"
        assert params.get("trip_class") == 1, "좌석 등급을 요청에 실어야 한다"
        return True, {"data": rows_for(params["origin"], params["destination"])}, None
    return fake


def _reset():
    S.BUSINESS[:] = []
    S.BIZSTAT.update({"calls": 0, "rows": 0, "kept": 0, "errors": [], "stopped": None})
    S.CIRCUIT.tripped = False


def test_only_business_rows_survive_and_are_deduped():
    _reset(); log = []
    out = S.fetch_business((30, 120), call_fn=fake_call_factory(log))
    assert out, "아무것도 안 남았다"
    for b in out:
        assert b["trip_class"] == 1 and b["cabin"] == "business"
        assert b["id"].endswith("-BUSINESS")
        assert b["one_way"] is True and b["return_date"] is None
        assert b["depart_date"] >= TODAY.isoformat()
        assert b["price_krw"] > 0
        assert "tier" not in b and "discount_pct" not in b and "baseline" not in b, \
            "참고값에 판정을 붙이면 안 된다"
        assert "annual_leave" not in b and "nights" not in b
        assert b["link"].startswith("https://www.aviasales.com/search/ICN")
        assert b["link"].endswith(b["arr"] + "1"), "편도 링크에 귀국일이 붙으면 안 된다"
    # 같은 편은 싼 쪽 하나만
    per = {}
    for b in out:
        per.setdefault((b["arr"], b["depart_date"]), []).append(b["price_krw"])
    for k, v in per.items():
        assert v == [1700000], f"{k}: {v}"


def test_budget_order_and_cap():
    """이코노미 뒤에 돌고, BIZ_MAX_CALLS 를 넘지 않고, 그 상한이 최악의
    이코노미 사용량 뒤에도 들어갈 만큼 작아야 한다."""
    _reset(); log = []
    S.fetch_business((30, 120), call_fn=fake_call_factory(log))
    assert len(log) == len(S.BIZ_TARGETS) * S.BIZ_MONTHS
    assert len(log) <= S.BIZ_MAX_CALLS
    src = open("scanner.py", encoding="utf-8").read()
    i = src.index("    fetch_business((WINDOW_MIN, WINDOW_MAX))")
    j = src.index("    meta = {\"date\": str(date.today()),")
    assert i < j, "비즈니스 수집은 meta 조립 직전(본 스캔 뒤)에 있어야 한다"
    assert src.index("def main(") < i


def test_cap_stops_early():
    _reset(); log = []
    old = S.BIZ_MAX_CALLS
    try:
        S.BIZ_MAX_CALLS = 2
        S.fetch_business((30, 120), call_fn=fake_call_factory(log))
        assert len(log) == 2 and S.BIZSTAT["stopped"] == "cap"
    finally:
        S.BIZ_MAX_CALLS = old


def test_budget_exceeded_stops_and_is_recorded():
    _reset()
    def broke(path, params, retries=2):
        return False, None, "BUDGET_EXCEEDED"
    out = S.fetch_business((30, 120), call_fn=broke)
    assert out == [] and S.BIZSTAT["stopped"] == "BUDGET_EXCEEDED"
    assert S.BIZSTAT["errors"]


def test_block_keeps_last_good_when_fetch_failed(tmp_path=None):
    _reset()
    S.BIZSTAT["errors"].append("ICN-ZRH 2026-10: HTTP 500")
    prev = os.path.join(_R, "flight-deals", "state", "deals.json")
    blk = S.business_block(prev)
    old = json.load(open(prev, encoding="utf-8")).get("business") or {}
    if old.get("offers"):
        assert blk["offers"] == old["offers"] and blk["stale"], "지난 값을 stale 로 남겨야 한다"
    else:
        assert blk["offers"] == [] and blk["stale"] is None
    assert blk["ts"]


def test_business_never_enters_offers_or_history_keys():
    src = open("scanner.py", encoding="utf-8").read()
    assert "BUSINESS.append" not in src.replace("BUSINESS[:] =", "")
    assert "offers.extend(BUSINESS)" not in src and "offers += BUSINESS" not in src
    d = json.load(open("flight-deals/state/deals.json", encoding="utf-8"))
    for o in d["offers"]:
        assert not str(o.get("id", "")).endswith("-BUSINESS")
        assert o.get("cabin") in (None, "economy")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
