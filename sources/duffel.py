"""Duffel provider — 실제 예약 가능한 offer 를 준다.

캐시가 아니라 항공사·GDS 에서 그 순간 조회한 값이라 source_confidence 는 A다.
대신 비싸고 느리다: 한 번 호출에 (가는 날, 오는 날) 한 쌍만 조회된다.
그래서 날짜를 무작정 훑지 않고 seed 날짜만 찍는다 (SEED_STEP 참고).

토큰이 없으면 조용히 꺼진다. 이 provider 가 없다고 스캔이 실패하지 않는다.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from core.normalize import make_offer, day
from .base import Provider

API = "https://api.duffel.com/air/offer_requests"
DUFFEL_VERSION = "v2"
TIMEOUT = 40
REQ_SLEEP = 0.6

# 날짜 폭발 방지 (§10). 모든 날짜 조합을 조회하면 호출량이 감당이 안 된다.
# 주 단위 seed 를 먼저 찍고, 좋은 값이 나온 구간만 ±SPREAD 로 넓힌다.
SEED_STEP = 7          # 며칠 간격으로 출발일 seed 를 찍나
SEED_MAX = 8           # seed 최대 개수
SPREAD = 2             # 좋은 구간 주변 ±며칠 확장
EXPAND_PCT = 0.85      # 현재까지 최저가의 이 비율 이하이면 '좋은 구간'

FX_CONFIG = os.path.join(os.getcwd(), "config", "fx.json")


def load_fx():
    try:
        with open(FX_CONFIG, encoding="utf-8") as f:
            return json.load(f).get("rates") or {"KRW": 1}
    except Exception:
        return {"KRW": 1}


class DuffelProvider(Provider):
    name = "duffel"
    env_key = "DUFFEL_TOKEN"

    def __init__(self, token=None, fx=None, http=None):
        super().__init__(token)
        self.fx = fx if fx is not None else load_fx()
        self._http = http               # 테스트에서 주입
        self.dropped_fx = 0

    # ── HTTP ─────────────────────────────────────────────
    def _post(self, body):
        self.calls += 1
        if self._http:
            return self._http(body)
        req = urllib.request.Request(
            API + "?return_offers=true",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}",
                     "Duffel-Version": DUFFEL_VERSION,
                     "Content-Type": "application/json",
                     "Accept": "application/json",
                     "Accept-Encoding": "gzip"},
            method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))

    # ── 변환 ─────────────────────────────────────────────
    def _to_krw(self, amount, currency):
        """환율표에 없는 통화는 버린다. 지어내지 않는다."""
        try:
            v = float(amount)
        except (TypeError, ValueError):
            return None, None
        rate = self.fx.get((currency or "").upper())
        if not rate:
            self.dropped_fx += 1
            return None, None
        return int(round(v * rate)), (None if (currency or "").upper() == "KRW"
                                      else {"from": currency, "rate": rate})

    def _offer(self, row):
        slices = row.get("slices") or []
        if not slices:
            return None
        out_seg = slices[0].get("segments") or []
        back_seg = (slices[1].get("segments") or []) if len(slices) > 1 else []
        if not out_seg:
            return None
        price, fx = self._to_krw(row.get("total_amount"), row.get("total_currency"))
        if price is None:
            return None
        owner = (row.get("owner") or {}).get("iata_code")
        o = make_offer(
            self.name, out_seg[0].get("origin", {}).get("iata_code"),
            out_seg[-1].get("destination", {}).get("iata_code"),
            out_seg[0].get("departing_at"), price,
            return_at=(back_seg[0].get("departing_at") if back_seg else None),
            airline=owner or (out_seg[0].get("marketing_carrier") or {}).get("iata_code"),
            flight_no=(out_seg[0].get("marketing_carrier_flight_number")),
            # 세그먼트 수 - 1 = 환승 횟수. 여기서는 셀 수 있다.
            outbound_stops=len(out_seg) - 1,
            return_stops=(len(back_seg) - 1) if back_seg else None,
            booking_url=None, live=True,
            found_at=row.get("created_at"))
        if fx:
            o["fx"] = fx
        return o

    # ── seed 날짜 ────────────────────────────────────────
    def _seed_pairs(self, req):
        if req.seed_dates:
            return list(req.seed_dates)[:SEED_MAX]
        lo, hi = req.window
        n_lo, n_hi = req.nights
        stay = max(n_lo, min(n_hi, (n_lo + n_hi) // 2))   # 중앙값 박수 하나로 시작
        out, d = [], lo
        while d <= hi - stay and len(out) < SEED_MAX:
            d0 = date.today() + timedelta(days=d)
            out.append((str(d0), str(d0 + timedelta(days=stay))))
            d += SEED_STEP
        return out

    def _search_pair(self, req, dep_day, ret_day):
        body = {"data": {
            "slices": [
                {"origin": req.dep, "destination": req.arr,
                 "departure_date": dep_day},
                {"origin": req.arr, "destination": req.dep,
                 "departure_date": ret_day},
            ],
            "passengers": [{"type": "adult"}],
            "cabin_class": req.cabin or "economy",
        }}
        if req.max_stops is not None:
            body["data"]["max_connections"] = int(req.max_stops)
        data = self._post(body)
        time.sleep(REQ_SLEEP)
        rows = ((data or {}).get("data") or {}).get("offers") or []
        if not isinstance(rows, list):
            return []
        got = []
        for r in rows:
            o = self._offer(r)
            if o:
                got.append(o)
        return got

    def _search(self, req):
        budget = req.budget if req.budget is not None else SEED_MAX + 6
        out, best = [], None
        pairs = self._seed_pairs(req)
        good = []
        for d0, d1 in pairs:
            if self.calls >= budget:
                break
            got = self._search_pair(req, d0, d1)
            out += got
            if got:
                lo = min(o["price"] for o in got)
                if best is None or lo < best:
                    best = lo
                # 좋은 구간만 나중에 넓힌다 (§10)
                if best and lo <= best / EXPAND_PCT * EXPAND_PCT:
                    good.append((d0, d1, lo))
        # 최저가 구간 ±SPREAD 확장
        good.sort(key=lambda x: x[2])
        for d0, d1, lo in good[:2]:
            if best and lo > best / EXPAND_PCT:
                continue
            for off in range(-SPREAD, SPREAD + 1):
                if off == 0 or self.calls >= budget:
                    continue
                a = str(date.fromisoformat(d0) + timedelta(days=off))
                b = str(date.fromisoformat(d1) + timedelta(days=off))
                out += self._search_pair(req, a, b)
        return out
