#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
항공권 데일리 스캐너 v2.1 — Travelpayouts(Aviasales) 연동본

프롬프트 v2.1 규칙을 코드로 구현한 것.
매일 1회 실행 → 수집 → 채점 → 어제 대비 변동 → latest.html 생성.

사용법
  export TP_TOKEN="토큰"
  python3 scanner.py                # 정상 실행
  python3 scanner.py --raw          # 원본 응답 확인 (첫 실행 시 필수)
  python3 scanner.py --all          # 로테이션 무시하고 전 노선 스캔

출력
  ./flight-deals/latest.html
  ./flight-deals/archive/deals-YYYY-MM-DD.html
  ./flight-deals/state/price_history.json
  ./flight-deals/logs/run-YYYY-MM-DD.md

의존성 없음 (표준 라이브러리만).

──────────────────────────────────────────────────────────────
등급 정책 (중요)

Travelpayouts는 캐시 데이터(2~7일)라서 이 스캐너는 구조적으로
A등급을 만들 수 없다. 최대 B등급이다. 코드에 하드코딩되어 있고,
바꾸지 마라. A등급은 실시간 확정 왕복가 + 예약페이지가 있어야 한다.

정상가 비교는 외부 소스 없이 자체 산출한다:
같은 노선·같은 박수의 그 달 전체 일자 가격 분포에서 중앙값을 뽑아
기준선으로 쓴다. 실측 데이터 기반이라 근거로 성립한다.
──────────────────────────────────────────────────────────────
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

# ══════════════════════════════════════════════════════════
# 설정
# ══════════════════════════════════════════════════════════

KST = timezone(timedelta(hours=9))
BASE = "https://api.travelpayouts.com"
# 내장 토큰 — Cowork 상시 실행용. 재발급하면 이 줄만 바꾸면 됨.
DEFAULT_TOKEN = ""   # 공개 레포. 토큰은 TP_TOKEN 환경변수/시크릿으로만.

CONFIG_PATHS = [
    os.path.join(os.getcwd(), "tp_config.json"),
    os.path.expanduser("~/.travelpayouts.json"),
]


def load_token(cli=None):
    """우선순위: --token > TP_TOKEN 환경변수 > 설정파일"""
    if cli:
        return cli.strip()
    env = os.environ.get("TP_TOKEN", "").strip()
    if env:
        return env
    for p in CONFIG_PATHS:
        try:
            with open(p, encoding="utf-8") as f:
                t = (json.load(f).get("token") or "").strip()
            if t:
                return t
        except Exception:
            continue
    return DEFAULT_TOKEN


def save_token(tok):
    """설정파일에 저장. 소유자만 읽기(0600)."""
    p = CONFIG_PATHS[1]
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"token": tok.strip()}, f)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass
    return p


TOKEN = ""   # main()에서 주입
CURRENCY = "krw"
ROOT = os.path.join(os.getcwd(), "flight-deals")

SEARCH_BUDGET = 120       # 노선당 4회(박수 4종). 풀스캔 17노선 = 68회
REQ_SLEEP = 0.45          # rate limit 여유
TIMEOUT = 25

WINDOW_MIN, WINDOW_MAX = 3, 75      # D+3 ~ D+75
NIGHTS = (2, 3, 4, 5)               # 2박3일 ~ 5박6일

# 출발지별 노선
ROUTES = {
    "icn": [("ICN", "KIX", "오사카", "일본"), ("ICN", "NRT", "도쿄", "일본"),
            ("ICN", "FUK", "후쿠오카", "일본"), ("ICN", "TPE", "타이베이", "중화권"),
            ("ICN", "BKK", "방콕", "동남아"), ("GMP", "HND", "도쿄", "일본")],
    "cjj": [("CJJ", "KIX", "오사카", "일본"), ("CJJ", "NRT", "도쿄", "일본"),
            ("CJJ", "TPE", "타이베이", "중화권"), ("CJJ", "DAD", "다낭", "동남아")],
    "tae": [("TAE", "KIX", "오사카", "일본"), ("TAE", "TPE", "타이베이", "중화권"),
            ("TAE", "DAD", "다낭", "동남아")],
    "pus": [("PUS", "FUK", "후쿠오카", "일본"), ("PUS", "KIX", "오사카", "일본"),
            ("PUS", "TPE", "타이베이", "중화권"), ("PUS", "DAD", "다낭", "동남아")],
}
SWISS = [("ICN", "ZRH", "취리히", "유럽"), ("ICN", "GVA", "제네바", "유럽"),
         ("ICN", "BSL", "바젤", "유럽")]

# 권역 기준선 (왕복 이코노미 KRW) — 절대가 점수용
# ★ --raw 판정 결과를 여기에 반영.
#   False = /v1/prices/calendar 의 price 가 왕복 총액 (현재 가정)
#   True  = 편도.  아래 REGION_BASE 가 자동으로 절반으로 스케일됨.
# 주의: discount_pct / verdict() 는 같은 버킷 중앙값 대비 상대값이라
#       스케일 불변이다. 이 플래그가 영향을 주는 곳은 REGION_BASE 뿐.
ONE_WAY_PRICE = False

_REGION_BASE_RT = {"일본": 220000, "중화권": 260000, "동남아": 380000,
                   "유럽": 1150000, "미주": 1300000, "국내선": 90000}
REGION_BASE = ({k: v // 2 for k, v in _REGION_BASE_RT.items()}
               if ONE_WAY_PRICE else _REGION_BASE_RT)

# 2026 하반기 확정 공휴일 (연휴 판정)
HOLIDAYS = {
    "2026-09-24": "추석", "2026-09-25": "추석", "2026-09-26": "추석",
    "2026-10-03": "개천절", "2026-10-05": "개천절 대체", "2026-10-09": "한글날",
    "2026-12-25": "성탄절",
}

AIRLINES = {"KE": "대한항공", "OZ": "아시아나", "7C": "제주항공", "TW": "티웨이",
            "LJ": "진에어", "BX": "에어부산", "RS": "에어서울", "ZE": "이스타",
            "RF": "에어로케이", "YP": "에어프레미아"}


# ══════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════

class Budget:
    def __init__(self, cap): self.cap, self.used = cap, 0
    def take(self):
        if self.used >= self.cap:
            return False
        self.used += 1
        return True


BUDGET = Budget(SEARCH_BUDGET)
ERRORS = []


class Circuit:
    """연속 실패가 임계치를 넘으면 즉시 중단. 장애 시 예산·시간 낭비 방지."""
    LIMIT = 6

    def __init__(self):
        self.streak, self.tripped, self.cause = 0, False, None

    def ok(self):
        self.streak = 0

    def fail(self, why):
        self.streak += 1
        if self.streak >= self.LIMIT and not self.tripped:
            self.tripped, self.cause = True, why


CIRCUIT = Circuit()


def call(path, params, retries=2):
    if CIRCUIT.tripped:
        return False, None, "CIRCUIT_OPEN"
    if not BUDGET.take():
        return False, None, "BUDGET_EXCEEDED"
    q = dict(params); q["token"] = TOKEN
    url = f"{BASE}{path}?{urllib.parse.urlencode(q)}"
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "X-Access-Token": TOKEN, "Accept": "application/json",
                "User-Agent": "flight-daily-scanner/2.1"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = json.loads(r.read().decode("utf-8"))
            if isinstance(body, dict) and body.get("success") is False:
                CIRCUIT.fail(str(body.get("error") or "success=false"))
                return False, None, str(body.get("error") or "success=false")
            CIRCUIT.ok()
            return True, body, None
        except urllib.error.HTTPError as e:
            deny = e.headers.get("x-deny-reason")
            if e.code == 401:
                CIRCUIT.fail("401 인증 실패 — 토큰 확인")
                return False, None, "401 인증 실패"
            if deny:                       # 방화벽/프록시 차단은 재시도 무의미
                why = f"HTTP {e.code} · {deny}"
                CIRCUIT.streak = CIRCUIT.LIMIT
                CIRCUIT.fail(why)
                return False, None, why
            if e.code == 429 and i < retries:
                time.sleep(2 * (i + 1)); continue
            CIRCUIT.fail(f"HTTP {e.code}")
            return False, None, f"HTTP {e.code}"
        except Exception as e:
            if i < retries:
                time.sleep(1.5); continue
            CIRCUIT.fail(type(e).__name__)
            return False, None, f"{type(e).__name__}"
    CIRCUIT.fail("unreachable")
    return False, None, "unreachable"


# ══════════════════════════════════════════════════════════
# 수집
# ══════════════════════════════════════════════════════════

def fetch_route(org, dst, city, region, months=None):
    """노선 하나를 박수별로 조회. 정규화된 offer 리스트 반환.

    depart_date(월) 필터는 API 가 무시하고 캐시 전 구간을 반환하므로
    월 루프를 돌리지 않는다. 월별로 돌리면 같은 데이터를 중복 수집해
    build_baselines() 의 표본 수가 부풀려진다. (2026-08-30 실측 확인)
    왕복 기간 통제는 length 파라미터가 담당한다.
    """
    out = []
    ym = date.today().strftime("%Y-%m")   # 무시되지만 필수 파라미터
    for n in NIGHTS:
        ok, data, err = call("/v1/prices/calendar", {
            "origin": org, "destination": dst, "depart_date": ym,
            "calendar_type": "departure_date", "length": n,
            "currency": CURRENCY})
        time.sleep(REQ_SLEEP)
        if not ok:
            if err in ("BUDGET_EXCEEDED", "CIRCUIT_OPEN"):
                return out, err
            ERRORS.append(f"{org}-{dst} {n}박: {err}")
            continue
        for dep, v in (data.get("data") or {}).items():
            o = normalize(org, dst, city, region, dep, n, v)
            if o:
                out.append(o)
    return out, None


def normalize(org, dst, city, region, dep, nights, v):
    price = v.get("price")
    if not price or price <= 0:
        return None
    try:
        d0 = datetime.strptime(dep[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    delta = (d0 - date.today()).days
    if not (WINDOW_MIN <= delta <= WINDOW_MAX):
        return None

    ret_at = v.get("return_at")
    if ret_at:
        try:
            d1 = datetime.strptime(ret_at[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
        roundtrip = True
        # length 가 무시되는 경우를 대비한 방어. 요청 박수와 실제가 다르면 버린다.
        # (length 미지정 시 7박·21박·28박까지 섞여 나오는 것을 실측 확인)
        actual = (d1 - d0).days
        if actual != nights:
            return None
    else:
        d1 = d0 + timedelta(days=nights)
        roundtrip = False          # ★ 왕복 미검증 → C등급 강등 사유

    al = v.get("airline") or "?"
    return {
        "id": f"{org}-{dst}-{d0}-{d1}-{al}-ECONOMY",
        "dep": org, "arr": dst, "city": city, "region": region,
        "depart_date": str(d0), "return_date": str(d1), "nights": nights,
        "airline": al, "airline_kr": AIRLINES.get(al, al),
        "api_origin": v.get("origin"), "api_destination": v.get("destination"),
        "flight_no": v.get("flight_number"),
        "stops": v.get("number_of_changes", v.get("transfers")),
        "price_krw": int(price),
        "roundtrip_verified": roundtrip,
        "expires_at": v.get("expires_at"),
        "link": aviasales_link(org, dst, d0, d1),
        "holiday": holiday_span(d0, d1),
        "annual_leave": leave_cost(d0, d1),
    }


def aviasales_link(org, dst, d0, d1):
    return (f"https://www.aviasales.com/search/"
            f"{org}{d0.strftime('%d%m')}{dst}{d1.strftime('%d%m')}1")


def holiday_span(d0, d1):
    d = d0
    while d <= d1:
        if str(d) in HOLIDAYS:
            return HOLIDAYS[str(d)]
        d += timedelta(days=1)
    return None


def leave_cost(d0, d1):
    """출국~귀국 사이 필요한 연차 일수 (주말·공휴일 제외)."""
    n, d = 0, d0
    while d <= d1:
        if d.weekday() < 5 and str(d) not in HOLIDAYS:
            n += 1
        d += timedelta(days=1)
    return max(0, n - 1)   # 귀국일 당일은 통상 이동일


# ══════════════════════════════════════════════════════════
# 응답 구조 검증 (--raw)
# ══════════════════════════════════════════════════════════

def _probe_call(label, params):
    ok, data, err = call("/v1/prices/calendar", params)
    if not ok:
        print(f"[{label}] 실패: {err}")
        return None
    recs = list((data.get("data") or {}).values())
    print(f"\n===== {label} =====")
    print(f"레코드 {len(recs)}건")
    if not recs:
        print("!! 비어 있음. 노선/월을 바꿔 재시도.")
        return None
    first = recs[0]
    print("필드:", sorted(first.keys()))
    print("return_at:", repr(first.get("return_at")))
    print(json.dumps(first, indent=2, ensure_ascii=False))
    prices = [r.get("price") for r in recs if isinstance(r.get("price"), (int, float))]
    if not prices:
        print("!! price 숫자 없음")
        return None
    med = sorted(prices)[len(prices) // 2]
    print(f"price min={min(prices):,} median={med:,} max={max(prices):,}")
    return {"median": med, "has_return": bool(first.get("return_at"))}


def probe_raw():
    """price 가 왕복 총액인지 편도인지, return_at 이 오는지 판정."""
    ym = months_ahead()[1]
    base = {"origin": "ICN", "destination": "KIX", "depart_date": ym,
            "calendar_type": "departure_date", "currency": CURRENCY}

    # A: 현재 scanner 가 실제로 쓰는 형태 (length 지정, one_way 미지정)
    a = _probe_call("A · length=3, one_way 미지정 (현행)",
                    dict(base, length=3))
    time.sleep(REQ_SLEEP)
    # B: 편도 명시 — A 와의 가격비가 판정 근거
    b = _probe_call("B · one_way=true (편도 명시)",
                    dict(base, one_way="true"))

    print("\n===== 판정 =====")
    if not a or not b:
        print("데이터 부족 → 판정 불가. 위 원본 JSON 을 직접 비교하세요.")
        return
    ratio = a["median"] / b["median"] if b["median"] else 0
    print(f"A/B 중앙값 비율 = {ratio:.2f}   (A return_at={a['has_return']})")

    if a["has_return"] and ratio >= 1.6:
        print("→ price = 왕복 총액. return_at 정상 수신.")
        print("→ ONE_WAY_PRICE = False 유지. 수정 불필요.")
    elif not a["has_return"] and ratio <= 1.25:
        print("→ price = 편도. return_at 없음.")
        print("→ ONE_WAY_PRICE = True 로 바꾸고, roundtrip 강등 정책을 재검토하세요.")
    elif a["has_return"] and ratio <= 1.25:
        print("→ 모순: return_at 은 오는데 가격이 편도와 동일.")
        print("   one_way 파라미터가 무시되고 있을 가능성. 원본 JSON 직접 확인 필요.")
    else:
        print(f"→ 애매 (ratio={ratio:.2f}). return_at 유무를 1차 근거로 삼되 표본을 늘려 재확인.")


# ══════════════════════════════════════════════════════════
# 채점
# ══════════════════════════════════════════════════════════

def build_baselines(offers):
    """노선+박수별 중앙값을 정상가 기준선으로 자체 산출."""
    buckets = {}
    for o in offers:
        buckets.setdefault((o["dep"], o["arr"], o["nights"]), []).append(o["price_krw"])
    out = {}
    for k, v in buckets.items():
        if len(v) < 3:          # 표본 3건 미만은 기준선 불가 (청주 등 얇은 노선 구제)
            continue
        s = sorted(v)
        out[k] = {"median": int(statistics.median(s)), "mean": int(statistics.fmean(s)),
                  "n": len(s), "min": s[0], "max": s[-1],
                  "p25": s[max(0, int(len(s) * .25) - 1)]}
    return out


def grade(o):
    """A는 이 소스로 불가. B가 천장."""
    if not o["roundtrip_verified"]:
        return "C", "왕복 미검증 (return_at 없음)"
    if o.get("baseline") is None:
        return "C", "정상가 표본 부족"
    if not o.get("link"):
        return "C", "링크 없음"
    return "B", "캐시 데이터 · 실시간 아님"


def verdict(pct):
    if pct is None:      return "판정 제외"
    if pct >= 70:        return "🚨 Error Fare 검증"
    if pct >= 50:        return "초특가"
    if pct >= 35:        return "강력 특가"
    if pct >= 20:        return "특가"
    if pct >= 10:        return "괜찮은 가격"
    return "일반 저가"


def score(o):
    if o["grade"] == "C":
        return None
    pct = o.get("discount_pct") or 0
    s = min(pct, 60) / 60 * 40                                    # 할인율 0~40
    base = REGION_BASE.get(o["region"], 300000)
    s += max(0.0, min((base - o["price_krw"]) / base, .5)) / .5 * 20   # 절대가 0~20
    lv = o["annual_leave"]
    s += 10 if lv == 0 else (7 if lv == 1 else 4)                 # 일정 0~10
    st = o.get("stops")
    s += 8 if st == 0 else (4 if st == 1 else 0)                  # 직항 0~8
    if o["holiday"]:
        s += 6                                                     # 연휴 보너스
    return round(min(s, 100) * (1.0 if o["grade"] == "A" else .85))


def enrich(offers, baselines):
    for o in offers:
        bl = baselines.get((o["dep"], o["arr"], o["nights"]))
        o["baseline"] = bl["median"] if bl else None
        o["baseline_n"] = bl["n"] if bl else 0
        if bl:
            o["bl_mean"], o["bl_min"], o["bl_max"] = bl["mean"], bl["min"], bl["max"]
            span = bl["max"] - bl["min"]
            # 0 = 그 노선·박수 최저가, 100 = 최고가
            o["band_pos"] = round((o["price_krw"] - bl["min"]) / span * 100) if span else 0
            o["vs_mean"] = round((o["price_krw"] - bl["mean"]) / bl["mean"] * 100, 1)
        else:
            o["bl_mean"] = o["bl_min"] = o["bl_max"] = None
            o["band_pos"] = o["vs_mean"] = None
        if o["baseline"]:
            o["saving"] = o["baseline"] - o["price_krw"]
            o["discount_pct"] = round(o["saving"] / o["baseline"] * 100, 1)
        else:
            o["saving"] = o["discount_pct"] = None
        g, why = grade(o)
        o["grade"], o["grade_reason"] = g, why
        o["verdict"] = verdict(o["discount_pct"]) if g != "C" else "판정 제외"
        o["deal_score"] = score(o)

    if offers and all(o["grade"] == "C" for o in offers):
        reasons = {}
        for o in offers:
            reasons[o["grade_reason"]] = reasons.get(o["grade_reason"], 0) + 1
        top = max(reasons.items(), key=lambda x: x[1])
        print(f"\n⚠️  전체 {len(offers)}건이 모두 C등급 → 브리프가 비게 됩니다.")
        print(f"    최다 사유: {top[0]} ({top[1]}건)")
        if "return_at" in top[0]:
            print("    → python3 scanner.py --raw 로 응답 구조를 재확인하세요.")
        ERRORS.append(f"전건 C등급 강등: {top[0]}")
    return offers


# ══════════════════════════════════════════════════════════
# 변동 추적
# ══════════════════════════════════════════════════════════

def diff(offers, hist):
    prev = hist.get("deals", {})
    today = str(date.today())
    seen = set()
    stats = {"new": 0, "down": 0, "up": 0, "gone": 0}

    for o in offers:
        seen.add(o["id"])
        p = prev.get(o["id"])
        if not p:
            o["change"] = "new"; o["delta"] = None
            o["price_log"] = [{"d": today, "p": o["price_krw"]}]
            o["first_seen"] = today
            stats["new"] += 1
        else:
            log = p.get("price_log", [])
            last = log[-1]["p"] if log else p.get("price_krw")
            d = o["price_krw"] - last
            o["delta"] = d
            o["change"] = "down" if d < 0 else ("up" if d > 0 else "flat")
            if d < 0: stats["down"] += 1
            elif d > 0: stats["up"] += 1
            if not log or log[-1]["d"] != today:
                log = log + [{"d": today, "p": o["price_krw"]}]
            o["price_log"] = log[-30:]
            o["first_seen"] = p.get("first_seen", today)
            lows = [x["p"] for x in o["price_log"]]
            o["record_low"] = o["price_krw"] <= min(lows)
            tail = [x["p"] for x in o["price_log"][-3:]]
            o["streak_down"] = len(tail) == 3 and tail[0] > tail[1] > tail[2]
        o["last_seen"] = today

    gone = []
    for k, v in prev.items():
        if k in seen:
            continue
        if v.get("depart_date", "9999") < today:
            continue                      # 출발일 경과 → 만료, 소멸 아님
        last = v.get("last_seen", "")
        if last and (date.today() - datetime.strptime(last, "%Y-%m-%d").date()).days <= 7:
            gone.append(v)
    stats["gone"] = len(gone)
    return stats, gone


# ══════════════════════════════════════════════════════════
# 렌더
# ══════════════════════════════════════════════════════════

CSS = """
:root{--bg:#0C1014;--surf:#141A21;--surf2:#1B232C;--line:#28323D;--tx:#E6EBF0;
--tx2:#93A1B0;--tx3:#5F6E7D;--good:#37C46B;--warn:#E0A32E;--bad:#FF5C4D;--info:#4B9BFF;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--sans:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard",sans-serif}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:var(--sans);font-size:15px;
line-height:1.5;padding-bottom:calc(40px + env(safe-area-inset-bottom));-webkit-text-size-adjust:100%}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
header{padding:calc(14px + env(safe-area-inset-top)) 16px 12px;border-bottom:1px solid var(--line);background:var(--surf)}
header h1{margin:0;font-size:16px;font-weight:700}
.meta{margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--tx2);line-height:1.7}
.meta b{color:var(--tx)}
nav.main{display:flex;overflow-x:auto;background:var(--surf);border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:20;scrollbar-width:none;-webkit-overflow-scrolling:touch}
nav.main::-webkit-scrollbar{display:none}
nav.main button{flex:0 0 auto;background:none;border:none;border-bottom:2px solid transparent;
color:var(--tx2);font-family:var(--sans);font-size:13px;font-weight:600;padding:12px 14px;
cursor:pointer;touch-action:manipulation;white-space:nowrap}
nav.main button[aria-selected="true"]{color:var(--tx);border-bottom-color:var(--info)}
nav.sub{display:flex;gap:6px;overflow-x:auto;padding:12px 16px 4px;scrollbar-width:none}
nav.sub::-webkit-scrollbar{display:none}
nav.sub button{flex:0 0 auto;background:var(--surf2);border:1px solid var(--line);border-radius:999px;
color:var(--tx2);font-family:var(--mono);font-size:12px;font-weight:600;padding:7px 13px;
cursor:pointer;touch-action:manipulation;white-space:nowrap}
nav.sub button[aria-selected="true"]{background:var(--info);border-color:var(--info);color:#06121F}
main{padding:16px}
.panel[hidden],div.sub[hidden]{display:none}
.strip{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:var(--line);
border:1px solid var(--line);border-radius:10px;overflow:hidden}
.strip div{background:var(--surf);padding:12px 13px}
.strip .k{font-size:11px;color:var(--tx2);margin-bottom:3px}
.strip .v{font-family:var(--mono);font-size:22px;font-weight:700}
.strip .v.zero{color:var(--tx3)}.strip .v.g{color:var(--good)}
.strip .v.w{color:var(--warn)}.strip .v.r{color:var(--bad)}
.mut{color:var(--tx3);font-size:11px}
table.rt{width:100%;border-collapse:collapse;font-size:13px}
table.rt th{text-align:right;font-size:11px;color:var(--tx2);padding:6px 8px;
  border-bottom:1px solid var(--line);font-weight:500}
table.rt th:first-child{text-align:left}
table.rt td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:right}
table.rt td:first-child{text-align:left;line-height:1.35}
table.rt td.num{font-family:var(--mono)}
table.rt td.g{color:var(--good);font-weight:700}
table.rt td.w{color:var(--warn)}
.band{display:grid;grid-template-columns:1fr;gap:5px;padding:11px 2px;
  border-bottom:1px solid var(--line)}
.band .bl{font-size:13px;line-height:1.35}
.band .br{display:flex;justify-content:space-between;align-items:baseline;
  font-family:var(--mono);font-size:13px}
.band .bar{position:relative;height:5px;border-radius:3px;
  background:linear-gradient(90deg,var(--good),var(--warn),var(--bad));opacity:.28}
.band .bar i{position:absolute;top:-3px;width:3px;height:11px;border-radius:2px;
  margin-left:-1px;opacity:1}
.band .bar i.g{background:var(--good)}.band .bar i.w{background:var(--warn)}
.band .bar i.r{background:var(--bad)}
.zone{margin-top:22px}
.zone>h3{margin:0 0 4px;font-size:13px;font-weight:700}
.zone>.desc{margin:0 0 10px;font-size:11.5px;color:var(--tx3);font-family:var(--mono)}
.empty{border:1px dashed var(--line);border-radius:8px;padding:18px 15px;color:var(--tx3);
font-size:13px;text-align:center;line-height:1.6}
.empty b{display:block;color:var(--tx2);margin-bottom:4px}
.card{background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:14px 15px;margin-bottom:10px}
.card.c{border-style:dashed;opacity:.94}
.card .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:9px}
.card .route{font-family:var(--mono);font-size:12px;color:var(--tx2)}
.card .city{font-size:15px;font-weight:700;margin-top:1px}
.price{font-family:var(--mono);font-weight:700;letter-spacing:-.03em;line-height:1.15;font-size:26px}
.price .unit{font-size:13px;color:var(--tx2);margin-left:2px}
.sub-price{font-family:var(--mono);font-size:12px;color:var(--tx2);margin-top:3px}
.row{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-top:1px solid var(--line);font-size:12.5px}
.kv .k{color:var(--tx3)}.kv .v{font-family:var(--mono);text-align:right}
.b{display:inline-flex;font-family:var(--mono);font-size:10.5px;font-weight:700;padding:3px 7px;
border-radius:5px;border:1px solid var(--line);color:var(--tx2)}
.b.g{color:var(--good);border-color:rgba(55,196,107,.45);background:rgba(55,196,107,.09)}
.b.w{color:var(--warn);border-color:rgba(224,163,46,.45);background:rgba(224,163,46,.09)}
.b.r{color:var(--bad);border-color:rgba(255,92,77,.45);background:rgba(255,92,77,.09)}
.b.i{color:var(--info);border-color:rgba(75,155,255,.45);background:rgba(75,155,255,.09)}
.secstat{border-radius:8px;padding:12px 14px;margin-bottom:16px;font-size:13px;border:1px solid var(--line);
background:var(--surf);line-height:1.6}
.secstat.part{border-left:3px solid var(--warn)}.secstat.fail{border-left:3px solid var(--bad)}
.secstat b{display:block;margin-bottom:4px}.secstat span{color:var(--tx2)}
a.book{display:block;margin-top:10px;padding:10px;text-align:center;background:var(--surf2);
border:1px solid var(--line);border-radius:8px;color:var(--info);text-decoration:none;
font-family:var(--mono);font-size:12.5px;font-weight:600}
footer{margin:28px 16px 0;padding:14px 0 4px;border-top:1px solid var(--line);
font-family:var(--mono);font-size:11px;color:var(--tx3);line-height:1.8}
"""

JS = """
document.querySelectorAll('nav.main,nav.sub').forEach(function(nav){
  var isMain=nav.classList.contains('main'),bs=nav.querySelectorAll('button');
  bs.forEach(function(b){b.addEventListener('click',function(){
    bs.forEach(function(x){x.setAttribute('aria-selected','false')});
    b.setAttribute('aria-selected','true');
    var id=b.getAttribute('data-id');
    if(isMain){document.querySelectorAll('section.panel').forEach(function(p){
      p.hidden=(p.id!=='p-'+id)});window.scrollTo(0,0);}
    else{nav.parentElement.querySelectorAll(':scope > div.sub').forEach(function(d){
      d.hidden=(d.id!=='s-'+id)});}
  },false)});
});
"""


def esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def card(o):
    ch = {"new": '<span class="b i">🆕 NEW</span>',
          "down": f'<span class="b g">📉 {o["delta"]:+,}원</span>' if o.get("delta") else "",
          "up": f'<span class="b w">📈 {o["delta"]:+,}원</span>' if o.get("delta") else "",
          }.get(o.get("change"), "")
    extra = ""
    if o.get("record_low"):   extra += '<span class="b g">🏆 최저</span>'
    if o.get("streak_down"):  extra += '<span class="b g">📉 연속하락</span>'
    if o.get("holiday"):      extra += f'<span class="b r">🎉 {esc(o["holiday"])}</span>'
    if o["annual_leave"] == 0: extra += '<span class="b g">연차 0일</span>'
    elif o["annual_leave"] == 1: extra += '<span class="b w">연차 1일</span>'

    gb = {"A": '<span class="b g">A</span>', "B": '<span class="b w">B · 캐시</span>',
          "C": '<span class="b">C</span>'}[o["grade"]]
    sc = (f'<span class="b i">SCORE {o["deal_score"]}</span>'
          if o.get("deal_score") else "")
    st = {0: "직항", 1: "1회 환승"}.get(o.get("stops"), "환승")

    kv = ""
    if o.get("baseline"):
        kv += (f'<div class="kv"><span class="k">기준선(중앙값)</span>'
               f'<span class="v">{o["baseline"]:,}원 · 표본 {o["baseline_n"]}</span></div>'
               f'<div class="kv"><span class="k">절감 / 할인율</span>'
               f'<span class="v">{o["saving"]:,}원 · {o["discount_pct"]}%</span></div>')
    kv += (f'<div class="kv"><span class="k">판정</span><span class="v">{esc(o["verdict"])}</span></div>'
           f'<div class="kv"><span class="k">등급 사유</span>'
           f'<span class="v" style="color:var(--tx3)">{esc(o["grade_reason"])}</span></div>')
    if not o["roundtrip_verified"]:
        kv += ('<div class="kv"><span class="k">⚠️ 주의</span>'
               '<span class="v" style="color:var(--warn)">왕복 총액 미확인</span></div>')

    return f"""<article class="card{' c' if o['grade']=='C' else ''}">
<div class="top"><div><div class="route">{o['dep']} → {o['arr']} · {esc(o['airline_kr'])} · {st}</div>
<div class="city">{esc(o['city'])}</div></div>
<div style="text-align:right"><div class="price">{o['price_krw']:,}<span class="unit">원</span></div>
<div class="sub-price">{o['depart_date'][5:]} → {o['return_date'][5:]} · {o['nights']}박{o['nights']+1}일</div></div></div>
<div class="row">{gb}{sc}{ch}{extra}</div>{kv}
<a class="book" href="{o['link']}" target="_blank" rel="noopener">항공권 검색 →</a></article>"""


def route_summary(offers):
    """노선별 요약 표. '지금 이 노선이 싼가'에 한 줄로 답한다."""
    g = {}
    for o in offers:
        g.setdefault((o["dep"], o["arr"], o["city"]), []).append(o)
    rows = []
    for (dep, arr, city), pool in g.items():
        pr = sorted(p["price_krw"] for p in pool)
        lo, mid = pr[0], int(statistics.median(pr))
        best = min(pool, key=lambda x: x["price_krw"])
        gap = round((lo - mid) / mid * 100) if mid else 0
        rows.append({"dep": dep, "arr": arr, "city": city, "n": len(pool),
                     "min": lo, "median": mid, "max": pr[-1], "gap": gap,
                     "best": best})
    rows.sort(key=lambda r: r["gap"])          # 평균 대비 많이 싼 노선 먼저

    out = ['<table class="rt"><thead><tr><th>노선</th><th>건수</th>'
           '<th>최저</th><th>중앙</th><th>최저-중앙</th></tr></thead><tbody>']
    for r in rows:
        cls = "g" if r["gap"] <= -15 else ("w" if r["gap"] <= -5 else "")
        out.append(
            f'<tr><td><b>{esc(r["city"])}</b><br><span class="mut">{r["dep"]}→{r["arr"]}</span></td>'
            f'<td class="num">{r["n"]}</td>'
            f'<td class="num">{r["min"]:,}</td>'
            f'<td class="num mut">{r["median"]:,}</td>'
            f'<td class="num {cls}">{r["gap"]:+d}%</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


def band_rows(offers, limit=40):
    """가격대 안에서 지금 어디쯤인지 막대로. 특가가 아니어도 전부 보인다."""
    pool = [o for o in offers if o.get("band_pos") is not None]
    pool.sort(key=lambda x: (x["band_pos"], x["price_krw"]))
    out = []
    for o in pool[:limit]:
        p = o["band_pos"]
        cls = "g" if p <= 20 else ("w" if p <= 60 else "r")
        vm = o["vs_mean"]
        out.append(
            f'<div class="band"><div class="bl">'
            f'<b>{esc(o["city"])}</b> <span class="mut">{o["dep"]}→{o["arr"]} · '
            f'{o["depart_date"][5:]} {o["nights"]}박</span></div>'
            f'<div class="bar"><i class="{cls}" style="left:{p}%"></i></div>'
            f'<div class="br"><b>{o["price_krw"]:,}</b>'
            f'<span class="mut">평균 {vm:+.0f}% · 표본 {o["baseline_n"]}</span></div></div>')
    if not out:
        return '<div class="empty"><b>0건</b>기준선이 만들어진 노선이 없습니다.</div>'
    return "".join(out)


def zone(title, desc, items, empty_msg):
    body = "".join(card(o) for o in items) if items else \
        f'<div class="empty"><b>0건</b>{empty_msg}</div>'
    return (f'<div class="zone"><h3>{title}</h3>'
            f'<p class="desc">{desc}</p>{body}</div>')


def render(offers, stats, gone, meta):
    by_grade = lambda g, pool: sorted(
        [o for o in pool if o["grade"] == g],
        key=lambda x: -(x.get("deal_score") or 0))

    tabs, panels = [], []

    # 요약
    a = by_grade("A", offers); b = by_grade("B", offers); c = by_grade("C", offers)
    top = (a + b)[:5]
    strip = f"""<div class="strip">
<div><div class="k">🔥 검증된 특가 (A)</div><div class="v {'g' if a else 'zero'} num">{len(a)}</div></div>
<div><div class="k">👀 현재 저가 (B)</div><div class="v {'w' if b else 'zero'} num">{len(b)}</div></div>
<div><div class="k">🆕 신규</div><div class="v {'i' if stats['new'] else 'zero'} num">{stats['new']}</div></div>
<div><div class="k">📉 하락</div><div class="v {'g' if stats['down'] else 'zero'} num">{stats['down']}</div></div>
<div><div class="k">📈 상승</div><div class="v {'w' if stats['up'] else 'zero'} num">{stats['up']}</div></div>
<div><div class="k">⚰️ 소멸</div><div class="v {'r' if stats['gone'] else 'zero'} num">{stats['gone']}</div></div></div>"""

    note = ""
    if not a and not b:
        note = ('<div class="secstat fail"><b>오늘은 기준을 넘는 딜이 없습니다</b>'
                '<span>C등급 후보만 있습니다. 예약 판단 근거로 쓰지 마세요.</span></div>')
    summary = strip + note + zone(
        "🏆 TOP 5", "전 노선 통합 · DEAL SCORE 순", top, "표시할 딜이 없습니다.")
    if gone:
        g = "".join(f'<div class="kv"><span class="k">{esc(x.get("city",""))} '
                    f'{x.get("depart_date","")}</span><span class="v">'
                    f'{x.get("price_krw",0):,}원</span></div>' for x in gone[:10])
        summary += f'<div class="zone"><h3>⚰️ 어제 사라진 딜</h3><p class="desc">재등장 추적 중</p>{g}</div>'
    tabs.append(("sum", "📊 요약")); panels.append(("sum", summary, None))

    # 출발지별
    subs = []
    for key, label in (("icn", "ICN / GMP"), ("cjj", "CJJ"), ("tae", "TAE"), ("pus", "PUS")):
        codes = {r[0] for r in ROUTES[key]}
        pool = [o for o in offers if o["dep"] in codes]
        html = (zone("🔥 검증된 특가", "A등급", by_grade("A", pool), "정상가 비교까지 끝난 딜이 없습니다.")
                + zone("👀 현재 저가", "B등급 · 캐시 데이터", by_grade("B", pool), "왕복 실판매가 확인 건이 없습니다.")
                + zone("🔎 추가 확인 후보", "C등급 · SCORE 미부여", by_grade("C", pool)[:10], "후보가 없습니다."))
        subs.append((key, label, html))
    tabs.append(("dep", "✈️ 출발지별")); panels.append(("dep", "", subs))

    # 주말
    wk = [o for o in offers if o["annual_leave"] <= 1 and o["grade"] != "C"]
    wk.sort(key=lambda x: (x["annual_leave"], -(x.get("deal_score") or 0)))
    tabs.append(("wkd", "🔥 주말"))
    panels.append(("wkd", zone("연차 0~1일", "공휴일 자동 반영", wk[:15],
                               "연차 0~1일 조건을 만족하는 검증 딜이 없습니다."), None))

    # 노선별 요약
    tabs.append(("rts", "🧭 노선별"))
    panels.append(("rts", '<div class="zone"><h3>노선별 요약</h3>'
                   '<p class="desc">최저-중앙 격차가 큰 노선이 위. 지금 어느 노선이 눌려 있는지 본다.</p>'
                   + (route_summary(offers) if offers else
                      '<div class="empty"><b>0건</b>수집된 노선이 없습니다.</div>')
                   + '</div>', None))

    # 평균 비교
    tabs.append(("avg", "📐 평균 비교"))
    panels.append(("avg", '<div class="zone"><h3>가격대 위치</h3>'
                   '<p class="desc">같은 노선·박수 안에서 지금 가격이 어디쯤인지. '
                   '왼쪽일수록 싸다. 특가 등급과 무관하게 전부 표시한다.</p>'
                   + band_rows(offers) + '</div>', None))

    # 스위스
    sw = [o for o in offers if o["arr"] in ("ZRH", "GVA", "BSL")]
    tabs.append(("swi", "🇨🇭 스위스"))
    panels.append(("swi", zone("스위스", "ICN 출발 · 4~5박", sorted(
        sw, key=lambda x: x["price_krw"])[:10],
        "이번 스캔에서 스위스 데이터가 없습니다.") if sw else
        '<div class="secstat part"><b>⏸ 오늘 스캔 대상 아님</b>'
        '<span>스위스는 화·금 심층 로테이션입니다.</span></div>', None))

    body = ""
    for pid, html, sub in panels:
        if sub:
            nav = '<nav class="sub" role="tablist">' + "".join(
                f'<button role="tab" aria-selected="{"true" if i==0 else "false"}" '
                f'data-id="{k}">{esc(l)}</button>' for i, (k, l, _) in enumerate(sub)) + "</nav>"
            inner = "".join(f'<div class="sub" id="s-{k}"{"" if i==0 else " hidden"}>{h}</div>'
                            for i, (k, _, h) in enumerate(sub))
            html = nav + inner
        body += (f'<section class="panel" id="p-{pid}"'
                 f'{"" if pid=="sum" else " hidden"}>{html}</section>')

    navmain = '<nav class="main" role="tablist">' + "".join(
        f'<button role="tab" aria-selected="{"true" if i==0 else "false"}" '
        f'data-id="{k}">{esc(l)}</button>' for i, (k, l) in enumerate(tabs)) + "</nav>"

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark"><title>항공권 데일리 스캐너 · {meta['date']}</title>
<style>{CSS}</style></head><body>
<header><h1>항공권 데일리 스캐너</h1><div class="meta">
스캔 <b>{meta['ts']}</b> · 심층 <b>{esc(meta['rotation'])}</b><br>
검색 <b>{meta['used']}/{meta['cap']}</b> · 수집 <b>{meta['count']}건</b> · 소스 <b>Travelpayouts (캐시)</b><br>
<span style="color:var(--warn)">캐시 데이터라 A등급 불가 · B등급이 천장</span>
</div></header>{navmain}<main>{body}</main>
<footer>실행 {meta['ts']} · A {len(a)} · B {len(b)} · C {len(c)}<br>
🆕 {stats['new']} · 📉 {stats['down']} · 📈 {stats['up']} · ⚰️ {stats['gone']}<br>
{('오류 ' + str(len(ERRORS)) + '건<br>') if ERRORS else ''}
가격은 캐시 기반 참고값입니다. 예약 전 판매처에서 직접 확인하세요.</footer>
<script>{JS}</script></body></html>"""


# ══════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════

def months_ahead():
    """검색창(D+3~D+75)과 겹치는 달만 반환. 남은 날이 5일 미만인 달은 제외."""
    lo = date.today() + timedelta(days=WINDOW_MIN)
    hi = date.today() + timedelta(days=WINDOW_MAX)
    out, d = [], lo.replace(day=1)
    while d <= hi:
        nxt = (d + timedelta(days=32)).replace(day=1)
        overlap = (min(hi, nxt - timedelta(days=1)) - max(lo, d)).days + 1
        if overlap >= 5:
            out.append(d.strftime("%Y-%m"))
        d = nxt
    return out


def rotation():
    wd = date.today().weekday()          # 0=월
    return {0: ("월/목 · 출발지별 풀스캔", ["icn", "cjj", "tae", "pus"]),
            3: ("월/목 · 출발지별 풀스캔", ["icn", "cjj", "tae", "pus"]),
            1: ("화/금 · 스위스 심층", ["icn", "swiss"]),
            4: ("화/금 · 스위스 심층", ["icn", "swiss"]),
            2: ("수 · 국내선 + 숙소", ["icn", "cjj"]),
            }.get(wd, ("주말 · 임박 딜", ["icn", "cjj", "pus"]))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="원본 응답 덤프 후 종료")
    ap.add_argument("--all", action="store_true", help="로테이션 무시, 전 노선")
    ap.add_argument("--token", help="토큰 직접 지정 (1회성)")
    ap.add_argument("--save-token", metavar="TOKEN",
                    help="토큰을 ~/.travelpayouts.json 에 저장 후 종료")
    args = ap.parse_args()

    global TOKEN

    if args.save_token:
        p = save_token(args.save_token)
        print(f"✅ 저장 완료: {p} (권한 0600)")
        print("   이제 python3 scanner.py 만 치면 됩니다.")
        return

    TOKEN = load_token(args.token)
    if not TOKEN:
        print("❌ 토큰 없음"); sys.exit(1)
    print(f"토큰 {TOKEN[:6]}…{TOKEN[-4:]}")

    for d in ("archive", "state", "logs"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)

    if args.raw:
        probe_raw()
        return

    rot_name, groups = rotation()
    if args.all:
        rot_name, groups = "전체 (수동)", ["icn", "cjj", "tae", "pus", "swiss"]
    print(f"▶ {date.today()} · {rot_name}")

    targets = []
    for g in groups:
        targets += SWISS if g == "swiss" else ROUTES.get(g, [])
    seen = set(); targets = [t for t in targets if not (t[:2] in seen or seen.add(t[:2]))]

    months = months_ahead()
    offers = []
    for org, dst, city, region in targets:
        got, stop = fetch_route(org, dst, city, region, months)
        tag = {"BUDGET_EXCEEDED": "  ⛔예산소진",
               "CIRCUIT_OPEN": "  ⛔중단"}.get(stop, "")
        print(f"  {org}→{dst} {len(got):>4}건{tag}")
        offers += got
        if stop:
            break

    # API 가 공항코드를 도시코드로 접어서 응답한다 (ICN/GMP→SEL, KIX→OSA, NRT/HND→TYO).
    # 요청 공항이 달라도 같은 편이 중복 수집될 수 있으므로 실제 편 기준으로 중복 제거.
    uniq, dedup_n = {}, 0
    for o in offers:
        k = (o.get("api_origin"), o.get("api_destination"), o["depart_date"],
             o["return_date"], o["airline"], o["flight_no"], o["price_krw"])
        if k in uniq:
            dedup_n += 1
            continue
        uniq[k] = o
    if dedup_n:
        print(f"  · 중복 제거 {dedup_n}건 (도시코드 병합)")
        offers = list(uniq.values())
    if CIRCUIT.tripped:
        print(f"\n⛔ 연속 실패 {CIRCUIT.LIMIT}회 — 조기 중단")
        print(f"   원인: {CIRCUIT.cause}")

    baselines = build_baselines(offers)
    offers = enrich(offers, baselines)

    hist = load(os.path.join(ROOT, "state", "price_history.json"), {"deals": {}})
    stats, gone = diff(offers, hist)

    meta = {"date": str(date.today()),
            "ts": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "rotation": rot_name, "used": BUDGET.used, "cap": BUDGET.cap,
            "count": len(offers)}
    html = render(offers, stats, gone, meta)

    for p in (os.path.join(ROOT, "latest.html"),
              os.path.join(ROOT, "archive", f"deals-{date.today()}.html")):
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)

    # ── 아침 브리프용 요약 (morning 스킬이 읽는 파일) ──
    A = [o for o in offers if o["grade"] == "A"]
    B = [o for o in offers if o["grade"] == "B"]
    C = [o for o in offers if o["grade"] == "C"]
    top = sorted(A + B, key=lambda x: -(x.get("deal_score") or 0))[:3]

    degraded = None
    if CIRCUIT.tripped:
        status, headline = "FAILED", f"스캔 실패 — {CIRCUIT.cause}"
    elif not (A or B):
        status, headline = "PARTIAL", "오늘은 기준을 넘는 딜이 없습니다"
        if C and len(C) >= 20:
            rc = {}
            for o in C:
                rc[o["grade_reason"]] = rc.get(o["grade_reason"], 0) + 1
            top_reason, n = max(rc.items(), key=lambda x: x[1])
            if n / len(C) >= 0.9:
                degraded = f"전건 강등 · {top_reason} ({n}건)"
    else:
        bits = [f"볼 것 {len(A) + len(B)}건"]
        if stats["new"]:  bits.append(f"신규 {stats['new']}")
        if stats["down"]: bits.append(f"하락 {stats['down']}")
        status, headline = "OK", " · ".join(bits)

    brief = {
        "date": meta["date"], "ts": meta["ts"], "status": status,
        "headline": headline, "rotation": rot_name,
        "reason": CIRCUIT.cause if CIRCUIT.tripped else None,
        "degraded": degraded,
        "counts": {"a": len(A), "b": len(B), "c": len(C), **stats},
        "source_note": "Travelpayouts 캐시 데이터 · A등급 불가, B가 천장",
        "top": [{
            "text": (f"{o['city']} {o['dep']}→{o['arr']} · "
                     f"{o['depart_date'][5:]}~{o['return_date'][5:]} {o['nights']}박 · "
                     f"{o['price_krw']:,}원"
                     + (f" -{o['discount_pct']:.0f}%" if o.get("discount_pct") else "")
                     + (f" · SCORE {o['deal_score']}" if o.get("deal_score") else "")
                     + ("  🆕" if o.get("change") == "new" else "")
                     + (f"  📉{o['delta']:+,}" if o.get("change") == "down" else "")),
            "grade": o["grade"], "verdict": o["verdict"], "link": o["link"],
        } for o in top],
        "dashboard": os.path.join(ROOT, "latest.html"),
    }
    with open(os.path.join(ROOT, "state", "brief.json"), "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=1)

    hist["last_run"] = meta["ts"]
    hist["deals"] = {o["id"]: o for o in offers}
    with open(os.path.join(ROOT, "state", "price_history.json"), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)

    with open(os.path.join(ROOT, "logs", f"run-{date.today()}.md"), "w", encoding="utf-8") as f:
        f.write(f"# 실행 {meta['ts']}\n\n로테이션: {rot_name}\n"
                f"검색: {BUDGET.used}/{BUDGET.cap}\n수집: {len(offers)}건\n\n"
                f"A {sum(1 for o in offers if o['grade']=='A')} · "
                f"B {sum(1 for o in offers if o['grade']=='B')} · "
                f"C {sum(1 for o in offers if o['grade']=='C')}\n\n"
                f"🆕 {stats['new']} · 📉 {stats['down']} · 📈 {stats['up']} · ⚰️ {stats['gone']}\n\n"
                + ("## 오류\n" + "\n".join(f"- {e}" for e in ERRORS[:30]) if ERRORS else ""))

    print(f"\n✅ 완료 · 수집 {len(offers)}건 · 검색 {BUDGET.used}/{BUDGET.cap}")
    print(f"   A {sum(1 for o in offers if o['grade']=='A')} / "
          f"B {sum(1 for o in offers if o['grade']=='B')} / "
          f"C {sum(1 for o in offers if o['grade']=='C')}")
    print(f"   🆕{stats['new']} 📉{stats['down']} 📈{stats['up']} ⚰️{stats['gone']}")
    if ERRORS:
        print(f"   ⚠️ 오류 {len(ERRORS)}건 — 로그 확인")
    print(f"\n   → {os.path.join(ROOT, 'latest.html')}")


if __name__ == "__main__":
    main()
