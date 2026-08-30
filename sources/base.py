"""Provider 추상화.

핵심 규칙 두 가지.

1. provider 하나가 실패해도 전체 스캔은 계속된다.
   API 는 죽고, 느려지고, 모양이 바뀐다. 그때마다 데일리 스캔이 통째로
   실패하면 이 앱은 쓸모가 없다. 예외는 여기서 전부 잡아 격리한다.

2. 토큰이 없는 provider 는 조용히 꺼진다.
   부가 provider 의 토큰이 없다고 실패로 처리하지 않는다. 로그 한 줄만
   남기고 넘어간다.
"""

import os
import time
import traceback


class ProviderResult:
    """한 번의 provider 호출 결과. 실패해도 이 모양으로 돌아온다."""

    def __init__(self, source, offers=None, calls=0, error=None, skipped=None):
        self.source = source
        self.offers = offers or []
        self.calls = calls
        self.error = error
        self.skipped = skipped          # 꺼져 있는 이유 (토큰 없음 등)

    @property
    def ok(self):
        return self.error is None

    def __repr__(self):
        n = len(self.offers)
        if self.skipped:
            return f"<{self.source} skipped: {self.skipped}>"
        if self.error:
            return f"<{self.source} ERROR {self.error}>"
        return f"<{self.source} {n}건 / {self.calls}회>"


class Provider:
    """모든 provider 의 공통 뼈대."""

    name = "base"
    env_key = None           # 이 환경변수가 없으면 provider 를 끈다

    def __init__(self, token=None):
        self.token = token or (os.environ.get(self.env_key) if self.env_key else None)
        self.calls = 0
        self.errors = []
        self.rows = 0

    # ── 가용성 ────────────────────────────────────────────
    @property
    def enabled(self):
        return bool(self.token) if self.env_key else True

    def disabled_reason(self):
        if self.env_key and not self.token:
            return f"missing {self.env_key}"
        return None

    # ── 하위 클래스가 구현 ────────────────────────────────
    def _search(self, req):
        raise NotImplementedError

    # ── 외부에서 부르는 진입점 ────────────────────────────
    def search(self, req):
        """절대 예외를 밖으로 내보내지 않는다."""
        if not self.enabled:
            return ProviderResult(self.name, skipped=self.disabled_reason())
        before = self.calls
        try:
            offers = self._search(req) or []
        except Exception as e:                      # noqa: BLE001 — 격리가 목적
            msg = f"{type(e).__name__}: {e}"
            self.errors.append(msg)
            return ProviderResult(self.name, calls=self.calls - before, error=msg,
                                  offers=[])
        self.rows += len(offers)
        return ProviderResult(self.name, offers=offers, calls=self.calls - before)

    def stats(self):
        return {"calls": self.calls, "rows": self.rows,
                "errors": list(self.errors),
                "enabled": self.enabled,
                "skipped": self.disabled_reason()}


class SearchRequest:
    """provider 에게 넘기는 검색 조건. provider 중립적으로 적는다."""

    def __init__(self, dep, arr, *, city="", region="", window=(3, 180),
                 nights=(1, 21), max_stops=None, cabin="economy",
                 seed_dates=None, budget=None):
        self.dep = dep
        self.arr = arr
        self.city = city
        self.region = region
        self.window = window            # (D+min, D+max)
        self.nights = nights            # (최소 박, 최대 박)
        self.max_stops = max_stops      # None = 제한 없음
        self.cabin = cabin
        self.seed_dates = seed_dates    # [(depart, return), ...] 지정 시 그것만
        self.budget = budget            # 이 요청에 허용된 최대 호출 수

    def __repr__(self):
        return (f"<{self.dep}→{self.arr} D+{self.window[0]}~{self.window[1]} "
                f"{self.nights[0]}~{self.nights[1]}박 stops<={self.max_stops}>")


def run_all(providers, req, log=None):
    """여러 provider 를 순서대로 돌리고 결과를 모은다. 하나도 안 죽는다."""
    out, results = [], []
    for p in providers:
        r = p.search(req)
        results.append(r)
        out += r.offers
        if log:
            log(r)
    return out, results
