# -*- coding: utf-8 -*-
"""배포된 것이 최신인지 확인할 수 있는가.

"GitHub 최신 코드와 실제 Pages 화면이 다르다" 는 신고가 들어왔는데,
실제로는 배포가 멀쩡했고 기기가 옛 app.js 를 캐시하고 있었다. UI 전체가
app.js 안에 있어서 그게 곧 "과거 화면" 이 된다. deals.json 만 no-cache 로
받으니 데이터는 최신이라 원인을 짚기가 더 어려웠다.

두 가지를 지킨다.
  1. 배포마다 app.js·app.css 의 URL 이 바뀐다 (캐시가 붙들 수 없다)
  2. 화면이 스스로 어떤 빌드인지 말한다 (다음엔 바로 알 수 있다)
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

fail = []
def chk(c, m):
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c:
        fail.append(m)

print("배포 최신성")

wf = open(os.path.join(ROOT, ".github/workflows/daily.yml"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()
app = open(os.path.join(ROOT, "web/app.js"), encoding="utf-8").read()

# ── 1. Pages 산출물에 필요한 파일이 전부 들어가는가 ────
for f in ("web/index.html", "web/app.css", "web/app.js",
          "deals.json", "brief.json", "manifest.webmanifest"):
    chk(f in wf, "산출물에 %s 가 들어간다" % f)

# ── 2. 캐시 무력화가 실제로 동작하는가 (sed 를 진짜 돌려 본다) ──
import yaml
d = yaml.safe_load(wf)
step = next(s for s in d["jobs"]["scan"]["steps"] if s.get("name") == "Pages 산출물 준비")
tmp = tempfile.mkdtemp()
open(os.path.join(tmp, "index.html"), "w", encoding="utf-8").write(html)
script = "\n".join(l for l in step["run"].splitlines()
                   if l.strip().startswith(("sed", "BUILD=")))
script = 'GITHUB_SHA="abc1234567890"\n' + script.replace("public/index.html", "index.html")
r = subprocess.run(["bash", "-c", script], cwd=tmp, capture_output=True, text=True)
chk(r.returncode == 0, "sed 스크립트가 돈다 (%s)" % (r.stderr.strip()[:120] or "ok"))
out = open(os.path.join(tmp, "index.html"), encoding="utf-8").read()
chk('src="app.js?v=abc1234"' in out, "app.js 에 빌드 버전이 붙는다")
chk('href="app.css?v=abc1234"' in out, "app.css 에 빌드 버전이 붙는다")
chk('content="abc1234"' in out, "meta build 가 채워진다")
chk("__BUILD__" not in out, "치환 안 된 자리가 남지 않는다")

# ── 3. 화면이 자기 빌드를 말하는가 ─────────────────────
chk('name="build"' in html, "index.html 에 build 표식이 있다")
chk("function buildId()" in app, "app.js 가 build 를 읽는다")
chk("'로컬'" in app, "치환 전이면 '로컬' 로 적는다 (가짜 SHA 를 지어내지 않는다)")

# ── 4. 스캔 나이와 provider 상태 ───────────────────────
chk("function scanAgo(" in app, "마지막 스캔이 몇 시간 전인지 적는다")
chk("+m[4] - 9" in app, "ts 를 KST 로 해석한다 (브라우저 시간대와 무관)")
chk("function providerLine(" in app, "provider 별 상태를 적는다")
chk("p.errors && p.errors.length" in app,
    "에러난 provider 와 토큰 없어 꺼진 provider 를 구분한다")

# ── 5. 데이터는 캐시하지 않는다 ────────────────────────
chk("cache: 'no-cache'" in app, "deals.json 은 캐시하지 않는다")

print("실패 %d" % len(fail))
sys.exit(1 if fail else 0)
