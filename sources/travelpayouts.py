"""Travelpayouts 를 provider 인터페이스로 감싼다.

★ 수집 로직을 새로 쓰지 않는다.
   scanner.py 의 fetch_route() 를 그대로 부른다. 캘린더 → latest → 3차
   소스 → v3 로 이어지는 단계, 예산, 서킷브레이커, 편도 격리, 단계별
   계측이 전부 거기 붙어 있다. 여기서 다시 구현하면 두 벌이 되고,
   기존 결과와 달라진다.

   그래서 이 클래스는 "이미 있는 것을 provider 모양으로 보이게" 할 뿐이다.
   기존 동작이 바뀌지 않는 것이 이 파일의 성공 조건이다.

fetch_route 는 import 하지 않고 주입받는다. scanner 가 sources 를 import
하는데 sources 가 scanner 를 import 하면 순환이 된다.
"""

from .base import Provider


class TravelpayoutsProvider(Provider):
    name = "travelpayouts"
    env_key = None                    # 토큰 확인은 scanner 가 이미 한다

    def __init__(self, fetch_route, rawcount=None):
        super().__init__(token="managed-by-scanner")
        self._fetch_route = fetch_route
        self._rawcount = rawcount if rawcount is not None else {}
        self.stops = []               # BUDGET_EXCEEDED / CIRCUIT_OPEN 기록

    def _search(self, req):
        """기존 legacy offer dict 를 그대로 돌려준다.

        공통 Offer 로 변환하지 않는다 — Travelpayouts 결과는 이미
        scanner.normalize() 를 통과해 전체 필드를 갖춘 상태이고, 그걸
        되돌렸다가 다시 만들면 정보만 잃는다. 다른 provider 결과가
        scanner 쪽으로 들어올 때만 변환이 필요하다.
        """
        kwargs = {"window": req.window, "latest": True}
        if req.nights:
            kwargs["flex"] = req.nights
        got, stop = self._fetch_route(req.dep, req.arr, req.city, req.region,
                                      **kwargs)
        self.calls += 1
        if stop:
            self.stops.append(stop)
        key = f"{req.dep}-{req.arr}"
        self.rows_raw = self._rawcount.get(key, 0)
        return got

    def valid_rows(self, offers):
        """가격이 확인된 왕복 건수. fallback 판단은 이 수로 한다.

        단순 row 수가 아니라 '쓸 수 있는 값' 을 센다. 원본 20건이 와도
        전부 편도면 왕복 가격은 0건이다.
        """
        return sum(1 for o in offers
                   if o.get("price_krw") and o.get("roundtrip_verified"))
