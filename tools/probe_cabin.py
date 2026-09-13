"""비즈니스석 데이터가 이 소스에서 실제로 나오는지 재는 프로브.

검토용이다. deals.json 을 건드리지 않고, 몇 개 노선에 대해
  - /v2/prices/latest        trip_class 없이 / =0 / =1 / =2
  - /v2/prices/month-matrix  trip_class 없이 / =1
를 호출해서 (a) 서버가 파라미터를 존중하는지, (b) 응답 행의 trip_class
분포가 어떤지, (c) 비즈니스 행이 몇 건이고 값이 얼마인지만 찍는다.

★ 문서는 latest 가 trip_class 를 요청 파라미터로 받는지 서로 다르게
  말한다. 코드 주석이나 문서를 믿지 않고 실행 결과로 판단한다.
★ 지금 스캐너는 trip_class 를 넘기지도, 응답의 trip_class 를 보지도
  않는다. 응답에 1(비즈니스)이 섞여 있으면 그게 지금 이코노미로 라벨돼
  들어가고 있다는 뜻이다 — 그것도 여기서 드러난다.
"""
import collections
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.travelpayouts.com"
TOKEN = os.environ.get("TP_TOKEN", "")
ROUTES = [("ICN", "NRT"), ("ICN", "BKK"), ("ICN", "SIN"), ("ICN", "ZRH"),
          ("ICN", "CDG"), ("ICN", "LAX"), ("CJJ", "NRT")]
CALLS = 0


def call(path, params):
    global CALLS
    CALLS += 1
    q = dict(params); q["token"] = TOKEN
    req = urllib.request.Request(f"{BASE}{path}?{urllib.parse.urlencode(q)}",
                                 headers={"X-Access-Token": TOKEN,
                                          "Accept": "application/json",
                                          "User-Agent": "flight-daily-scanner/probe"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if isinstance(body, dict) and body.get("success") is False:
        return None, str(body.get("error"))
    rows = body.get("data") if isinstance(body, dict) else body
    if isinstance(rows, dict):
        rows = list(rows.values())
    return rows or [], None


def summarize(rows):
    tc = collections.Counter(str(r.get("trip_class")) for r in rows)
    biz = [r for r in rows if str(r.get("trip_class")) in ("1", "2")]
    vals = sorted(int(r.get("value") or 0) for r in biz)
    return {"n": len(rows), "trip_class": dict(tc),
            "biz_n": len(biz),
            "biz_min": vals[0] if vals else None,
            "biz_max": vals[-1] if vals else None,
            "biz_sample": [{k: r.get(k) for k in ("origin", "destination",
                                                   "depart_date", "return_date",
                                                   "value", "trip_class",
                                                   "airline", "found_at")}
                           for r in biz[:3]]}


def main():
    if not TOKEN:
        print("TP_TOKEN 없음"); sys.exit(2)
    out = {}
    for org, dst in ROUTES:
        key = f"{org}-{dst}"
        out[key] = {}
        for label, extra in (("latest·없음", {}), ("latest·0", {"trip_class": 0}),
                             ("latest·1", {"trip_class": 1}), ("latest·2", {"trip_class": 2})):
            rows, err = call("/v2/prices/latest", dict(
                {"origin": org, "destination": dst, "currency": "krw",
                 "period_type": "year", "page": 1, "limit": 100, "sorting": "price"},
                **extra))
            out[key][label] = {"err": err} if err else summarize(rows)
            time.sleep(0.4)
        for label, extra in (("matrix·없음", {}), ("matrix·1", {"trip_class": 1})):
            rows, err = call("/v2/prices/month-matrix", dict(
                {"origin": org, "destination": dst, "currency": "krw",
                 "month": time.strftime("%Y-%m-01", time.gmtime(time.time() + 40 * 86400)),
                 "show_to_affiliates": "false"}, **extra))
            out[key][label] = {"err": err} if err else summarize(rows)
            time.sleep(0.4)
    print(json.dumps({"calls": CALLS, "routes": out}, ensure_ascii=False, indent=1))

    # 한 줄 판정
    honoured = any(v.get("latest·1", {}).get("n") is not None
                   and v["latest·1"].get("trip_class", {}).keys() <= {"1", "2"}
                   and v["latest·1"]["n"] > 0
                   for v in out.values())
    leaked = sum(v.get("latest·없음", {}).get("biz_n", 0) for v in out.values())
    print(f"\n판정: trip_class=1 존중={'예' if honoured else '아니오/불명'} · "
          f"파라미터 없이 부를 때 섞여 들어오는 비즈니스 행={leaked}건")


if __name__ == "__main__":
    main()
