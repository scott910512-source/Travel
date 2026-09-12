"""주말여행 판정이 실제 데이터에서 0건으로 죽어 있지 않은지 검사한다.

한때 weekend_trip 에 `and tp["leave_confirmed"]` 가 걸려 있었다. 도착
시각을 주는 소스가 v3 뿐이라 confirmed 는 한 건도 나오지 않았고, 그래서
주말 화면이 몇 달 동안 통째로 비어 있었다. 화면은 멀쩡해 보였다 —
"이 구간에 연차 1일 이하 일정이 없습니다" 라고 적혀 있었으니까.

거르는 기준(최소값)과 단정하는 말('연차 1일')은 다르다. 둘 다 확인한다.
"""
import datetime
import json
import os
import re
import sys

_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)
os.chdir(_R)

import scanner  # noqa: E402

D = datetime.date.fromisoformat
DATA = json.load(open("flight-deals/state/deals.json", encoding="utf-8"))
JS = open("web/app.js", encoding="utf-8").read()


def _wk(o):
    tp = scanner.trip_profile(
        D(o["depart_date"]), D(o["return_date"]), o.get("dep_hour"),
        D(o["home_arrive_date"]) if o.get("home_arrive_date") else None)
    return tp["weekend"] and tp["leave"] <= 1.0


def test_weekend_trip_is_not_permanently_empty():
    """오늘 데이터에서 주말여행 후보가 실제로 잡혀야 한다."""
    hits = [o for o in DATA["offers"] if _wk(o)]
    assert hits, (
        "주말여행 후보가 0건이다. 판정 조건이 실제 데이터에서 절대 참이 "
        "될 수 없는 값(예: leave_confirmed)에 걸려 있지 않은지 확인하라")


def test_weekend_trip_does_not_require_a_field_the_source_never_sends():
    src = open("scanner.py", encoding="utf-8").read()
    i = src.index('"weekend_trip":')
    expr = src[i:src.index("\n", src.index(",", i))]
    assert "leave_confirmed" not in expr, (
        "확정 여부로 후보를 거르면 안 된다 — 소스가 도착 시각을 거의 안 준다. "
        "거르는 것은 최소값으로 하고, 확정 여부는 화면 문구로 구분하라")


def test_unconfirmed_leave_is_never_stated_as_a_fact():
    """후보에는 넣되, 확정이라고 말하지는 않는다."""
    assert "연차 최소 ${n}일" in JS, "미확정 연차는 '최소' 라고 적는다"
    wk = JS[JS.index("function viewWeekend()"):JS.index("function plainHeader(")]
    assert "unsure" in wk and "연차는 최소값입니다" in wk, \
        "주말 화면이 '최소' 라는 사실을 알리지 않는다"
    assert "{ v: 0, l: '연차 0일'" not in wk, \
        "구간 제목이 연차를 확정처럼 적는다"


def test_home_arrive_coverage_is_reported_honestly():
    """실제로 도착일이 얼마나 채워지는지 기록해 둔다 (0이어도 실패는 아니다)."""
    n = sum(1 for o in DATA["offers"] if o.get("home_arrive_date"))
    print(f"     한국 도착일 확인 {n}/{len(DATA['offers'])}건")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
