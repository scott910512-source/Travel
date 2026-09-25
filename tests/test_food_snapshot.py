"""식당 리스트의 구글 조회는 '한 번 조회해서 저장, 다시 조회는 요청할 때만' 이어야 한다."""
import os, re, sys, subprocess, json, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
food = open(os.path.join(ROOT, "web/okinawa-2026-10-food.html"), encoding="utf-8").read()
wf = open(os.path.join(ROOT, ".github/workflows/daily.yml"), encoding="utf-8").read()
probe = open(os.path.join(ROOT, "tools/probe_food.mjs"), encoding="utf-8").read()
fails = 0
def chk(c, m):
    global fails
    print(("  ✅ " if c else "  ❌ ") + m)
    if not c: fails += 1

js = food[food.index("<script>"):]
# 자동 조회 금지: genrich 호출은 버튼 핸들러 안에만 있어야 한다.
calls = [m.start() for m in re.finditer(r"(?<!function )genrich\(", js)]
auto = [c for c in calls if "addEventListener" not in js[max(0, c - 400):c] and "on('gre'" not in js[max(0, c - 400):c]]
chk(not auto, "페이지가 열릴 때 구글을 자동으로 조회하지 않는다 (genrich 는 버튼에서만)")
chk("24*3600" not in js and "24 * 3600" not in js, "24시간 만료가 없다 (한 번 저장하면 계속 쓴다)")
chk("fetch(SNAP" in js and "okinawa-2026-10-food.json" in js, "시작할 때 저장본 JSON 을 읽는다")
chk("function merge()" in js and "(b.t||0)>st" in js, "저장본과 기기 조회 중 더 최근 것을 쓴다")
chk("MIN_RATING_FALLBACK=4.0" in js and "function computeTH()" in js and "thr(x)" in js, "4.3 이상이 없는 메뉴는 4.0 기준으로 낮춘다")
chk("confirm(" in js and "다시 조회" in js, "다시 조회는 사람이 누르고 확인해야 한다")
chk("AIza" not in js.replace("AIza… 브라우저 API 키", "").replace("startsWith('__')", ""), "소스에 실제 키가 없다")

chk("probe == 'food'" in wf and "node tools/probe_food.mjs" in wf, "워크플로 probe=food 가 저장본을 만든다")
chk("git add web/okinawa-2026-10-food.json web/food-photos" in wf, "저장본과 사진을 커밋한다")
chk("cp web/okinawa-2026-10-food.json public/" in wf and "cp -r web/food-photos public/" in wf, "배포 산출물에 저장본·사진이 들어간다")
chk("MAPS_SERVER_KEY" in wf and "secrets.MAPS_SERVER_KEY" in wf, "서버 키는 Secret 에서만 온다")
chk("console.log(key" not in probe and "console.log(`" not in probe.split("const key")[0], "프로브가 키를 로그에 찍지 않는다")
chk("replace(key, '***')" in probe, "오류 메시지에서도 키를 가린다")
chk("JSON.stringify(out).includes(key)" in probe, "결과 JSON 에 키가 들어가면 실패한다")

# Verify extractor completeness against the exported catalog, without freezing its size.
r = subprocess.run(["node", "--input-type=module", "-e",
    "import fs from 'node:fs'; import {createRequire} from 'node:module'; const req=createRequire(import.meta.url); const m=await import('%s'); const R=m.extractList(fs.readFileSync('%s','utf8')); const expected=req('%s').restaurants; console.log(JSON.stringify({actual:R.map(x=>x.id).sort(),expected:expected.map(x=>x.id).sort(),valid:R.every(x=>x.id&&x.n&&x.a)}));"
    % (os.path.join(ROOT, "tools/probe_food.mjs").replace("\\", "/"), os.path.join(ROOT, "web/trip-data.js").replace("\\", "/"), os.path.join(ROOT, "web/trip-data.js").replace("\\", "/"))],
    capture_output=True, text=True, env={**os.environ, "MAPS_SERVER_KEY": "x"})
try:
    result = json.loads(r.stdout)
except (ValueError, TypeError):
    result = {}
actual = result.get("actual", [])
chk(r.returncode == 0 and len(actual) >= 49 and len(set(actual)) == len(actual) and actual == result.get("expected") and result.get("valid"), "프로브가 식당 목록 전체를 중복·누락 없이 읽는다 (%d곳)" % len(actual))
print("실패", fails)
sys.exit(1 if fails else 0)
