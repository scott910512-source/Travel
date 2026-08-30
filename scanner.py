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

SEARCH_BUDGET = 140       # CJJ 4×6 + ICN·GMP 6×4 + TAE 3×4 + PUS 4×4
                          # + 스위스 6×1(flex) = 82회
REQ_SLEEP = 0.45          # rate limit 여유
TIMEOUT = 25

WINDOW_MIN, WINDOW_MAX = 3, 75      # D+3 ~ D+75
NIGHTS = (2, 3, 4, 5)               # 근거리: 2박3일 ~ 5박6일

# 유럽은 캐시가 극단적으로 얇다. 조건을 걸수록 결과가 0 이 된다.
#
# 2026-08-30 실측 경과:
#   length 5~10박 지정 → 원본 0건 (그 박수의 왕복이 캐시에 없음)
#   length 제거 + 5~10박 필터 → ICN/SEL→GVA 원본 2건, 전부 탈락
#   4~14박으로 완화 → 여전히 탈락. 사유 집계 결과 "체류일 범위 밖 (3박)"
#
# 즉 캐시에 있는 것은 3박 제네바 왕복 2건뿐이었다. "유럽은 길게 간다"는
# 상식으로 범위를 잡은 것이 오히려 유일한 데이터를 걸러냈다. 이렇게 희소한
# 노선에서는 거르지 않고 있는 것을 그대로 보여준 뒤, 실제 박수를 카드에
# 표시하는 편이 맞다. 판단은 사람이 한다.
SWISS_NIGHTS = (2, 21)              # 사실상 필터 해제. 캐시에 있는 것을 다 본다
SWISS_WINDOW = (3, 180)             # 유럽 출발일 D+3 ~ D+180

# 지방공항은 직항만 본다.
# 청주에서 2회 환승 도쿄를 볼 이유가 없고, 환승편 가격이 섞이면 기준선까지
# 오염된다. (2026-08-30 실측: CJJ 10건 중 4건이 환승, 그중 2건은 2회 환승)
DIRECT_ONLY = {"CJJ", "TAE", "PUS"}

# 출발지별 수집 전략. 캐시가 얇은 곳일수록 넓게 훑는다.
# ICN 은 하루치로 버킷당 8건 이상 모이지만 CJJ 는 1~2건이라 같은 창을 쓰면
# 기준선이 아예 안 만들어진다. 청주만 창과 박수를 넓혀 후보를 늘린다.
# CJJ 는 여기 없다. 전용 스캐너(scan_cjj)가 노선별로 직접 조회한다.
ORIGIN_PROFILE = {
    "TAE": {"window": (3, 100), "nights": (2, 3, 4, 5)},
    "PUS": {"window": (3, 100), "nights": (2, 3, 4, 5)},
}


def profile(org):
    return ORIGIN_PROFILE.get(org, {"window": (WINDOW_MIN, WINDOW_MAX),
                                    "nights": NIGHTS})


# 표본 누적 — "표본 부족하면 기간을 넓혀 모은다"
#
# 보관 기간을 출발지별로 다르게 둔다. ICN 은 하루치로도 버킷당 8건 안팎이라
# 30일이면 충분하고, 오래된 가격을 끌어오면 오히려 현재 시세를 흐린다.
# 청주·대구·부산은 버킷당 1~2건이라 90일을 모아야 기준선이 선다.
THIN_SAMPLE = 10                       # 이 미만이면 얇은 버킷
SAMPLE_CAP = 30                        # 하루·버킷당 저장 상한

# 공항별 가격 기준선 계산 기간(일). 캐시가 얇을수록 길게 본다.
HISTORY_WINDOW = {"CJJ": 90, "TAE": 45, "PUS": 45, "ICN": 30, "GMP": 30}
HISTORY_WINDOW_DEFAULT = 30


def retention(dep):
    return HISTORY_WINDOW.get(dep, HISTORY_WINDOW_DEFAULT)


# 출발 편의성 가산점. 가격을 조작하지 않고 DEAL SCORE 에만 더한다.
# 화면에 보이는 실부담가는 항상 실제 값 그대로다.
AIRPORT_BONUS = {"CJJ": 10, "ICN": 0, "GMP": 2, "TAE": 3, "PUS": -2}

# 실부담가가 이 차이 안이면 청주를 위로 올린다 (이동시간·주차·스트레스)
TIE_BREAK_KRW = 10000


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
    "SEL": 44000,      # 도시코드 조회분. 실제로는 인천/김포다.
}

# 이동에 드는 "시간" 부담 (돈으로 안 잡히는 것). 점수 0~10.
ACCESS_SCORE = {"CJJ": 10, "TAE": 5, "PUS": 4, "ICN": 3, "GMP": 3, "SEL": 3}

# 출발지별 노선 — 청주(홈)를 맨 앞에 둔다. 표시 순서가 이 순서를 따른다.
ROUTES = {
    "icn": [("ICN", "KIX", "오사카", "일본"), ("ICN", "NRT", "도쿄", "일본"),
            ("ICN", "FUK", "후쿠오카", "일본"), ("ICN", "TPE", "타이베이", "중화권"),
            ("ICN", "BKK", "방콕", "동남아"), ("GMP", "HND", "도쿄", "일본")],
    "tae": [("TAE", "KIX", "오사카", "일본"), ("TAE", "TPE", "타이베이", "중화권"),
            ("TAE", "DAD", "다낭", "동남아")],
    "pus": [("PUS", "FUK", "후쿠오카", "일본"), ("PUS", "KIX", "오사카", "일본"),
            ("PUS", "TPE", "타이베이", "중화권"), ("PUS", "DAD", "다낭", "동남아")],
}
# API 가 공항코드를 도시코드로 접으므로(ICN→SEL) 캐시가 도시 단위로만
# 잡혀 있을 수 있다. 두 코드로 모두 조회하고 중복은 뒤에서 제거한다.
SWISS = [("ICN", "ZRH", "취리히", "유럽"), ("ICN", "GVA", "제네바", "유럽"),
         ("ICN", "BSL", "바젤", "유럽"),
         ("SEL", "ZRH", "취리히", "유럽"), ("SEL", "GVA", "제네바", "유럽"),
         ("SEL", "BSL", "바젤", "유럽")]

# 권역 기준선 (왕복 이코노미 KRW) — 절대가 점수용
# ★ --raw 판정 결과를 여기에 반영.
#   False = /v1/prices/calendar 의 price 가 왕복 총액 (현재 가정)
#   True  = 편도.  아래 REGION_BASE 가 자동으로 절반으로 스케일됨.
# 주의: discount_pct / verdict() 는 같은 버킷 중앙값 대비 상대값이라
#       스케일 불변이다. 이 플래그가 영향을 주는 곳은 REGION_BASE 뿐.
ONE_WAY_PRICE = False

_REGION_BASE_RT = {"일본": 220000, "중화권": 260000, "동남아": 380000,
                   "인니": 700000, "몽골": 450000,
                   "유럽": 1150000, "미주": 1300000, "국내선": 90000}
REGION_BASE = ({k: v // 2 for k, v in _REGION_BASE_RT.items()}
               if ONE_WAY_PRICE else _REGION_BASE_RT)

# ══════════════════════════════════════════════════════════
# 청주 전용 노선
# ══════════════════════════════════════════════════════════
# Travelpayouts 는 "CJJ 출발 전체"를 훑어주지 않는다. 청주는 캐시가 얇아
# 노선별로 직접 물어봐야 한다. 운항 노선 목록은 config 로 따로 관리한다.
#
# ★ 결과 없음 ≠ 운항 없음. 이 둘을 절대 섞지 않는다.
#   운항 여부는 config(active) 가, 가격 유무는 API 응답이 결정한다.

CJJ_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "config", "cjj_routes.json")


def load_cjj_routes():
    try:
        with open(CJJ_CONFIG, encoding="utf-8") as f:
            routes = json.load(f).get("routes") or {}
    except Exception as e:
        print(f"⚠️  {CJJ_CONFIG} 를 읽지 못했습니다 ({e}). CJJ 전용 스캔을 건너뜁니다.")
        return {}
    return {k: v for k, v in routes.items() if v.get("active", True)}


CJJ_ROUTES = load_cjj_routes()

# priority 별 실행 요일 (0=월). 1=매일, 2=월·수·금, 3=일요일.
PRIORITY_DAYS = {1: None, 2: {0, 2, 4}, 3: {6}}


def cjj_targets_today(force_all=False):
    """오늘 스캔할 청주 노선. force_all 이면 priority 무시하고 전부."""
    wd = date.today().weekday()
    out = []
    for code, info in CJJ_ROUTES.items():
        pr = int(info.get("priority", 1))
        days = PRIORITY_DAYS.get(pr)
        if force_all or days is None or wd in days:
            out.append((code, info))
    return out


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
RAWCOUNT = {}     # 노선별 원본 레코드 수 (필터 전). 빈 응답 진단용.
DROPS = {}        # 노선별 탈락 사유 집계. "원본은 왔는데 왜 0건인가" 에 답한다.
STAGES = {}       # 노선별 단계 생존 수. 어디서 데이터가 사라지는지 추적한다.

# normalize() 가 거르는 실제 순서와 같아야 한다. 그래야 깔때기가
# 단조 감소하고 "어디서 사라졌는지"를 한눈에 읽을 수 있다.
STAGE_ORDER = ("api_raw", "price", "date", "window",
               "roundtrip", "length", "direct", "final")
STAGE_LABEL = {"api_raw": "API raw", "price": "price filter",
               "date": "date parse", "window": "date filter",
               "direct": "direct filter", "roundtrip": "round-trip filter",
               "length": "length filter", "final": "final"}


def _stage(org, dst, name):
    """그 단계를 '통과한' 레코드 수를 센다."""
    k = f"{org}-{dst}"
    STAGES.setdefault(k, {})
    STAGES[k][name] = STAGES[k].get(name, 0) + 1


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

def fetch_route(org, dst, city, region, nights=None, flex=None, window=None):
    """노선 하나를 조회. 정규화된 offer 리스트 반환.

    두 가지 모드가 있다.

    1) nights=(2,3,4,5)  — 박수마다 length 를 지정해 따로 호출한다.
       근거리는 캐시가 두꺼워 원하는 박수가 실제로 존재한다.
    2) flex=(5, 10)      — length 를 아예 빼고 한 번만 호출한 뒤,
       응답에 실린 return_at 으로 실제 체류일을 계산해 5~10박만 남긴다.
       장거리는 캐시가 얇아서 length 를 못 박으면 응답이 통째로 빈다.
       (2026-08-30 실측: ICN→ZRH/GVA/BSL 을 length 5~10 으로 18회 호출해
        전부 0건. length 를 빼면 캐시에 있는 것을 그대로 받는다.)

    depart_date(월) 필터는 API 가 무시하고 캐시 전 구간을 반환하므로
    월 루프를 돌리지 않는다. 월별로 돌리면 같은 데이터를 중복 수집해
    build_baselines() 의 표본 수가 부풀려진다. (2026-08-30 실측 확인)
    왕복 기간 통제는 length 파라미터가 담당한다.
    """
    out = []
    ym = date.today().strftime("%Y-%m")   # 무시되지만 필수 파라미터
    raw = 0
    plans = [None] if flex else list(nights or NIGHTS)
    for n in plans:
        q = {"origin": org, "destination": dst, "depart_date": ym,
             "calendar_type": "departure_date", "currency": CURRENCY}
        if n is not None:
            q["length"] = n
        ok, data, err = call("/v1/prices/calendar", q)
        time.sleep(REQ_SLEEP)
        if not ok:
            if err in ("BUDGET_EXCEEDED", "CIRCUIT_OPEN"):
                return out, err
            ERRORS.append(f"{org}-{dst} {n if n else 'flex'}박: {err}")
            continue
        recs = (data.get("data") or {})
        raw += len(recs)
        STAGES.setdefault(f"{org}-{dst}", {})
        STAGES[f"{org}-{dst}"]["api_raw"] = \
            STAGES[f"{org}-{dst}"].get("api_raw", 0) + len(recs)
        for dep, v in recs.items():
            o = normalize(org, dst, city, region, dep, n, v, flex, window)
            if o:
                out.append(o)
    # 원본 건수를 같이 남긴다. 0건일 때 "응답이 없었나 / 걸러졌나" 를 구분한다.
    RAWCOUNT[f"{org}-{dst}"] = raw
    return out, None


def _drop(org, dst, why):
    DROPS.setdefault(f"{org}-{dst}", {})
    DROPS[f"{org}-{dst}"][why] = DROPS[f"{org}-{dst}"].get(why, 0) + 1
    return None


def normalize(org, dst, city, region, dep, nights, v, flex=None, window=None):
    price = v.get("price")
    if not price or price <= 0:
        return _drop(org, dst, "가격 없음")
    _stage(org, dst, "price")
    try:
        d0 = datetime.strptime(dep[:10], "%Y-%m-%d").date()
    except ValueError:
        return _drop(org, dst, "출발일 파싱 실패")
    _stage(org, dst, "date")
    lo, hi = window or (WINDOW_MIN, WINDOW_MAX)
    delta = (d0 - date.today()).days
    if not (lo <= delta <= hi):
        return _drop(org, dst, f"출발일 창 밖 (D+{delta})")
    _stage(org, dst, "window")

    ret_at = v.get("return_at")
    if ret_at:
        try:
            d1 = datetime.strptime(ret_at[:10], "%Y-%m-%d").date()
        except ValueError:
            return _drop(org, dst, "귀국일 파싱 실패")
        roundtrip = True
        _stage(org, dst, "roundtrip")
        actual = (d1 - d0).days
        if flex:
            # length 를 안 걸었으므로 실제 체류일이 범위 안인 것만 받는다.
            if not (flex[0] <= actual <= flex[1]):
                return _drop(org, dst, f"체류일 범위 밖 ({actual}박)")
            _stage(org, dst, "length")
            nights = actual
        else:
            # length 가 무시되는 경우를 대비한 방어. 요청 박수와 다르면 버린다.
            # (length 미지정 시 7박·21박·28박까지 섞여 나오는 것을 실측 확인)
            if actual != nights:
                return _drop(org, dst, f"요청 박수 불일치 ({actual}≠{nights})")
            _stage(org, dst, "length")
    elif flex:
        # 체류일을 못 세면 flex 모드에서는 쓸 수 없다 (귀국일을 지어낼 수 없음)
        return _drop(org, dst, "return_at 없음 (편도 캐시)")
    else:
        d1 = d0 + timedelta(days=nights)
        roundtrip = False          # ★ 왕복 미검증 → C등급 강등 사유

    stops = v.get("number_of_changes", v.get("transfers"))
    if org in DIRECT_ONLY and stops != 0:
        # stops 가 None 이면 직항임을 확인할 수 없다. 지방공항에서는 버린다.
        return _drop(org, dst, f"환승편 제외 (지방공항 직항만, stops={stops})")
    _stage(org, dst, "direct")
    _stage(org, dst, "final")

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
        "stops": stops,
        "price_krw": int(price),
        "access_cost": access,
        "effective_krw": int(price) + access,   # 청주 기준 실부담가 (보조 지표)
        "roundtrip_verified": roundtrip,
        "expires_at": v.get("expires_at"),
        "link": aviasales_link(org, dst, d0, d1),
        "dep_hour": dep_hour,
        "ret_hour": parse_hour(v.get("return_at")),
        "holiday": tp["holiday"],
        "weekend": tp["weekend"],
        "red_days": tp["red"],
        "annual_leave": tp["leave"],
        "night_departure": tp["night_departure"],
        # 사용자 기준: 주말(토·일) 포함 + 연차 0~1일.
        # 빨간날이 붙으면 그만큼 일정이 길어져도 조건을 유지한다.
        "weekend_trip": tp["weekend"] and tp["leave"] <= 1.0,
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


def leave_for_departure_day(dep_hour):
    """출국일이 평일일 때 드는 연차. 출발 시각으로 0 / 0.5 / 1 을 가른다.

      20시 이후  → 0    퇴근하고 그대로 공항
      18~20시    → 0.5  반차
      그 외       → 1
    시각을 모르면(=None) 보수적으로 1 로 센다.
    """
    if dep_hour is None:
        return 1.0
    if dep_hour >= 20:
        return 0.0
    if dep_hour >= 18:
        return 0.5
    return 1.0


def trip_profile(d0, d1, dep_hour=None):
    """여행 구간의 빨간날·연차 구성.

    연차 기준 (청주 거주자 시점):
      - 토·일·공휴일은 연차가 들지 않는다.
      - 그 외 평일은 출국일·귀국일을 포함해 연차 1일로 센다.
        토·일·월(공휴일)·화 일정이면 화요일 1일만 연차다.
      - 출국일이 평일이면 출발 시각에 따라 0 / 0.5 / 1 로 나눈다.

    귀국일은 항상 1로 센다. 캘린더 API 의 return_at 은 도착이 아니라
    현지 출발 시각이라 한국 도착 시각을 알 수 없기 때문이다. 모르는 것을
    유리하게 반올림하지 않는다.
    """
    weekend, red, leave, holi = False, 0, 0.0, None
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
        elif d == d0:
            cost = leave_for_departure_day(dep_hour)
            leave += cost
            night_dep = cost < 1.0
        else:
            leave += 1.0
        d += timedelta(days=1)
    return {"weekend": weekend, "red": red, "leave": round(leave, 1),
            "holiday": holi, "night_departure": night_dep}


# ══════════════════════════════════════════════════════════
# 청주 전용 스캔
# ══════════════════════════════════════════════════════════

CJJ_FLEX = (1, 10)          # 체류 1~10박. length 를 못 박지 않고 받는 대로 거른다
CJJ_WINDOW = (3, 120)       # 출발일 D+3 ~ D+120


def scan_cjj(force_all=False, debug=False):
    """청주 노선을 하나씩 직접 조회한다.

    length 를 지정하지 않고 노선당 1회만 호출한다. 캐시가 얇은 곳에서
    박수를 못 박으면 응답이 통째로 비기 때문이다 (스위스에서 실측). 대신
    응답의 return_at 으로 실제 체류일을 계산해 1~10박만 남긴다.

    반환: (offers, statuses)
      statuses 는 노선마다 route_status / price_status 를 따로 담는다.
      가격이 없다고 노선을 지우지 않는다 — 운항 여부와 가격 유무는 별개다.
    """
    offers, statuses = [], []
    targets = cjj_targets_today(force_all)
    if not targets:
        return offers, statuses

    print(f"\n▶ 청주 전용 스캔 · 노선 {len(targets)}/{len(CJJ_ROUTES)}"
          f"{' (전체)' if force_all else ' (오늘 priority 대상)'}")

    for code, info in targets:
        got, stop = fetch_route("CJJ", code, info["city"], info["region"],
                                flex=CJJ_FLEX, window=CJJ_WINDOW)
        key = f"CJJ-{code}"
        raw = RAWCOUNT.get(key, 0)

        if stop in ("BUDGET_EXCEEDED", "CIRCUIT_OPEN"):
            price_status = "error"
        elif got:
            price_status = "available"
        elif raw == 0:
            price_status = "missing"      # 응답 자체가 빔 = 캐시에 없음
        else:
            price_status = "missing"      # 응답은 왔지만 조건에 안 맞음

        statuses.append({
            "origin": "CJJ", "destination": code,
            "city": info["city"], "country": info["country"],
            "flag": info.get("flag", ""), "region": info["region"],
            "priority": int(info.get("priority", 1)),
            # 운항 여부는 config 가 정한다. API 응답으로 판단하지 않는다.
            "route_status": "active" if info.get("active", True) else "inactive",
            "price_status": price_status,
            "raw": raw,
            "count": len(got),
            "price": min((o["price_krw"] for o in got), default=None),
            "stages": STAGES.get(key, {}),
            "drops": DROPS.get(key, {}),
        })
        offers += got

        mark = {"available": "✅", "missing": "· ", "error": "⚠️"}[price_status]
        print(f"  {mark} CJJ→{code} {info['city']:6} "
              f"{len(got):>3}건 (원본 {raw})")
        if debug:
            print_cjj_stages(key)
        if stop:
            print(f"     ⛔ {stop} — 남은 노선 중단")
            break

    print_cjj_summary(statuses)
    return offers, statuses


def print_cjj_stages(key):
    """단계별로 몇 건이 살아남았는지. 데이터가 어디서 사라지는지 본다."""
    st = STAGES.get(key, {})
    if not st:
        return
    print(f"     [{key}]")
    for name in STAGE_ORDER:
        if name in st:
            print(f"       {STAGE_LABEL[name]:<20}: {st[name]}")
    d = DROPS.get(key, {})
    for why, cnt in sorted(d.items(), key=lambda x: -x[1])[:4]:
        print(f"       └ 탈락 {why}: {cnt}")


def print_cjj_summary(statuses):
    if not statuses:
        return
    avail = [x for x in statuses if x["price_status"] == "available"]
    miss = [x for x in statuses if x["price_status"] == "missing"]
    err = [x for x in statuses if x["price_status"] == "error"]
    print("\n  [CJJ SUMMARY]")
    print(f"    등록 노선        {len(CJJ_ROUTES)}")
    print(f"    오늘 조회        {len(statuses)}")
    print(f"    가격 확인        {len(avail)}")
    print(f"    가격 데이터 부족 {len(miss)}")
    if err:
        print(f"    조회 오류        {len(err)}")
    if miss:
        print("    부족: " + ", ".join(f"{x['city']}({x['destination']})"
                                       for x in miss[:12]))


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

def bucket_key(o):
    return f"{o['dep']}-{o['arr']}-{o['nights']}"


def track_samples(offers, hist):
    """표본이 얇은 (출발지·목적지·박수) 버킷만 과거 가격을 누적한다.

    ICN 처럼 하루치로 표본이 차는 노선은 저장하지 않는다. 저장할 이유도 없고
    price_history 만 무거워진다. 대상은 청주·대구처럼 버킷당 1~2건인 곳이다.
    (2026-08-30 실측: CJJ 버킷 7개의 표본이 min 1 / 중앙 1 / max 2)

    두꺼워진 버킷은 누적을 버린다. 오래된 가격이 현재 시세를 흐리기 때문이다.
    """
    store = hist.get("thin_samples", {})
    today = str(date.today())
    todays = {}
    for o in offers:
        todays.setdefault(bucket_key(o), []).append(o["price_krw"])

    for k, ps in todays.items():
        if len(ps) >= THIN_SAMPLE:
            store.pop(k, None)
            continue
        store.setdefault(k, {})[today] = sorted(ps)[:SAMPLE_CAP]

    for k in list(store):
        dep = k.split("-")[0]
        cut = str(date.today() - timedelta(days=retention(dep)))
        kept = {d: v for d, v in store[k].items() if d >= cut}
        if kept:
            store[k] = kept
        else:
            del store[k]
    hist["thin_samples"] = store
    return store


def build_baselines(offers, thin=None):
    """정상가 기준선을 3단으로 만든다.

    노선·박수 버킷만 쓰면 청주처럼 캐시가 얇은 출발지는 버킷마다 1~2건이라
    기준선이 안 생기고 전건이 "비교 불가"로 빠진다. 그래서 두 가지를 한다.

    1) 얇은 버킷에는 과거 표본(HISTORY_WINDOW 일)을 끌어와 채운다.
       오늘 결과가 아예 없는 버킷은 채우지 않는다 — 비교할 대상이 없다.
    2) 그래도 모자라면 아래로 한 단계씩 내려간다.

         1단 노선·박수  (CJJ-KIX 3박)      표본 3건 이상 — 가장 정확
         2단 노선 전체  (CJJ-KIX 전 박수)  표본 3건 이상
         3단 목적지·박수 (→KIX 3박, 출발지 혼합) 표본 5건 이상 — 가장 거침

    어느 단을 썼는지, 누적을 썼는지는 baseline_tier 로 남겨 화면에 표시한다.
    """
    b1, b2, b3 = {}, {}, {}
    for o in offers:
        b1.setdefault((o["dep"], o["arr"], o["nights"]), []).append(o["price_krw"])
        b2.setdefault((o["dep"], o["arr"]), []).append(o["price_krw"])
        b3.setdefault((o["arr"], o["nights"]), []).append(o["price_krw"])

    today = str(date.today())
    pooled = {}          # {버킷: 끌어온 보관일수} — 라벨에 그대로 쓴다
    for key, days in (thin or {}).items():
        try:
            dep, arr, nights = key.rsplit("-", 2)
            k1, k2 = (dep, arr, int(nights)), (dep, arr)
        except ValueError:
            continue
        if k1 not in b1:
            continue                      # 오늘 없는 버킷은 되살리지 않는다
        past = [p for d, ps in days.items() if d != today for p in ps]
        if not past:
            continue
        if len(b1[k1]) < THIN_SAMPLE:
            b1[k1] = b1[k1] + past
            pooled[k1] = retention(dep)
        if k2 in b2 and len(b2[k2]) < THIN_SAMPLE:
            b2[k2] = b2[k2] + past

    def pack(buckets, need):
        out = {}
        for k, v in buckets.items():
            if len(v) < need:
                continue
            srt = sorted(v)
            out[k] = {"median": int(statistics.median(srt)),
                      "mean": int(statistics.fmean(srt)), "n": len(srt),
                      "min": srt[0], "max": srt[-1],
                      "p25": srt[max(0, int(len(srt) * .25) - 1)]}
        return out

    return {"exact": pack(b1, 3), "route": pack(b2, 3), "dest": pack(b3, 5),
            "pooled": pooled}


def pick_baseline(o, baselines):
    """offer 하나에 맞는 기준선을 위에서부터 찾는다. (기준선, 단계명)"""
    key = (o["dep"], o["arr"], o["nights"])
    bl = baselines["exact"].get(key)
    if bl:
        days = baselines["pooled"].get(key)
        return bl, ("노선·박수" if not days else f"노선·박수 · {days}일 누적")
    bl = baselines["route"].get((o["dep"], o["arr"]))
    if bl:
        return bl, "노선 전체 박수"
    bl = baselines["dest"].get((o["arr"], o["nights"]))
    if bl:
        return bl, "목적지 기준 (출발지 혼합)"
    return None, None


# ── 특가 판정 ─────────────────────────────────────────────
# ★ 이 판정식은 web/app.js 의 dealTier()/dealScore() 와 같은 규칙이다.
#   여기(파이썬)는 brief.json — 설정 없이 읽히는 아침 브리프 — 전용이고,
#   화면에 보이는 값은 항상 app.js 가 사용자 설정으로 다시 계산한다.
#   한쪽을 고치면 반드시 다른 쪽도 같이 고쳐야 한다.

STRONG_PCT_DEFAULT = 30      # 강력 특가 기준: 평균 대비 몇 % 이상 저렴한가


def confidence(n):
    """표본 수 → 신뢰도. 표본이 적으면 가격이 싸도 강력 특가로 올리지 않는다."""
    if n >= 10:
        return "높음"
    if n >= 5:
        return "보통"
    if n >= 3:
        return "낮음"
    return "참고"


def deal_tier(pct, n, strong=STRONG_PCT_DEFAULT):
    """평균 대비 할인율 + 표본 수 → 특가 등급.

    strong / deal 은 표본 문턱을 함께 넘어야 한다. 표본 3건짜리 노선에서
    '평균보다 60% 싸다'는 말은 평균이 곧 그 3건이라는 뜻이라 근거가 못 된다.
    """
    if pct is None:
        return "unknown"
    if pct >= strong and n >= 10:
        return "strong"
    if pct >= 20 and n >= 5:
        return "deal"
    if pct >= 10 and n >= 3:
        return "candidate"
    if pct >= strong:            # 싸지만 표본이 모자라 확정 못 함
        return "candidate"
    return "normal"


TIER_LABEL = {"strong": "강력 특가", "deal": "특가",
              "candidate": "특가 후보", "normal": "일반",
              "unknown": "비교 불가"}


def deal_score(o, access=0, strong=STRONG_PCT_DEFAULT):
    """0~100. 정렬 보조용이며 화면에 숫자로 노출하지 않는다.

    할인율 40 · 과거 최저 근접 15 · 실부담 절대수준 15
    · 직항 10 · 신규 5 · 최근 하락 7 · 주말 적합 8
    합계에 표본 신뢰도 계수를 곱한다.
    """
    pct = o.get("discount_pct")
    if pct is None:
        return 0
    sc = max(0.0, min(pct / max(strong, 1), 1.0)) * 40

    lo = o.get("low_all")
    if lo:
        # 추적기간 최저와 같거나 낮으면 만점, 30% 위면 0점
        gap = (o["price_krw"] - lo) / lo
        sc += max(0.0, 1 - gap / 0.30) * 15

    base = REGION_BASE.get(o["region"], 300000)
    eff = o["price_krw"] + access
    sc += max(0.0, min((base - eff) / base, .5)) / .5 * 15

    st = o.get("stops")
    sc += 10 if st == 0 else (5 if st == 1 else 0)
    sc += AIRPORT_BONUS.get(o["dep"], 0)      # 편의성. 가격은 건드리지 않는다
    if o.get("change") == "new":
        sc += 5
    if o.get("change") == "down":
        sc += 7
    if o.get("weekend_trip"):
        sc += 8

    mult = {"높음": 1.0, "보통": .9, "낮음": .75}.get(
        confidence(o.get("baseline_n", 0)), .55)
    return round(min(sc * mult, 100))


def enrich(offers, baselines):
    """offer 에 기준선·할인율·등급을 붙인다.

    실부담가와 최종 점수는 여기서 확정하지 않는다. 교통비가 사용자 설정이라
    화면에서 다시 계산해야 하기 때문이다. 여기서는 교통비와 무관한 사실
    (기준선, 할인율, 표본, 신뢰도)까지만 확정한다.
    """
    for o in offers:
        bl, tier = pick_baseline(o, baselines)
        o["baseline_tier"] = tier
        o["baseline"] = bl["median"] if bl else None
        o["baseline_avg"] = bl["mean"] if bl else None
        o["baseline_n"] = bl["n"] if bl else 0
        o["confidence"] = confidence(o["baseline_n"])

        if o["baseline"]:
            # 평균가 대비 차액. 양수 = 그만큼 싸다, 음수 = 그만큼 비싸다.
            # 화면에서는 부호를 그대로 노출하지 않고 "저렴/비쌈"으로 바꿔 쓴다.
            o["diff_krw"] = o["baseline"] - o["price_krw"]
            o["discount_pct"] = round(o["diff_krw"] / o["baseline"] * 100, 1)
        else:
            o["diff_krw"] = o["discount_pct"] = None

        # 데이터 품질 — 등급이 아니라 "이 값을 믿을 수 있는가"
        if not o["roundtrip_verified"]:
            o["data_ok"], o["data_note"] = False, "왕복 총액 미확인"
        elif o["baseline"] is None:
            o["data_ok"], o["data_note"] = False, "비교할 표본 없음"
        else:
            o["data_ok"], o["data_note"] = True, None

        o["tier"] = deal_tier(o["discount_pct"], o["baseline_n"]) \
            if o["data_ok"] else "unknown"
        o["tier_label"] = TIER_LABEL[o["tier"]]

    bad = [o for o in offers if not o["data_ok"]]
    if offers and len(bad) == len(offers):
        reasons = {}
        for o in bad:
            reasons[o["data_note"]] = reasons.get(o["data_note"], 0) + 1
        top = max(reasons.items(), key=lambda x: x[1])
        print(f"\n⚠️  전체 {len(offers)}건이 비교 불가 → 브리프가 비게 됩니다.")
        print(f"    최다 사유: {top[0]} ({top[1]}건)")
        ERRORS.append(f"전건 비교 불가: {top[0]}")
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


def track_routes(offers, hist):
    """노선별 일자 최저가를 누적한다. 30일 최저·90일 그래프의 근거.

    price_history 의 deals 는 offer 단위(출발일까지 포함)라 노선 전체의
    시세 흐름을 못 본다. 노선 단위 일별 최저가를 따로 쌓는다.
    90일이 지난 것은 버린다 — 파일이 무한히 커지면 매 실행 커밋이 무거워진다.
    """
    daily = hist.get("route_daily", {})
    today = str(date.today())
    todays = {}
    for o in offers:
        k = f"{o['dep']}-{o['arr']}"
        p = o["price_krw"]
        if k not in todays or p < todays[k]:
            todays[k] = p
    for k, p in todays.items():
        daily.setdefault(k, {})[today] = p

    cut = str(date.today() - timedelta(days=90))
    for k in list(daily):
        kept = {d: p for d, p in daily[k].items() if d >= cut}
        if kept:
            daily[k] = kept
        else:
            del daily[k]
    hist["route_daily"] = daily
    return daily


def route_stats(offers, daily, lows):
    """노선별 집계. 용어를 여기서 한 번만 정의하고 화면은 그대로 쓴다.

      today_low  오늘 최저가      — 이번 스캔에서 가장 싼 값
      avg        노선 평균가      — 이번 스캔 평균
      low30      최근 30일 최저   — route_daily 30일 구간의 최저
      low_all    추적 기간 최저   — 추적 시작 이후 전체 최저
    """
    groups = {}
    for o in offers:
        groups.setdefault(f"{o['dep']}-{o['arr']}", []).append(o)

    c30 = str(date.today() - timedelta(days=30))
    out = {}
    for k, pool in groups.items():
        pr = sorted(p["price_krw"] for p in pool)
        h30 = {d: p for d, p in daily.get(k, {}).items() if d >= c30}
        rec = lows.get(k) or {}
        first = pool[0]
        out[k] = {
            "dep": first["dep"], "arr": first["arr"], "city": first["city"],
            "region": first["region"], "n": len(pr),
            "today_low": pr[0],
            "avg": int(statistics.fmean(pr)),
            "median": int(statistics.median(pr)),
            "low30": min(h30.values()) if h30 else None,
            "low30_date": min(h30, key=h30.get) if h30 else None,
            "low_all": rec.get("price"),
            "low_all_date": rec.get("date"),
            # 그래프용 일별 시계열 (오래된 것부터)
            "series": [{"d": d, "p": p} for d, p in sorted(daily.get(k, {}).items())],
        }
    return out


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
    return "전 출발지 + 스위스 · 상시", ["icn", "tae", "pus", "swiss"]


def brief_line(o):
    """브리프 한 줄. 항공권 실가격이 주 표기, 실부담가는 괄호 안 보조.

    설정이 없는 곳에서 읽히므로 기본 교통비(ACCESS_COST)로 계산한다.
    """
    access = ACCESS_COST.get(o["dep"], 0)
    eff = o["price_krw"] + access
    txt = (f"{o['city']} {o['dep']}→{o['arr']} · "
           f"{o['depart_date'][5:]}~{o['return_date'][5:]} {o['nights']}박 · "
           f"{o['price_krw']:,}원")
    if access:
        txt += f" (실부담 {eff:,})"
    pct = o.get("discount_pct")
    if pct is not None and pct > 0:
        txt += f" · 평균보다 {pct:.0f}% 저렴"
    elif pct is not None and pct < 0:
        txt += f" · 평균보다 {abs(pct):.0f}% 비쌈"
    if o.get("tier") in ("strong", "deal"):
        txt += f" · {o['tier_label']}"
    lv = o.get("annual_leave")
    if o.get("weekend_trip"):
        txt += f" · 주말 연차{lv:g}일"
    if o.get("holiday"):
        txt += f" · {o['holiday']}"
    if o.get("change") == "new":
        txt += "  🆕"
    elif o.get("change") == "down" and o.get("delta"):
        txt += f"  📉{o['delta']:+,}"
    lo = o.get("low_all")
    if lo and o["price_krw"] <= lo:
        txt += "  🔻추적기간 최저"
    return {"text": txt, "tier": o.get("tier"), "tier_label": o.get("tier_label"),
            "confidence": o.get("confidence"), "sample": o.get("baseline_n"),
            "price": o["price_krw"], "access": access, "effective": eff,
            "weekend_trip": bool(o.get("weekend_trip")),
            "leave": lv, "link": o["link"]}


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ══════════════════════════════════════════════════════════
# 산출물 — 화면이 읽는 단일 데이터 파일
# ══════════════════════════════════════════════════════════

# 화면에 필요한 필드만 골라 내보낸다. price_history 는 내부 상태라
# 그대로 노출하지 않는다 (파일이 커지고, 화면이 안 쓰는 필드까지 딸려간다).
OFFER_FIELDS = (
    "id dep arr city region depart_date return_date nights airline airline_kr "
    "stops price_krw link dep_hour ret_hour holiday weekend red_days "
    "annual_leave weekend_trip night_departure roundtrip_verified "
    "baseline baseline_avg baseline_n baseline_tier confidence diff_krw "
    "discount_pct data_ok data_note tier tier_label deal_score "
    "low30 low_all route_avg change delta first_seen last_seen price_log"
).split()


def write_deals(offers, routes, meta, stats, gone, cjj_status=None):
    """web/ 앱이 읽는 deals.json.

    실부담가·최종 정렬은 여기서 굳히지 않는다. 교통비가 사용자 설정이라
    화면에서 계산해야 하기 때문이다. 기본 교통비는 같이 실어 보낸다.
    """
    out = {
        "schema": 2,
        "meta": meta,
        "stats": stats,
        "home": HOME,
        "access_cost_default": ACCESS_COST,
        "airlines": AIRLINES,
        "holidays": HOLIDAYS,
        "region_base": REGION_BASE,
        "routes": routes,
        "cjj": {
            "config": {k: v for k, v in CJJ_ROUTES.items()},
            "status": cjj_status or [],
            "flex": list(CJJ_FLEX), "window": list(CJJ_WINDOW),
        },
        "airport_bonus": AIRPORT_BONUS,
        "tie_break_krw": TIE_BREAK_KRW,
        "offers": [{k: o.get(k) for k in OFFER_FIELDS} for o in offers],
        "gone": [{k: g.get(k) for k in
                  ("id", "dep", "arr", "city", "depart_date", "return_date",
                   "nights", "price_krw", "last_seen")} for g in gone[:40]],
    }
    p = os.path.join(ROOT, "state", "deals.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="원본 응답 덤프 후 종료")
    ap.add_argument("--all", action="store_true",
                    help="priority 무시하고 CJJ 전 노선까지 조회")
    ap.add_argument("--cjj", action="store_true",
                    help="청주 노선만 조회 (다른 출발지·스위스 건너뜀)")
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

    # --raw 단독은 API 응답 구조 프로브, --cjj --raw 는 청주 단계별 debug 다.
    if args.raw and not args.cjj:
        probe_raw()
        return

    rot_name, groups = rotation()
    print(f"▶ {date.today()} · {rot_name} · 홈 {HOME}")
    if not CJJ_ROUTES:
        ERRORS.append("config/cjj_routes.json 을 읽지 못해 청주 스캔을 건너뜀")

    # 공휴일 표가 검색창을 못 덮으면 연차 계산이 조용히 틀린다. 반드시 알린다.
    horizon = date.today() + timedelta(days=WINDOW_MAX)
    holiday_gap = str(horizon) > HOLIDAY_MAX
    if holiday_gap:
        msg = (f"공휴일 표가 {HOLIDAY_MAX} 까지만 있음 "
               f"(검색창은 {horizon} 까지) → 그 이후 일정의 연차 계산이 부정확")
        print(f"⚠️  {msg}")
        ERRORS.append(msg)

    # 청주는 전용 스캐너가 노선별로 직접 물어본다 (캐시가 얇아 전체 훑기가 안 됨)
    offers, cjj_status = scan_cjj(force_all=args.all, debug=args.raw)

    if args.cjj:
        targets = []
        print("\n▶ --cjj: 다른 출발지와 스위스는 건너뜁니다")
    else:
        targets = []
        for g in groups:
            targets += SWISS if g == "swiss" else ROUTES.get(g, [])
        seen = set()
        targets = [t for t in targets if not (t[:2] in seen or seen.add(t[:2]))]

    for org, dst, city, region in targets:
        if region == "유럽":
            got, stop = fetch_route(org, dst, city, region,
                                    flex=SWISS_NIGHTS, window=SWISS_WINDOW)
        else:
            pf = profile(org)
            got, stop = fetch_route(org, dst, city, region,
                                    pf["nights"], window=pf["window"])
        tag = {"BUDGET_EXCEEDED": "  ⛔예산소진",
               "CIRCUIT_OPEN": "  ⛔중단"}.get(stop, "")
        key = f"{org}-{dst}"
        rawn = RAWCOUNT.get(key, 0)
        why = ""
        if not got and rawn:
            d = DROPS.get(key, {})
            why = "  ← " + ", ".join(f"{k} {v}" for k, v in
                                     sorted(d.items(), key=lambda x: -x[1])[:3])
        print(f"  {org}→{dst} {len(got):>4}건 (원본 {rawn}){tag}{why}")
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

    # 기준선을 만들기 전에 과거 표본을 먼저 확보한다 (얇은 버킷 보강)
    hist = load(os.path.join(ROOT, "state", "price_history.json"), {"deals": {}})
    thin = track_samples(offers, hist)
    baselines = build_baselines(offers, thin)
    offers = enrich(offers, baselines)

    lows = track_lows(offers, hist)
    daily = track_routes(offers, hist)
    stats, gone = diff(offers, hist)

    # 노선 집계를 offer 에 되먹인다 (30일/추적기간 최저는 점수와 화면 양쪽에 쓰인다)
    routes = route_stats(offers, daily, lows)
    for o in offers:
        r = routes.get(f"{o['dep']}-{o['arr']}", {})
        o["low30"] = r.get("low30")
        o["low_all"] = r.get("low_all")
        o["route_avg"] = r.get("avg")
    for o in offers:
        o["deal_score"] = deal_score(o, ACCESS_COST.get(o["dep"], 0))

    meta = {"date": str(date.today()),
            "ts": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "rotation": rot_name, "used": BUDGET.used, "cap": BUDGET.cap,
            "count": len(offers), "home": HOME,
            "holiday_gap": HOLIDAY_MAX if holiday_gap else None,
            "window": [WINDOW_MIN, WINDOW_MAX],
            "nights": [NIGHTS[0], NIGHTS[-1]],
            "swiss_nights": list(SWISS_NIGHTS),
            "swiss_window": list(SWISS_WINDOW),
            "strong_pct_default": STRONG_PCT_DEFAULT,
            "direct_only": sorted(DIRECT_ONLY),
            "origin_profile": {k: {"window": list(v["window"]),
                                   "nights": list(v["nights"])}
                               for k, v in ORIGIN_PROFILE.items()},
            "thin_sample": THIN_SAMPLE,
            "thin_retention": dict(HISTORY_WINDOW,
                                   **{"기본": HISTORY_WINDOW_DEFAULT}),
            "pooled_buckets": {f"{d}-{a}-{nn}": v
                               for (d, a, nn), v in baselines["pooled"].items()},
            "errors": ERRORS[:30],
            "raw_counts": RAWCOUNT,
            "drops": DROPS}

    write_deals(offers, routes, meta, stats, gone, cjj_status)

    # ── 아침 브리프용 요약 (설정 없이 읽히는 파일) ──
    ok = [o for o in offers if o["data_ok"]]
    by_score = sorted(ok, key=lambda x: -(x.get("deal_score") or 0))
    strong = [o for o in ok if o["tier"] == "strong"]
    top = by_score[:3]
    wk = [o for o in by_score if o.get("weekend_trip")][:3]
    home = [o for o in by_score if o["dep"] == HOME][:3]
    swiss = sorted([o for o in offers if o["region"] == "유럽"],
                   key=lambda x: x["price_krw"])[:3]

    degraded = None
    if CIRCUIT.tripped:
        status, headline = "FAILED", f"스캔 실패 — {CIRCUIT.cause}"
    elif not ok:
        status, headline = "PARTIAL", "비교 가능한 항공권이 없습니다"
        notes = {}
        for o in offers:
            notes[o["data_note"]] = notes.get(o["data_note"], 0) + 1
        if notes:
            top_reason, cnt = max(notes.items(), key=lambda x: x[1])
            degraded = f"{top_reason} ({cnt}건)"
    else:
        bits = [f"볼 것 {len(ok)}건"]
        if strong:        bits.append(f"강력특가 {len(strong)}")
        if wk:            bits.append(f"주말여행 {len(wk)}")
        if home:          bits.append(f"{HOME} {len(home)}")
        if stats["new"]:  bits.append(f"신규 {stats['new']}")
        if stats["down"]: bits.append(f"하락 {stats['down']}")
        status, headline = "OK", " · ".join(bits)

    brief = {
        "date": meta["date"], "ts": meta["ts"], "status": status,
        "headline": headline, "home": HOME,
        "reason": CIRCUIT.cause if CIRCUIT.tripped else None,
        "degraded": degraded,
        "holiday_gap": meta["holiday_gap"],
        "counts": {
            "total": len(offers), "comparable": len(ok),
            "strong": len(strong),
            "deal": sum(1 for o in ok if o["tier"] == "deal"),
            "candidate": sum(1 for o in ok if o["tier"] == "candidate"),
            "weekend": sum(1 for o in ok if o.get("weekend_trip")),
            "home": sum(1 for o in ok if o["dep"] == HOME), **stats},
        "source_note": "Travelpayouts 캐시 데이터 · 실시간 확정가 아님",
        "access_note": f"실부담가 = 항공권 + {HOME} 기준 왕복 교통비 (추정치)",
        "top": [brief_line(o) for o in top],
        "weekend": [brief_line(o) for o in wk],
        "home_airport": [brief_line(o) for o in home],
        "swiss": [brief_line(o) for o in swiss],
        "dashboard": "index.html",
    }
    with open(os.path.join(ROOT, "state", "brief.json"), "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=1)

    hist["last_run"] = meta["ts"]
    hist["deals"] = {o["id"]: o for o in offers}
    with open(os.path.join(ROOT, "state", "price_history.json"), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)

    tiers = {t: sum(1 for o in offers if o["tier"] == t)
             for t in ("strong", "deal", "candidate", "normal", "unknown")}
    with open(os.path.join(ROOT, "logs", f"run-{date.today()}.md"), "w", encoding="utf-8") as f:
        f.write(f"# 실행 {meta['ts']}\n\n"
                f"검색: {BUDGET.used}/{BUDGET.cap}\n수집: {len(offers)}건\n\n"
                f"강력특가 {tiers['strong']} · 특가 {tiers['deal']} · "
                f"후보 {tiers['candidate']} · 일반 {tiers['normal']} · "
                f"비교불가 {tiers['unknown']}\n\n"
                f"🆕 {stats['new']} · 📉 {stats['down']} · 📈 {stats['up']} · "
                f"⚰️ {stats['gone']}\n\n"
                + ("## 오류\n" + "\n".join(f"- {e}" for e in ERRORS[:30])
                   if ERRORS else ""))

    pooled_n = len(baselines["pooled"])
    for org in sorted(DIRECT_ONLY):
        got = [o for o in offers if o["dep"] == org]
        ok = [o for o in got if o["data_ok"]]
        print(f"   {org}: {len(got)}건 (직항만) · 비교가능 {len(ok)}건")
    print(f"   누적 표본으로 기준선을 세운 버킷 {pooled_n}개 "
          f"(CJJ 90일 · TAE·PUS 45일 · 그 외 {HISTORY_WINDOW_DEFAULT}일)")

    print(f"\n✅ 완료 · 수집 {len(offers)}건 · 검색 {BUDGET.used}/{BUDGET.cap}")
    print(f"   🔥강력특가 {tiers['strong']} / 특가 {tiers['deal']} / "
          f"후보 {tiers['candidate']} / 일반 {tiers['normal']} / "
          f"비교불가 {tiers['unknown']}")
    print(f"   🆕{stats['new']} 📉{stats['down']} 📈{stats['up']} ⚰️{stats['gone']}")
    if ERRORS:
        print(f"   ⚠️ 오류 {len(ERRORS)}건 — 로그 확인")
    print(f"\n   → {os.path.join(ROOT, 'state', 'deals.json')}")


if __name__ == "__main__":
    main()
