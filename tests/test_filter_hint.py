# -*- coding: utf-8 -*-
"""좁은 조건과 조회 실패를 구분해서 보여주는가.

"다른 월 보는 게 조회가 제대로 안 된다" 는 신고가 들어왔다. 실제로는
청주 칩이 켜져 있어서 22건만 보인 것이었고(앱 전체 해외는 419건),
11월 칩은 그 조합에 0건이라 통째로 사라져 있었다. 조회가 안 되는 것과
조건이 좁은 것은 다르다 — 화면이 그걸 구분해 말해야 한다.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
css = open(os.path.join(ROOT, "web", "app.css"), encoding="utf-8").read()

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("좁은 조건 안내")

# ── 1. 월 목록은 출발지·국내해외를 걸기 전에서 만든다 ──
#     (안 그러면 0건인 달이 사라져 "조회가 안 된다" 로 읽힌다)
m = re.search(r"const wide = visibleOffers\(\);\s*\n\s*const months = monthsIn\(wide\)", app)
chk(m is not None, "월 칩 목록을 visibleOffers() 에서 만든다 (좁힌 pool 이 아니라)")
chk("monthsIn(base)" not in app, "예전처럼 좁힌 pool 로 월을 만들지 않는다")
chk("m.n ? '' : ' zero'" in app, "0건인 달은 지우지 않고 흐리게 둔다")

# ── 2. 지금 걸린 조건을 건수 옆에 그대로 적는다 ────────
chk("function activeFilterTxt(" in app, "걸린 조건을 문장으로 만든다")
for k in ("S.origin !== 'all'", "S.scope !== 'all'", "monthLabel(mo)"):
    chk(k in app.split("function activeFilterTxt(")[1].split("\n}")[0],
        "activeFilterTxt 가 %s 를 본다" % k)

# ── 3. 안내 숫자는 그 버튼이 실제로 하는 일과 같아야 한다 ──
#     예전 초안은 두 조건을 다 푼 값(37)을 적고 버튼은 출발지만 풀어서(36)
#     눌러 보면 숫자가 달랐다. 안내가 틀리면 없느니만 못하다.
body = app[app.index("function narrowInfo("):app.index("function narrowNote(")]
chk("wide.filter(o => inScope(o, S.scope)).length" in body,
    "byOrigin 은 국내/해외를 유지한 채 출발지만 푼 값이다")
chk("wide.filter(o => inGroup(o.dep, S.origin)).length" in body,
    "byScope 는 출발지를 유지한 채 국내/해외만 푼 값이다")
note = app[app.index("function narrowNote("):app.index("function viewList()")]
chk("data-origin=\"all\"" in note and "info.byOrigin" in note,
    "'전체 출발지' 버튼에 byOrigin 을 적는다")
chk("data-scope=\"all\"" in note and "info.byScope" in note,
    "'국내+해외' 버튼에 byScope 를 적는다")
chk("g.key !== S.origin" in note, "이미 고른 출발지는 바로가기에 다시 넣지 않는다")

# ── 4. 이유를 두 번 적지 않는다 ────────────────────────
chk("narrowWhy" not in app, "이유를 두 곳에서 만들던 함수가 남아 있지 않다")
chk("위 안내에서 조건을 넓혀 보세요" in app,
    "빈 화면은 이유를 되풀이하지 않고 위 안내를 가리킨다")

# ── 5. 문단 안 강조가 줄을 끊지 않는다 ─────────────────
chk(".note>b{display:block" in css, "안내 제목만 block 이다")
chk(".note p b{display:inline" in css,
    "문단 안 <b> 는 inline (예전에는 '36건' 이 매번 줄바꿈됐다)")

# ── 6. 홈에서도 달을 고를 수 있는가 ────────────────────
chk("function monthChipsHTML(" in app, "홈에 월 칩 줄이 있다")
chk("${headerHTML()}${chipsHTML()}${monthChipsHTML()}" in app,
    "홈이 월 칩을 그린다")
chk("S.listMonth" not in app,
    "홈과 목록이 같은 S.month 를 쓴다 (두 벌이면 '전체 보기' 에서 어긋난다)")
chk("const inMonth = o => !S.month || monthKey(o) === S.month;" in app,
    "달이 출발지·국내해외와 곱해서 걸린다")
chk("homeOffers().filter(inMonth)" in app, "홈 pool 에 달이 걸린다")
hnd = app[app.index("const mf = t.getAttribute('data-month');"):][:600]
chk("t.hasAttribute('data-month-goto')" in hnd,
    "칩은 그 자리에서 걸고, '월별로 보기' 줄만 목록으로 넘어간다")
chk("data-month-goto" in app.split("function monthSection(")[1],
    "월 섹션 줄에만 이동 표식이 붙는다")
m2 = re.search(r"function monthChipsHTML\(\)[\s\S]*?\n}", app)
chk(m2 and "monthsIn(wide)" in m2.group(0),
    "홈 월 칩도 좁히기 전 목록에서 만든다 (0건인 달이 사라지지 않는다)")

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
