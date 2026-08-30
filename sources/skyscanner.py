"""Skyscanner 계열 provider — 인터페이스만 확정해 둔다.

공식 API access 가 없을 수 있어서, 구현체를 갈아끼울 수 있는 모양으로
만든다. 비공식 스크래핑을 여기에 하드코딩하지 않는다 — 그런 코드는
수명이 짧고, 한번 섞이면 걷어내기 어렵다.

동작 방식
  SKYSCANNER_API_KEY 있음  → _search() 가 실제 호출
  없음                     → provider 비활성, 스캔은 정상 진행

응답 파서(`parse_rows`)는 키와 무관하게 테스트할 수 있게 분리해 두었다.
실제 엔드포인트가 정해지면 `_fetch()` 만 바꾸면 된다.
"""

import json
import os
import time
import urllib.request

from core.normalize import make_offer
from .base import Provider

TIMEOUT = 40
REQ_SLEEP = 0.5

# 실제 계약에 따라 달라지는 부분. 환경변수로 바꿀 수 있게 둔다.
DEFAULT_HOST = os.environ.get("SKYSCANNER_API_HOST",
                              "https://partners.api.skyscanner.net")
DEFAULT_PATH = os.environ.get("SKYSCANNER_API_PATH",
                              "/apiservices/v3/flights/live/search/create")


def parse_rows(payload, dep, arr):
    """provider 응답 → 공통 Offer 리스트.

    Skyscanner v3 계열의 흔한 모양(itineraries/legs/carriers 사전 참조)을
    가정한다. 모양이 다르면 여기만 고치면 된다. 필수 값이 없는 행은
    지어내지 않고 버린다.
    """
    if not isinstance(payload, dict):
        return []
    content = payload.get("content") or payload
    results = content.get("results") or content
    itins = results.get("itineraries") or {}
    legs = results.get("legs") or {}
    carriers = results.get("carriers") or {}
    if isinstance(itins, list):
        itins = {str(i): v for i, v in enumerate(itins)}

    out = []
    for _iid, it in (itins or {}).items():
        opts = it.get("pricingOptions") or []
        if not opts:
            continue
        price = None
        url = None
        for op in opts:
            amt = ((op.get("price") or {}).get("amount"))
            if amt is None:
                continue
            try:
                v = int(float(amt))
            except (TypeError, ValueError):
                continue
            if price is None or v < price:
                price = v
                items = op.get("items") or []
                url = (items[0].get("deepLink") if items else None)
        if price is None:
            continue

        leg_ids = it.get("legIds") or []
        out_leg = legs.get(leg_ids[0]) if leg_ids else None
        back_leg = legs.get(leg_ids[1]) if len(leg_ids) > 1 else None
        if not out_leg:
            continue
        cid = (out_leg.get("marketingCarrierIds") or [None])[0]
        air = (carriers.get(str(cid)) or {}).get("iata") if cid else None
        out.append(make_offer(
            "skyscanner", out_leg.get("originPlaceId") or dep,
            out_leg.get("destinationPlaceId") or arr,
            out_leg.get("departureDateTime") or out_leg.get("departure"),
            price, currency=(content.get("currency") or "KRW"),
            return_at=(back_leg or {}).get("departureDateTime")
                      or (back_leg or {}).get("departure"),
            airline=air,
            outbound_stops=out_leg.get("stopCount"),
            return_stops=(back_leg or {}).get("stopCount") if back_leg else None,
            booking_url=url, live=True))
    return out


class SkyscannerProvider(Provider):
    name = "skyscanner"
    env_key = "SKYSCANNER_API_KEY"

    def __init__(self, token=None, http=None, host=None, path=None):
        super().__init__(token)
        self._http = http               # 테스트/대체 구현 주입점
        self.host = host or DEFAULT_HOST
        self.path = path or DEFAULT_PATH

    def _fetch(self, req, dep_day, ret_day):
        self.calls += 1
        if self._http:
            return self._http(req, dep_day, ret_day)
        body = {"query": {
            "market": "KR", "locale": "ko-KR", "currency": "KRW",
            "queryLegs": [
                {"originPlaceId": {"iata": req.dep},
                 "destinationPlaceId": {"iata": req.arr},
                 "date": _ymd(dep_day)},
            ],
            "cabinClass": "CABIN_CLASS_ECONOMY",
            "adults": 1,
        }}
        if ret_day:
            body["query"]["queryLegs"].append(
                {"originPlaceId": {"iata": req.arr},
                 "destinationPlaceId": {"iata": req.dep},
                 "date": _ymd(ret_day)})
        r = urllib.request.Request(
            self.host + self.path, data=json.dumps(body).encode("utf-8"),
            headers={"x-api-key": self.token, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _search(self, req):
        pairs = req.seed_dates or _default_pairs(req)
        budget = req.budget if req.budget is not None else len(pairs)
        out = []
        for d0, d1 in pairs:
            if self.calls >= budget:
                break
            payload = self._fetch(req, d0, d1)
            time.sleep(REQ_SLEEP)
            out += parse_rows(payload, req.dep, req.arr)
        return out


def _ymd(s):
    y, m, d = str(s)[:10].split("-")
    return {"year": int(y), "month": int(m), "day": int(d)}


def _default_pairs(req):
    from datetime import date, timedelta
    lo, hi = req.window
    n_lo, n_hi = req.nights
    stay = max(n_lo, min(n_hi, (n_lo + n_hi) // 2))
    out, d = [], lo
    while d <= hi - stay and len(out) < 6:
        d0 = date.today() + timedelta(days=d)
        out.append((str(d0), str(d0 + timedelta(days=stay))))
        d += 14
    return out
