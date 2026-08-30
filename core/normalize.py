"""공통 Offer 모델.

provider 마다 응답 모양이 다르다. 그 차이를 여기서 흡수하고, 아래쪽
(가격 평가·점수·기록)에는 한 가지 모양만 넘긴다.

★ 중요 — source_confidence 와 가격 등급은 다른 축이다.
   source_confidence : 이 값을 얼마나 믿을 수 있나 (실시간이냐 캐시냐)
   deal tier         : 이 값이 싸냐 (강력특가/특가/후보/일반)
   둘을 한 등급으로 섞지 않는다. 실시간으로 확인된 비싼 표가 있고,
   사흘 된 캐시에 찍힌 싼 값이 있다. 서로 다른 이야기다.
"""

from datetime import datetime

# ── source confidence ────────────────────────────────────
# A: 예약 가능한 실제 offer (provider 가 그 가격으로 팔겠다고 응답한 것)
# B: 실시간 메타서치 결과 또는 최근 캐시
# C: 오래됐거나 출처가 불확실한 값
CONF_A, CONF_B, CONF_C = "A", "B", "C"

SOURCE_META = {
    # source        : (기본 confidence, live 여부, 병합 우선순위 — 클수록 우선)
    "duffel":        (CONF_A, True, 30),
    "skyscanner":    (CONF_B, True, 20),
    "travelpayouts": (CONF_B, False, 10),
}
UNKNOWN_META = (CONF_C, False, 0)


def source_priority(source):
    return SOURCE_META.get(source, UNKNOWN_META)[2]


def make_offer(source, dep, arr, departure_at, price, currency="KRW", *,
               return_at=None, airline=None, outbound_stops=None,
               return_stops=None, booking_url=None, found_at=None,
               live=None, confidence=None, duration_min=None,
               duration_rt_min=None, flight_no=None, raw=None):
    """provider 응답 한 건 → 공통 Offer.

    필수는 source/dep/arr/departure_at/price 뿐이다. 나머지를 못 주는
    provider 가 있어도 None 으로 남긴다 — 모르는 값을 지어내지 않는다.
    """
    conf, dflt_live, _ = SOURCE_META.get(source, UNKNOWN_META)
    return {
        "source": source,
        "dep": dep,
        "arr": arr,
        "departure_at": departure_at,
        "return_at": return_at,
        "price": int(price) if price is not None else None,
        "currency": currency,
        "airline": airline or "?",
        "flight_no": flight_no,
        "outbound_stops": outbound_stops,
        "return_stops": return_stops,
        "booking_url": booking_url,
        "live": dflt_live if live is None else bool(live),
        "found_at": found_at,
        "source_confidence": confidence or conf,
        "duration_min": duration_min,
        "duration_rt_min": duration_rt_min,
        "_raw": raw,
    }


def day(ts):
    """'2026-11-08T13:05:00+09:00' → '2026-11-08'. 실패하면 None."""
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    d = ts[:10]
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        return None
    return d


def nights_between(dep_at, ret_at):
    """실제 체류 박수. 둘 중 하나라도 없으면 None (편도이거나 미확인)."""
    a, b = day(dep_at), day(ret_at)
    if not a or not b:
        return None
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def trip_stops(o):
    """이 여정의 환승 횟수 — **편도 기준 최대값**이다. 합이 아니다.

    ★ 여기서 한 번 틀렸다. 가는 편 1회 + 오는 편 1회를 더해 2로 세면,
      "1회 환승" 왕복이 max_stops=1 필터에 걸려 통째로 사라진다.
      사용자가 스크린샷으로 보여준 에티하드 편이 정확히 그것이었다
      (가는 편 1 layover, 오는 편 1 layover = 우리가 찾던 그 표).

    화면 표기("1회 환승")도, Travelpayouts 의 number_of_changes 도 편도
    기준이다. 여기에 맞춘다. 왕복 합이 필요하면 sum_stops() 를 쓴다.
    """
    a, b = o.get("outbound_stops"), o.get("return_stops")
    vals = [v for v in (a, b) if v is not None]
    if not vals:
        return None
    return max(vals)


def sum_stops(o):
    """왕복 전체 환승 횟수의 합. 표시용이 아니라 계산용."""
    a, b = o.get("outbound_stops"), o.get("return_stops")
    vals = [v for v in (a, b) if v is not None]
    return sum(vals) if vals else None


# 예전 이름 호환. 의미가 바뀌었으므로 새 코드는 trip_stops 를 쓴다.
total_stops = trip_stops


def legacy_key(o):
    """기존 scanner 의 offer dict 와 맞물리는 식별 키."""
    return (o["dep"], o["arr"], day(o["departure_at"]),
            day(o.get("return_at")), o.get("airline"), total_stops(o))


def to_legacy(o, city="", region=""):
    """공통 Offer → 기존 scanner 가 쓰는 dict 모양의 '씨앗'.

    기존 normalize() 가 만드는 전체 필드를 여기서 다 채우지 않는다.
    scanner 쪽 정규화 경로(trip_profile·연차·링크)를 그대로 태우기 위해
    그 함수가 먹는 입력 모양(v)으로 되돌려 준다. 로직 중복을 만들지 않는다.
    """
    return {
        "price": o["price"],
        "origin": o["dep"], "destination": o["arr"],
        "airline": o.get("airline") or "?",
        "flight_number": o.get("flight_no"),
        "departure_at": o["departure_at"],
        "return_at": o.get("return_at"),
        "number_of_changes": trip_stops(o),
        "duration_min": o.get("duration_min"),
        "duration_rt_min": o.get("duration_rt_min"),
        "found_at": o.get("found_at"),
        # provider 가 실제 구간을 준 경우. scanner 가 이걸 보고 추정 대신 확정으로 쓴다.
        "via_airports": o.get("via_airports"),
        "expires_at": None,
        # provider 꼬리표. scanner.normalize() 가 그대로 실어 보낸다.
        "source": o["source"],
        "source_confidence": o.get("source_confidence"),
        "live": o.get("live"),
        "booking_url": o.get("booking_url"),
    }
