"""여러 provider 결과를 하나로 합친다.

같은 항공편이 provider 마다 다른 가격으로 온다. 실제로 예약 조건이 다를
수 있으므로(수하물·환불 규정·판매처) 최저가만 남기고 나머지를 버리지
않는다. 대표값 하나를 고르되, 어디서 얼마였는지는 sources[] 에 남긴다.

대표를 고르는 기준은 '가격' 이 아니라 '신뢰도' 다.
  실제 예약 가능한 offer(Duffel) > 실시간 메타서치 > 캐시
싼 캐시값이 실시간 확정가를 밀어내면, 눌렀을 때 없는 가격을 보여주게 된다.
"""

from datetime import datetime

from .normalize import day, trip_stops, source_priority


def _offset_min(ts):
    """'+09:00' → 540, '-05:30' → -330, 'Z' → 0. 없으면 None."""
    if not isinstance(ts, str):
        return None
    if ts.endswith("Z") and len(ts) >= 20:
        return 0
    if len(ts) >= 25 and ts[19] in "+-" and ts[20:22].isdigit() and ts[23:25].isdigit():
        v = int(ts[20:22]) * 60 + int(ts[23:25])
        return v if ts[19] == "+" else -v
    return None


def _when(ts):
    """출발 시각을 비교 가능한 하나의 값으로.

    ★ 시각은 **순간(instant)** 으로 비교한다. provider 마다 타임존 표기가
      달라 같은 편이 '2026-10-29T13:05+09:00' 과 '2026-10-29T04:05Z' 로
      온다. 날짜와 시각을 따로 문자열 비교하면 같은 편이 둘로 갈라지고,
      자정을 넘으면 날짜까지 어긋난다.

      오프셋이 있으면 UTC 순간으로 환산하고, 없으면 원문을 그대로 쓴다.
      한쪽만 오프셋이 있으면 키가 달라 합쳐지지 않는다 — 모르는 것을
      같다고 보지 않는 쪽이 안전하다.
    """
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    d = day(ts)
    if not d:
        return None
    if len(ts) < 16 or ts[10] not in "T ":
        return "D" + d                      # 날짜만 있는 값
    hh, mm = ts[11:13], ts[14:16]
    if not (hh.isdigit() and mm.isdigit()):
        return "D" + d
    off = _offset_min(ts)
    if off is None:
        return "L" + d + "T" + ts[11:16]    # 오프셋 없음 — 원문 그대로
    epoch = (datetime.strptime(d, "%Y-%m-%d") - datetime(1970, 1, 1)).days * 1440
    return "U%d" % (epoch + int(hh) * 60 + int(mm) - off)


def _seg_sig(o):
    """구간이 있으면 구간으로 여정을 식별한다. 이게 가장 확실하다."""
    segs = o.get("segments")
    if not segs:
        return None
    try:
        return tuple((s.get("from"), s.get("to"), (s.get("at") or "")[:16],
                      (s.get("flight_no") or "").upper()) for s in segs)
    except (AttributeError, TypeError):
        return None


def dedupe_key(o):
    """같은 여정으로 볼 기준.

    ★ 예전에는 (출발지, 도착지, 출발일, 귀국일, 항공사, 환승횟수) 뿐이었다.
      편명도 출발 시각도 안 봐서, 같은 날 같은 항공사의 오전편과 오후편이
      한 건으로 합쳐졌다 (KE701 08:00 과 KE705 19:00 → 1건). 실측 재현.

    순서대로 본다.
      1) segments 가 있으면 구간별 공항·시각·편명 — 가장 확실하다
      2) 없으면 편명 + 출발/귀국 순간까지 본다
      3) 편명도 시각도 없으면 합치지 않는다. 모르는 것을 같다고 보면
         서로 다른 편이 사라진다.
    """
    base = (o["dep"], o["arr"], _when(o["departure_at"]), _when(o.get("return_at")),
            (o.get("airline") or "?").upper(), trip_stops(o),
            (o.get("cabin") or None))

    seg = _seg_sig(o)
    if seg:
        return ("seg",) + base + (seg,)

    fno = (o.get("flight_no") or "").strip().upper() or None
    has_time = isinstance(o.get("departure_at"), str) and len(o["departure_at"]) >= 16
    if fno or has_time:
        return ("id",) + base + (fno,)

    # 식별할 게 아무것도 없다. 합치지 않는다.
    return ("solo", id(o))


def merge_offers(offers):
    """공통 Offer 리스트 → 중복 제거된 리스트.

    반환 항목에는 sources[] 와 best_price 가 붙는다. 기존 스키마를 깨지
    않도록 '추가' 만 한다.
    """
    groups = {}
    for o in offers:
        # 같은 여정이라도 수하물·환불·판매처가 다르면 다른 상품이다.
        # 한 줄로 합쳐 놓고 싼 쪽 가격에 비싼 쪽 조건을 붙이면 안 된다.
        fare = (o.get("baggage"), o.get("refundable"), o.get("fare_brand"))
        groups.setdefault((dedupe_key(o), fare), []).append(o)

    out = []
    for (_k, _fare), rows in groups.items():
        # 신뢰도 우선, 같으면 싼 쪽
        rows = sorted(rows, key=lambda r: (-source_priority(r["source"]),
                                           r["price"] if r["price"] else 1 << 40))
        rep = dict(rows[0])
        # ★ 교차검증이 "같은 조건인가" 를 판단하려면 조건도 같이 실어야
        #   한다. 가격만 넘기면 화면은 숫자 두 개밖에 못 본다.
        #   booking_url·유효시각도 반드시 그 소스의 것을 그대로 가져간다 —
        #   다른 소스의 링크에 이 소스의 가격을 붙이면 없는 가격이 된다.
        rep["sources"] = [{"source": r["source"], "price": r["price"],
                           "currency": r.get("currency"),
                           "live": r.get("live"),
                           "confidence": r.get("source_confidence"),
                           "found_at": r.get("found_at"),
                           "cabin": r.get("cabin"), "pax": r.get("pax"),
                           "tax_included": r.get("tax_included"),
                           "baggage": r.get("baggage"),
                           "refundable": r.get("refundable"),
                           "fare_brand": r.get("fare_brand"),
                           "roundtrip": bool(r.get("return_at")),
                           "price_valid_until": r.get("price_valid_until"),
                           "booking_url": r.get("booking_url"),
                           "flight_no": r.get("flight_no")} for r in rows]
        prices = [r["price"] for r in rows if r.get("price")]
        rep["best_price"] = min(prices) if prices else rep.get("price")
        # 이름 없는 행이 섞여 있으면 이름 있는 쪽 정보를 채운다.
        # 값을 조합하지는 않는다 — 대표 가격은 대표 행의 것 그대로다.
        if rep.get("airline") in (None, "?"):
            named = next((r for r in rows if r.get("airline") not in (None, "?")), None)
            if named:
                rep["airline"] = named["airline"]
                rep["flight_no"] = rep.get("flight_no") or named.get("flight_no")
        out.append(rep)
    return out


def merge_stats(before, after):
    return {"input": len(before), "duplicates": len(before) - len(after),
            "final": len(after)}
