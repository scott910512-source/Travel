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

SEARCH_BUDGET = 130       # 국내 17노선×4박 = 68 + 스위스 3노선×6박 = 18 → 86회
REQ_SLEEP = 0.45          # rate limit 여유
TIMEOUT = 25

WINDOW_MIN, WINDOW_MAX = 3, 75      # D+3 ~ D+75
NIGHTS = (2, 3, 4, 5)               # 근거리: 2박3일 ~ 5박6일
SWISS_NIGHTS = (5, 6, 7, 8, 9, 10)  # 유럽: 5박 ~ 10박

# ══════════════════════════════════════════════════════════
# 청주 기준 설정
# ══════════════════════════════════════════════════════════
# 이 스캐너는 "청주 근처 거주자" 시점으로 채점한다.
# 항공권 실가격이 항상 주 표기이고, 이동비용은 보조 지표로만 붙는다.

HOME = "CJJ"

# 청주 출발 기준 공항까지 왕복 교통비 (1인, KRW).
# ★ 추정치다. 실제 이동수단·인원에 맞춰 이 숫자만 고치면 전부 반영된다.
ACCESS_COST = {
    "CJJ": 0,          # 집 앞
    "ICN": 44000,      # 청주 ↔ 인천공항 리무진 왕복
    "GMP": 40000,      # 청주 ↔ 김포
    "TAE": 30000,      # 청주 ↔ 대구 (버스 왕복 + 공항 이동)
    "PUS": 56000,      # 청주 ↔ 부산 (버스/KTX 왕복 + 공항 이동)
}

# 이동에 드는 "시간" 부담 (돈으로 안 잡히는 것). 점수 0~10.
ACCESS_SCORE = {"CJJ": 10, "TAE": 5, "PUS": 4, "ICN": 3, "GMP": 3}

# 출발지별 노선 — 청주(홈)를 맨 앞에 둔다. 표시 순서가 이 순서를 따른다.
ROUTES = {
    "cjj": [("CJJ", "KIX", "오사카", "일본"), ("CJJ", "NRT", "도쿄", "일본"),
            ("CJJ", "TPE", "타이베이", "중화권"), ("CJJ", "DAD", "다낭", "동남아")],
    "icn": [("ICN", "KIX", "오사카", "일본"), ("ICN", "NRT", "도쿄", "일본"),
            ("ICN", "FUK", "후쿠오카", "일본"), ("ICN", "TPE", "타이베이", "중화권"),
            ("ICN", "BKK", "방콕", "동남아"), ("GMP", "HND", "도쿄", "일본")],
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

# 공휴일 표가 어디까지 채워져 있는지. 검색창이 이걸 넘어가면 연차 계산이
# 조용히 틀리므로 실행 시 경고한다.
HOLIDAY_MAX = max(HOLIDAYS)

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

def fetch_route(org, dst, city, region, nights=None):
    """노선 하나를 박수별로 조회. 정규화된 offer 리스트 반환.

    nights 미지정 시 NIGHTS(2~5박). 유럽은 SWISS_NIGHTS(5~10박)를 넘긴다.

    depart_date(월) 필터는 API 가 무시하고 캐시 전 구간을 반환하므로
    월 루프를 돌리지 않는다. 월별로 돌리면 같은 데이터를 중복 수집해
    build_baselines() 의 표본 수가 부풀려진다. (2026-08-30 실측 확인)
    왕복 기간 통제는 length 파라미터가 담당한다.
    """
    out = []
    ym = date.today().strftime("%Y-%m")   # 무시되지만 필수 파라미터
    for n in (nights or NIGHTS):
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
    dep_hour = parse_hour(v.get("departure_at"))
    tp = trip_profile(d0, d1, dep_hour)
    access = ACCESS_COST.get(org, 0)
    return {
        "id": f"{org}-{dst}-{d0}-{d1}-{al}-ECONOMY",
        "dep": org, "arr": dst, "city": city, "region": region,
        "depart_date": str(d0), "return_date": str(d1), "nights": nights,
        "airline": al, "airline_kr": AIRLINES.get(al, al),
        "api_origin": v.get("origin"), "api_destination": v.get("destination"),
        "flight_no": v.get("flight_number"),
        "stops": v.get("number_of_changes", v.get("transfers")),
        "price_krw": int(price),
        "access_cost": access,
        "effective_krw": int(price) + access,   # 청주 기준 실부담가 (보조 지표)
        "roundtrip_verified": roundtrip,
        "expires_at": v.get("expires_at"),
        "link": aviasales_link(org, dst, d0, d1),
        "dep_hour": dep_hour,
        "holiday": tp["holiday"],
        "weekend": tp["weekend"],
        "red_days": tp["red"],
        "annual_leave": tp["leave"],
        "night_departure": tp["night_departure"],
        # 사용자 기준: 주말(토·일) 포함 + 연차 0~1일.
        # 빨간날이 붙으면 그만큼 일정이 길어져도 조건을 유지한다.
        "weekend_trip": tp["weekend"] and tp["leave"] <= 1,
    }


def aviasales_link(org, dst, d0, d1):
    return (f"https://www.aviasales.com/search/"
            f"{org}{d0.strftime('%d%m')}{dst}{d1.strftime('%d%m')}1")


def parse_hour(ts):
    """'2026-09-20T21:35:00+09:00' → 21. 실패하면 None.

    출발지 현지시각 기준이다. 오프셋을 UTC 로 환산하지 않고 표기된 시각을
    그대로 읽는다 — 알고 싶은 것이 '퇴근하고 탈 수 있느냐'이기 때문이다.
    """
    if not isinstance(ts, str) or len(ts) < 13 or ts[10] not in "T ":
        return None
    try:
        h = int(ts[11:13])
    except ValueError:
        return None
    return h if 0 <= h <= 23 else None


def trip_profile(d0, d1, dep_hour=None):
    """여행 구간의 빨간날·연차 구성.

    연차 기준 (청주 거주자 시점):
      - 토·일·공휴일은 연차가 들지 않는다.
      - 그 외 평일은 출국일·귀국일을 포함해 전부 연차 1일로 센다.
        토·일·월(공휴일)·화 일정이면 화요일 1일만 연차다.
      - 단, 평일 19시 이후 출발이면 그 날은 퇴근 후 탑승이므로 세지 않는다.
    """
    weekend, red, leave, holi = False, 0, 0, None
    night_dep = False
    d = d0
    while d <= d1:
        key = str(d)
        is_hol = key in HOLIDAYS
        if is_hol and holi is None:
            holi = HOLIDAYS[key]
        if d.weekday() >= 5:
            weekend = True
        if d.weekday() >= 5 or is_hol:
            red += 1
        elif d == d0 and dep_hour is not None and dep_hour >= 19:
            night_dep = True          # 퇴근 후 심야 출발 → 연차 불필요
        else:
            leave += 1
        d += timedelta(days=1)
    return {"weekend": weekend, "red": red, "leave": leave,
            "holiday": holi, "night_departure": night_dep}


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
    """청주 거주자 + 주말여행 기준 배점.

    할인율 35 · 실부담가 15 · 주말적합도 22 · 접근성 10 · 직항 8 · 연휴 6
    = 96점 만점. B등급 계수 0.85 를 곱하므로 실질 상한은 82점이다.
    """
    if o["grade"] == "C":
        return None
    pct = o.get("discount_pct") or 0
    s = min(pct, 60) / 60 * 35                                     # 할인율 0~35

    base = REGION_BASE.get(o["region"], 300000)
    eff = o.get("effective_krw") or o["price_krw"]
    s += max(0.0, min((base - eff) / base, .5)) / .5 * 15          # 실부담가 0~15

    # 주말 적합도 — 주말이 안 걸린 일정은 이 항목에서 0점이다.
    if o.get("weekend"):
        s += {0: 22, 1: 17, 2: 8}.get(o["annual_leave"], 0)

    s += ACCESS_SCORE.get(o["dep"], 0)                             # 접근성 0~10

    st = o.get("stops")
    s += 8 if st == 0 else (4 if st == 1 else 0)                   # 직항 0~8
    if o["holiday"]:
        s += 6                                                      # 연휴 보너스
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
            # 할인율은 실가격 기준이다. 이동비용은 같은 출발지 안에서 상수라
            # 어차피 상쇄되고, 사용자에게 익숙한 숫자는 항공권 실가격이다.
            o["saving"] = o["baseline"] - o["price_krw"]
            o["discount_pct"] = round(o["saving"] / o["baseline"] * 100, 1)
            o["eff_baseline"] = o["baseline"] + o.get("access_cost", 0)
        else:
            o["saving"] = o["discount_pct"] = o["eff_baseline"] = None
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

def track_lows(offers, hist):
    """노선별 역대 최저가. '지금이 최저인가'에 답하는 근거.

    price_history.json 에 누적되므로 실행을 거듭할수록 정확해진다.
    첫 실행에서는 비교 대상이 없어 전건이 최저로 잡힌다.
    """
    prev = hist.get("route_lows", {})
    today = str(date.today())

    for o in offers:                       # 1패스: 직전까지의 기록과 비교
        rec = prev.get(f"{o['dep']}-{o['arr']}")
        o["route_low_prev"] = rec["price"] if rec else None
        o["route_low_date"] = rec.get("date") if rec else None
        o["route_record_low"] = (rec is None) or (o["price_krw"] <= rec["price"])

    lows = dict(prev)                      # 2패스: 기록 갱신
    for o in offers:
        k = f"{o['dep']}-{o['arr']}"
        cur = lows.get(k)
        if cur is None or o["price_krw"] < cur["price"]:
            lows[k] = {"price": o["price_krw"], "date": today,
                       "depart_date": o["depart_date"], "nights": o["nights"],
                       "city": o["city"]}
    hist["route_lows"] = lows
    return lows


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
:root{
--bg:#F4F5FA;--surf:#FFF;--surf2:#F8F9FD;--line:#E7E9F2;--line2:#EFF1F8;
--tx:#191C2A;--tx2:#666D85;--tx3:#9BA2B6;
--pri:#6C4CE6;--priw:#F1EDFE;--prib:#DCD3FB;
--good:#12A150;--goodw:#E8F8EF;--bad:#E5484D;--badw:#FDECEC;
--warn:#DF8A1F;--warnw:#FDF4E7;--info:#2E6BE6;--infow:#EBF1FE;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--sans:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",Pretendard,system-ui,sans-serif;
--sh:0 1px 2px rgba(20,24,44,.05),0 2px 10px rgba(20,24,44,.04);
--nav:64px}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:var(--sans);font-size:15px;
line-height:1.5;-webkit-text-size-adjust:100%;
padding-bottom:calc(var(--nav) + env(safe-area-inset-bottom))}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.mut{color:var(--tx3);font-size:11.5px;font-weight:500}
h3,h4{margin:0}

/* ── 헤더 ───────────────────────────────────────────── */
.bar{display:block}
.hd{background:var(--surf);border-bottom:1px solid var(--line);
padding:calc(12px + env(safe-area-inset-top)) 16px 12px;
display:flex;align-items:center;gap:12px;position:relative;z-index:5}
.hd .logo{width:38px;height:38px;border-radius:11px;background:var(--priw);
display:grid;place-items:center;font-size:19px;flex:0 0 auto}
.hd .ttl{flex:1;min-width:0}
.hd h1{margin:0;font-size:16.5px;font-weight:800;letter-spacing:-.02em}
.hd .sub{font-size:11.5px;color:var(--tx3);margin-top:1px}
.hd .upd{text-align:right;font-size:10.5px;color:var(--tx3);line-height:1.45;flex:0 0 auto}
.hd .upd b{display:block;color:var(--tx2);font-family:var(--mono);font-size:11px;font-weight:600}

/* ── 출발지 칩 ──────────────────────────────────────── */
nav.chips{display:flex;gap:8px;overflow-x:auto;padding:12px 16px;background:var(--surf);
border-bottom:1px solid var(--line);scrollbar-width:none}
nav.chips::-webkit-scrollbar{display:none}
nav.chips button{flex:0 0 auto;display:flex;align-items:center;gap:6px;
background:var(--surf);border:1px solid var(--line);border-radius:12px;
color:var(--tx2);font-family:var(--sans);font-size:13.5px;font-weight:700;
padding:10px 15px;cursor:pointer;white-space:nowrap;box-shadow:var(--sh)}
nav.chips button.on{background:var(--pri);border-color:var(--pri);color:#fff}

/* ── 메인 탭: 데스크톱 상단 알약 / 모바일 하단 바 ───── */
nav.main{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;
background:rgba(255,255,255,.97);backdrop-filter:blur(12px);
border-top:1px solid var(--line);overflow-x:auto;scrollbar-width:none;
padding-bottom:env(safe-area-inset-bottom)}
nav.main::-webkit-scrollbar{display:none}
nav.main button{flex:1 1 0;min-width:0;background:none;border:none;cursor:pointer;
display:flex;flex-direction:column;align-items:center;gap:3px;padding:9px 2px 8px;
color:var(--tx3);font-family:var(--sans);font-size:10px;font-weight:700;
white-space:nowrap}
nav.main button .ic{font-size:18px;line-height:1}
nav.main button .lg{display:none}
nav.main button[aria-selected=true]{color:var(--pri)}

/* ── 레이아웃 ───────────────────────────────────────── */
.app{display:block}
.side{display:none}
main{padding:16px;max-width:1180px;margin:0 auto}
.panel[hidden],div.sub[hidden]{display:none}

/* ── 서브 탭 ────────────────────────────────────────── */
nav.sub{display:flex;gap:7px;overflow-x:auto;padding:2px 0 6px;scrollbar-width:none}
nav.sub::-webkit-scrollbar{display:none}
nav.sub button{flex:0 0 auto;background:var(--surf);border:1px solid var(--line);
border-radius:999px;color:var(--tx2);font-family:var(--sans);font-size:12.5px;
font-weight:700;padding:8px 15px;cursor:pointer;white-space:nowrap}
nav.sub button[aria-selected=true]{background:var(--pri);border-color:var(--pri);color:#fff}

/* ── 요약 스트립 ────────────────────────────────────── */
.strip{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-bottom:14px}
.strip>div{background:var(--surf);border:1px solid var(--line);border-radius:13px;
padding:11px 12px;box-shadow:var(--sh);min-width:0}
.strip .k{font-size:10.5px;color:var(--tx3);margin-bottom:3px;font-weight:600;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.strip .v{font-family:var(--mono);font-size:21px;font-weight:800;letter-spacing:-.03em}
.strip .v.zero{color:var(--tx3)}.strip .v.g{color:var(--good)}
.strip .v.w{color:var(--warn)}.strip .v.r{color:var(--bad)}
.strip .v.i{color:var(--info)}.strip .v.p{color:var(--pri)}

/* ── TOP5 타일 ──────────────────────────────────────── */
.top5{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.top5 .tile:first-child{grid-column:1/-1}
.tile{background:var(--surf);border:1px solid var(--line);border-radius:14px;
padding:13px 14px;box-shadow:var(--sh);display:flex;flex-direction:column;
text-decoration:none;color:inherit;position:relative;overflow:hidden}
.tile:first-child{background:linear-gradient(160deg,#FFF5F6 0%,#FFF 55%);border-color:#FADCE0}
.tile .rk{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);
font-size:10.5px;font-weight:800;margin-bottom:8px}
.tile .rk i{width:19px;height:19px;border-radius:6px;display:grid;place-items:center;
font-style:normal;color:#fff;background:var(--tx3);font-size:11px}
.tile.r1 .rk i{background:#E5484D}.tile.r2 .rk i{background:#F0770B}
.tile.r3 .rk i{background:#E0A21C}
.tile.r1 .rk{color:#E5484D}.tile.r2 .rk{color:#F0770B}.tile.r3 .rk{color:#B9860F}
.tile .rt2{font-size:15px;font-weight:800;letter-spacing:-.02em;line-height:1.3;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .rc{font-family:var(--mono);font-size:11.5px;font-weight:700;color:var(--tx3);
margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .dt{font-size:11px;color:var(--tx2);margin-top:5px;font-family:var(--mono);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .pw{margin-top:auto;padding-top:10px}
.tile .lb{display:inline-block;font-size:10px;font-weight:800;color:var(--bad);
background:var(--badw);border-radius:6px;padding:3px 7px;margin-bottom:5px}
.tile .pv{font-family:var(--mono);font-size:21px;font-weight:800;color:var(--bad);
letter-spacing:-.03em}
.tile .pv small{font-size:12px;font-weight:700}
.tile .bd{font-family:var(--mono);font-size:10.5px;color:var(--tx3);margin-top:4px}
.tile .sm{font-family:var(--mono);font-size:10px;color:var(--tx3);margin-top:7px;
border-top:1px solid var(--line2);padding-top:7px;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.tile .bd{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile:first-child .rt2{font-size:19px}
.tile:first-child .pv{font-size:27px}

/* ── 카드 ───────────────────────────────────────────── */
.card{background:var(--surf);border:1px solid var(--line);border-radius:14px;
padding:14px 15px;margin-bottom:10px;box-shadow:var(--sh)}
.card.c{border-style:dashed;box-shadow:none;background:var(--surf2)}
.card .top{display:block}
.pblock{margin-top:10px;padding-top:10px;border-top:1px solid var(--line2)}
.card .route{font-family:var(--mono);font-size:11.5px;color:var(--tx3);font-weight:600}
.card .city{font-size:16px;font-weight:800;margin-top:2px;letter-spacing:-.02em}
.price{font-family:var(--mono);font-weight:800;letter-spacing:-.035em;line-height:1.1;
font-size:25px;color:var(--tx)}
.price .unit{font-size:12.5px;color:var(--tx2);margin-left:2px;font-weight:700}
.tot{font-family:var(--mono);font-size:12.5px;font-weight:800;color:var(--bad);margin-top:4px}
.sub-price{font-family:var(--mono);font-size:11px;color:var(--tx3);margin-top:3px}
.row{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:8px 0;
border-top:1px solid var(--line2);font-size:12.5px}
.kv .k{color:var(--tx3);flex:0 0 auto;font-weight:600}
.kv .v{font-family:var(--mono);text-align:right}
.b{display:inline-flex;font-family:var(--sans);font-size:10.5px;font-weight:800;
padding:4px 8px;border-radius:7px;border:1px solid var(--line);color:var(--tx2);
background:var(--surf2)}
.b.g{color:var(--good);border-color:#BFE8D0;background:var(--goodw)}
.b.w{color:var(--warn);border-color:#F5DFBB;background:var(--warnw)}
.b.r{color:var(--bad);border-color:#F7C9CB;background:var(--badw)}
.b.i{color:var(--info);border-color:#C6D9FB;background:var(--infow)}
.b.p{color:var(--pri);border-color:var(--prib);background:var(--priw)}
a.book{display:block;margin-top:11px;padding:11px;text-align:center;background:var(--pri);
border-radius:10px;color:#fff;text-decoration:none;font-size:13px;font-weight:800}

/* ── 존 / 표 / 밴드 ─────────────────────────────────── */
.zone{background:var(--surf);border:1px solid var(--line);border-radius:16px;
padding:15px 15px 16px;margin-bottom:14px;box-shadow:var(--sh)}
.zone>h3{font-size:14px;font-weight:800;letter-spacing:-.02em;margin-bottom:3px}
.zone>.desc{margin:0 0 12px;font-size:11.5px;color:var(--tx3);font-weight:500}
.zone .card{background:var(--surf2);box-shadow:none}
.zone .top5{margin-top:2px}
.empty{border:1px dashed var(--line);border-radius:11px;padding:20px 15px;color:var(--tx3);
font-size:13px;text-align:center;line-height:1.6;background:var(--surf2)}
.empty b{display:block;color:var(--tx2);margin-bottom:4px}
table.rt{width:100%;border-collapse:collapse;font-size:13px}
table.rt th{text-align:right;font-size:11px;color:var(--tx3);padding:7px 8px;
border-bottom:1px solid var(--line);font-weight:700}
table.rt th:first-child{text-align:left}
table.rt td{padding:11px 8px;border-bottom:1px solid var(--line2);text-align:right}
table.rt td:first-child{text-align:left;line-height:1.35;font-weight:700}
table.rt tr:last-child td{border-bottom:none}
table.rt td.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
table.rt td.g{color:var(--good);font-weight:800}
table.rt td.w{color:var(--warn);font-weight:700}
table.rt td.r{color:var(--bad);font-weight:800}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
.band{display:grid;gap:6px;padding:12px 2px;border-bottom:1px solid var(--line2)}
.band:last-child{border-bottom:none}
.band .bl{font-size:13px;line-height:1.35;font-weight:700}
.band .br{display:flex;justify-content:space-between;align-items:baseline;
font-family:var(--mono);font-size:13px;font-weight:700}
.band .bar{position:relative;height:6px;border-radius:3px;
background:linear-gradient(90deg,var(--good),var(--warn),var(--bad));opacity:.22}
.band .bar i{position:absolute;top:-3px;width:3px;height:12px;border-radius:2px;
margin-left:-1px;opacity:1}
.band .bar i.g{background:var(--good)}.band .bar i.w{background:var(--warn)}
.band .bar i.r{background:var(--bad)}
.secstat{border-radius:13px;padding:13px 15px;margin-bottom:14px;font-size:13px;
border:1px solid var(--line);background:var(--surf);line-height:1.6;box-shadow:var(--sh)}
.secstat.part{border-left:4px solid var(--warn)}
.secstat.fail{border-left:4px solid var(--bad)}
.secstat b{display:block;margin-bottom:3px;font-weight:800}
.secstat span{color:var(--tx2);font-size:12.5px}
footer{padding:20px 16px 26px;color:var(--tx3);font-size:11px;line-height:1.75;
text-align:center;font-family:var(--mono)}

/* ── 데스크톱 ───────────────────────────────────────── */
@media(min-width:1024px){
body{padding-bottom:0}
.app{display:grid;grid-template-columns:264px 1fr;align-items:start;
min-height:100vh;max-width:1560px;margin:0 auto}
.side{display:block;position:sticky;top:0;height:100vh;overflow-y:auto;
background:var(--surf);border-right:1px solid var(--line);padding:20px 16px 26px}
.side .brand{display:flex;align-items:center;gap:11px;margin-bottom:26px}
.side .brand .logo{width:42px;height:42px;border-radius:12px;background:var(--priw);
display:grid;place-items:center;font-size:21px}
.side .brand h1{font-size:16px;font-weight:800;letter-spacing:-.02em}
.side .brand .sub{font-size:11px;color:var(--tx3);margin-top:2px}
.side h4{font-size:11px;color:var(--tx3);font-weight:700;margin:0 0 9px 3px;
letter-spacing:.02em}
.side .sgroup{margin-bottom:22px}
.side .ob{display:flex;align-items:center;gap:9px;width:100%;background:var(--surf);
border:1px solid var(--line);border-radius:12px;padding:11px 13px;margin-bottom:7px;
font-family:var(--sans);font-size:13.5px;font-weight:700;color:var(--tx2);
cursor:pointer;text-align:left}
.side .ob .ic{font-size:15px}
.side .ob b{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--tx3);font-weight:700}
.side .ob.on{background:var(--pri);border-color:var(--pri);color:#fff}
.side .ob.on b{color:rgba(255,255,255,.8)}
.side .sum{background:var(--surf2);border:1px solid var(--line);border-radius:13px;padding:13px}
.side .sum .r{display:flex;justify-content:space-between;align-items:center;
padding:6px 0;font-size:12.5px;color:var(--tx2);font-weight:600}
.side .sum .r b{font-family:var(--mono);font-size:12px;font-weight:800;color:#fff;
background:var(--tx3);border-radius:7px;padding:2px 8px;min-width:32px;text-align:center}
.side .sum .r b.g{background:var(--good)}.side .sum .r b.r{background:var(--bad)}
.side .sum .r b.p{background:var(--pri)}.side .sum .r b.i{background:var(--info)}
.side .tip{margin-top:18px;background:var(--warnw);border:1px solid #F3E2C4;
border-radius:13px;padding:13px;font-size:11.5px;color:#8A6316;line-height:1.65}
.side .tip b{display:block;margin-bottom:4px;font-size:12px}
.bar{display:flex;align-items:center;gap:16px;padding:14px 26px;
background:var(--surf);border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:30}
.hd{order:2;margin-left:auto;padding:0;border:none;background:none;flex:0 0 auto}
.hd .logo,.hd .ttl{display:none}
nav.chips{display:none}
nav.main{order:1;position:static;border-top:none;background:none;backdrop-filter:none;
padding:0;gap:9px;max-width:none;flex:0 1 auto}
nav.main button{flex:0 0 auto;min-width:0;flex-direction:row;gap:7px;
background:var(--surf);border:1px solid var(--line);border-radius:13px;
padding:10px 15px;font-size:13px;box-shadow:var(--sh);color:var(--tx2)}
nav.main button .ic{font-size:15px}
nav.main button .lg{display:inline}
nav.main button .sm2{display:none}
nav.main button[aria-selected=true]{background:var(--priw);border-color:var(--prib);color:var(--pri)}
main{padding:18px 26px 40px}
.strip{grid-template-columns:repeat(6,1fr)}
.top5{grid-template-columns:repeat(5,1fr)}
.top5 .tile:first-child{grid-column:auto}
.tile:first-child .rt2{font-size:15px}
.tile:first-child .pv{font-size:21px}
.cards2{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.cards2 .card{margin-bottom:0}
.card .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.pblock{margin-top:0;padding-top:0;border-top:none;text-align:right;flex:0 0 auto}
}
@media(min-width:1440px){.cards2{grid-template-columns:repeat(3,1fr)}}
"""


JS = """
function selMain(id){
  document.querySelectorAll('nav.main button').forEach(function(x){
    x.setAttribute('aria-selected', x.getAttribute('data-id')===id?'true':'false');});
  document.querySelectorAll('section.panel').forEach(function(p){p.hidden=(p.id!=='p-'+id);});
  window.scrollTo(0,0);
}
function selSub(pid,sid){
  var root=document.getElementById('p-'+pid); if(!root) return;
  root.querySelectorAll(':scope > nav.sub button').forEach(function(x){
    x.setAttribute('aria-selected', x.getAttribute('data-id')===sid?'true':'false');});
  root.querySelectorAll(':scope > div.sub').forEach(function(d){d.hidden=(d.id!=='s-'+sid);});
  document.querySelectorAll('[data-go]').forEach(function(x){
    x.classList.toggle('on', x.getAttribute('data-sub')===sid);});
}
document.querySelectorAll('nav.main button').forEach(function(b){
  b.addEventListener('click',function(){selMain(b.getAttribute('data-id'));},false);});
document.querySelectorAll('nav.sub button').forEach(function(b){
  var pid=b.closest('section.panel').id.slice(2);
  b.addEventListener('click',function(){selSub(pid,b.getAttribute('data-id'));},false);});
document.querySelectorAll('[data-go]').forEach(function(b){
  b.addEventListener('click',function(){
    var g=b.getAttribute('data-go');selMain(g);selSub(g,b.getAttribute('data-sub'));},false);});
document.querySelectorAll('[data-reload]').forEach(function(b){
  b.addEventListener('click',function(){location.reload();},false);});
"""



def esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def tile(o, rank):
    """TOP 타일. 실가격이 큰 숫자, 교통비 포함 총액은 바로 아래 보조 표기."""
    cls = f"tile r{rank}" if rank <= 3 else "tile"
    if o.get("access_cost"):
        bd = (f'<div class="bd">총액 {o["effective_krw"]:,} '
              f'· 이동 +{o["access_cost"]:,}</div>')
    else:
        bd = '<div class="bd">이동비 0원 · 집 앞 공항</div>'
    wkd = (f' · 주말 연차{o["annual_leave"]}' if o.get("weekend_trip") else "")
    return (f'<a class="{cls}" href="{o["link"]}" target="_blank" rel="noopener">'
            f'<div class="rk"><i>{rank}</i>{esc(o.get("verdict") or "")}</div>'
            f'<div class="rt2">{esc(o["city"])}</div>'
            f'<div class="rc">{o["dep"]} → {o["arr"]} · {esc(o["airline_kr"])}</div>'
            f'<div class="dt">{o["depart_date"][5:]}~{o["return_date"][5:]} · '
            f'{o["nights"]}박{o["nights"]+1}일</div>'
            f'<div class="pw"><span class="lb">항공권 실가격</span>'
            f'<div class="pv">{o["price_krw"]:,}<small>원</small></div>{bd}</div>'
            f'<div class="sm">표본 {o.get("baseline_n", 0)} · '
            f'SCORE {o.get("deal_score") or "-"}{wkd}</div></a>')


def tiles(items, empty_msg):
    if not items:
        return f'<div class="empty"><b>0건</b>{empty_msg}</div>'
    return ('<div class="top5">'
            + "".join(tile(o, i + 1) for i, o in enumerate(items)) + '</div>')


def card(o):
    ch = {"new": '<span class="b i">🆕 NEW</span>',
          "down": f'<span class="b g">📉 {o["delta"]:+,}원</span>' if o.get("delta") else "",
          "up": f'<span class="b w">📈 {o["delta"]:+,}원</span>' if o.get("delta") else "",
          }.get(o.get("change"), "")
    extra = ""
    if o.get("weekend_trip"):
        extra += f'<span class="b g">🔥 주말+연차{o["annual_leave"]}일</span>'
    elif o.get("weekend"):
        extra += f'<span class="b">주말 · 연차{o["annual_leave"]}일</span>'
    else:
        extra += f'<span class="b">주말 없음 · 연차{o["annual_leave"]}일</span>'
    if o.get("night_departure"): extra += '<span class="b i">🌙 퇴근후 출발</span>'
    if o.get("record_low"):   extra += '<span class="b g">🏆 추적내 최저</span>'
    if o.get("route_record_low") and o.get("route_low_prev"):
        extra += '<span class="b g">🔻 노선 역대최저</span>'
    if o.get("streak_down"):  extra += '<span class="b g">📉 연속하락</span>'
    if o.get("holiday"):      extra += f'<span class="b r">🎉 {esc(o["holiday"])}</span>'

    gb = {"A": '<span class="b g">A</span>', "B": '<span class="b w">B · 캐시</span>',
          "C": '<span class="b">C</span>'}[o["grade"]]
    sc = (f'<span class="b i">SCORE {o["deal_score"]}</span>'
          if o.get("deal_score") else "")
    st = {0: "직항", 1: "1회 환승"}.get(o.get("stops"), "환승")
    eff = (f'<div class="tot">총액 {o["effective_krw"]:,}원</div>'
           f'<div class="sub-price">항공 {o["price_krw"]:,} + 이동 '
           f'{o["access_cost"]:,}</div>') if o.get("access_cost") else ""

    kv = (f'<div class="kv"><span class="k">일정 구성</span><span class="v">'
          f'{"주말 포함" if o.get("weekend") else "주말 없음"} · '
          f'빨간날 {o.get("red_days", 0)}일 · 연차 {o["annual_leave"]}일'
          f'</span></div>')
    if o.get("access_cost"):
        kv += (f'<div class="kv"><span class="k">실부담가 ({HOME} 기준)</span>'
               f'<span class="v">{o["effective_krw"]:,}원 '
               f'<span style="color:var(--tx3)">= {o["price_krw"]:,} + 이동 '
               f'{o["access_cost"]:,}</span></span></div>')
    if o.get("route_low_prev"):
        kv += (f'<div class="kv"><span class="k">노선 역대최저</span>'
               f'<span class="v">{o["route_low_prev"]:,}원 '
               f'<span style="color:var(--tx3)">{esc(o.get("route_low_date") or "")}</span>'
               f'</span></div>')
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
<div class="pblock"><div class="price">{o['price_krw']:,}<span class="unit">원</span></div>
<div class="sub-price">{o['depart_date'][5:]} → {o['return_date'][5:]} · {o['nights']}박{o['nights']+1}일</div>
{eff}</div></div>
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

    out = ['<div class="tw"><table class="rt"><thead><tr><th>노선</th><th>건수</th>'
           '<th>최저</th><th>중앙</th><th>최저-중앙</th></tr></thead><tbody>']
    for r in rows:
        cls = "g" if r["gap"] <= -15 else ("w" if r["gap"] <= -5 else "")
        out.append(
            f'<tr><td><b>{esc(r["city"])}</b><br><span class="mut">{r["dep"]}→{r["arr"]}</span></td>'
            f'<td class="num">{r["n"]}</td>'
            f'<td class="num">{r["min"]:,}</td>'
            f'<td class="num mut">{r["median"]:,}</td>'
            f'<td class="num {cls}">{r["gap"]:+d}%</td></tr>')
    out.append("</tbody></table></div>")
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


def origin_compare(offers):
    """같은 도시를 어느 공항에서 뜨는 게 유리한가.

    청주 거주자에게 실제로 필요한 판단이다. 인천이 5만원 싸도 리무진 왕복
    4만원이면 실이득은 1만원이라는 것을 한 줄로 보여준다.
    실가격이 주 표기이고, 실부담가는 그 옆에 보조로 붙는다.
    """
    by_city = {}
    for o in offers:
        if o["grade"] == "C":
            continue
        cur = by_city.setdefault(o["city"], {}).get(o["dep"])
        if cur is None or o["price_krw"] < cur["price_krw"]:
            by_city[o["city"]][o["dep"]] = o
    if not by_city:
        return '<div class="empty"><b>0건</b>비교할 검증 딜이 없습니다.</div>'

    # 실부담가 최저를 기준으로, 청주 대비 이득이 큰 도시부터
    def city_key(item):
        _, per = item
        best = min(per.values(), key=lambda x: x["effective_krw"])
        home = per.get(HOME)
        return -((home["effective_krw"] - best["effective_krw"]) if home else 0)

    out = []
    for city, per in sorted(by_city.items(), key=city_key):
        rows = sorted(per.values(), key=lambda x: x["effective_krw"])
        cheap_air = min(r["price_krw"] for r in rows)
        cheap_eff = rows[0]["effective_krw"]
        body = []
        for r in rows:
            marks = []
            if r["price_krw"] == cheap_air: marks.append('<span class="b w">항공권 최저</span>')
            if r["effective_krw"] == cheap_eff: marks.append('<span class="b g">실부담 최저</span>')
            if r["dep"] == HOME: marks.append('<span class="b i">홈</span>')
            body.append(
                f'<tr><td><b>{r["dep"]}</b>→{r["arr"]}<br>'
                f'<span class="mut">{r["depart_date"][5:]} {r["nights"]}박 · '
                f'{esc(r["airline_kr"])}</span></td>'
                f'<td class="num">{r["price_krw"]:,}</td>'
                f'<td class="num mut">+{r["access_cost"]:,}</td>'
                f'<td class="num{" g" if r["effective_krw"] == cheap_eff else ""}">'
                f'{r["effective_krw"]:,}</td>'
                f'<td>{"".join(marks)}</td></tr>')
        home = per.get(HOME)
        if home:
            gap = home["effective_krw"] - cheap_eff
            note = (f'{HOME} 가 실부담 최저' if gap <= 0 else
                    f'{HOME} 대비 실이득 {gap:,}원')
        else:
            note = f'{HOME} 출발 없음'
        out.append(
            f'<div class="zone"><h3>{esc(city)}</h3><p class="desc">{note}</p>'
            f'<div class="tw"><table class="rt"><thead><tr><th>공항</th><th>실가격</th>'
            f'<th>이동비</th><th>총액</th><th></th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')
    return "".join(out)


def zone(title, desc, items, empty_msg):
    # .cards2 는 데스크톱에서만 그리드가 된다 (모바일은 그대로 세로 적층).
    body = (f'<div class="cards2">{"".join(card(o) for o in items)}</div>'
            if items else f'<div class="empty"><b>0건</b>{empty_msg}</div>')
    return (f'<div class="zone"><h3>{title}</h3>'
            f'<p class="desc">{desc}</p>{body}</div>')


def render(offers, stats, gone, meta):
    by_grade = lambda g, pool: sorted(
        [o for o in pool if o["grade"] == g],
        key=lambda x: -(x.get("deal_score") or 0))

    tabs, panels = [], []

    # 요약
    a = by_grade("A", offers); b = by_grade("B", offers); c = by_grade("C", offers)
    good = a + b
    top = good[:5]
    home_top = [o for o in good if o["dep"] == HOME][:5]
    wk_all = [o for o in good if o.get("weekend_trip")]
    strip = f"""<div class="strip">
<div><div class="k">🏠 {HOME} 출발</div><div class="v {'g' if home_top else 'zero'} num">{sum(1 for o in good if o['dep'] == HOME)}</div></div>
<div><div class="k">🔥 주말여행</div><div class="v {'g' if wk_all else 'zero'} num">{len(wk_all)}</div></div>
<div><div class="k">👀 현재 저가 (B)</div><div class="v {'w' if b else 'zero'} num">{len(b)}</div></div>
<div><div class="k">🆕 신규</div><div class="v {'i' if stats['new'] else 'zero'} num">{stats['new']}</div></div>
<div><div class="k">📉 하락</div><div class="v {'g' if stats['down'] else 'zero'} num">{stats['down']}</div></div>
<div><div class="k">⚰️ 소멸</div><div class="v {'r' if stats['gone'] else 'zero'} num">{stats['gone']}</div></div></div>"""

    note = ""
    if not a and not b:
        note = ('<div class="secstat fail"><b>오늘은 기준을 넘는 딜이 없습니다</b>'
                '<span>C등급 후보만 있습니다. 예약 판단 근거로 쓰지 마세요.</span></div>')
    summary = strip + note + (
        f'<div class="zone"><h3>👑 오늘의 강력 특가 TOP 5</h3>'
        f'<p class="desc">네 공항 통합 · DEAL SCORE 순 (주말 적합도 22점 반영) · '
        f'항공권 실가격 기준</p>'
        + tiles(top, "표시할 딜이 없습니다.") + '</div>'
        + f'<div class="zone"><h3>🏠 {HOME} 출발 TOP</h3>'
        f'<p class="desc">집 앞 공항. 이동비용 0원.</p>'
        + tiles(home_top, f"오늘 {HOME} 출발 중 기준을 넘는 딜이 없습니다. "
                          f"청주는 캐시가 얇아 자주 비어 있습니다.") + '</div>')
    if gone:
        g = "".join(f'<div class="kv"><span class="k">{esc(x.get("city",""))} '
                    f'{x.get("depart_date","")}</span><span class="v">'
                    f'{x.get("price_krw",0):,}원</span></div>' for x in gone[:10])
        summary += f'<div class="zone"><h3>⚰️ 어제 사라진 딜</h3><p class="desc">재등장 추적 중</p>{g}</div>'
    tabs.append(("sum", "요약")); panels.append(("sum", summary, None))

    # 주말여행 — 사용자 기준: 주말(토·일) 포함 + 연차 0~1일
    wk = [o for o in offers if o.get("weekend_trip") and o["grade"] != "C"]
    wk.sort(key=lambda x: (x["annual_leave"], -(x.get("deal_score") or 0)))
    wk_home = [o for o in wk if o["dep"] == HOME]
    tabs.append(("wkd", "주말여행"))
    panels.append(("wkd",
                   zone(f"🏠 {HOME} 출발", "청주에서 바로 뜨는 주말 일정",
                        wk_home[:8], f"{HOME} 출발 중 조건을 만족하는 딜이 없습니다.")
                   + zone("전 출발지", "주말 포함 · 연차 0~1일 · SCORE 순",
                          wk[:20],
                          "주말 포함 + 연차 0~1일 조건을 만족하는 검증 딜이 없습니다."),
                   None))

    # 어디서 뜰까 — 출발지 비교
    tabs.append(("cmp", "어디서 뜰까"))
    panels.append(("cmp", '<div class="secstat part"><b>실가격이 기준입니다</b>'
                   f'<span>실부담가 = 항공권 + {HOME} 기준 왕복 교통비(추정치). '
                   '교통비는 scanner.py 의 ACCESS_COST 에서 조정합니다.</span></div>'
                   + origin_compare(offers), None))

    # 출발지별 (청주가 첫 서브탭)
    subs = []
    for key, label in (("cjj", "🏠 CJJ"), ("icn", "ICN / GMP"),
                       ("tae", "TAE"), ("pus", "PUS")):
        codes = {r[0] for r in ROUTES[key]}
        pool = [o for o in offers if o["dep"] in codes]
        html = (zone("🔥 주말여행", "주말 포함 · 연차 0~1일",
                     [o for o in by_grade("B", pool) + by_grade("A", pool)
                      if o.get("weekend_trip")][:10],
                     "이 출발지에는 주말 조건을 만족하는 딜이 없습니다.")
                + zone("👀 현재 저가", "B등급 · 캐시 데이터", by_grade("B", pool)[:20],
                       "왕복 실판매가 확인 건이 없습니다.")
                + zone("🔎 추가 확인 후보", "C등급 · SCORE 미부여",
                       by_grade("C", pool)[:10], "후보가 없습니다."))
        subs.append((key, label, html))
    tabs.append(("dep", "출발지별")); panels.append(("dep", "", subs))

    # 스위스 — 특가와 별개로 "지금 최저가"를 항상 보여준다
    sw = [o for o in offers if o["arr"] in ("ZRH", "GVA", "BSL")]
    if sw:
        cheap = sorted(sw, key=lambda x: x["price_krw"])
        deals = sorted([o for o in sw if o["grade"] != "C"],
                       key=lambda x: -(x.get("deal_score") or 0))
        lo = cheap[0]
        head = (f'<div class="secstat"><b>현재 최저 {lo["price_krw"]:,}원</b>'
                f'<span>{esc(lo["city"])} {lo["dep"]}→{lo["arr"]} · '
                f'{lo["depart_date"]} ~ {lo["return_date"]} · {lo["nights"]}박 · '
                f'{esc(lo["airline_kr"])}</span></div>')
        swi_html = head + zone(
            "💰 최저가 순", f"등급 무관 · {SWISS_NIGHTS[0]}~{SWISS_NIGHTS[-1]}박 전 구간",
            cheap[:10], "스위스 데이터가 없습니다.") + zone(
            "🔥 특가 순", "B등급 · SCORE 순", deals[:10],
            "정상가 비교가 성립한 스위스 딜이 없습니다.")
    else:
        swi_html = ('<div class="secstat fail"><b>스위스 데이터 없음</b>'
                    '<span>이번 스캔에서 ZRH·GVA·BSL 응답이 비었습니다. '
                    '캐시가 얇거나 호출이 예산에서 잘렸을 수 있습니다.</span></div>')
    tabs.append(("swi", "스위스")); panels.append(("swi", swi_html, None))

    # 노선별 요약
    tabs.append(("rts", "노선별"))
    panels.append(("rts", '<div class="zone"><h3>노선별 요약</h3>'
                   '<p class="desc">최저-중앙 격차가 큰 노선이 위. 지금 어느 노선이 눌려 있는지 본다.</p>'
                   + (route_summary(offers) if offers else
                      '<div class="empty"><b>0건</b>수집된 노선이 없습니다.</div>')
                   + '</div>', None))

    # 평균 비교
    tabs.append(("avg", "평균 비교"))
    panels.append(("avg", '<div class="zone"><h3>가격대 위치</h3>'
                   '<p class="desc">같은 노선·박수 안에서 지금 가격이 어디쯤인지. '
                   '왼쪽일수록 싸다. 특가 등급과 무관하게 전부 표시한다.</p>'
                   + band_rows(offers) + '</div>', None))

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

    ICON = {"sum": "🏠", "wkd": "📅", "cmp": "✈️", "dep": "🛫",
            "swi": "🏔️", "rts": "🧭", "avg": "📐"}
    SHORT = {"sum": "요약", "wkd": "주말", "cmp": "어디서", "dep": "출발지",
             "swi": "스위스", "rts": "노선", "avg": "평균"}
    navmain = '<nav class="main" role="tablist">' + "".join(
        f'<button role="tab" aria-selected="{"true" if i==0 else "false"}" data-id="{k}">'
        f'<span class="ic">{ICON.get(k, "•")}</span>'
        f'<span class="lg">{esc(l)}</span>'
        f'<span class="sm2">{esc(SHORT.get(k, l))}</span></button>'
        for i, (k, l) in enumerate(tabs)) + "</nav>"

    # 출발지 바로가기 — 사이드바(데스크톱)와 칩(모바일)이 같은 동작을 공유한다
    ORIGINS = (("cjj", "청주", "CJJ", "🏠"), ("icn", "인천·김포", "ICN·GMP", "✈️"),
               ("tae", "대구", "TAE", "✈️"), ("pus", "부산", "PUS", "✈️"))
    side_ob = "".join(
        f'<button class="ob{" on" if k == "cjj" else ""}" data-go="dep" data-sub="{k}">'
        f'<span class="ic">{ic}</span>{esc(nm)}<b>{code}</b></button>'
        for k, nm, code, ic in ORIGINS)
    chips = '<nav class="chips">' + "".join(
        f'<button class="{"on" if k == "cjj" else ""}" data-go="dep" data-sub="{k}">'
        f'{ic} {esc(nm)}</button>' for k, nm, code, ic in ORIGINS) + "</nav>"

    hol = (f'<div class="tip"><b>⚠️ 공휴일 표 만료</b>{esc(meta["holiday_gap"])} 까지만 '
           f'채워져 있어 그 이후 일정의 연차 계산이 부정확합니다. scanner.py 의 '
           f'HOLIDAYS 를 갱신하세요.</div>') if meta.get("holiday_gap") else (
           '<div class="tip"><b>💡 실부담가란</b>항공권 + 청주에서 그 공항까지 '
           '왕복 교통비(추정치)입니다. 인천이 싸도 리무진 값을 더하면 '
           '역전되는 경우를 잡아냅니다.</div>')

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light"><title>항공권 데일리 스캐너 · {meta['date']}</title>
<style>{CSS}</style></head><body>
<div class="app">
<aside class="side">
<div class="brand"><div class="logo">✈️</div><div>
<h1>항공권 데일리 스캐너</h1><div class="sub">매일 07:00 KST 업데이트</div></div></div>
<div class="sgroup"><h4>출발지 (홈: {meta.get('home', HOME)})</h4>{side_ob}</div>
<div class="sgroup"><h4>검색 범위</h4>
<div class="sum"><div class="r">출발일<b>D+{WINDOW_MIN}~{WINDOW_MAX}</b></div>
<div class="r">근거리<b>{NIGHTS[0]}~{NIGHTS[-1]}박</b></div>
<div class="r">스위스<b>{SWISS_NIGHTS[0]}~{SWISS_NIGHTS[-1]}박</b></div></div></div>
<div class="sgroup"><h4>오늘의 요약</h4><div class="sum">
<div class="r">🆕 신규<b class="i">{stats['new']}</b></div>
<div class="r">📉 가격 하락<b class="g">{stats['down']}</b></div>
<div class="r">📈 가격 상승<b class="r">{stats['up']}</b></div>
<div class="r">🔥 주말여행<b class="p">{len(wk_all)}</b></div>
<div class="r">👀 모니터링 중<b>{len(offers)}</b></div></div></div>
{hol}</aside>
<div class="mainwrap">
<div class="bar">
<header class="hd">
<div class="logo">✈️</div>
<div class="ttl"><h1>항공권 데일리 스캐너</h1>
<div class="sub">매일 07:00 KST 업데이트</div></div>
<div class="upd">마지막 업데이트<b>{esc(meta['ts'])}</b></div>
</header>
{navmain}
</div>
{chips}
<main>{body}</main>
<footer>수집 {meta['count']}건 · 검색 {meta['used']}/{meta['cap']} · A {len(a)} · B {len(b)} · C {len(c)}<br>
🆕 {stats['new']} · 📉 {stats['down']} · 📈 {stats['up']} · ⚰️ {stats['gone']}<br>
소스 Travelpayouts (캐시) · A등급 불가, B가 천장<br>
{('오류 ' + str(len(ERRORS)) + '건<br>') if ERRORS else ''}
가격은 캐시 기반 참고값입니다. 예약 전 판매처에서 직접 확인하세요.</footer>
</div></div>
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
    """로테이션 없음 — 매일 전 출발지 + 스위스를 스캔한다.

    요일 로테이션을 쓰면 청주가 주 3회만 잡히고 스위스는 화·금에만 나온다.
    청주 거주자 기준으로는 매일 네 공항을 동시에 비교할 수 있어야 의미가
    있으므로, 86회 호출(예산 130 이내)을 매일 그대로 쓴다.
    """
    return "전 출발지 + 스위스 · 상시", ["cjj", "icn", "tae", "pus", "swiss"]


def brief_line(o):
    """브리프 한 줄. 실가격이 주 표기, 실부담가는 괄호 안 보조."""
    txt = (f"{o['city']} {o['dep']}→{o['arr']} · "
           f"{o['depart_date'][5:]}~{o['return_date'][5:]} {o['nights']}박 · "
           f"{o['price_krw']:,}원")
    if o.get("access_cost"):
        txt += f" (실부담 {o['effective_krw']:,})"
    if o.get("discount_pct"):
        txt += f" -{o['discount_pct']:.0f}%"
    if o.get("deal_score"):
        txt += f" · SCORE {o['deal_score']}"
    if o.get("weekend_trip"):
        txt += f" · 주말+연차{o['annual_leave']}일"
    if o.get("holiday"):
        txt += f" · {o['holiday']}"
    if o.get("change") == "new":
        txt += "  🆕"
    elif o.get("change") == "down":
        txt += f"  📉{o['delta']:+,}"
    if o.get("route_record_low") and o.get("route_low_prev"):
        txt += "  🔻역대최저"
    return {"text": txt, "grade": o["grade"], "verdict": o.get("verdict"),
            "price": o["price_krw"], "effective": o.get("effective_krw"),
            "weekend_trip": bool(o.get("weekend_trip")),
            "leave": o.get("annual_leave"), "link": o["link"]}


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="원본 응답 덤프 후 종료")
    ap.add_argument("--all", action="store_true",
                    help="(호환용) 로테이션은 폐지됐고 항상 전 노선을 본다")
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
    print(f"▶ {date.today()} · {rot_name} · 홈 {HOME}")

    # 공휴일 표가 검색창을 못 덮으면 연차 계산이 조용히 틀린다. 반드시 알린다.
    horizon = date.today() + timedelta(days=WINDOW_MAX)
    holiday_gap = str(horizon) > HOLIDAY_MAX
    if holiday_gap:
        msg = (f"공휴일 표가 {HOLIDAY_MAX} 까지만 있음 "
               f"(검색창은 {horizon} 까지) → 그 이후 일정의 연차 계산이 부정확")
        print(f"⚠️  {msg}")
        ERRORS.append(msg)

    targets = []
    for g in groups:
        targets += SWISS if g == "swiss" else ROUTES.get(g, [])
    seen = set(); targets = [t for t in targets if not (t[:2] in seen or seen.add(t[:2]))]

    offers = []
    for org, dst, city, region in targets:
        nights = SWISS_NIGHTS if region == "유럽" else NIGHTS
        got, stop = fetch_route(org, dst, city, region, nights)
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
    track_lows(offers, hist)
    stats, gone = diff(offers, hist)

    meta = {"date": str(date.today()),
            "ts": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "rotation": rot_name, "used": BUDGET.used, "cap": BUDGET.cap,
            "count": len(offers), "home": HOME,
            "holiday_gap": HOLIDAY_MAX if holiday_gap else None}
    html = render(offers, stats, gone, meta)

    for p in (os.path.join(ROOT, "latest.html"),
              os.path.join(ROOT, "archive", f"deals-{date.today()}.html")):
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)

    # ── 아침 브리프용 요약 (morning 스킬이 읽는 파일) ──
    A = [o for o in offers if o["grade"] == "A"]
    B = [o for o in offers if o["grade"] == "B"]
    C = [o for o in offers if o["grade"] == "C"]
    good = A + B
    top = sorted(good, key=lambda x: -(x.get("deal_score") or 0))[:3]

    # 주말여행 (주말 포함 + 연차 0~1) · 청주 출발 · 스위스 최저가
    wk = sorted([o for o in good if o.get("weekend_trip")],
                key=lambda x: -(x.get("deal_score") or 0))[:3]
    home = sorted([o for o in good if o["dep"] == HOME],
                  key=lambda x: -(x.get("deal_score") or 0))[:3]
    swiss = sorted([o for o in offers if o["region"] == "유럽"],
                   key=lambda x: x["price_krw"])[:3]

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
        bits = [f"볼 것 {len(good)}건"]
        if wk:            bits.append(f"주말여행 {len(wk)}")
        if home:          bits.append(f"{HOME} {len(home)}")
        if stats["new"]:  bits.append(f"신규 {stats['new']}")
        if stats["down"]: bits.append(f"하락 {stats['down']}")
        status, headline = "OK", " · ".join(bits)

    brief = {
        "date": meta["date"], "ts": meta["ts"], "status": status,
        "headline": headline, "rotation": rot_name, "home": HOME,
        "reason": CIRCUIT.cause if CIRCUIT.tripped else None,
        "degraded": degraded,
        "holiday_gap": meta["holiday_gap"],
        "counts": {"a": len(A), "b": len(B), "c": len(C),
                   "weekend": sum(1 for o in good if o.get("weekend_trip")),
                   "home": sum(1 for o in good if o["dep"] == HOME), **stats},
        "source_note": "Travelpayouts 캐시 데이터 · A등급 불가, B가 천장",
        "access_note": f"실부담가 = 항공권 + {HOME} 기준 왕복 교통비 (추정치)",
        "top": [brief_line(o) for o in top],
        "weekend": [brief_line(o) for o in wk],
        "home_airport": [brief_line(o) for o in home],
        "swiss": [brief_line(o) for o in swiss],
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
