"""화면 구성이 요청대로 재배치됐는지, 문구가 서로 어긋나지 않는지 검사한다.

여기 있는 건 전부 "실제로 그렇게 틀렸던 것" 이다:
 - PC 에서 메뉴가 본문 뒤에 있어 긴 홈을 다 지나야 나왔다
 - 홈은 '실부담가 순' 이라 적고 실제로는 추천 점수로 줄을 세웠다
 - 설정은 '평균 대비', 상세는 '중앙값' 이라 적어 기준이 둘로 읽혔다
 - 카드를 누르면 상세가 열리는데 버튼에는 '예약 페이지' 라 적혀 있었다
 - 이동비 0원을 '집 앞' 이라고 단정했다 (0원은 위치를 증명하지 않는다)
"""
import os
import re
import sys

_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _R)
os.chdir(_R)

JS = open("web/app.js", encoding="utf-8").read()
# 화면에 실제로 나가는 문구만 보려면 주석을 떼야 한다. 주석에는 "예전에는
# 집 앞이라고 적었다" 같은 설명이 남아 있고, 그건 검사 대상이 아니다.
JS_OUT = re.sub(r"/\*.*?\*/", "", JS, flags=re.S)
JS_OUT = re.sub(r"^\s*//.*$", "", JS_OUT, flags=re.M)
HTML = open("web/index.html", encoding="utf-8").read()
CSS = open("web/app.css", encoding="utf-8").read()


def _fn(name):
    """함수 본문을 대충 떼어 온다 (최상위 function 끝은 줄머리 })."""
    i = JS.index(f"function {name}(")
    j = JS.index("\n}", i)
    return JS[i:j]


# ── 메뉴 ──────────────────────────────────────────────
def test_nav_comes_before_main():
    assert HTML.index("<nav id=\"tabbar\"") < HTML.index("<main id=\"app\""), \
        "PC 에서 sticky 메뉴가 본문 뒤에 있으면 화면 아래에 붙는다"


def test_tabs_are_the_four_agreed_ones():
    m = re.search(r"const TABS = \[(.*?)\];", JS, re.S)
    keys = re.findall(r"k: '(\w+)'", m.group(1))
    assert keys == ["home", "find", "swiss", "more"], keys


def test_secondary_screens_have_a_back_button():
    """더보기 아래로 내려간 화면은 돌아갈 길이 있어야 한다."""
    for name in ("설정", "에러페어", "주말여행", "가격 자료 부족 노선"):
        m = re.search(r"plainHeader\('" + re.escape(name) + r"',[^)]*\)", JS)
        assert m, f"{name} 화면을 못 찾았다"
        assert m.group(0).rstrip(")").rstrip().endswith("true"), \
            f"{name} 화면에 뒤로가기 버튼이 없다"


# ── 홈 ────────────────────────────────────────────────
def test_home_sort_label_matches_the_actual_ordering():
    home = _fn("viewHome")
    assert "ranked(" in home, "홈은 ranked() 로 줄을 세운다"
    assert "실부담가 순" not in home, \
        "ranked() 는 등급·추천점수까지 쓰는데 '실부담가 순' 이라 적으면 안 된다"
    assert "추천순" in home


def test_home_keeps_its_title_when_there_is_no_strong_deal():
    home = _fn("viewHome")
    assert "<h2>오늘 추천</h2>" in home
    assert "오늘 강력 특가가 없습니다" not in home, \
        "특가가 없는 것을 경고처럼 띄우지 않는다 — 정렬 상태만 설명한다"


def test_operational_blocks_moved_off_home():
    home = _fn("viewHome")
    for gone in ("seedChecklist(", "cjjSection(", "monthSection(", "providerLine("):
        assert gone not in home, f"홈에 아직 {gone} 이 남아 있다"
    more = _fn("viewMore")
    ana = _fn("viewAnalysis")
    assert "seedChecklist(" in _fn("viewSeed")
    assert "cjjSection(" in ana and "monthSection(" in ana
    assert "providerLine()" in more


# ── 문구 ──────────────────────────────────────────────
def test_comparison_baseline_is_named_consistently():
    assert "평균 대비" not in JS_OUT, "설정과 상세가 서로 다른 기준을 말하면 안 된다"
    assert "비교 기준가 대비" in JS


def test_card_cta_says_what_the_click_does():
    assert "이 가격으로 예약 페이지 열기" not in JS_OUT
    assert "일정·가격 보기" in JS, "카드를 누르면 상세가 열린다"
    assert "판매처에서 가격 확인" in JS, "상세에서만 판매처로 간다"


def test_zero_transfer_cost_is_not_called_home_airport():
    assert "집 앞" not in JS_OUT, \
        "이동비 0원은 위치를 증명하지 않는다 (설정에서 0으로 둔 것일 수도 있다)"
    assert "0원으로 설정됨" in JS


def test_annual_leave_plus_sign_is_spelled_out():
    assert "연차 ${n}일${confirmed" not in JS
    assert "연차 최소 ${n}일" in JS


def test_external_search_does_not_promise_collection():
    assert "검색이 끝까지\n      안 돌았다는 뜻" not in JS
    assert "외부 서비스 사정에 따라 반영되지 않을 수도 있습니다" in JS


def test_sort_names_match_what_they_do():
    m = re.search(r"const LIST_SORTS = \[(.*?)\];", JS, re.S)
    body = m.group(1)
    assert "'예상 부담액 낮은순'" in body and "effective(x) - effective(y)" in body
    assert "'할인율 높은순'" in body


# ── 만료 기준 통일 ────────────────────────────────────
def test_every_candidate_list_applies_the_same_expiry():
    """원본 offers 를 직접 거르는 곳은 만료도 같이 걸어야 한다.

    스위스 탭만 원본을 써서 만료 기준이 화면마다 달랐다."""
    for m in re.finditer(r"S\.data\.offers\.filter\(([^\n]*(?:\n[^\n]*){0,3}?)\)", JS):
        chunk = m.group(0)
        start = JS.rfind("\n", 0, m.start())
        line_no = JS[:m.start()].count("\n") + 1
        # 후보 목록이 아닌 것(표본 세기·진단)은 가격 유무로 거른다
        if "price_krw" in chunk or "isExpired(o)" in chunk or "duration" in chunk:
            continue
        raise AssertionError(f"app.js:{line_no} 만료 판정 없이 원본을 쓴다: {chunk[:80]}")


# ── 접근성 / 레이아웃 ─────────────────────────────────
def test_live_region_is_not_the_whole_body():
    assert 'id="live"' in HTML and 'role="status"' in HTML
    assert 'aria-live="polite"><div class="boot"' not in HTML, \
        "본문 전체를 aria-live 로 두면 렌더마다 화면을 통째로 읽는다"


def test_detail_sheet_has_a_pinned_action_area():
    assert ".sheet-cta{" in CSS and "position:sticky" in CSS.split(".sheet-cta{")[1][:200]
    d = _fn("detailHTML")
    assert 'class="sheet-cta"' in d
    assert d.index('class="sheet-cta"') > d.index("<h4>일정</h4>"), \
        "판매처 버튼은 일정·비용 뒤 하단 고정이다"
    assert "details class=\"fold\"" in d or '<details class="fold">' in d


def test_graph_range_does_not_rerender_the_whole_screen():
    assert "return paintChart();" in JS
    assert "id=\"chartbox\"" in JS


def test_touch_targets():
    """주요 조작 요소는 44px 이상."""
    for sel in (".fchip{", ".chip{", ".iconbtn{", ".rangebtns button{"):
        block = CSS.split(sel)[1].split("}")[0]
        m = re.search(r"min-height:(\d+)px|height:(\d+)px", block)
        assert m, f"{sel} 에 높이 지정이 없다"
        px = int(m.group(1) or m.group(2))
        assert px >= 44, f"{sel} {px}px < 44px"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
