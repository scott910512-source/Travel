# -*- coding: utf-8 -*-
"""표본이 얇은 노선을 "채워졌다" 고 넘기지 않는지 본다.

취리히는 3건뿐이라 아무리 싸도 '강력 특가' 가 안 붙는다. 그런데 0건이
아니라는 이유로 씨앗 목록에서 빠져 있었다. 회원님이 직접 잡아낸 것이다.

여기서 두 가지를 지킨다.
  1. 얇음 기준(SEED_THIN_N)이 특가 판정 기준과 같은 숫자다
  2. 이미 가진 날짜를 또 검색하라고 하지 않는다 (시간대 무관)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("얇은 노선 (표본 부족)")

# 1. 얇음 기준 == 특가 판정 기준. 둘이 어긋나면 "채우라" 고 해 놓고
#    채워도 판정이 안 되거나, 판정되는데도 계속 채우라고 한다.
m = re.search(r"const SEED_THIN_N = (\d+);", APP)
chk(m is not None, "SEED_THIN_N 이 있다")
thin_n = int(m.group(1)) if m else -1
tier = re.search(r"if \(pct >= strong && n >= (\d+)\) return 'strong';", APP)
chk(tier is not None and int(tier.group(1)) == thin_n,
    "SEED_THIN_N(%s) 이 dealTier 의 강력특가 표본 기준과 같다" % thin_n)

# 2. 취리히가 1순위다 (스위스 탭 규칙과 같은 말을 해야 한다)
m = re.search(r"const SEED_PRIORITY = \[(.*?)\];", APP)
chk(m is not None and "'ZRH'" in m.group(1), "취리히가 SEED_PRIORITY 에 있다")
chk("(b.pri ? 1 : 0) - (a.pri ? 1 : 0)" in APP,
    "정렬이 1순위를 맨 위로 올린다")

# 3. 매일 가격이 들어오는 노선까지 손으로 검색하라고 하지 않는다
chk("const needsMe = x =>" in APP and "SWISS_ORDER.indexOf(x.arr) !== -1" in APP,
    "저절로 차는 노선은 버튼 목록에서 뺀다")
chk("저절로 찹니다" in APP, "그 노선들도 숨기지 않고 한 줄로 알린다")

# ── 실제 로직을 node 로 돌린다 ─────────────────────────
# seedOffset 은 시간대 함정이 있는 코드다 (가격 변동 배지에서 한 번 겪었다).
# 소스만 훑지 말고 진짜 실행해서 확인한다.
def grab(name):
    i = APP.index("function %s(" % name)
    depth, j = 0, APP.index("{", i)
    k = j
    while True:
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return APP[i:k + 1]

src = re.search(r"const LIVE_OFFSETS = \[.*?\];", APP).group(0) + "\n"
src += grab("seedOffset") + "\n" + grab("samplesOf") + "\n"
src += """
const today = new Date();
const iso = d => d.toISOString().slice(0, 10);
const plus = n => { const d = new Date(today); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
const out = {};
// 취리히 실제 데이터: 45일 근처에 3건이 몰려 있다
out.clustered = seedOffset([{depart_date: plus(45)}, {depart_date: plus(46)}, {depart_date: plus(48)}]);
out.empty = seedOffset([]);
out.far = seedOffset([{depart_date: plus(105)}]);
out.samples0 = samplesOf([]);
out.samplesRows = samplesOf([{}, {}, {}]);
out.samplesBase = samplesOf([{baseline_n: 18}, {baseline_n: 3}]);
console.log(JSON.stringify(out));
"""

with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
    f.write(src)
    path = f.name

results = {}
for tz in ("UTC", "Asia/Seoul", "America/New_York", "Pacific/Kiritimati"):
    env = dict(os.environ, TZ=tz)
    p = subprocess.run(["node", path], capture_output=True, text=True, env=env)
    if p.returncode:
        chk(False, "node 실행 실패 (%s): %s" % (tz, p.stderr.strip()[:200]))
        break
    results[tz] = json.loads(p.stdout)
os.unlink(path)

if len(results) == 4:
    r = results["UTC"]
    chk(r["clustered"] != 45,
        "이미 45일 근처에 3건이 있으면 45일을 또 고르지 않는다 (고른 값 %s)" % r["clustered"])
    chk(r["empty"] == 45, "가진 게 없으면 첫 후보(45일)를 고른다")
    chk(r["far"] != 105, "105일에 데이터가 있으면 105일을 피한다 (고른 값 %s)" % r["far"])
    chk(r["samples0"] == 0, "행이 없으면 표본 0")
    chk(r["samplesRows"] == 3, "baseline_n 이 없으면 행 수를 쓴다")
    chk(r["samplesBase"] == 18, "baseline_n 이 크면 그걸 쓴다")
    same = all(v == r for v in results.values())
    chk(same, "시간대가 달라도 같은 날짜를 고른다 (%s)"
        % ", ".join("%s→%s" % (k.split("/")[-1], v["clustered"]) for k, v in results.items()))

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
