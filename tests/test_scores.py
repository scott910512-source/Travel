# -*- coding: utf-8 -*-
"""DEAL / CONFIDENCE 를 섞지 않는가, 표본이 모자랄 때 판정을 미루는가.

이 앱에서 가장 위험한 오류는 특가를 놓치는 것이 아니라, 특가가 아닌 것을
특가라고 확신시키는 것이다. 그러니 애매하면 판정하지 않아야 한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("판정과 신뢰도")
import scanner as S

# ── 1. 표본이 모자라면 등급을 주지 않는다 ──────────────
chk(S.deal_tier(61.4, 4) == "unknown",
    "표본 4건 · 61% 할인 → 판정 보류 (예전에는 '특가 후보')")
chk(S.deal_tier(80.0, 1) == "unknown", "표본 1건은 아무리 싸도 판정 보류")
chk(S.deal_tier(35.0, 10) == "strong", "표본 10건 · 35% → 강력 특가")
chk(S.deal_tier(25.0, 6) == "deal", "표본 6건 · 25% → 특가")
chk(S.deal_tier(None, 50) == "unknown", "할인율을 모르면 판정 보류")
chk(S.MIN_JUDGE_N == 5, "판정 문턱이 5건이다")

# ── 2. 하루에 몰린 표본을 '높음' 이라 하지 않는다 ──────
chk(S.confidence(20) == "높음", "추적일수를 모르면 표본대로 (구버전 호환)")
chk(S.confidence(20, 3) == "보통", "★ 표본 20건이어도 추적 3일이면 '보통' 이 상한")
chk(S.confidence(20, 30) == "높음", "30일 쌓였으면 '높음'")
chk(S.confidence(2, 30) == "참고", "추적이 길어도 표본이 없으면 '참고'")

# ── 3. CONFIDENCE 는 근거를 말할 수 있어야 한다 ────────
o = {"baseline_n": 20, "roundtrip_verified": True, "stops_src": "row",
     "sources": [{"s": 1}, {"s": 2}], "found_at": None}
sc, parts = S.confidence_score(o, 30)
chk(sc > 0 and parts, "점수와 근거가 같이 나온다 (%d점, %d항목)" % (sc, len(parts)))
chk(sum(p for _, p in parts) >= sc, "점수가 근거 합을 넘지 않는다")
lo, _ = S.confidence_score(dict(o, baseline_n=3), 30)
chk(lo <= 25, "표본이 문턱 아래면 다른 게 좋아도 상한 25 (%d)" % lo)
mid, _ = S.confidence_score(dict(o, baseline_n=7), 30)
chk(mid <= 45, "표본 5~9건이면 상한 45 (%d)" % mid)
few, _ = S.confidence_score(o, 1)
many, _ = S.confidence_score(o, 30)
chk(few < many, "추적이 짧으면 점수가 낮다 (%d < %d)" % (few, many))
one, _ = S.confidence_score(dict(o, sources=[{"s": 1}]), 30)
chk(one < many, "provider 가 하나면 점수가 낮다 (%d < %d)" % (one, many))
nort, _ = S.confidence_score(dict(o, roundtrip_verified=False), 30)
chk(nort < many, "왕복 미확인이면 점수가 낮다 (%d < %d)" % (nort, many))

# ── 4. 지난 정상 데이터를 지킨다 ───────────────────────
import tempfile
tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "deals.json")
json.dump({"meta": {"ts": "2026-09-01 13:02 KST"},
           "offers": [{"id": i} for i in range(100)]},
          open(p, "w", encoding="utf-8"))

S.ERRORS.clear()
kept, note = S.guard_previous([{"id": "x"}] * 90, p)
chk(note is None and len(kept) == 90, "조금 줄어든 건 그대로 내보낸다")

kept, note = S.guard_previous([{"id": "x"}] * 5, p)
chk(note is None and len(kept) == 5,
    "에러 없이 크게 줄었으면 소스에 없는 것이다 — 그대로 내보낸다")

S.ERRORS.append("HTTP 500")
kept, note = S.guard_previous([{"id": "x"}] * 5, p)
chk(note and len(kept) == 100, "★ 에러 + 급감이면 지난 데이터를 지킨다")
chk(note and note["last_good"] == "2026-09-01 13:02 KST",
    "마지막 정상 시각을 같이 남긴다 (%s)" % (note or {}).get("last_good"))
S.ERRORS.clear()

kept, note = S.guard_previous([{"id": "x"}], os.path.join(tmp, "없음.json"))
chk(note is None and len(kept) == 1, "이전 파일이 없으면 그냥 진행한다")

# ── 5. 화면이 세 축을 따로 그리는가 ────────────────────
app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
for fn in ("function dealScore(", "function confScore(", "function tripFit(",
           "function rankScore(", "function scoresHTML(", "function staleNote("):
    chk(fn in app, "%s 가 있다" % fn.replace("function ", "").replace("(", ""))
chk("o.confidence ]" not in app and "mult" not in app.split("function dealScore(")[1].split("}")[0],
    "DEAL 안에 신뢰도 계수가 섞여 있지 않다")
chk("'최신 스캔 실패'" in app or "최신 스캔이 실패" in app,
    "지난 데이터를 보고 있으면 화면이 말한다")

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
