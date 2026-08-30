"""여러 provider 결과를 하나로 합친다.

같은 항공편이 provider 마다 다른 가격으로 온다. 실제로 예약 조건이 다를
수 있으므로(수하물·환불 규정·판매처) 최저가만 남기고 나머지를 버리지
않는다. 대표값 하나를 고르되, 어디서 얼마였는지는 sources[] 에 남긴다.

대표를 고르는 기준은 '가격' 이 아니라 '신뢰도' 다.
  실제 예약 가능한 offer(Duffel) > 실시간 메타서치 > 캐시
싼 캐시값이 실시간 확정가를 밀어내면, 눌렀을 때 없는 가격을 보여주게 된다.
"""

from .normalize import day, trip_stops, source_priority


def dedupe_key(o):
    """같은 항공편으로 볼 기준.

    시각까지 쓰지 않고 날짜로 자른다. provider 마다 타임존 표기가 달라
    시각을 그대로 비교하면 같은 편이 갈라진다.
    """
    return (o["dep"], o["arr"], day(o["departure_at"]), day(o.get("return_at")),
            (o.get("airline") or "?").upper(), trip_stops(o))


def merge_offers(offers):
    """공통 Offer 리스트 → 중복 제거된 리스트.

    반환 항목에는 sources[] 와 best_price 가 붙는다. 기존 스키마를 깨지
    않도록 '추가' 만 한다.
    """
    groups = {}
    for o in offers:
        groups.setdefault(dedupe_key(o), []).append(o)

    out = []
    for _k, rows in groups.items():
        # 신뢰도 우선, 같으면 싼 쪽
        rows = sorted(rows, key=lambda r: (-source_priority(r["source"]),
                                           r["price"] if r["price"] else 1 << 40))
        rep = dict(rows[0])
        rep["sources"] = [{"source": r["source"], "price": r["price"],
                           "live": r.get("live"),
                           "confidence": r.get("source_confidence"),
                           "found_at": r.get("found_at")} for r in rows]
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
