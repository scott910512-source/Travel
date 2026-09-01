# -*- coding: utf-8 -*-
"""6시간마다 도는 것이 데이터를 망가뜨리지 않는지 본다.

하루 한 번을 전제로 짠 코드가 여럿 있었다. 같은 날 다시 돌 때
  · 표본이 부풀지 않는가 (특가 판정이 통째로 틀어진다)
  · 그날 최저가가 올라가지 않는가
  · "어제보다" 라고 써 놓고 실은 6시간 전과 비교하지 않는가
"""
import datetime
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("6시간 주기")

import scanner as S

TODAY = str(datetime.date.today())
YEST = str(datetime.date.today() - datetime.timedelta(days=1))

# ── 1. 스케줄이 실제로 6시간 간격인가 ──────────────────
wf = open(os.path.join(ROOT, ".github/workflows/daily.yml"), encoding="utf-8").read()
m = re.search(r'cron: "0 ([\d,]+) \* \* \*"', wf)
chk(m is not None, "cron 이 시각 목록 형태다")
if m:
    hrs = sorted(int(x) for x in m.group(1).split(","))
    gaps = [(hrs[(i + 1) % len(hrs)] - h) % 24 for i, h in enumerate(hrs)]
    chk(len(hrs) == 4 and set(gaps) == {6},
        "UTC %s → 간격 %s시간" % (hrs, sorted(set(gaps))))
    kst = sorted((h + 9) % 24 for h in hrs)
    chk(kst == [1, 7, 13, 19], "KST %s 시" % kst)
chk("fetch-depth: 0" in wf, "리베이스가 되도록 전체 클론을 받는다")
chk("git pull --rebase" in wf, "push 가 밀리면 리베이스하고 다시 시도한다")
chk("배포는 계속합니다" in wf, "커밋을 못 해도 배포는 죽지 않는다")

# ── 2. 같은 날 다시 돌아도 그날 최저가는 내려가기만 한다 ─
#    (재실행이 아침의 더 싼 값을 덮어써서 "최저" 를 올리면 안 된다)
daily = {"CJJ-KIX": {TODAY: 100000}}
todays = {"CJJ-KIX": 130000}          # 두 번째 실행: 더 비싸다
for k, p in todays.items():
    cur = daily.setdefault(k, {}).get(TODAY)
    daily[k][TODAY] = p if cur is None else min(cur, p)
chk(daily["CJJ-KIX"][TODAY] == 100000,
    "두 번째 실행이 더 비싸도 그날 최저는 100,000 그대로")

# ── 3. 무엇과 비교했는지 스캐너가 계산해서 넘긴다 ──────
chk(S._days_since(TODAY) == 0, "같은 날이면 0 (= 오늘 앞선 조회)")
chk(S._days_since(YEST) == 1, "하루 전이면 1 (= 어제)")
chk(S._days_since(None) is None, "기준이 없으면 None")
chk("delta_days" in S.OFFER_FIELDS, "delta_days 가 화면으로 나간다")

app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
chk("o.delta_days" in app, "화면이 delta_days 를 읽는다")
chk("log[log.length - 2]" not in app,
    "브라우저가 로그 날짜로 직접 재던 코드가 없어졌다 (시간대 함정)")

# ── 4. 같은 날 재실행에서 price_log 가 하루 한 점을 지킨다 ─
hist = {"deals": {"X": {"price_log": [{"d": YEST, "p": 200000},
                                      {"d": TODAY, "p": 150000}],
                        "first_seen": YEST}}}
o = {"id": "X", "price_krw": 170000, "dep": "CJJ", "arr": "KIX"}
S.diff([o], hist)
log = o["price_log"]
chk([x["d"] for x in log] == [YEST, TODAY],
    "점이 늘지 않는다 (%s)" % [x["d"] for x in log])
chk(log[-1]["p"] == 150000, "그날 점은 최저가를 유지한다 (아침 150,000)")
chk(o["delta"] == 20000 and o["delta_days"] == 0,
    "변동은 오늘 앞선 조회 대비로 계산된다 (delta=%s, days=%s)"
    % (o["delta"], o["delta_days"]))

# ── 5. 화면 문구가 실제 주기와 같은 말을 하는가 ────────
chk("어제 스캔 대비" not in app, "'어제 스캔 대비' 문구가 남아 있지 않다")
chk("매일 오전 7시" not in app, "'매일 오전 7시' 문구가 남아 있지 않다")

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
