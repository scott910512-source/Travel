"""커버리지 측정 및 A/B 비교.

전체 offer 수는 마지막 지표다. 그 앞에 더 중요한 것이 있다 (§14).
  1) CJJ 가격 0건 노선 수      — 줄어야 한다
  2) 가격 확인된 CJJ 목적지 수  — 늘어야 한다
  3) ICN-ZRH 유효 가격 row
  4) ICN-ZRH 직항 row
  5) 전체 offer

전체가 늘어도 1번이 그대로면 실패다. 그 판단을 사람 눈에 맡기지 않기 위해
숫자로 뽑는다.
"""

ZRH_KEY = ("ICN", "ZRH")


def _stops(o):
    s = o.get("stops")
    return s


def coverage(deals, cjj_status=None):
    """deals.json 모양(dict) 또는 offers 리스트에서 지표를 뽑는다."""
    if isinstance(deals, dict):
        offers = deals.get("offers") or []
        cjj = cjj_status or ((deals.get("cjj") or {}).get("status") or [])
    else:
        offers = deals or []
        cjj = cjj_status or []

    cjj_offers = [o for o in offers if o.get("dep") == "CJJ"]
    by_dst = {}
    for o in cjj_offers:
        if o.get("price_krw"):
            by_dst.setdefault(o["arr"], 0)
            by_dst[o["arr"]] += 1

    # 노선 목록은 status 가 있으면 그걸, 없으면 관측된 목적지로
    routes = [s["destination"] for s in cjj if s.get("route_status") != "inactive"] \
        if cjj else sorted(by_dst)
    zero = [c for c in routes if not by_dst.get(c)]

    zrh = [o for o in offers
           if (o.get("dep"), o.get("arr")) == ZRH_KEY and o.get("price_krw")]
    zrh_direct = [o for o in zrh if _stops(o) == 0]
    zrh_1stop = [o for o in zrh if _stops(o) == 1]

    return {
        "offers_total": len(offers),
        "cjj_valid_offers": sum(1 for o in cjj_offers if o.get("price_krw")),
        "cjj_routes_scanned": len(routes),
        "cjj_zero_routes": len(zero),
        "cjj_zero_list": sorted(zero),
        "cjj_priced_destinations": len(by_dst),
        "zrh_offers": len(zrh),
        "zrh_direct": len(zrh_direct),
        "zrh_1stop": len(zrh_1stop),
    }


ROWS = [
    ("전체 Offer", "offers_total", "up"),
    ("CJJ 전체 유효 Offer", "cjj_valid_offers", "up"),
    ("CJJ 가격 0건 노선", "cjj_zero_routes", "down"),
    ("CJJ 가격 확인 목적지", "cjj_priced_destinations", "up"),
    ("ICN-ZRH 유효 Offer", "zrh_offers", "up"),
    ("ICN-ZRH 직항", "zrh_direct", "up"),
    ("ICN-ZRH 1회 환승", "zrh_1stop", "up"),
]


def report(before, after, merge_info=None):
    """사람이 읽는 A/B 표. 좋아졌는지 나빠졌는지까지 표시한다."""
    L = ["===== DATA COVERAGE TEST =====",
         f"{'':<24}{'기존':>8}{'신규':>8}   변화"]
    for label, key, want in ROWS:
        b, a = before.get(key, 0), after.get(key, 0)
        d = a - b
        if d == 0:
            mark = "="
        elif (want == "up" and d > 0) or (want == "down" and d < 0):
            mark = f"↑ {d:+d}" if want == "up" else f"↓ {d:+d}"
        else:
            mark = f"⚠ {d:+d}"
        L.append(f"{label:<24}{b:>8}{a:>8}   {mark}")
    if merge_info:
        L.append(f"{'중복 제거 전':<24}{'-':>8}{merge_info.get('input', 0):>8}")
        L.append(f"{'중복 제거 후':<24}{'-':>8}{merge_info.get('final', 0):>8}")
    if before.get("cjj_zero_list") or after.get("cjj_zero_list"):
        L.append("")
        L.append(f"  0건 노선 기존: {', '.join(before.get('cjj_zero_list') or []) or '없음'}")
        L.append(f"  0건 노선 신규: {', '.join(after.get('cjj_zero_list') or []) or '없음'}")
    return "\n".join(L)


def verdict(before, after, targets=None):
    """§15 목표 대비 PASS / PARTIAL / FAIL."""
    t = targets or {}
    checks = [
        ("CJJ 0건 노선 감소", after["cjj_zero_routes"] < before["cjj_zero_routes"]
         or after["cjj_zero_routes"] <= t.get("cjj_zero_max", 2)),
        ("CJJ 가격 확인 목적지 +40%",
         after["cjj_priced_destinations"] >=
         before["cjj_priced_destinations"] * 1.4),
        ("ICN-ZRH 유효 20건 이상", after["zrh_offers"] >= t.get("zrh_offers", 20)),
        ("ICN-ZRH 직항 3건 이상", after["zrh_direct"] >= t.get("zrh_direct", 3)),
        ("ICN-ZRH 1회환승 10건 이상", after["zrh_1stop"] >= t.get("zrh_1stop", 10)),
    ]
    passed = sum(1 for _n, c in checks if c)
    status = "PASS" if passed == len(checks) else ("FAIL" if passed == 0 else "PARTIAL")
    return status, checks


def provider_log(stats, merge_info=None):
    L = ["[PROVIDERS]"]
    for name, s in stats.items():
        if s.get("skipped"):
            L.append(f"  {name:<15} disabled: {s['skipped']}")
            continue
        L.append(f"  {name:<15} calls: {s.get('calls', 0):<5} rows: {s.get('rows', 0)}")
        for e in (s.get("errors") or [])[:2]:
            L.append(f"  {'':<15} error: {e}")
    if merge_info:
        L += ["[MERGE]",
              f"  input: {merge_info.get('input', 0)}",
              f"  duplicates: {merge_info.get('duplicates', 0)}",
              f"  final: {merge_info.get('final', 0)}"]
    return "\n".join(L)


def cjj_coverage_log(per_route):
    """per_route: {code: {'tp': n, 'sky': n, 'final': n}}"""
    L = ["[CJJ COVERAGE]"]
    for code in sorted(per_route):
        v = per_route[code]
        L.append(f"  {code:<5} TP {v.get('tp', 0):>3}  SKY {v.get('sky', 0):>3}"
                 f"  FINAL {v.get('final', 0):>3}")
    return "\n".join(L)


def zrh_coverage_log(v):
    return ("[ZRH COVERAGE]\n"
            f"  TP     {v.get('tp', 0):>3}\n"
            f"  Duffel {v.get('duffel', 0):>3}\n"
            f"  Sky    {v.get('sky', 0):>3}\n"
            f"  Merged {v.get('merged', 0):>3}\n"
            f"  Direct {v.get('direct', 0):>3}\n"
            f"  1-stop {v.get('one_stop', 0):>3}")
