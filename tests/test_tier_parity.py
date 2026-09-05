# -*- coding: utf-8 -*-
"""Python 브리프와 JavaScript 화면의 특가 판정이 같은가.

두 곳에 같은 규칙이 따로 구현돼 있다. 한쪽만 고치면 아침 브리프와 화면이
다른 말을 한다. 공유 사례로 붙잡아 둔다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import scanner as S

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

cases = json.load(open(os.path.join(ROOT, "tests/fixtures/tier_cases.json"),
                       encoding="utf-8"))["cases"]

print("특가 판정 — Python ↔ JavaScript")

# JS 쪽 dealTier 를 그대로 잘라 실행한다
app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
src = app[app.index("const MIN_JUDGE_N"):app.index("const TIER_LABEL")]
body = ("const out=[];" +
        "for (const c of " + json.dumps(cases) + ") {"
        "  S={settings:{strongPct:c.strong}};"
        "  out.push(dealTier({data_ok:true, discount_pct:c.pct, baseline_n:c.n}));"
        "}" "console.log(JSON.stringify(out));")
p = subprocess.run(["node", "-e", "let S;" + src + body],
                   capture_output=True, text=True)
if p.returncode:
    print(p.stderr[:400]); sys.exit(1)
js = json.loads(p.stdout)

for c, got_js in zip(cases, js):
    got_py = S.deal_tier(c["pct"], c["n"], c["strong"])
    ok = got_py == got_js == c["tier"]
    chk(ok, "%-28s py=%-9s js=%-9s 기대=%s"
        % (c["why"], got_py, got_js, c["tier"]))

chk("MIN_JUDGE_N" in app or "baseline_n" in app,
    "JS 도 표본 문턱을 본다")
print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
